.PHONY: help lint type test check build clean check-oo update-oo check-coupling update-coupling check-suppressions update-suppressions check-layers update-layers

SRC := src/oo_ratchet/
OO_BASE ?=
COUPLING_BASE ?=
SUPPRESSION_BASE ?=
LAYERS_BASE ?=
LAYERS_UPDATE ?=
EVAL_VARIANTS := $(wildcard evals/design/*/bad evals/design/*/good)
EVAL_TYPE_TARGETS := $(addprefix type-,$(EVAL_VARIANTS))

.PHONY: $(EVAL_TYPE_TARGETS)

help: ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

lint: ## ruff check + format check
	uv run ruff check src tests evals
	uv run ruff format --check src tests evals

type: $(EVAL_TYPE_TARGETS) ## mypy (strict) + pyright, including isolated eval packages
	uv run mypy src tests
	uv run pyright tests evals

$(EVAL_TYPE_TARGETS): type-%:
	uv run mypy $*/loans $(dir $*)behavior.py

test: ## full suite, including the real-git slow tier
	uv run pytest -m ""

check: lint type test check-oo check-coupling check-suppressions check-layers ## all gates

check-oo: ## OO must-improve ratchet (dogfooded on this package)
	uv run oo-ratchet oo $(SRC) --check $(OO_BASE)

update-oo:
	uv run oo-ratchet oo $(SRC) --update $(OO_BASE)

check-coupling: ## coupling/cohesion regression gate
	uv run oo-ratchet coupling $(SRC) --check $(COUPLING_BASE)

update-coupling:
	uv run oo-ratchet coupling $(SRC) --update $(COUPLING_BASE)

check-suppressions: ## suppression-count regression gate
	uv run oo-ratchet suppressions $(SRC) --check $(SUPPRESSION_BASE)

update-suppressions:
	uv run oo-ratchet suppressions $(SRC) --update

check-layers: ## layer-import ratchet (the four-ring table in pyproject.toml)
	uv run oo-ratchet layers $(SRC) --check $(LAYERS_BASE)

update-layers: ## drop retired layer edges from the baseline (extra flags: LAYERS_UPDATE)
	uv run oo-ratchet layers $(SRC) --update $(LAYERS_UPDATE)

build: ## wheel + sdist
	uv build

clean:
	rm -rf dist .pytest_cache .mypy_cache .ruff_cache
