"""Adoption is decided from the base; dynamic bindings are joined."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from oo_ratchet.design.layer_edges import Edge
from oo_ratchet.layers.scan import LayerScan
from tests.layers_repo import BAD_SERVICE, OK_SERVICE, PYPROJECT, LayersRepo

DECLARED = """\
[tool.oo-ratchet.layers.kernel]
prefixes = ["kernel"]
imports = []

[tool.oo-ratchet.layers.service]
prefixes = ["service"]
imports = ["kernel"]
"""
WIDER = PYPROJECT.replace(
    'prefixes = ["service"]\nimports = ["kernel"]',
    'prefixes = ["service"]\nimports = ["kernel", "cli"]',
)


def _edge(tmp_path: Path, kernel: str) -> bool:
    (tmp_path / "pyproject.toml").write_text(DECLARED)
    pkg = tmp_path / "src" / "app"
    pkg.mkdir(parents=True)
    for name, text in {
        "__init__": "",
        "service": "thing = 1\n",
        "kernel": kernel,
    }.items():
        (pkg / f"{name}.py").write_text(text)
    return Edge("app.kernel", "app.service") in LayerScan(pkg).edges


def _lines(*lines: str) -> str:
    return "\n".join(lines) + "\n"


CALL = 'load("app.service")'
EVER_BOUND = [
    _lines("import importlib", "load = importlib.import_module", CALL, "load = other"),
    _lines(
        "from importlib import import_module",
        'import_module("app.service")',
        "import_module = None",
    ),
    _lines(
        "import importlib",
        "if cond:",
        "    load = importlib.import_module",
        "else:",
        "    load = other",
        CALL,
    ),
    _lines(
        "import importlib", "importlib = fake", "importlib.import_module('app.service')"
    ),
    _lines("load = __import__", CALL),
]


class TestDynamicBindingsAreJoined:
    """A call counts if its callee was ever bound to the stdlib helper in scope."""

    @pytest.mark.parametrize("kernel", EVER_BOUND)
    def test_a_name_ever_bound_to_the_helper_counts(
        self, tmp_path: Path, kernel: str
    ) -> None:
        assert _edge(tmp_path, kernel)

    @pytest.mark.parametrize(
        "kernel",
        [
            'load = other\nload("app.service")\n',
            "import importlib\nload = importlib.util\nload('app.service')\n",
        ],
    )
    def test_a_name_never_bound_to_the_helper_does_not(
        self, tmp_path: Path, kernel: str
    ) -> None:
        assert not _edge(tmp_path, kernel)


class TestAdoptionComesFromTheBase:
    """A package is new only if the base baseline and the base tree lack it."""

    def _second(self, repo: LayersRepo) -> Path:
        for name, text in {
            "__init__": "",
            "kernel": "import app2.service\n",
            "service": OK_SERVICE.replace("app", "app2"),
            "cli": "",
        }.items():
            repo.write(f"src/app2/{name}.py", text)
        return repo.root / "src" / "app2"

    def test_a_moved_package_that_adds_a_violation_fails(
        self, repo: LayersRepo
    ) -> None:
        repo.adopt()
        base = repo.commit_as_origin_main()
        (repo.root / "lib").mkdir()
        shutil.move(str(repo.root / "src" / "app"), str(repo.root / "lib" / "app"))
        repo.write("lib/app/service.py", BAD_SERVICE)
        rows = {"app.kernel": ["app.service"], "app.service": ["app.cli"]}
        repo.write(".oo-layers-baseline.json", json.dumps(rows))
        code, out = repo.run_on(
            repo.root / "lib" / "app", "--check", "--base-ref", base
        )
        assert code == 1
        assert "did not" in out

    def test_a_package_with_zero_rows_at_the_base_that_gains_one_fails(
        self, repo: LayersRepo
    ) -> None:
        repo.edit("kernel", "")
        repo.adopt()
        base = repo.commit_as_origin_main()
        repo.edit("kernel", "import app.service\n")
        assert repo.run("--update")[0] == 0
        assert repo.run("--check", "--base-ref", base)[0] == 1

    def test_a_truly_new_package_is_adopted(self, repo: LayersRepo) -> None:
        repo.adopt()
        base = repo.commit_as_origin_main()
        second = self._second(repo)
        assert repo.run_on(second, "--update")[0] == 0
        assert repo.run_on(second, "--check", "--base-ref", base)[0] == 0

    def test_widening_in_an_adoption_change_still_fails(self, repo: LayersRepo) -> None:
        repo.adopt()
        base = repo.commit_as_origin_main()
        second = self._second(repo)
        repo.write("pyproject.toml", WIDER)
        assert repo.run_on(second, "--update")[0] == 0
        code, out = repo.run_on(second, "--check", "--base-ref", base)
        assert code == 1
        assert "widened" in out
        waived = repo.run_on(
            second, "--check", "--base-ref", base, "--allow-config-change"
        )
        assert waived[0] == 0
