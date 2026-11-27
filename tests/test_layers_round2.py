"""Round-two review findings: export flow, dynamic bindings, adoption, atomicity."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from oo_ratchet.core.domain.declared_layers import DeclaredLayers
from oo_ratchet.core.domain.layer_config import LayerConfig
from oo_ratchet.core.domain.layer_edges import Edge
from oo_ratchet.core.domain.layer_widening import LayerWidening
from oo_ratchet.layers.scan import LayerScan
from tests.layers_repo import OK_SERVICE, LayersRepo

DECLARED = """\
[tool.oo-ratchet.layers.kernel]
prefixes = ["kernel"]
imports = []

[tool.oo-ratchet.layers.service]
prefixes = ["service"]
imports = ["kernel"]
"""


def _edge_through(
    tmp_path: Path, init: str, service: str = "thing = 1\n", kernel: str = ""
) -> bool:
    """Return whether ``from app import thing`` reaches app.service from kernel."""
    (tmp_path / "pyproject.toml").write_text(DECLARED)
    pkg = tmp_path / "src" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(init)
    (pkg / "service.py").write_text(service)
    (pkg / "other.py").write_text("thing = 2\n")
    (pkg / "kernel.py").write_text(kernel or "from app import thing\n")
    return Edge("app.kernel", "app.service") in LayerScan(pkg).edges


TRY_FALLBACK = (
    "try:\n    from .service import thing\nexcept ImportError:\n    thing = None\n"
)
MATCH_ARMS = (
    "match 1:\n    case 1:\n        from .service import thing\n"
    "    case _:\n        from .other import thing\n"
)


class TestExportFlow:
    """A name is an export if any module-scope path leaves it bound to the import."""

    @pytest.mark.parametrize(
        "init",
        [
            TRY_FALLBACK,
            "from .service import thing\nthing: int\n",
            "from .service import thing\nthing.attr = 1\nthing[0] = 2\n",
            "match 1:\n    case _:\n        from .service import thing\n",
            MATCH_ARMS,
            "from .service import thing\nif cond:\n    thing = 1\n",
            "if cond:\n    pass\nelse:\n    from .service import thing\n",
            "from .service import *\n",
        ],
    )
    def test_reachable_binding_is_an_export(self, tmp_path: Path, init: str) -> None:
        assert _edge_through(tmp_path, init)

    @pytest.mark.parametrize(
        "init",
        [
            "try:\n    from .service import thing\nfinally:\n    thing = None\n",
            "from .service import thing\ndel thing\n",
            "from .service import thing\nthing = 1\n",
            "from .service import thing\ndef thing(): ...\n",
            "from .service import thing\nclass thing: ...\n",
            "from .service import thing\nfrom .other import thing\n",
        ],
    )
    def test_rebinding_never_ends_the_export(self, tmp_path: Path, init: str) -> None:
        assert _edge_through(tmp_path, init)

    def test_wildcard_ignores_a_literal_all(self, tmp_path: Path) -> None:
        service = 'thing = 1\nother = 2\n__all__ = ["other"]\n'
        assert _edge_through(tmp_path, "from .service import *\n", service)

    def test_wildcard_exports_private_names_too(self, tmp_path: Path) -> None:
        init = "from .service import *\n"
        assert _edge_through(tmp_path, init, "_thing = 1\n", "from app import _thing\n")

    def test_wildcard_exports_public_names_without_all(self, tmp_path: Path) -> None:
        assert _edge_through(tmp_path, "from .service import *\n", "thing = 1\n")


SERVICE = 'importlib.import_module("app.service")'
UNBOUND = [
    'thing.__import__("app.service")\n',
    'from .importlib import import_module as load\nload("app.service")\n',
    f"def f():\n    import importlib\ndef g():\n    {SERVICE}\n",
    f"def f(importlib):\n    {SERVICE}\n",
]


class TestDynamicBindings:
    """A dynamic-import call counts only if its name is bound to the stdlib."""

    def _edge(self, tmp_path: Path, kernel: str) -> bool:
        return _edge_through(tmp_path, "", kernel=kernel)

    @pytest.mark.parametrize(
        "kernel",
        [
            'import builtins\nbuiltins.__import__("app.service")\n',
            'import builtins as b\nb.__import__("app.service")\n',
            'from builtins import __import__ as load\nload("app.service")\n',
            'import importlib\ndef f():\n    importlib.import_module("app.service")\n',
            f"def f():\n    import importlib\n    {SERVICE}\n",
        ],
    )
    def test_stdlib_bound_calls_are_edges(self, tmp_path: Path, kernel: str) -> None:
        assert self._edge(tmp_path, kernel)

    @pytest.mark.parametrize("kernel", UNBOUND)
    def test_unbound_or_rebound_calls_are_deliberate_edges(
        self, tmp_path: Path, kernel: str
    ) -> None:
        assert self._edge(tmp_path, kernel)


class TestSecondPackageAdoption:
    """A package that is new in a change can be adopted beside existing ones."""

    def _second(self, repo: LayersRepo) -> Path:
        for name, text in {
            "__init__": "",
            "kernel": "import app2.service\n",
            "service": OK_SERVICE.replace("app", "app2"),
            "cli": "",
        }.items():
            repo.write(f"src/app2/{name}.py", text)
        return repo.root / "src" / "app2"

    def test_a_violating_second_package_is_adopted_and_checks_clean(
        self, repo: LayersRepo
    ) -> None:
        repo.adopt()
        base = repo.commit_as_origin_main()
        second = self._second(repo)
        code, _ = repo.run_on(second, "--update")
        assert code == 0
        assert repo.run_on(second, "--check", "--base-ref", base)[0] == 0
        assert repo.run("--check", "--base-ref", base)[0] == 0
        rows = json.loads(repo.baseline.read_text())
        assert set(rows) == {"app.kernel", "app2.kernel"}

    def test_an_existing_package_gaining_a_violation_still_fails(
        self, repo: LayersRepo
    ) -> None:
        repo.edit("kernel", "")
        repo.adopt()
        base = repo.commit_as_origin_main()
        repo.edit("kernel", "import app.service\n")
        assert repo.run("--update")[0] == 0
        assert repo.run("--check", "--base-ref", base)[0] == 1


class TestRetiredRows:
    """Rows of a package that no longer exists are dropped by --update."""

    def test_update_drops_and_audits_retired_rows(self, repo: LayersRepo) -> None:
        repo.edit("kernel", "")
        repo.write(".oo-layers-baseline.json", '{"gone.kernel": ["gone.service"]}')
        assert repo.run("--update")[0] == 0
        assert json.loads(repo.baseline.read_text()) == {}
        assert repo.audit[-1]["retired"] == ["gone.kernel -> gone.service"]

    def test_rows_of_an_existing_package_are_kept(self, repo: LayersRepo) -> None:
        repo.edit("kernel", "")
        repo.write("src/app2/__init__.py", "")
        repo.write(".oo-layers-baseline.json", '{"app2.kernel": ["app2.service"]}')
        assert repo.run("--update")[0] == 0
        assert "app2.kernel" in json.loads(repo.baseline.read_text())


class TestAtomicWrite:
    """A baseline write that fails part-way leaves the old file untouched."""

    def test_failed_replace_keeps_the_previous_baseline(
        self, repo: LayersRepo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo.adopt()
        before = repo.baseline.read_text()
        repo.edit("kernel", "")

        def refuse(*_args: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", refuse)
        code, out = repo.run("--update")
        assert code == 1
        assert "FAIL" in out
        assert repo.baseline.read_text() == before
        assert [p.name for p in repo.root.glob(".oo-layers-baseline*")] == [
            ".oo-layers-baseline.json"
        ]


class TestWideningCompareActiveLayers:
    """Only layers that match modules count when comparing permissions."""

    def _declared(self) -> DeclaredLayers:
        return DeclaredLayers(
            {
                "entry": {"prefixes": ["entry"], "imports": ["domain"]},
                "domain": {"prefixes": ["domain"], "imports": []},
            }
        )

    def test_equivalent_migration_to_the_fixed_form_is_not_widening(self) -> None:
        fixed = LayerConfig({"entry": ["app.entry"], "domain": ["app.domain"]})
        assert LayerWidening(fixed, self._declared()).lines() == []

    def test_activating_an_empty_layer_is_widening(self) -> None:
        fixed = LayerConfig(
            {
                "entry": ["app.entry"],
                "adapters": ["app.adapters"],
                "domain": ["app.domain"],
            }
        )
        assert LayerWidening(fixed, self._declared()).lines()
