# Reference sources

`docs/spec/narakeet-markdown.md` was written on 2026-10-08 from the sources
below. Run `scripts/fetch-narakeet-reference.sh` to refresh the local copies:

- `narakeet-docs/` holds Narakeet doc pages and news posts, `<main>` only,
  converted to Markdown.
- `examples/` holds the scripts and CSS from `github.com/narakeet/examples`.
  With `--media` (`just reference`), it also holds their media and the
  `result.mp4` Narakeet rendered from each, which the conformance tests
  compare against.

Both directories are git-ignored. Narakeet's docs are copyright Video Puppet
Ltd, and the examples repository has no licence.

| Source | URL | Notes |
| --- | --- | --- |
| Format reference | https://www.narakeet.com/docs/format/ | The core reference. Sitemap lastmod 2026-07-31. |
| Getting started | https://www.narakeet.com/docs/script/ | |
| Scripting guides | https://www.narakeet.com/docs/scripting/ | Callouts, pan/zoom, subtitle styling |
| How-to guides | https://www.narakeet.com/docs/how-to/ | Pauses, speed, pitch, languages, Pinyin, normalisation, compression |
| Automation | https://www.narakeet.com/docs/automating/ | CLI, REST video API, GitHub Action |
| Pricing and limits | https://www.narakeet.com/docs/pricing/ | Scene, script and upload limits |
| News posts | https://www.narakeet.com/news/ | Features that are missing from the reference, e.g. `voice: name/lang` (2026-04-14) and ellipsis pauses (2024-05-28) |
| Example projects | https://github.com/narakeet/examples | 22 projects; the conformance corpus |

Site-wide page list: https://www.narakeet.com/sitemap.xml (about 100 `/docs/` URLs).

Some code blocks in Narakeet's published HTML have their newlines collapsed (for
example `--- size: 720p target: self-hosted ---` on one line). That is a
publishing artefact, not syntax; see spec §2.3.
