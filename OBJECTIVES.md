# narrate: objectives

narrate turns a Markdown script and a folder of pictures and clips into a narrated video on your own computer, since 2026-10-21 it is a public MIT project with releases, a Docker image and a Marketplace Action.

## Status

done: v0.1.0 and v0.1.1 released 2026-10-21, last merge 2026-10-22. Feature complete and able to generate videos at scale, now in maintenance mode and to be updated when new requirements arise. 


## Milestones

- [x] Narakeet scripts build unchanged, locally, with every spec feature: 2026-10-08 (spec §16; conformance tests match Narakeet's renders within 0.1 s, examples without narration)
- [x] Scripts written, previewed and rendered in a browser studio: #28, M1 to M3 closed 2026-10-12
- [x] Programs and AI agents make videos: internal HTTP API #23 (2026-10-12), agent skill #68 (2026-10-10)
- [x] Anyone can install, use and contribute: public, MIT, v0.1.0/v0.1.1 (2026-10-21), amd64+arm64 image, Action on the Marketplace; #93 closed 2026-10-22
- [ ] The problems found getting ready for new users are fixed: #100, #107, #112, #113, #114, #116 (#93 follow-ups)  ← next
- [ ] Scripts can ask for AI-generated pictures and clips: #41, #42 (research 2026-10-13 recommends a Google provider first)
- [ ] Other people can use narrate as a hosted service: #85, with `narrate remote` #82 and an MCP endpoint #83

## Not goals

- PowerPoint, Google Slides or Keynote input (#25, closed "Not required"; README)
- Narakeet's REST API, web editor or command line (README; `narakeet-api-client` removed in #121)
- Running natively on Windows: Docker there (README; #34)
- Building factor-q's intro: factor-q's concern (#43, closed not planned)
- Shipping Narakeet's docs or example projects: they have no licence (CONTRIBUTING)

