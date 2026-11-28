"""Coupling is clean architecture: pure domain, filesystem work in adapters.

The characterization half pins the gate's JSON output on a fixture tree so the
split of the coupling package cannot change a number.  The architecture half
runs this repository's own layer and design scans and demands no finding for
the coupling modules that belong to the domain ring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from oo_ratchet.__main__ import main as dispatch

if TYPE_CHECKING:
    import pytest

    from tests.conftest import GitSandbox

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden_coupling_scan.json"

FIXTURE = {
    "pyproject.toml": (
        '[project]\nname = "x"\n'
        "[tool.oo-ratchet.coupling.caps]\n"
        '"pkg/hub.py" = { efferent_coupling = 20 }\n'
    ),
    "pkg/__init__.py": "from .a import A\nfrom .b import B\n",
    "pkg/a.py": (
        "from __future__ import annotations\nfrom .b import B\n"
        "class A:\n    def __init__(self): self.x = B()\n"
        "    def f(self): return self.x\n"
    ),
    "pkg/b.py": (
        "from __future__ import annotations\nfrom . import a\n"
        "class B:\n    def g(self): return a.A\n"
    ),
    "pkg/hub.py": "from .sub import one, two\nfrom . import a, b\n",
    "pkg/bad.py": "def (:\n",
    "pkg/sub/__init__.py": 'from .one import X\n__all__ = ["X", "Y", "Z"]\n',
    "pkg/sub/one.py": "from ..a import A\nclass X: pass\n",
    "pkg/sub/two.py": "from . import one\n",
    "pkg/empty/__init__.py": "",
}


def _json(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    target: str,
) -> dict[str, object]:
    for rel, text in FIXTURE.items():
        git_sandbox.write(rel, text)
    git_sandbox.commit("fixture")
    monkeypatch.chdir(git_sandbox.root)
    capsys.readouterr()
    dispatch(["coupling", target, "--json"])
    out: dict[str, object] = json.loads(capsys.readouterr().out)
    return out


class TestCharacterization:
    """The coupling JSON for a fixture tree does not change."""

    def test_package_scan_json_is_pinned(
        self,
        git_sandbox: GitSandbox,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        got = _json(git_sandbox, monkeypatch, capsys, "pkg")
        assert got == json.loads(GOLDEN.read_text())["package"]

    def test_single_file_scan_json_is_pinned(
        self,
        git_sandbox: GitSandbox,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        got = _json(git_sandbox, monkeypatch, capsys, "pkg/a.py")
        assert got == json.loads(GOLDEN.read_text())["file"]


class TestRings:
    """No coupling module in the domain ring imports IO or an outer ring."""

    def test_layer_scan_has_no_coupling_module_violation(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(ROOT)
        dispatch(["layers", "src/oo_ratchet/", "--json"])
        report = json.loads(capsys.readouterr().out)
        found = [
            f"{v['source']} -> {v['target']}"
            for v in report["violations"]
            if v["source"].startswith("oo_ratchet.coupling.")
        ]
        assert found == []

    def test_design_scan_has_no_domain_rule_finding_for_coupling(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(ROOT)
        dispatch(["design", "src/oo_ratchet/", "--json"])
        report = json.loads(capsys.readouterr().out)
        found = [
            f"{f['rule']} {f['path']}:{f['line']} {f['symbol']}"
            for f in report["findings"]
            if "/coupling/" in f["path"]
            and f["rule"] in {"domain-io", "layer-import"}
            and not f["path"].endswith("__init__.py")
        ]
        assert found == []
