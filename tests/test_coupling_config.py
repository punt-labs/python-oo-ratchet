"""Per-repo coupling config: path caps, stateless-value LCOM, coupling bless."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from oo_ratchet.coupling.cli import main
from oo_ratchet.coupling.config import CouplingConfig, CouplingConfigError
from oo_ratchet.coupling.imports import ImportResolver
from oo_ratchet.coupling.metrics import ModuleCouplingMetrics
from oo_ratchet.coupling.report import CouplingReport
from oo_ratchet.coupling.scorer import CouplingScorer
from oo_ratchet.coupling.thresholds import CouplingTargets

from .test_coupling_ratchet import GitFixture

_HEADER = "from __future__ import annotations\n\n"
_HUB_CAPS = {"pkg/hub.py": {"efferent_coupling": 20.0}}


def _hub(fx: GitFixture, imports: int) -> None:
    fx.write("pkg/__init__.py", "")
    for i in range(13):
        fx.write(f"pkg/m{i}.py", f"{_HEADER}VALUE = {i}\n")
    body = "".join(f"from . import m{i}\n" for i in range(imports))
    fx.write("pkg/hub.py", f"{_HEADER}{body}")


@pytest.fixture
def fx(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> GitFixture:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return GitFixture(tmp_path, capsys, monkeypatch)


class TestConfigLoad:
    """``[tool.oo-ratchet.coupling]`` parses strictly and defaults when absent."""

    def test_absent_pyproject_is_default(self, tmp_path: Path) -> None:
        assert CouplingConfig.load(tmp_path) == CouplingConfig()

    def test_reads_caps_and_mode(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.oo-ratchet.coupling]\n"
            'stateless-values = "any"\n'
            "[tool.oo-ratchet.coupling.caps]\n"
            '"./src/p/facade.py" = { efferent_coupling = 20 }\n'
        )
        config = CouplingConfig.load(tmp_path)
        assert config.caps == {"src/p/facade.py": {"efferent_coupling": 20.0}}
        assert config.stateless_values == "any"

    @pytest.mark.parametrize(
        "table",
        [
            {"caps": {"a.py": {"nope": 3}}},
            {"caps": {"a.py": {"efferent_coupling": "20"}}},
            {"caps": {"a.py": {"efferent_coupling": True}}},
            {"caps": {"a.py": {}}},
            {"caps": {"/abs/a.py": {"efferent_coupling": 20}}},
            {"caps": {"../a.py": {"efferent_coupling": 20}}},
            {"caps": {"C:\\repo\\a.py": {"efferent_coupling": 20}}},
            {"caps": {"pkg/../../a.py": {"efferent_coupling": 20}}},
            {"caps": ["a.py"]},
            {"stateless-values": "all"},
            {"hub-caps": {}},
            {"stateless-values": ["any"]},
        ],
    )
    def test_rejects_malformed(self, table: dict[str, object]) -> None:
        with pytest.raises(CouplingConfigError):
            CouplingConfig.from_table(table)

    @pytest.mark.parametrize(
        "text",
        [
            'tool = "bad"\n',
            "[tool]\noo-ratchet = 3\n",
            "[tool.oo-ratchet]\ncoupling = 1\n",
        ],
    )
    def test_non_table_parents_are_controlled_error(
        self, tmp_path: Path, text: str
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(text)
        with pytest.raises(CouplingConfigError):
            CouplingConfig.load(tmp_path)

    def test_equivalent_paths_normalize(self) -> None:
        config = CouplingConfig.from_table(
            {"caps": {"pkg/../pkg//hub.py": {"efferent_coupling": 20}}}
        )
        assert set(config.caps) == {"pkg/hub.py"}

    def test_bad_toml_is_controlled_error(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool\n")
        with pytest.raises(CouplingConfigError):
            CouplingConfig.load(tmp_path)


class TestPathCaps:
    """An exact-path cap overrides the default target for that file only."""

    def test_cap_applies_to_exact_path_only(self) -> None:
        targets = CouplingTargets(_HUB_CAPS)
        assert targets.metric("efferent_coupling", "pkg/hub.py").meets(12)
        assert not targets.metric("efferent_coupling", "other/pkg/hub.py").meets(12)
        assert not targets.metric("efferent_coupling", "pkg/hub.py").meets(21)
        capped = targets.metric("efferent_coupling", "pkg/hub.py")
        assert (capped.op, capped.target) == ("<=", 20.0)

    def test_equality_metric_cap_is_an_upper_bound(self) -> None:
        caps = {"pkg/hub.py": {"circular_imports": 1.0}}
        assert CouplingTargets(caps).metric("circular_imports", "pkg/hub.py").meets(0)
        assert CouplingTargets(caps).metric("circular_imports", "pkg/hub.py").meets(1)
        assert (
            not CouplingTargets(caps).metric("circular_imports", "pkg/hub.py").meets(2)
        )

    def test_per_file_report_honors_cap(self, fx: GitFixture) -> None:
        _hub(fx, 12)
        scorer = CouplingScorer(
            fx.root / "pkg", fx.root, CouplingConfig(caps=_HUB_CAPS)
        )
        lines = CouplingReport(scorer).render_per_file()
        hub = lines.index("\n  pkg/hub.py")
        assert "PASS" in lines[hub + 1]
        assert "efferent_coupling" in lines[hub + 1]


_PUBLIC_STATE = (
    f"{_HEADER}\nclass Pair:\n"
    "    def __init__(self) -> None:\n"
    "        self.left = 1\n"
    "        self.right = 2\n\n"
    "    def get_left(self) -> int:\n"
    "        return self.left\n\n"
    "    def get_right(self) -> int:\n"
    "        return self.right\n"
)
_SETATTR = (
    f"{_HEADER}\nclass Frozen:\n"
    "    def __new__(cls) -> Frozen:\n"
    "        self = super().__new__(cls)\n"
    '        object.__setattr__(self, "_a", 1)\n'
    '        object.__setattr__(self, "_b", 2)\n'
    "        return self\n\n"
    "    def get_a(self) -> int:\n"
    "        return self._a\n\n"
    "    def get_b(self) -> int:\n"
    "        return self._b\n"
)


def _frozen(write: str) -> str:
    return (
        f"{_HEADER}\nclass Frozen:\n"
        "    def __init__(self) -> None:\n"
        f"        {write.format(n='a')}\n"
        f"        {write.format(n='b')}\n\n"
        "    def get_a(self) -> int:\n"
        "        return self._a\n\n"
        "    def get_b(self) -> int:\n"
        "        return self._b\n"
    )


def _max_lcom(source: str, mode: str) -> float:
    resolver = ImportResolver("m", frozenset({"m"}), "pkg", is_package=False)
    metrics = ModuleCouplingMetrics("m.py", ast.parse(source), resolver, mode)
    return float(metrics.compute()["max_lcom"])


class TestCappedGrades:
    """The aggregate grade honors per-file caps, so the exit code agrees."""

    def test_capped_hub_passes_summary(self, fx: GitFixture) -> None:
        _hub(fx, 12)
        capped = CouplingScorer(
            fx.root / "pkg", fx.root, CouplingConfig(caps=_HUB_CAPS)
        )
        strict = CouplingScorer(fx.root / "pkg", fx.root)
        assert capped.grades["efferent_coupling"] == "PASS"
        assert strict.grades["efferent_coupling"] == "FAIL"

    def test_averaged_metric_honors_cap(self, fx: GitFixture) -> None:
        _hub(fx, 1)
        fx.write("pkg/m0.py", _PUBLIC_STATE)
        strict = CouplingScorer(fx.root / "pkg", fx.root)
        assert strict.grades["avg_lcom"] == "FAIL" or strict.summary["avg_lcom"] <= 0.5
        caps = {"pkg/m0.py": {"avg_lcom": 1.0, "max_lcom": 1.0}}
        capped = CouplingScorer(fx.root / "pkg", fx.root, CouplingConfig(caps=caps))
        assert capped.grades["avg_lcom"] == "PASS"
        assert capped.grades["max_lcom"] == "PASS"


class TestStatelessValues:
    """``stateless-values = "any"`` skips classes holding no private state."""

    def test_default_measures_plain_class(self) -> None:
        assert _max_lcom(_PUBLIC_STATE, "dataclass") > 0.0

    def test_any_exempts_class_without_private_state(self) -> None:
        assert _max_lcom(_PUBLIC_STATE, "any") == 0.0

    @pytest.mark.parametrize(
        "write",
        [
            'object.__setattr__(self, "_{n}", 1)',
            'super().__setattr__("_{n}", 1)',
            'self.__setattr__("_{n}", 1)',
            'type(self).__setattr__(self, "_{n}", 1)',
            'setattr(self, "_{n}", 1)',
            'self.__dict__["_{n}"] = 1',
            'self._cache["{n}"] = 1',
            'self._cache["{n}"] += 1',
            'del self._cache["{n}"]',
            "self._cache.update({n}=1)",
            'self._items.append("{n}")',
            'self._groups["{n}"].append(1)',
            'self._grid[0]["{n}"] = 1',
            "self.__dict__.update(_{n}=1)",
            'self.__dict__.update({{"_{n}": 1}})',
            'self.__dict__["_{n}"][0] = 1',
            'self.__dict__.setdefault("_{n}", 1)',
        ],
    )
    def test_any_still_measures_private_writes(self, write: str) -> None:
        assert _max_lcom(_frozen(write), "any") > 0.0

    def test_public_dunder_dict_write_is_not_private_state(self) -> None:
        source = (
            f"{_HEADER}class Bag:\n"
            '    def left(self) -> None:\n        self.__dict__["left"] = 1\n\n'
            "    def right(self) -> None:\n        self.__dict__.update(right=2)\n"
        )
        assert _max_lcom(source, "any") == 0.0

    def test_reading_private_collection_is_not_a_write(self) -> None:
        source = (
            f"{_HEADER}class Reader:\n"
            "    _table: dict[str, int] = {}\n\n"
            '    def left(self) -> int:\n        return self._table["a"]\n\n'
            '    def right(self) -> int:\n        return self._table.get("b", 0)\n'
        )
        assert _max_lcom(source, "any") == 0.0

    def test_nested_class_state_does_not_block_parent(self) -> None:
        source = (
            f"{_HEADER}\nclass Outer:\n"
            "    def left(self) -> int:\n        return 1\n\n"
            "    def right(self) -> int:\n        return 2\n\n"
            "    class Inner:\n"
            "        def __init__(self) -> None:\n"
            "            self._v = 1\n"
        )
        assert _max_lcom(source, "any") == 0.0


@pytest.mark.slow
class TestCouplingBless:
    """``--rebaseline-files`` is bounded by per-file caps and waives at check."""

    def _setup(self, fx: GitFixture) -> str:
        _hub(fx, 11)
        fx.snapshot()
        base = fx.commit("base")
        _hub(fx, 12)
        return base

    @staticmethod
    def _caps(fx: GitFixture, caps: dict[str, dict[str, float]]) -> None:
        rows = "".join(
            f'"{path}" = {{ {metric} = {cap:g} }}\n'
            for path, metrics in caps.items()
            for metric, cap in metrics.items()
        )
        if rows:
            fx.write("pyproject.toml", f"[tool.oo-ratchet.coupling.caps]\n{rows}")

    def _bless(self, fx: GitFixture, caps: dict[str, dict[str, float]]) -> int:
        self._caps(fx, caps)
        outcome = fx.writer().bless(["pkg/hub.py"], reason="wiring hub gains a module")
        return outcome.exit_code

    def test_over_default_cap_refused(self, fx: GitFixture) -> None:
        self._setup(fx)
        assert self._bless(fx, {}) == 1
        entry = fx.row("pkg/hub.py")
        assert entry is not None
        assert entry["efferent_coupling"] == 11.0

    def test_within_path_cap_blessed_and_waived(self, fx: GitFixture) -> None:
        base = self._setup(fx)
        assert self._bless(fx, _HUB_CAPS) == 0
        entry = fx.row("pkg/hub.py")
        assert entry is not None
        assert entry["efferent_coupling"] == 12.0
        fx.commit("bless")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 0, outcome.lines

    def test_renamed_file_bless_waives_at_check(self, fx: GitFixture) -> None:
        _hub(fx, 11)
        fx.snapshot()
        base = fx.commit("base")
        fx.move("pkg/hub.py", "pkg/wiring.py")
        body = "".join(f"from . import m{i}\n" for i in range(12))
        fx.write("pkg/wiring.py", f"{_HEADER}{body}")
        self._caps(fx, {"pkg/wiring.py": {"efferent_coupling": 20.0}})
        outcome = fx.writer().bless(
            ["pkg/wiring.py"], reason="renamed hub gains a module", base_ref=base
        )
        assert outcome.exit_code == 0, outcome.lines
        assert fx.row("pkg/hub.py") is None
        fx.commit("rename and bless")
        check = fx.ratchet().check(base_ref=base, require_base=True)
        assert check.exit_code == 0, check.lines

    def test_unblessed_regression_still_fails(self, fx: GitFixture) -> None:
        base = self._setup(fx)
        fx.commit("no bless")
        outcome = fx.ratchet().check(base_ref=base, require_base=True)
        assert outcome.exit_code == 1

    def test_edited_worktree_baseline_does_not_bypass_gate(
        self, fx: GitFixture
    ) -> None:
        base = self._setup(fx)
        row = fx.row("pkg/hub.py")
        assert row is not None
        fx.write_baseline({"pkg/hub.py": {**row, "efferent_coupling": 12.0}})
        outcome = fx.writer().bless(["pkg/hub.py"], base_ref=base)
        assert outcome.exit_code == 1

    def test_unresolvable_base_ref_fails(self, fx: GitFixture) -> None:
        self._setup(fx)
        self._caps(fx, _HUB_CAPS)
        outcome = fx.writer().bless(["pkg/hub.py"], base_ref="no-such-ref")
        assert outcome.exit_code == 1

    def test_new_over_cap_file_refused_despite_worktree_row(
        self, fx: GitFixture
    ) -> None:
        base = self._setup(fx)
        fx.write("pkg/fresh.py", fx.root.joinpath("pkg/hub.py").read_text())
        current = fx.metrics()
        fx.write_baseline({**fx.rows(), **current})
        outcome = fx.writer().bless(["pkg/fresh.py"], base_ref=base)
        assert outcome.exit_code == 1

    def test_require_base_without_base_fails(self, fx: GitFixture) -> None:
        self._setup(fx)
        self._caps(fx, _HUB_CAPS)
        outcome = fx.writer().bless(["pkg/hub.py"], require_base=True)
        assert outcome.exit_code == 1

    def test_require_base_with_empty_base_baseline_fails(self, fx: GitFixture) -> None:
        _hub(fx, 11)
        fx.write_baseline({})
        base = fx.commit("base without rows")
        self._caps(fx, _HUB_CAPS)
        outcome = fx.writer().bless(["pkg/hub.py"], base_ref=base, require_base=True)
        assert outcome.exit_code == 1

    def test_unknown_path_refused(self, fx: GitFixture) -> None:
        self._setup(fx)
        outcome = fx.writer().bless(["pkg/missing.py"])
        assert outcome.exit_code == 1

    def test_blocked_in_ci(
        self, fx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup(fx)
        self._caps(fx, _HUB_CAPS)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        outcome = fx.writer().bless(["pkg/hub.py"], allow_ci_write=False)
        assert outcome.exit_code == 1

    def test_cli_reads_pyproject_caps(
        self,
        fx: GitFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._setup(fx)
        fx.write(
            "pyproject.toml",
            "[tool.oo-ratchet.coupling.caps]\n"
            '"pkg/hub.py" = { efferent_coupling = 20 }\n',
        )
        monkeypatch.chdir(fx.root)
        code = main(
            [
                "pkg",
                "--rebaseline-files",
                "pkg/hub.py",
                "--reason",
                "hub",
                "--allow-ci-write",
            ]
        )
        assert code == 0, capsys.readouterr().out

    def test_cli_requires_reason(
        self, fx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(fx.root)
        assert main(["pkg", "--rebaseline-files", "pkg/hub.py"]) == 1
        assert main(["pkg", "--rebaseline-files", ",", "--reason", "x"]) == 1

    def test_cli_bad_config_fails_cleanly(
        self, fx: GitFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hub(fx, 1)
        fx.write(
            "pyproject.toml", '[tool.oo-ratchet.coupling]\nstateless-values = "x"\n'
        )
        monkeypatch.chdir(fx.root)
        assert main(["pkg", "--json"]) == 1
