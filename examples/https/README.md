# How HTTPS works

An explainer video made with narrate: what the padlock means, from a plain
HTTP request to the TLS handshake. Every picture is an animated HTML scene,
timed to the narration.

- `https.md`: the script. Each scene's narration carries marks
  (`<mark name="…"/>`) where something should appear on screen.
- `scenes/`: the scene pages, one per scene, sharing `common.css`. Each part of
  the story keeps its colour: your browser teal, the server amber, whoever is
  listening rose, secrets violet, passing checks green.
- `overlays/chapters.html`: the five chapters along the bottom, an overlay on
  the whole video's clock. It finds each chapter's start from `--scene-N`.
- `voices.yaml`: the narrator, pinned on each engine: `af_heart` on Kokoro and
  Alice on ElevenLabs.

The scenes, in order:

| # | Scene | What it shows |
| --- | --- | --- |
| 1 | `title` | The address bar: the padlock shuts, the S lights up |
| 2 | `postcard` | Plain HTTP: a request read, and rewritten, along the way |
| 3 | `promises` | Private, intact, authentic |
| 4 | `tunnel` | HTTP + TLS = HTTPS, and the tunnel's two jobs |
| 5 | `cipher` | A shared key, and why it can't just be sent |
| 6 | `paint` | The key exchange as paint mixing |
| 7 | `math` | An elliptic curve, forward secrecy, post-quantum key exchange |
| 8 | `mitm` | The attacker in the middle |
| 9 | `cert` | A certificate, filled in field by field |
| 10 | `sign` | Signatures: the private key signs, the public key checks |
| 11 | `chain` | The chain of trust, up to a root in the browser |
| 12 | `handshake` | The TLS 1.3 handshake, message by message |
| 13 | `seal` | A flipped bit breaks the seal |
| 14 | `limits` | What HTTPS hides, what it doesn't, and a padlock on a scam site |
| 15 | `close` | The three promises, and the padlock |

To build it, from a narrate checkout:

```sh
cd examples/https
narrate check https.md --timing --tts kokoro
narrate build https.md --tts kokoro -o /tmp/https.mp4

# The final cut on ElevenLabs' eleven_v4 (about 4,000 characters; check the price first)
narrate check https.md --timing --tts elevenlabs --tts-model eleven_v4
narrate build https.md --tts elevenlabs --tts-model eleven_v4 -o /tmp/https.mp4
```

The overlay and several scenes animate throughout, so they're captured frame
by frame: a build takes several minutes, even with `--tts silent`.
