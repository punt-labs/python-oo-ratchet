A0 (PL-1718) measurement on the `src/oo_ratchet` of main 987f57b, with the ring table of `docs/architecture/four-rings.toml` as added in b4b85a5.
Reproduce: extract `src` of 987f57b (`git archive 987f57b src`), save `git show b4b85a5:docs/architecture/four-rings.toml` to a file and run
`uv run oo-ratchet design src/oo_ratchet/ --layers <that file> --json` (137 files scanned, 243 findings).
The current tree, with the table in `pyproject.toml`
(`uv run oo-ratchet design src/oo_ratchet/ --json`): 139 files scanned, 248
findings; `layer-import` 130, `domain-io` 9, `thick-entry` 9.

Commands:

- `uv run oo-ratchet design src/oo_ratchet/ --layers <table of 987f57b> --json`
- `uv run python docs/architecture/tools/adopter_shape.py src/oo_ratchet`

Design check with the four rings: 137 files scanned, 243 findings. `*.cli` modules are entry and `*.writer` modules are application, as PL-1718 specifies.

- `layer-import` 130, `concrete-cross-package-import` 40, `size-cap` 10, `thick-entry` 9, `domain-io` 9, `primitive-params` 9, `stateless-function-bag` 8, `feature-envy` 7, `stateless-single-method` 5, `data-clump` 6, `getter-heavy` 3, `split-cohesion` 3, `middle-man` 2, `envied-data` 1, `tag-switch` 1.
- 0 for `unlayered-module`, `misplaced-function`.

`layer-import` by importing ring and ring imported: domain to adapters 42, domain to entry 12, domain to application 21, application to adapters 55. Entry and adapters have 0. 54 of the 130 are in the four package `__init__.py` files (`oo`, `coupling`, `layers`, `suppression`). Most imported outer modules: `source_set` 17, `coupling/outcome` 7, `oo/baseline` 7, `coupling/gitio` 6, `oo/compare` 6, `oo/audit` 6, `oo/gitio` 6.

`domain-io` 9 findings in 8 modules: 6 import `pathlib`, 2 import `io`, and `oo/scorer` also imports `json`.

Without layers (adopter shape): 131 modules excluding `__init__`, module size median 62 (p25 38, p75 98, max 256), 36 modules of at most 40 code lines, 0 over the 400-line ceiling, classes per module 0 (10), 1 (116), 2 (5). Design findings 153: 43 `primitive-params`, 40 `concrete-cross-package-import`, 24 `data-clump`, 13 `feature-envy`, 10 `size-cap`, 8 `stateless-function-bag`, 5 `stateless-single-method`, 3 `getter-heavy`, 3 `split-cohesion`, 2 `middle-man`, 1 `envied-data`, 1 `tag-switch`.
