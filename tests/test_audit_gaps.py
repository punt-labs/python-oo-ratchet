"""0.2.2: "any" is a superset of the default LCOM exemptions; bless audits gains."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oo_ratchet.coupling.audit import CouplingAudit
from oo_ratchet.coupling.baseline import CouplingBaseline
from oo_ratchet.coupling.bless import CouplingBless
from oo_ratchet.coupling.gitio import GitRepo

from .test_coupling_config import _HEADER, _frozen, _hub, _max_lcom
from .test_coupling_ratchet import GitFixture
from .test_oo_ratchet import GOOD, WORSE
from .test_oo_ratchet import GitFixture as OoFixture

pytestmark = pytest.mark.slow

_MARKER_MIXIN = (
    f"{_HEADER}class EventHandlerHost:\n"
    "    __slots__ = ()\n\n"
    "    def on(self, kind: str, handler: object) -> None:\n"
    "        self._handlers.setdefault(kind, []).append(handler)\n\n"
    "    def clear(self) -> None:\n"
    "        self._other.clear()\n"
)


@pytest.mark.parametrize("mode", ["dataclass", "any"])
def test_marker_mixin_mutating_host_state_is_exempt(mode: str) -> None:
    assert _max_lcom(_MARKER_MIXIN, mode) == 0.0


@pytest.mark.parametrize("mode", ["dataclass", "any"])
@pytest.mark.parametrize(
    "write",
    [
        'setattr(self, "_{n}", 1)',
        'self.__setattr__("_{n}", 1)',
        'super().__setattr__("_{n}", 1)',
        'self.__dict__["_{n}"] = 1',
        "self.__dict__.update(_{n}=1)",
    ],
)
def test_dataclass_storing_state_indirectly_is_measured(write: str, mode: str) -> None:
    source = _frozen(write).replace("class Frozen:", "@dataclass\nclass Frozen:")
    assert _max_lcom(source, mode) > 0.0


def _last(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text().splitlines()[-1]))


def test_oo_rebaseline_files_audits_improvements(tmp_path: Path) -> None:
    fx = OoFixture(tmp_path)
    fx.write("sub/w.py", WORSE)
    fx.snapshot("sub")
    fx.commit("base")
    fx.write("sub/w.py", GOOD)
    outcome = fx.writer().rebaseline_files(
        fx.scorer(), ["sub/w.py"], reason="r", allow_ci_write=True, source=None
    )
    assert outcome.exit_code == 0
    entry = _last(fx.root / ".oo-audit.jsonl")
    assert entry["deltas"] == {}
    assert entry["improved"] == {"sub/w.py": {"max_complexity": [3.0, 1.0]}}


def test_coupling_rebaseline_files_audits_improvements(tmp_path: Path) -> None:
    fx = GitFixture(tmp_path)
    _hub(fx, 9)
    fx.snapshot()
    fx.commit("base")
    _hub(fx, 8)
    outcome = CouplingBless(fx.root, GitRepo(fx.root)).apply(
        CouplingBaseline.metrics_by_file(fx.scorer().results),
        ["pkg/hub.py"],
        reason="r",
        source=None,
        allow_ci_write=True,
    )
    assert outcome.exit_code == 0
    entry = _last(fx.root / CouplingAudit.FILENAME)
    assert entry["deltas"] == {}
    assert entry["improved"] == {"pkg/hub.py": {"efferent_coupling": [9.0, 8.0]}}
    assert entry["files_improved"] == 1


def test_coupling_rebaseline_records_deltas_and_reason(tmp_path: Path) -> None:
    fx = GitFixture(tmp_path)
    _hub(fx, 8)
    fx.snapshot()
    _hub(fx, 9)
    outcome = fx.writer().rebaseline(
        fx.scorer(), allow_ci_write=True, source="PL-1", reason="counter change"
    )
    assert outcome.exit_code == 0
    entry = _last(fx.root / CouplingAudit.FILENAME)
    assert entry["reason"] == "counter change"
    deltas = entry["deltas"]
    assert isinstance(deltas, dict)
    assert deltas["pkg/hub.py"]["efferent_coupling"] == [8.0, 9.0]
    assert (entry["files_improved"], entry["files_regressed"]) == (0, 1)


def test_coupling_rebaseline_counts_improved_files(tmp_path: Path) -> None:
    fx = GitFixture(tmp_path)
    _hub(fx, 9)
    fx.snapshot()
    _hub(fx, 8)
    fx.writer().rebaseline(fx.scorer(), allow_ci_write=True, source=None)
    entry = _last(fx.root / CouplingAudit.FILENAME)
    assert (entry["files_improved"], entry["files_regressed"]) == (1, 0)
