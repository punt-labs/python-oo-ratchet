# Design evals

Each directory contains two isolated, importable `loans` packages and one shared
`behavior.py`. The public `loans.api.quote(days)` contract covers zero, normal,
multi-week and invalid loan durations. The god-class pair deliberately keeps a
600-plus-line tariff catalogue on the bad side; the good side represents the
same thirty tariffs as values. The over-split pair recomposes six function
objects in separate files into one stateful loan with related operations.

`expected.toml` keys use paths relative to `loans/` and qualified symbols, not
line numbers. The layer-leak pair additionally declares the proposed
`[tool.oo-ratchet.layers]` contract in `layers.toml`, consumed by the scanner.
The evals do not change production ratchet gates.

Run `uv run pytest tests/test_design_evals.py`. All seeded rules are implemented;
recall, precision and ordering include D1-D8, layer rules and Tier 0 size caps.
Precision checks cover every seeded rule. The `decoys` pair declares its rings in
`layers.toml`; with them, `Codec.from_wire` in `adapters/wire.py` and the `entry.py`
wiring of `FeeStore` in layer-leak no longer fire, because `stateless-single-method`
and `concrete-cross-package-import` are scoped by ring. `adapters/gateway.py` in both
variants is a three-method class with no fields: `split-cohesion` does not fire on a
class whose methods touch no field and call no other method (B4 measured 14 of 30
sampled findings of that shape). One known misfire is open and not seeded: the
stateless rules read a class whose only data is a mutated `ClassVar` as stateless.

The layer-leak pair passes its `layers.toml` to the scanner; its four layer
expectations are implemented checks, not future-rule xfails.

## Approved PR3b expectation updates

- Bad tag-switch `policy.py:fee` additionally expects `primitive-params`:
  `kind: str` and `days: int` are two primitive parameters. The good variant
  still expects no findings.
- Bad god-class `library.py` additionally expects `size-cap` on `<module>`:
  its 608 code lines exceed 400, independently of the existing `Library`
  method-count overflow. These are separate stable keys.

No behavior fixtures changed. LCOM4 excludes `__init__`, `__new__` and
`__post_init__` from both the method count and graph: initialization does not
connect otherwise independent groups of behavior.
Properties, cached properties, setters and deleters are accessors, not methods,
so they also stay out of the LCOM4 count and graph. The tag-switch fixture's
contiguous early-return `if` statements are a structural dispatch chain.

`make type` runs strict mypy separately for every variant plus its shared
behavior file, since every variant intentionally uses the same package name.
Pyright and Ruff cover all evals. The self-ratchets retain their `src/` scope.
