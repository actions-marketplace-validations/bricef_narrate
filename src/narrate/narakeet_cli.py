"""`narakeet-api-client`: Narakeet's command-line interface, building locally with narrate.

Existing build scripts can point at narrate without changes:

    narakeet-api-client --repository-type local-dir --repository my-project --source video.txt
    narakeet-api-client --repository-type local-zip --repository project.zip --source script.md
    narakeet-api-client --repository-type zip-url --repository https://example.com/v1.zip --source script.txt
    narakeet-api-client --repository-type github --repository owner/repo --source path/script.md \\
        --github-token "$GITHUB_TOKEN" [--github-sha SHA]

--api-key is accepted and ignored: nothing leaves the machine except the
downloads for zip-url and github projects.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

from . import cli


def _get(url: str, token: str | None = None, accept: str | None = None) -> bytes:
    headers = {"User-Agent": "narrate"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if accept:
        headers["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as resp:
        return resp.read()


def fetch_github(repository: str, source: str, token: str | None, sha: str | None, dest: Path,
                 get=_get) -> Path:
    """Download the files under the script's directory (not the whole repository)."""
    api = f"https://api.github.com/repos/{repository}"
    ref = sha or json.loads(get(api, token))["default_branch"]
    tree = json.loads(get(f"{api}/git/trees/{urllib.parse.quote(ref)}?recursive=1", token))
    folder = PurePosixPath(source).parent
    prefix = "" if str(folder) == "." else f"{folder}/"
    blobs = [item["path"] for item in tree.get("tree", []) if item["type"] == "blob" and item["path"].startswith(prefix)]
    if source not in blobs:
        raise SystemExit(f"error: {source} is not in {repository}@{ref}")
    for path in blobs:
        target = dest / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(get(f"{api}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref)}", token,
                               "application/vnd.github.raw"))
    return dest / source


def main(argv: list[str] | None = None, get=_get) -> int:
    parser = argparse.ArgumentParser(prog="narakeet-api-client", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repository-type", required=True, choices=["local-dir", "local-zip", "zip-url", "github"])
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source", required=True, help="path of the main script inside the repository")
    parser.add_argument("--output", default="result.mp4")
    parser.add_argument("--project-type", choices=["video", "audio"], default="video")
    parser.add_argument("--api-key", help="accepted for compatibility; narrate builds locally")
    parser.add_argument("--github-token")
    parser.add_argument("--github-sha")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--tts", choices=["auto", "kokoro", "elevenlabs", "silent"], default="auto",
                        help="narrate's speech engine (not a Narakeet option)")
    args = parser.parse_args(argv)
    if args.project_type == "audio":
        print("error: --project-type audio is not supported yet", file=sys.stderr)
        return 2

    build = ["build", "--tts", args.tts, "-o", str(Path(args.output).resolve())] + ([] if args.verbose else ["-q"])
    kind, repo = args.repository_type, args.repository
    if kind == "local-dir":
        return cli.main([*build, str(Path(repo) / args.source)])
    if kind == "local-zip":
        return cli.main([*build, repo, "--source", args.source])
    workdir = Path(tempfile.mkdtemp(prefix="narrate-fetch-"))
    try:
        if kind == "zip-url":
            archive = workdir / "project.zip"
            archive.write_bytes(get(repo))
            return cli.main([*build, str(archive), "--source", args.source])
        script = fetch_github(repo, args.source, args.github_token, args.github_sha, workdir / "repo", get)
        return cli.main([*build, str(script)])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
