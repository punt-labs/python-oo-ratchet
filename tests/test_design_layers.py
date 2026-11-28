"""Layer contracts on tiny isolated packages, exercised through the scanner/CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oo_ratchet.core.domain.findings import Rules
from oo_ratchet.core.domain.layer_config import LayerConfig, LayerConfigError
from oo_ratchet.design.cli import main
from oo_ratchet.design.scan import DesignScanner

LAYERS = {
    Rules.LAYER_IMPORT,
    Rules.DOMAIN_IO,
    Rules.UNLAYERED_MODULE,
    Rules.THICK_ENTRY,
}
CONFIG = """[tool.oo-ratchet.layers]
entry = ["pkg", "pkg.entry"]
adapters = ["pkg.adapters", "pkg.adapters.*"]
application = ["pkg.application"]
domain = ["pkg.domain", "pkg.domain.*"]
"""


def package(tmp_path: Path, source: str, module: str = "domain.py") -> Path:
    root = tmp_path / "pkg"
    root.mkdir(exist_ok=True)
    (root / "__init__.py").write_text("")
    target = root / module
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source)
    (tmp_path / "pyproject.toml").write_text(CONFIG)
    return root


def keys(root: Path) -> set[tuple[str, str, str]]:
    doc = json.loads(DesignScanner(root).report.to_json())
    return {
        (r["rule"], Path(r["path"]).relative_to(root).as_posix(), r["symbol"])
        for r in doc["findings"]
        if r["rule"] in LAYERS
    }


@pytest.mark.parametrize(
    "source,symbol",
    [
        ("from .adapters import Store", "Store"),
        ("from pkg.adapters import Store as S", "Store"),
        ("import pkg.adapters as edge", "pkg.adapters"),
        ("from pkg import adapters as edge", "adapters"),
        (
            (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n from .adapters import Store"
            ),
            "Store",
        ),
    ],
)
def test_outward_import(tmp_path: Path, source: str, symbol: str) -> None:
    root = package(tmp_path, source)
    (root / "adapters.py").write_text("class Store: pass")
    assert (Rules.LAYER_IMPORT, "domain.py", symbol) in keys(root)


def test_nested_relative_import_and_inward_allowed(tmp_path: Path) -> None:
    root = package(tmp_path, "from .. import application", "domain/inner.py")
    (root / "domain" / "__init__.py").write_text("")
    (root / "application.py").write_text("from .domain import inner")
    (root / "entry.py").write_text("from . import application")
    assert keys(root) == {(Rules.LAYER_IMPORT, "domain/inner.py", "application")}


@pytest.mark.parametrize(
    "library",
    [
        "subprocess",
        "socket",
        "shutil",
        "json",
        "sqlite3",
        "httpx",
        "requests",
        "urllib.request",
        "typer",
        "rich",
        "mcp",
        "fastmcp",
        "logging.handlers",
        "os",
        "os.path",
        "pathlib",
        "io",
        "tempfile",
        "glob",
    ],
)
def test_domain_io_imports(tmp_path: Path, library: str) -> None:
    root = package(tmp_path, f"import {library} as io")
    assert keys(root) == {(Rules.DOMAIN_IO, "domain.py", library)}


def test_unbound_bare_open_calls(tmp_path: Path) -> None:
    root = package(tmp_path, "open('x')\ndef load():\n return open('y')")
    rows = json.loads(DesignScanner(root).report.to_json())["findings"]
    assert [(r["symbol"], r["line"]) for r in rows if r["rule"] == Rules.DOMAIN_IO] == [
        ("open", 1),
        ("open", 3),
    ]


@pytest.mark.parametrize(
    "source",
    [
        "",
        "import math",
        "from collections import Counter",
        "def load(open):\n return open('x')",
    ],
)
def test_pure_domain(tmp_path: Path, source: str) -> None:
    assert keys(package(tmp_path, source)) == set()


def test_io_outside_domain_is_allowed(tmp_path: Path) -> None:
    assert keys(package(tmp_path, "import json\nopen('x')", "adapters.py")) == set()


def test_unlayered_and_root_package(tmp_path: Path) -> None:
    root = package(tmp_path, "", "forgotten.py")
    assert keys(root) == {(Rules.UNLAYERED_MODULE, "forgotten.py", "<module>")}


def test_entry_complexity_and_qualified_names(tmp_path: Path) -> None:
    root = package(
        tmp_path,
        """
