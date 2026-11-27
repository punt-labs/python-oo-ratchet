"""The suppression gate on the shared core, run on real git repositories.

Each scenario builds a real repository and runs ``oo_ratchet.suppression.cli.main``.
The expected stdout, exit codes and state files are the ones the previous
per-gate implementation produced: commit e4bd9db ran 18 scenarios through both
implementations and compared exit code, stdout and every state file byte for
byte (timestamps masked) before the old code was deleted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from oo_ratchet.suppression.cli import main
from tests.conftest import GitSandbox

pytestmark = pytest.mark.slow

STATE = (
    ".suppression-baseline.json",
    ".suppression-audit.jsonl",
    ".suppression-relax.json",
)
STAMP = re.compile(r'("(?:updated_at|ts|added_at)": ?)"[^"]*"')
ONE = "x = 1  # noqa\n"
TWO = "x = 1  # noqa\ny = 2  # noqa\n"
THREE = "x = 1  # noqa\ny = 2  # noqa\nz = 3  # noqa\n"
CLEAN = "x = 1\n"
CATEGORIES = {
    "noqa": 0,
    "type_ignore": 0,
    "pylint_disable": 0,
    "pyright_ignore": 0,
    "file_level": 0,
    "per_file_ignores": 0,
}


def out(*lines: str) -> str:
    """Return the stdout of a gate that printed ``lines``."""
    return "".join(f"{line}\n" for line in lines)


def head(base: int, current: int, note: str = "") -> list[str]:
    return [f"\nBaseline total: {base}", f"Current total:  {current}{note}"]


class Gate:
    """Run the CLI in a repository and read its state files."""

    def __init__(self, box: GitSandbox, capsys: pytest.CaptureFixture[str]) -> None:
        self.box = box
        self.capsys = capsys

    def source(self, text: str) -> None:
        self.box.write("pkg/a.py", text)

    def state(self, name: str) -> str | None:
        path = self.box.root / name
        return STAMP.sub(r'\1"T"', path.read_text()) if path.exists() else None

    def audit(self) -> list[dict[str, object]]:
        text = self.state(".suppression-audit.jsonl") or ""
        return [json.loads(STAMP.sub(r'\1"T"', ln)) for ln in text.splitlines()]

    def run(self, *argv: str) -> tuple[int, str]:
        self.capsys.readouterr()
        code = main(list(argv))
        return code, self.capsys.readouterr().out


@pytest.fixture
def gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Gate:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)  # CI refuses baseline writes
    return Gate(GitSandbox(tmp_path), capsys)


def check(base: str, *flags: str) -> list[str]:
    return ["pkg", "--check", "--base-ref", base, *flags]


def test_regression_is_caught(gate: Gate) -> None:
    gate.source(ONE)
    base = gate.box.commit("base")
    gate.source(TWO)
    assert gate.run(*check(base, "--require-base")) == (
        1,
        out(
            *head(1, 2),
            "\nFAIL: suppression count increased by 1 (after waivers)",
            "\nFiles with new or increased, unwaived suppressions:",
            "  pkg/a.py: +1 unwaived (1 -> 2)",
        ),
    )


def test_unchanged_passes(gate: Gate) -> None:
    gate.source(ONE)
    base = gate.box.commit("base")
    assert gate.run(*check(base, "--require-base")) == (
        0,
        out(*head(1, 1), "\nPASS: suppression count unchanged"),
    )


def test_reduction_is_credited(gate: Gate) -> None:
    gate.source(TWO)
    base = gate.box.commit("base")
    gate.source(ONE)
    assert gate.run(*check(base, "--require-base")) == (
        0,
        out(*head(2, 1), "\nPASS: suppression count decreased by 1"),
    )


def test_base_is_rescanned_not_read_from_a_stale_baseline(gate: Gate) -> None:
    gate.source(CLEAN)
    assert gate.run("pkg", "--update")[0] == 0
    gate.box.commit("baseline at zero")
    gate.source(ONE)
    base = gate.box.commit("suppression lands, baseline not refreshed")
    assert gate.run(*check(base, "--require-base")) == (
        0,
        out(*head(1, 1), "\nPASS: suppression count unchanged"),
    )


def test_relax_writes_a_ceiling_the_check_honours(gate: Gate) -> None:
    gate.source(ONE)
    base = gate.box.commit("base")
    gate.source(TWO)
    code, text = gate.run(
        "pkg", "--relax", "pkg/a.py", "--justify", "needed", "--base-ref", base
    )
    ledger = gate.box.root / ".suppression-relax.json"
    assert (code, text) == (
        0,
        out(
            "\nRelaxed pkg/a.py: ceiling set to 2 (was 1, reason: needed)",
            f"  ledger: {ledger}",
        ),
    )
    assert json.loads(gate.state(".suppression-relax.json") or "") == [
        {"file": "pkg/a.py", "ceiling": 2, "justify": "needed", "added_at": "T"}
    ]
    (entry,) = gate.audit()
    assert entry["verdict"] == "relaxed"
    assert (entry["file"], entry["before"], entry["after"]) == ("pkg/a.py", 1, 2)
    assert gate.run(*check(base, "--require-base")) == (
        0,
        out(
            *head(1, 2, " (1 waived, see .suppression-relax.json)"),
            "\nPASS: suppression count unchanged",
        ),
    )


def test_ceiling_does_not_cover_a_larger_rise(gate: Gate) -> None:
    gate.source(ONE)
    base = gate.box.commit("base")
    gate.source(TWO)
    gate.run("pkg", "--relax", "pkg/a.py", "--justify", "needed", "--base-ref", base)
    gate.source(THREE)
    code, text = gate.run(*check(base, "--require-base"))
    assert code == 1
    assert "  pkg/a.py: +1 unwaived (1 -> 3)\n" in text
    assert "Current total:  3 (1 waived, see .suppression-relax.json)\n" in text


def test_merged_ceiling_is_retired(gate: Gate) -> None:
    gate.source(ONE)
    pre = gate.box.commit("base")
    gate.source(THREE)
    gate.run("pkg", "--relax", "pkg/a.py", "--justify", "needed", "--base-ref", pre)
    gate.box.commit("merge the relaxed change")
    gate.source(CLEAN)
    cleanup = gate.box.commit("cleanup")
    gate.source(TWO)
    code, text = gate.run(*check(cleanup, "--require-base"))
    assert code == 1
    assert "  pkg/a.py: +2 unwaived (0 -> 2)\n" in text
    assert "waived, see" not in text


def test_ledger_only_entry_grants_no_headroom(gate: Gate) -> None:
    gate.source(ONE)
    entry = {
        "file": "pkg/a.py",
        "ceiling": 5,
        "justify": "hand-written",
        "added_at": "2026-01-01T00:00:00Z",
    }
    (gate.box.root / ".suppression-relax.json").write_text(json.dumps([entry]))
    merged = gate.box.commit("ledger-only change")
    gate.source(TWO)
    code, text = gate.run(*check(merged, "--require-base"))
    assert code == 1
    assert "  pkg/a.py: +1 unwaived (1 -> 2)\n" in text


def test_relax_refusals(gate: Gate) -> None:
    gate.source(ONE)
    base = gate.box.commit("base")
    flags = ("--base-ref", base)
    assert gate.run("pkg", "--relax", "pkg/a.py", "--justify", " ", *flags) == (
        1,
        out("FAIL: --relax requires a non-empty --justify"),
    )
    assert gate.run("pkg", "--relax", "pkg/a.py", "--justify", "why", *flags) == (
        1,
        out("FAIL: nothing to relax for pkg/a.py (no rise)"),
    )
    gate.source(TWO)
    bad = "0" * 40
    assert gate.run(
        "pkg", "--relax", "pkg/a.py", "--justify", "w", "--base-ref", bad
    ) == (
        1,
        out(
            f"FAIL: cannot resolve comparison base for --relax (base_ref='{bad}'); "
            "nothing was relaxed"
        ),
    )
    assert gate.state(".suppression-relax.json") is None


def test_relax_fails_when_the_base_has_no_source_tree(gate: Gate) -> None:
    gate.box.write("README.md", "placeholder\n")
    base = gate.box.commit("before pkg existed")
    gate.source(ONE)
    gate.box.commit("add pkg")
    flags = ("--justify", "why", "--base-ref", base)
    assert gate.run("pkg", "--relax", "pkg/a.py", *flags) == (
        1,
        out(f"FAIL: pkg does not exist at base {base}; nothing was relaxed"),
    )
    assert gate.state(".suppression-relax.json") is None


def test_adoption_without_a_base_source_tree(gate: Gate) -> None:
    gate.box.write("README.md", "placeholder\n")
    base = gate.box.commit("before pkg existed")
    gate.source(ONE)
    assert gate.run(*check(base)) == (
        0,
        out(
            "No source tree at base and no origin/main -- first-adoption bootstrap pass"
        ),
    )
    gate.run("pkg", "--update")
    gate.box.commit("adopt")
    assert gate.run(*check(base)) == (
        1,
        out(
            "FAIL: base has no scanned source tree and origin/main is unresolvable "
            "with an in-tree baseline present; fetch origin/main"
        ),
    )
    assert gate.run(*check(base, "--tripwire")) == (
        0,
        out(
            "Base predates baseline adoption on push tripwire -- "
            "one-time bootstrap pass"
        ),
    )


def test_tip_without_the_tree_is_a_bootstrap(gate: Gate) -> None:
    gate.box.write("README.md", "placeholder\n")
    base = gate.box.commit("before pkg existed")
    gate.box.run_git("update-ref", "refs/remotes/origin/main", base)
    gate.source(ONE)
    assert gate.run(*check(base)) == (
        0,
        out(
            "No source tree at base or origin/main tip -- first-adoption bootstrap pass"
        ),
    )


def test_tip_already_carrying_the_tree_demands_a_rebase(gate: Gate) -> None:
    gate.box.write("README.md", "placeholder\n")
    base = gate.box.commit("before pkg existed")
    gate.source(ONE)
    tip = gate.box.commit("pkg lands")
    gate.box.run_git("update-ref", "refs/remotes/origin/main", tip)
    assert gate.run(*check(base)) == (
        1,
        out(
            "FAIL: base commit predates the scanned source tree; "
            "rebase onto current main"
        ),
    )


def test_tripwire_without_a_baseline_fails(gate: Gate) -> None:
    gate.box.write("README.md", "placeholder\n")
    base = gate.box.commit("before pkg existed")
    gate.source(ONE)
    assert gate.run(*check(base, "--tripwire")) == (
        1,
        out(
            "FAIL: --tripwire with no baseline on main; only the adoption commit "
            "that adds the baseline may bootstrap"
        ),
    )


def test_no_base(gate: Gate) -> None:
    gate.source(ONE)
    gate.box.commit("first")
    bad = "0" * 40
    assert gate.run(*check(bad, "--require-base")) == (
        1,
        out("FAIL: base ref unresolvable and --require-base is set"),
    )
    assert gate.run(*check(bad)) == (
        0,
        out("No base and no in-tree baseline -- first-adoption bootstrap pass"),
    )
    gate.run("pkg", "--update")
    assert gate.run(*check(bad)) == (
        1,
        out(
            "FAIL: cannot resolve merge-base (origin/main unfetched or stale) "
            "with an in-tree baseline present; fetch origin/main or pass --base-ref"
        ),
    )


def test_update_writes_the_baseline_and_audits_it(gate: Gate) -> None:
    gate.source(ONE)
    baseline = gate.box.root / ".suppression-baseline.json"
    code, text = gate.run("pkg", "--update")
    assert (code, text) == (
        0,
        out(
            f"\nBaseline updated: {baseline}",
            "  total: 1",
            "  file_level: 0",
            "  noqa: 1",
            "  per_file_ignores: 0",
            "  pylint_disable: 0",
            "  pyright_ignore: 0",
            "  type_ignore: 0",
        ),
    )
    written = json.loads(gate.state(".suppression-baseline.json") or "")
    assert written == {
        "total": 1,
        "by_category": {**CATEGORIES, "noqa": 1},
        "by_file": {"pkg/a.py": {"noqa": 1}},
        "updated_at": "T",
    }
    assert gate.audit() == [
        {"ts": "T", "total": 1, "by_category": {**CATEGORIES, "noqa": 1}}
    ]


def test_update_refuses_growth_and_writes_a_reduction(gate: Gate) -> None:
    gate.source(ONE)
    assert gate.run("pkg", "--update")[0] == 0  # first adoption bootstraps
    gate.source(TWO)
    before = gate.state(".suppression-baseline.json")
    assert gate.run("pkg", "--update") == (
        1,
        out(
            *head(1, 2),
            "\nFAIL: refusing to raise the suppression baseline by 1 "
            "(1 -> 2); update never loosens",
        ),
    )
    assert gate.state(".suppression-baseline.json") == before
    gate.source(CLEAN)
    assert gate.run("pkg", "--update")[0] == 0
    assert gate.run("pkg", "--update")[0] == 0  # an equal total rewrites
    assert len(gate.audit()) == 3


def test_rebaseline_is_audited(gate: Gate) -> None:
    gate.source(ONE)
    baseline = gate.box.root / ".suppression-baseline.json"
    assert gate.run("pkg", "--rebaseline") == (
        1,
        out("FAIL: --rebaseline requires --reason <text>"),
    )
    assert gate.run("pkg", "--rebaseline", "--reason", "reset", "--source", "PL-1") == (
        0,
        out(
            f"\nBaseline rebaselined: {baseline} (reason: reset)",
            "  total: (none) -> 1",
        ),
    )
    gate.source(THREE)
    assert gate.run("pkg", "--rebaseline", "--reason", "grow")[1].endswith(
        "  total: 1 -> 3\n"
    )
    first, second = gate.audit()
    assert (first["verdict"], first["before"], first["total"]) == (
        "rebaseline",
        None,
        1,
    )
    assert (first["reason"], first["source"]) == ("reset", "PL-1")
    assert (second["before"], second["total"]) == (1, 3)


def test_writes_are_blocked_in_ci(gate: Gate, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    gate.source(ONE)
    refusal = out(
        "FAIL: refusing to write suppression baseline under GITHUB_ACTIONS "
        "without --allow-ci-write"
    )
    assert gate.run("pkg", "--update") == (1, refusal)
    assert gate.run("pkg", "--rebaseline", "--reason", "r") == (1, refusal)
    assert gate.state(".suppression-baseline.json") is None
    assert gate.run("pkg", "--update", "--allow-ci-write")[0] == 0


def test_corrupt_state_fails_closed(gate: Gate) -> None:
    gate.source(ONE)
    base = gate.box.commit("base")
    baseline = gate.box.root / ".suppression-baseline.json"
    ledger = gate.box.root / ".suppression-relax.json"
    baseline.write_text("{ not json")
    code, text = gate.run(*check(base, "--require-base"))
    assert (
        code,
        text.startswith(f"FAIL: unreadable suppression baseline file {baseline}"),
    ) == (1, True)
    baseline.write_text("[]")
    assert gate.run(*check(base, "--require-base")) == (
        1,
        out(f"FAIL: non-dict suppression baseline file {baseline}"),
    )
    baseline.unlink()
    ledger.write_text("{}")
    assert gate.run(*check(base, "--require-base")) == (
        1,
        out(f"FAIL: non-list suppression relax ledger {ledger}"),
    )
    ledger.write_text('[{"file": "a", "ceiling": true, "justify": "", "added_at": ""}]')
    assert gate.run("pkg", "--json")[1] == out(
        f"FAIL: non-integer ceiling for 'a' in {ledger}"
    )
    ledger.write_text('[{"file": "a", "ceiling": 0, "justify": "", "added_at": ""}]')
    assert gate.run("pkg")[1] == out(f"FAIL: non-positive ceiling for 'a' in {ledger}")


def test_malformed_base_ledger_fails_closed(gate: Gate) -> None:
    gate.source(ONE)
    ledger = gate.box.root / ".suppression-relax.json"
    ledger.write_text("{ not json")
    base = gate.box.commit("bad ledger")
    ledger.write_text("[]")
    code, text = gate.run(*check(base, "--require-base"))
    assert (
        code,
        text.startswith(f"FAIL: unreadable suppression relax ledger {ledger}"),
    ) == (1, True)


def test_views_and_missing_target(gate: Gate) -> None:
    gate.source(TWO)
    code, text = gate.run("pkg")
    assert (code, text.startswith("\nTotal suppressions: 2\n")) == (0, True)
    code, text = gate.run("pkg", "--threshold")
    assert (code, "  pkg/a.py  (total: 2)\n" in text) == (0, True)
    assert json.loads(gate.run("pkg", "--json")[1])["total"] == 2
    assert gate.run("nowhere", "--check") == (1, out("not found: nowhere"))
