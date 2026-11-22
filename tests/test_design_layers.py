"""Layer contracts on tiny isolated packages, exercised through the scanner/CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oo_ratchet.design.cli import main
from oo_ratchet.design.findings import Rules
from oo_ratchet.design.layer_config import LayerConfig, LayerConfigError
from oo_ratchet.design.scanner import DesignScanner

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
    ],
)
def test_domain_io_imports(tmp_path: Path, library: str) -> None:
    root = package(tmp_path, f"import {library} as io")
    assert keys(root) == {(Rules.DOMAIN_IO, "domain.py", library)}


@pytest.mark.parametrize(
    "source,symbol",
    [
        ("from json import loads as decode", "loads"),
        ("from urllib import request", "request"),
        ("import os as system\nx = system.getenv('HOME')", "os"),
        ("import os\nx = os.environ['HOME']", "os"),
        ("from os import listdir as ls\nx = ls('.')", "listdir"),
        ("from pathlib import Path as P\nx = P('.').read_text()", "Path"),
        ("from pathlib import Path\np = Path('.')\nx = p.exists()", "Path"),
        ("def load():\n return open('x')", "open"),
        ("import builtins\nx = builtins.open('x')", "open"),
        ("from builtins import open as read\nx = read('x')", "open"),
        (
            "from pathlib import Path\np: Path = Path('.') / 'x'\nx = p.read_text()",
            "Path",
        ),
    ],
)
def test_domain_io_uses(tmp_path: Path, source: str, symbol: str) -> None:
    assert keys(package(tmp_path, source)) == {(Rules.DOMAIN_IO, "domain.py", symbol)}


@pytest.mark.parametrize(
    "source",
    [
        "",
        "import os",
        "from pathlib import Path\np = Path('x')",
        "import os\nx = os.path.join('a', 'b')",
        "from pathlib import PurePath\nx = PurePath('x').name",
        "def load(open):\n return open('x')",
    ],
)
def test_pure_domain(tmp_path: Path, source: str) -> None:
    assert keys(package(tmp_path, source)) == set()


def test_io_outside_domain_is_allowed(tmp_path: Path) -> None:
    assert keys(package(tmp_path, "import json\nopen('x')", "adapters.py")) == set()


def test_local_open_does_not_hide_sibling_builtin(tmp_path: Path) -> None:
    root = package(
        tmp_path, "def custom(open):\n return open('x')\ndef load():\n return open('x')"
    )
    rows = json.loads(DesignScanner(root).report.to_json())["findings"]
    assert [(r["symbol"], r["line"]) for r in rows if r["rule"] == Rules.DOMAIN_IO] == [
        ("open", 4)
    ]


def test_unlayered_and_root_package(tmp_path: Path) -> None:
    root = package(tmp_path, "", "forgotten.py")
    assert keys(root) == {(Rules.UNLAYERED_MODULE, "forgotten.py", "<module>")}


def test_class_open_does_not_hide_method_builtin(tmp_path: Path) -> None:
    root = package(
        tmp_path, "class Reader:\n open = custom\n def read(self):\n  return open('x')"
    )
    assert keys(root) == {(Rules.DOMAIN_IO, "domain.py", "open")}


@pytest.mark.parametrize(
    "expression",
    [
        "[open for open in xs]",
        "{open for open in xs}",
        "{open: open for open in xs}",
        "(open for open in xs)",
    ],
)
def test_comprehension_open_does_not_bind_outer(
    tmp_path: Path, expression: str
) -> None:
    root = package(
        tmp_path, f"def read(xs):\n values = {expression}\n return open('x')"
    )
    assert keys(root) == {(Rules.DOMAIN_IO, "domain.py", "open")}


@pytest.mark.parametrize(
    "body",
    [
        "os = Fake()\n return os.getenv('HOME')",
        "return os.getenv('HOME')",
    ],
)
def test_io_alias_local_shadowing(tmp_path: Path, body: str) -> None:
    params = "" if body.startswith("os =") else "os"
    root = package(tmp_path, f"import os\ndef read({params}):\n {body}")
    assert keys(root) == set()


@pytest.mark.parametrize(
    "source",
    [
        "import os as system\ndef f(system):\n return system.getenv('HOME')",
        "from os import getenv as env\ndef f(env):\n return env('HOME')",
        "from pathlib import Path\ndef f(Path):\n return Path('x').exists()",
        "import builtins\ndef f(builtins):\n return builtins.open('x')",
        "import os\ndef outer(os):\n def inner():\n  return os.getenv('HOME')",
        "def local():\n import os\ndef other(os):\n return os.getenv('HOME')",
    ],
)
def test_shadowed_alias_variants(tmp_path: Path, source: str) -> None:
    assert keys(package(tmp_path, source)) == set()


def test_shadowed_alias_keeps_real_sibling_use(tmp_path: Path) -> None:
    source = (
        "import os\ndef fake(os):\n return os.getenv('HOME')\n"
        "def real():\n return os.getenv('HOME')"
    )
    assert keys(package(tmp_path, source)) == {(Rules.DOMAIN_IO, "domain.py", "os")}


@pytest.mark.parametrize(
    "operation",
    [
        "path.isfile",
        "path.isdir",
        "path.islink",
        "path.lexists",
        "path.isjunction",
        "path.isdevdrive",
        "path.sameopenfile",
        "path.exists",
        "path.getsize",
        "path.getmtime",
        "path.getatime",
        "path.getctime",
        "path.ismount",
        "path.samefile",
        "listdir",
    ],
)
def test_os_filesystem_spellings(tmp_path: Path, operation: str) -> None:
    root = package(tmp_path, f"import os\nx = os.{operation}('x')")
    assert keys(root) == {(Rules.DOMAIN_IO, "domain.py", "os")}


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
