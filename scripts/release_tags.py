"""The moving tags of a release: the image's 0 and 0.2, and the action's v0, for v0.2.0.

    python3 scripts/release_tags.py newest v0.2.0                  # which image tags it moves
    python3 scripts/release_tags.py move v0.2.0 COMMIT [--dry-run]  # move v0 to it

.github/workflows/image.yml runs both. A release is a tag vX.Y.Z. Only the
newest release of a series moves that series' tags, so re-running an older
release's workflow, or a fix for an older series, leaves them where they are.
A pre-release, such as v0.3.0-rc.1, moves nothing. The tags are read from the
remote, so the answer doesn't depend on what this checkout has fetched.
"""

import argparse
import re
import shlex
import subprocess
import sys

RELEASE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def version(tag: str) -> tuple[int, int, int] | None:
    m = RELEASE.fullmatch(tag)
    return tuple(int(n) for n in m.groups()) if m else None


def remote_tags(remote: str) -> dict[str, str]:
    """Each tag on the remote, and the commit it points at."""
    listing = subprocess.run(["git", "ls-remote", "--tags", remote], check=True, capture_output=True, text=True)
    tags = {}
    for line in listing.stdout.splitlines():
        sha, ref = line.split("\t")
        name = ref.removeprefix("refs/tags/")
        if name.endswith("^{}"):
            tags[name.removesuffix("^{}")] = sha  # an annotated tag's commit, rather than the tag object
        else:
            tags.setdefault(name, sha)
    return tags


def newest(tag: str, tags) -> tuple[bool, bool]:
    """Whether tag is the newest release of its major version, and of its minor version."""
    v = version(tag)
    if v is None:
        return False, False
    releases = [r for r in map(version, tags) if r]
    return (all(r <= v for r in releases if r[0] == v[0]),
            all(r <= v for r in releases if r[:2] == v[:2]))


def move(tag: str, commit: str, remote: str, dry_run: bool) -> None:
    """Point vX at the release tag's commit, if it's the newest X.x release and the tag still points there."""
    v = version(tag)
    if v is None:
        print(f"{tag} isn't a release (vX.Y.Z): no major tag moves")
        return
    major = f"v{v[0]}"
    tags = remote_tags(remote)
    commit = subprocess.run(["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
                            check=True, capture_output=True, text=True).stdout.strip()
    if tags.get(tag) != commit:
        print(f"{tag} no longer points at {commit[:7]} on {remote}: {major} stays")
        return
    if not newest(tag, tags)[0]:
        latest = max(r for r in map(version, tags) if r and r[0] == v[0])
        print(f"v{'.'.join(map(str, latest))} is newer than {tag}: {major} stays")
        return
    if tags.get(major) == commit:
        print(f"{major} is already at {tag}")
        return
    commands = [
        ["git", "tag", "--force", "--annotate", major, commit,
         "--message", f"narrate {v[0]}.x: moves to the latest {v[0]}.x release (now {tag})"],
        ["git", "push", "--force", remote, f"refs/tags/{major}"],
    ]
    for command in commands:
        print("+", shlex.join(command), flush=True)
        if not dry_run and subprocess.run(command).returncode:
            sys.exit(f"::error::{major} wasn't moved to {tag}. To move it from a checkout that can push "
                     f"tags: python3 scripts/release_tags.py move {tag} {tag}")
    print(f"{major} {'would move' if dry_run else 'moved'} to {tag} ({commit[:7]})")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("newest", help="print, as step outputs, which of the image's moving tags TAG moves")
    check.add_argument("tag")
    check.add_argument("--remote", default="origin")
    mover = commands.add_parser("move", help="move the major tag, vX, to TAG's commit")
    mover.add_argument("tag")
    mover.add_argument("commit", help="the commit the workflow ran for, which TAG must still point at")
    mover.add_argument("--remote", default="origin")
    mover.add_argument("--dry-run", action="store_true", help="print the git commands rather than run them")
    args = parser.parse_args(argv)
    if args.command == "newest":
        major, minor = newest(args.tag, remote_tags(args.remote)) if version(args.tag) else (False, False)
        print(f"newest-major={str(major).lower()}\nnewest-minor={str(minor).lower()}")
    else:
        move(args.tag, args.commit, args.remote, args.dry_run)


if __name__ == "__main__":
    main()
