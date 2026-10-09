# Vendored front-end libraries

narrate studio has no front-end build step (docs/design/studio.md, D7). These
are the only third-party files it loads, kept here so it works offline.

| File | From | sha256 |
| --- | --- | --- |
| `htm-preact.js` | `preact/standalone.module.js` in the npm package `htm@3.1.1` (MIT): Preact, its hooks and htm in one module. Checked against the registry's integrity hash. | `72284e8e9079c87817145df1110f74e8a2aa040b2fc384922e18dfcb46fc1fd7` |
| `codemirror.js` | `scripts/vendor-codemirror.sh`: the packages pinned in `scripts/codemirror/package-lock.json` (MIT), bundled by esbuild. The build is reproducible: rebuilding from the lock gives the same bytes. | `d7f50efbdf0caba902191b758c8865321292695c2f749d955286470372dc8cdf` |

To update CodeMirror, change the versions in `scripts/codemirror/package.json`,
run `scripts/vendor-codemirror.sh --update` (with Node, for example through
`mise exec node@24 --`), and record the new hash here.
