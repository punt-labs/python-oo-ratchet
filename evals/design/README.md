# Design evals

Each directory contains two isolated, importable `loans` packages and one shared
`behavior.py`. The public `loans.api.quote(days)` contract covers zero, normal,
multi-week and invalid loan durations. The god-class pair deliberately keeps a
600-plus-line tariff catalogue on the bad side; the good side represents the
same thirty tariffs as values. The over-split pair recomposes six function
objects in separate files into one stateful loan with related operations.

`expected.toml` keys use paths relative to `loans/` and qualified symbols, not
line numbers. The layer-leak pair additionally declares the proposed
`[tool.oo-ratchet.layers]` contract in `layers.toml`; today's scanner does not
load it. No new rules or production gate changes are implemented here.

Run `uv run pytest tests/test_design_evals.py`. Future-rule recall cases are
strict xfails, intentionally retained even if the rule joins `Rules.ordered()`:
an XPASS forces removing that rule from the harness's `FUTURE_RULES`. Recall,
precision and ordering then automatically include the implemented rule.
Precision checks remain active around the exact known-misfire keys; separate
strict xfails track their removal. The known cases are:

- `decoys`, both variants: `Codec.from_wire` triggers
  `stateless-single-method` on `adapters/wire.py:Codec`, despite being boundary
  deserialization rather than a domain strategy.
- `layer-leak`, good: wiring `FeeStore` in `entry.py` triggers
  `concrete-cross-package-import`, despite keeping the concrete dependency out
  of the domain. Ordering excludes known-misfire keys, as precision does;
  separate precision xfails still track their removal.

`make type` runs strict mypy separately for every variant plus its shared
behavior file, since every variant intentionally uses the same package name.
Pyright and Ruff cover all evals. The self-ratchets retain their `src/` scope.