def thin(x):
    if x: pass
    if x: pass
    if x: pass
class App:
    async def run(self, x):
        if x: pass
        if x: pass
        if x: pass
        if x: pass
def outer():
    def inner(x):
        if x: pass
        if x: pass
        if x: pass
        if x: pass
    return inner
""",
        "entry.py",
    )
    assert keys(root) == {
        (Rules.THICK_ENTRY, "entry.py", "App.run"),
        (Rules.THICK_ENTRY, "entry.py", "outer.inner"),
    }


def test_no_config_silence_and_nearest_project(tmp_path: Path) -> None:
    root = package(tmp_path, "import json\nfrom .entry import run")
    (tmp_path / "pyproject.toml").unlink()
    assert keys(root) == set()
    (tmp_path / "pyproject.toml").write_text(CONFIG)
    (root / "pyproject.toml").write_text("[project]\nname = 'no-layers'")
    assert keys(root) == set()


def test_empty_config_marks_all_modules_unlayered(tmp_path: Path) -> None:
    root = package(tmp_path, "")
    (tmp_path / "pyproject.toml").write_text("[tool.oo-ratchet.layers]")
    assert len(keys(root)) == 2


@pytest.mark.parametrize(
    "content",
    [
        "[tool.oo-ratchet.layers]\ndomian = []",
        "[tool.oo-ratchet.layers]\ndomain = 'pkg.*'",
        "[tool.oo-ratchet.layers]\ndomain = [1]",
        "[tool.oo-ratchet.layers]\ndomain = ['']",
        "[tool.oo-ratchet]\nlayers = []",
        "tool = 1",
        "not valid toml",
    ],
)
def test_bad_config(
    tmp_path: Path, content: str, capsys: pytest.CaptureFixture[str]
) -> None:
    root = package(tmp_path, "")
    (tmp_path / "pyproject.toml").write_text(content)
    with pytest.raises(LayerConfigError):
        DesignScanner(root)
    assert main([str(root)]) == 2
    assert "oo-ratchet design:" in capsys.readouterr().err


def test_override_and_advisory_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = package(tmp_path, "import json")
    override = tmp_path / "layers.toml"
    override.write_text(CONFIG)
    (tmp_path / "pyproject.toml").write_text("invalid toml")
    assert main([str(root), "--layers", str(override), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"][Rules.DOMAIN_IO] == 1
    override.write_text("")
    assert main([str(root), "--layers", str(override)]) == 2
    assert "missing" in capsys.readouterr().err
    override.unlink()
    assert main([str(root), "--layers", str(override)]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_layer_order_not_toml_order() -> None:
    config = LayerConfig({"domain": ["pkg.*"], "entry": ["pkg.entry"]})
    assert config.layer("pkg.entry") == "entry"
    assert config.layer("pkg.core") == "domain"


def test_dot_root_uses_resolved_package_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = package(tmp_path, "import json\nfrom pkg.adapters import Store")
    (root / "adapters.py").write_text("class Store: pass")
    monkeypatch.chdir(root)
    assert keys(Path()) == {
        (Rules.DOMAIN_IO, "domain.py", "json"),
        (Rules.LAYER_IMPORT, "domain.py", "Store"),
    }


def test_symlink_uses_package_spelling(tmp_path: Path) -> None:
    root = package(tmp_path, "import json\nfrom pkg.adapters import Store")
    (root / "adapters.py").write_text("class Store: pass")
    target = tmp_path / "other_dir"
    root.rename(target)
    root.symlink_to(target, target_is_directory=True)
    assert keys(root) == {
        (Rules.DOMAIN_IO, "domain.py", "json"),
        (Rules.LAYER_IMPORT, "domain.py", "Store"),
    }


@pytest.mark.parametrize("spelling", [".", "..", "pkg/", "symlink"])
def test_lexically_normalized_package_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    root = package(tmp_path, "import json\nfrom pkg.adapters import Store")
    (root / "adapters.py").write_text("class Store: pass")
    if spelling == "symlink":
        target = tmp_path / "other_dir"
        root.rename(target)
        root.symlink_to(target, target_is_directory=True)
        monkeypatch.chdir(tmp_path)
        source = Path("pkg/")
    elif spelling == "..":
        (root / "child").mkdir()
        monkeypatch.chdir(root / "child")
        source = Path("..")
    else:
        monkeypatch.chdir(root if spelling == "." else tmp_path)
        source = Path(spelling)
    rows = json.loads(DesignScanner(source).report.to_json())["findings"]
    assert {(r["rule"], r["symbol"]) for r in rows if r["rule"] in LAYERS} == {
        (Rules.DOMAIN_IO, "json"),
        (Rules.LAYER_IMPORT, "Store"),
    }


@pytest.mark.parametrize(
    "source,symbol",
    [
        ("import os", "os"),
        ("import os\nx = os.path.join('a', 'b')", "os"),
        ("from os import getenv as env", "os"),
        ("from os.path import join", "os.path"),
        ("from pathlib import PurePath", "pathlib"),
        ("import io", "io"),
        ("import tempfile", "tempfile"),
        ("import glob", "glob"),
        ("import os\ndef f(os): return os.getenv('HOME')", "os"),
    ],
)
def test_domain_io_is_import_based(tmp_path: Path, source: str, symbol: str) -> None:
    assert keys(package(tmp_path, source)) == {(Rules.DOMAIN_IO, "domain.py", symbol)}


@pytest.mark.parametrize("guard", ["TYPE_CHECKING", "typing.TYPE_CHECKING"])
def test_type_checking_io_imports_are_exempt(tmp_path: Path, guard: str) -> None:
    source = (
        f"import typing\nfrom typing import TYPE_CHECKING\nif {guard}:\n import json"
    )
    assert keys(package(tmp_path, source)) == set()


@pytest.mark.parametrize("guard", ["TYPE_CHECKING", "typing.TYPE_CHECKING"])
def test_type_checking_bare_open_is_exempt(tmp_path: Path, guard: str) -> None:
    source = (
        f"import typing\nfrom typing import TYPE_CHECKING\nif {guard}:\n x = open('f')"
    )
    assert keys(package(tmp_path, source)) == set()


def test_domain_io_once_per_imported_module(tmp_path: Path) -> None:
    root = package(
        tmp_path,
        "from json import loads, dumps\nimport json\nfrom urllib import request, parse",
    )
    rows = json.loads(DesignScanner(root).report.to_json())["findings"]
    assert [(r["symbol"], r["line"]) for r in rows if r["rule"] == Rules.DOMAIN_IO] == [
        ("json", 1),
        ("json", 2),
        ("urllib.request", 3),
    ]


@pytest.mark.parametrize(
    "binding",
    [
        "def other(open): pass",
        "class Reader:\n open = custom",
        "values = [open for open in xs]",
        "def other():\n open = custom",
        "def open(): pass",
        "async def open(): pass",
        "class open: pass",
        "from custom import open",
        "import custom as open",
        "open: object",
        "for open in xs: pass",
        "with resource() as open: pass",
        "if (open := custom): pass",
        "def other(value=lambda open: open): pass",
        "match value:\n case open: pass",
        "match value:\n case [*open]: pass",
        "match value:\n case {'x': _, **open}: pass",
    ],
)
def test_any_module_binding_suppresses_builtin_open(
    tmp_path: Path, binding: str
) -> None:
    assert keys(package(tmp_path, binding + "\nopen('x')")) == set()


def test_qualified_open_is_not_builtin_open(tmp_path: Path) -> None:
    assert keys(package(tmp_path, "import builtins\nbuiltins.open('x')")) == set()


def test_type_checking_else_is_runtime_io(tmp_path: Path) -> None:
    source = (
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n import json\n"
        "else:\n import os"
    )
    assert keys(package(tmp_path, source)) == {(Rules.DOMAIN_IO, "domain.py", "os")}


def test_relative_import_is_not_external_io(tmp_path: Path) -> None:
    assert (
        keys(package(tmp_path, "from .json import loads\nimport jsonpickle")) == set()
    )
