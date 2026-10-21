# Contributing to narrate

Thank you for helping. narrate is looked after by one person, and every bug
report, docs fix and example makes it better for the next person who tries it.

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## Ways to help

- **Report a bug:** open an issue with the bug report form. A script that
  shows the problem, and the output of `narrate doctor`, make it quick to fix.
- **Improve the docs:** a step that confused you, a missing example, a broken
  link. Docs changes are as welcome as code.
- **Share an example:** a script that shows a feature well, or a use of
  narrate nobody expected.
- **Write code:** fix a bug or build a feature from the issues.

## Ask a question

Check the [documentation](README.md#documentation) first. If the answer isn't
there, open an issue with the question form, which labels it `question`.
That's a sign the docs need a line too.

## Set up

- **On Linux or macOS:** follow [Install from source](README.md#from-source),
  then [Development](docs/development.md) for `just`, the tests and a tour of
  the code. `uv run narrate doctor` checks the setup and says what's missing.
- **Anywhere else, or in GitHub Codespaces:** open the repository in its
  [dev container](.devcontainer/), which has the Linux setup ready.

## Find something to work on

- **[`good first issue`](https://github.com/bricef/narrate/labels/good%20first%20issue):**
  small and well described, a good way in.
- **[`help wanted`](https://github.com/bricef/narrate/labels/help%20wanted):**
  issues where help is especially welcome.
- **Something larger:** say on the issue before you start, or open one, so we
  can agree on the approach before you spend your time on it.

## What a pull request needs

- **One change:** one fix or feature, linked to its issue ("Fixes #92").
- **Tests:** for the new behaviour, or for the bug you fixed.
- **Docs:** updated where they describe what changed: the README, `docs/`,
  the [format specification](docs/spec/narakeet-markdown.md) and the
  [agent skill](skills/narrate/SKILL.md).
- **Checks:** `just test` and `just lint` pass.

## Conventions worth knowing

- **Commit subjects** say what changed in plain words and end with the issue:
  `Studio: retake render:web captures (#77)`. The body says why.
- **Script examples in the docs** are fenced with four backticks and
  `markdown`, so `tests/test_docs.py` builds each one and they stay correct.
  Examples that need the network (`render:web`) are fenced with `md`, which
  the test skips.
- **ElevenLabs tests are opt-in:** they spend credits, so they're marked
  `elevenlabs` and run only with `just test -m elevenlabs` and a key in
  `.env`. A plain `just test` spends nothing.
- **Conformance tests** compare narrate's videos with Narakeet's. They need
  `just reference` first, and are skipped without it. Narakeet's files have no
  licence: never commit what `just reference` downloads.
- **Docs style:** plain, short sentences, British spelling, and bold lead-ins
  in lists, as in the rest of the docs.

## Licence

narrate is under the [MIT licence](LICENSE). By contributing, you agree that
your contributions are licensed under it too. There's no contributor licence
agreement to sign.

## Security

Please don't report vulnerabilities in public issues. See
[SECURITY.md](SECURITY.md) for how to report them privately.
