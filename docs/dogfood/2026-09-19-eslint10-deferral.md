# eslint ^10 deferral — measured 2026-09-19 (tick 397)

**Status: BLOCKED upstream. Do not attempt `npm install --save-dev eslint@^10` until a re-check
flips.** This artifact is the in-repo record of the deferral so the re-check does not start from
zero on every `next`/DEPS bump (board row: `HYG-9ROUTER-6`, successor: `HYG-9ROUTER-14`).

## Why it is blocked

`eslint-config-next/parser` re-exports `next/dist/compiled/babel/eslint-parser.js`, and the
`scopeManager` object that parser returns has no `addGlobals` method. ESLint 10's
`source-code.js` (`addDeclaredGlobals`) calls it, so the upgrade fails at runtime as:

```
TypeError: scopeManager.addGlobals is not a function
```

with `npm run lint:gate` exiting 2 (and even a single-file
`./node_modules/.bin/eslint src/lib/db/schema.js` exiting 2).

## The probe (corrected — the old one was vacuous)

An earlier version of the row asserted `grep -c addGlobals node_modules/next/dist/compiled/babel/eslint-parser.js > 0`.
That file is a **52-byte shim**:

```js
module.exports = require('./bundle').eslintParser()
```

so the grep returns 0 **by construction** and can never flip, even after upstream fixes the parser.
The real parser lives in `next/dist/compiled/babel/bundle.js` (1,364,777 bytes), and the decisive
check is the live object ESLint actually receives:

```bash
node -e '
  const p = require("next/dist/compiled/babel/eslint-parser");
  const res = p.parseForESLint("const x = 1;", { requireConfigFile: false, ecmaVersion: 2024,
    sourceType: "module" });
  console.log("addGlobals:", typeof res.scopeManager.addGlobals);
'
```

Expected while blocked: `addGlobals: undefined` (verified 2026-09-19).

Note: pass plain JavaScript to `parseForESLint` in this one-liner. Inline JSX in a `node -e`
string does not reach the JSX parser under these options and can surface as a module-level
error out of `babel-packages` instead of the real result; keep the probe's input simple.

## Measurements (2026-09-19, next 16.3.5 installed)

| Check | Result |
|---|---|
| `wc -c` shim `eslint-parser.js` | 52 (throwaway shim, not the parser) |
| `wc -c` `bundle.js` | 1,364,777 |
| `grep -c addGlobals` on `bundle.js` | 0 |
| `typeof scopeManager.addGlobals` (runtime) | `undefined` |
| scopeManager own props | `scopes, globalScope, __nodeToScope, __currentScope, __options, __declaredVariables` |
| scopeManager prototype | the `eslint-scope-5-internals` class — no `addGlobals` |
| eslint 9.39.5 `source-code.js` `addGlobals` refs | 0 (the call site is ESLint-10-only) |
| `npm run lint:gate` (eslint ^9, current tree) | exit 0 — errors=135 warnings=204 problems=339 filesLinted=1300, baseline intact |

Wiring confirmed: `node_modules/eslint-config-next/dist/index.js` -> `./parser` ->
`next/dist/compiled/babel/eslint-parser` — i.e. the measured object is what the config uses.

## Second, independent blocker

Three plugins nested under `eslint-config-next` carry peer ranges that stop at ^9:

- `eslint-plugin-react@7.37.5` — `peer eslint: ^3 || ... || ^9.7`
- `eslint-plugin-jsx-a11y@6.10.2` — `peer eslint: ... || ^9`
- `eslint-plugin-import@2.32.0` — `peer eslint: ... || ^9`

None admit ^10, so even a fixed vendored parser would still leave an unsatisfied peer tree.

## Forward look (does the next bump clear it?)

- upstream `@babel/eslint-parser@latest` = 7.29.9 — `grep -r addGlobals` across the package: **0**
- Next `16.4.0-canary.36` vendored bundle `sha256 0cb0c45dae15d4080c022d6b60b88d27923ddfb29dd0a1e18aac4df39f4082b6`
  is **byte-identical** to the installed 16.3.5 bundle

So the blocker does not clear at the next Next bump either, as of this measurement.

## Pinned origin

First measured at HEAD `c348f7af` (tick 366, log `/tmp/9r366-lintgate2.log`, evidence
`/tmp/9r366_evidence.md`); re-measured at `b292f8ce` (tick 367) and again at `c86d9f22`
(2026-09-19, tick 397).

## Re-check cadence

Re-measure on each `next` or DEPS bump. The criterion is satisfied when the runtime probe prints
`addGlobals: function`; only then run `npm install --save-dev eslint@^10` and
`npm run lint:gate`, requiring exit 0 with `scripts/lint-baseline.json` unchanged.
