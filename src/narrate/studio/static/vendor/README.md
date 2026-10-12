# Vendored front-end libraries

narrate studio has no front-end build step (docs/design/studio.md, D7). These
are the only third-party files it loads, kept here so it works offline.

| File | From | sha256 |
| --- | --- | --- |
| `htm-preact.js` | `preact/standalone.module.js` in the npm package `htm@3.1.1` (MIT): Preact, its hooks and htm in one module. Checked against the registry's integrity hash. | `72284e8e9079c87817145df1110f74e8a2aa040b2fc384922e18dfcb46fc1fd7` |
| `codemirror.js` | `scripts/vendor.sh codemirror`: the packages pinned in `scripts/codemirror/package-lock.json` (MIT), bundled by esbuild as a module. The build is reproducible: rebuilding from the lock gives the same bytes. | `d7f50efbdf0caba902191b758c8865321292695c2f749d955286470372dc8cdf` |
| `fake-timers.js` | `scripts/vendor.sh fake-timers`: `@sinonjs/fake-timers@15.4.0` (BSD-3-Clause) and its dependencies, pinned in `scripts/fake-timers/package-lock.json`, bundled by esbuild as a plain script defining `NarrateFakeTimers`, so it runs before an HTML scene's own scripts (#73). Reproducible in the same way. | `3f01ee4b3d3445819ea3e0d7b4d4c382d7d3d69a1b56be15b5e7498cd08caa4e` |

To update a bundle, change the versions in `scripts/NAME/package.json`, run
`scripts/vendor.sh NAME --update` (with Node, for example through
`mise exec node@24 --`), and record the new hash here.
