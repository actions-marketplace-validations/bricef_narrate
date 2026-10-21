# Security policy

## Report a vulnerability

Please report vulnerabilities privately, through
[GitHub's private vulnerability reporting](https://github.com/bricef/narrate/security/advisories/new),
not in a public issue.

Say what you found, how to reproduce it, and what someone could do with it.
A script or project that shows it helps most.

narrate is maintained by one person, on a best-effort basis, so there's no
promised response time. The report stays private while it's looked into and
fixed.

## Supported versions

Before 1.0, fixes go into `main` and the latest release only:

| Version | Gets fixes |
| --- | --- |
| `main`, and the image's `latest` tag | yes |
| the latest release | yes |
| older releases | no: update to the latest |

## Scope

narrate builds videos on your own machine. Some of what it does is by design,
and not a vulnerability:

- **The studio and the service have no login.** Anyone who can reach
  `narrate studio` or `narrate serve` can read the project's files, run builds
  and spend the ElevenLabs credits of the key it holds. Both listen on
  localhost by default: keep them there, or on a private network you trust.
  Web pages in your browser are kept out (see "Crossing into localhost"
  below).
- **Scripts reach the network.** `render:web` fetches the pages a script
  names. HTML scenes and overlays can load from the network while they're
  captured; [#84](https://github.com/bricef/narrate/issues/84) tracks
  limiting them to the project's files.

What does matter, for example:

- **Escaping the project:** a ZIP project, or a request to the studio or the
  service, that reads or writes files outside its folder.
- **Captured pages:** an HTML scene, an overlay or a `render:web` capture
  that reads local files it shouldn't, or gets out of headless Chromium.
- **Crossing into localhost:** a web page open in your browser that makes a
  studio or service on localhost act for it, or read what they answer. Both
  defend against this. They answer only to their own host names
  (`localhost`, `127.0.0.1`, `[::1]`, the `--host` address and each
  `--allow-host`). They refuse a request that changes something when its
  `Origin` is another site. They send no CORS headers. A way past these is a
  vulnerability.
- **Leaking keys:** `ELEVENLABS_API_KEY`, or the credentials a `render:web`
  block names, ending up in a video, a log, an error, a cache, a response, or
  the published image.

If you're not sure, report it privately anyway.
