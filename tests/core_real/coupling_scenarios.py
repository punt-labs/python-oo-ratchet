"""The coupling gate scenarios: each is a short script over a real repository.

Every scenario builds its own history, then runs the gate through its CLI. The
runs are recorded (see ``coupling_play``); a scenario asserts nothing itself.
"""

from __future__ import annotations

from collections.abc import Callable

from tests.core_real.coupling_play import BROKEN, HEADER, HIGH, HIGHER, LOW, Play

Scenario = Callable[[Play], None]
CHECK = ("pkg", "--check", "--base-ref", "base", "--require-base")


def _base(p: Play, text: str = LOW) -> None:
    """Commit ``pkg/a.py`` with a seeded baseline and tag the commit ``base``."""
    p.write("pkg/a.py", text).seed().commit("base").tag("base")


def _hub(p: Play, imports: int) -> None:
    p.write("pkg/__init__.py", "")
    for i in range(13):
        p.write(f"pkg/m{i}.py", f"{HEADER}VALUE = {i}\n")
    body = "".join(f"from . import m{i}\n" for i in range(imports))
    p.write("pkg/hub.py", f"{HEADER}{body}")


def _caps(p: Play, cap: int = 20) -> None:
    row = f'"pkg/hub.py" = {{ efferent_coupling = {cap} }}'
    table = f"[tool.oo-ratchet.coupling.caps]\n{row}\n"
    p.write("pyproject.toml", table)


def check_regression(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", HIGH).commit("regress")
    p.run(*CHECK)


def check_improvement(p: Play) -> None:
    _base(p, HIGH)
    p.write("pkg/a.py", LOW).commit("improve")
    p.run(*CHECK)


def check_unchanged(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", LOW + "# comment\n").commit("touch")
    p.run(*CHECK)


def check_new_file_is_info(p: Play) -> None:
    _base(p)
    p.write("pkg/new.py", HIGHER).commit("add")
    p.run(*CHECK)


def check_no_python_touched(p: Play) -> None:
    _base(p)
    p.write("notes.txt", "x\n").commit("notes")
    p.run(*CHECK)


def check_regression_in_earlier_commit(p: Play) -> None:
    p.write("pkg/a.py", LOW).write("pkg/b.py", LOW).seed().commit("fork").tag("base")
    p.checkout_new("feature")
    p.write("pkg/a.py", HIGH).commit("regress a")
    p.write("pkg/b.py", LOW + "# x\n").commit("touch b")
    p.run(*CHECK)


def check_laundered_in_tree_baseline(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", HIGH).seed().commit("regress and launder")
    p.run(*CHECK)


def check_parse_error(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", BROKEN).commit("break")
    p.run(*CHECK)


def check_rename_carries_regression(p: Play) -> None:
    _base(p)
    p.move("pkg/a.py", "pkg/b.py").write("pkg/b.py", HIGH).commit("rename and worsen")
    p.run(*CHECK)


def check_rename_unchanged(p: Play) -> None:
    _base(p)
    p.move("pkg/a.py", "pkg/b.py").commit("rename")
    p.run(*CHECK)


def check_metric_missing_from_base_row(p: Play) -> None:
    p.write("pkg/a.py", HIGH)
    p.write(".oo-coupling-baseline.json", '{"pkg/a.py": {"public_names": 2}}\n')
    p.commit("base").tag("base")
    p.write("pkg/a.py", HIGH + "# c\n").commit("touch")
    p.run(*CHECK)


def check_empty_base_baseline(p: Play) -> None:
    p.write("pkg/a.py", LOW).write(".oo-coupling-baseline.json", "{}\n")
    p.commit("base").tag("base")
    p.write("pkg/a.py", HIGH).commit("change")
    p.run(*CHECK)
    p.run("pkg", "--check", "--base-ref", "base")


def check_empty_base_baseline_parse(p: Play) -> None:
    p.write("pkg/a.py", LOW).write(".oo-coupling-baseline.json", "{}\n")
    p.commit("base").tag("base")
    p.write("pkg/a.py", BROKEN).commit("break")
    p.run("pkg", "--check", "--base-ref", "base")


def check_base_unresolvable(p: Play) -> None:
    _base(p)
    p.run("pkg", "--check", "--base-ref", "nope", "--require-base")
    p.run("pkg", "--check", "--base-ref", "nope")


def check_no_origin_main(p: Play) -> None:
    _base(p)
    p.run("pkg", "--check")
    p.run("pkg", "--check", "--require-base")


def check_first_adoption(p: Play) -> None:
    p.write("pkg/a.py", LOW).commit("no baseline")
    p.run("pkg", "--check")
    p.run("pkg", "--check", "--require-base")


def check_base_without_baseline(p: Play) -> None:
    p.write("pkg/a.py", LOW).commit("pre-adoption").tag("base")
    p.seed().write("pkg/a.py", HIGH).commit("adopt")
    p.run("pkg", "--check", "--base-ref", "base")
    p.origin_main()
    p.run("pkg", "--check", "--base-ref", "base")
    p.run("pkg", "--check", "--base-ref", "base", "--tripwire")


def check_base_without_baseline_and_tip(p: Play) -> None:
    p.write("pkg/a.py", LOW).commit("pre-adoption").tag("base").origin_main()
    p.seed().commit("adopt")
    p.git("update-ref", "refs/remotes/origin/main", p.git("rev-parse", "base").strip())
    p.run("pkg", "--check", "--base-ref", "base")


def check_tripwire_without_baseline(p: Play) -> None:
    p.write("pkg/a.py", LOW).commit("pre-adoption").tag("base")
    p.run("pkg", "--check", "--base-ref", "base", "--tripwire")


def check_relaxed_regression_is_waived(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", HIGH)
    p.setup("pkg", "--relax", "pkg/a.py", "--justify", "debt", "--allow-ci-write")
    p.commit("relax")
    p.run(*CHECK)


def check_relaxed_regression_in_base_log_is_history(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", HIGH)
    p.setup("pkg", "--relax", "pkg/a.py", "--justify", "debt", "--allow-ci-write")
    p.commit("relax").tag("mid")
    p.write("pkg/a.py", HIGHER).seed().commit("worse and re-lock")
    p.run("pkg", "--check", "--base-ref", "mid", "--require-base")


def check_relax_does_not_waive_other_metric(p: Play) -> None:
    _hub(p, 9)
    p.seed().commit("base").tag("base")
    _hub(p, 12)
    p.setup("pkg", "--relax", "pkg/hub.py", "--justify", "j", "--allow-ci-write")
    p.write(
        "pkg/hub.py",
        HEADER
        + "".join(f"from . import m{i}\n" for i in range(12))
        + "__all__ = "
        + repr([f"n{i}" for i in range(20)])
        + "\n",
    )
    p.commit("relax")
    p.run(*CHECK)


def check_corrupt_in_tree_baseline(p: Play) -> None:
    _base(p)
    p.write(".oo-coupling-baseline.json", "{not json")
    p.run_state_error(*CHECK)
    p.run_state_error("pkg", "--json")
    p.write(".oo-coupling-baseline.json", '{"pkg/a.py": []}')
    p.run_state_error(*CHECK)
    p.write(".oo-coupling-baseline.json", '{"pkg/a.py": {"public_names": true}}')
    p.run_state_error(*CHECK)
    p.write(".oo-coupling-baseline.json", "[]")
    p.run_state_error("pkg", "--update", "--allow-ci-write")


def check_corrupt_base_baseline(p: Play) -> None:
    p.write("pkg/a.py", LOW).write(".oo-coupling-baseline.json", "{oops")
    p.commit("base").tag("base")
    p.seed().write("pkg/a.py", HIGH).commit("fix")
    p.run_state_error(*CHECK)


def check_malformed_audit(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", HIGH).commit("regress")
    p.write(".oo-coupling-audit.jsonl", "not json\n")
    p.run_state_error(*CHECK)


def check_not_found_target(p: Play) -> None:
    _base(p)
    p.run("nope", "--check")


def check_ci_env_is_irrelevant(p: Play) -> None:
    _base(p)
    p.env("GITHUB_ACTIONS", "true")
    p.write("pkg/a.py", HIGH).commit("regress")
    p.run(*CHECK)


def update_writes_improvement(p: Play) -> None:
    _base(p, HIGH)
    p.write("pkg/a.py", LOW)
    p.run(
        "pkg", "--update", "--base-ref", "base", "--allow-ci-write", "--source", "PL-1"
    )


def update_refuses_regression(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", HIGH)
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_refuses_in_tree_loosening_that_beats_base(p: Play) -> None:
    _base(p, HIGHER)
    p.write("pkg/a.py", LOW).seed().commit("tighten")
    p.write("pkg/a.py", HIGH)
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_ignores_row_rewritten_outside_the_diff(p: Play) -> None:
    p.write("pkg/a.py", LOW).write("pkg/b.py", LOW).seed().commit("base").tag("base")
    p.write(
        ".oo-coupling-baseline.json",
        '{"pkg/a.py": {"public_names": 5}, "pkg/b.py": {"public_names": 1}}\n',
    )
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_metric_missing_from_in_tree_row(p: Play) -> None:
    p.write("pkg/a.py", HIGHER)
    p.write(".oo-coupling-baseline.json", '{"pkg/a.py": {"public_names": 3}}\n')
    p.commit("base").tag("base")
    p.write("pkg/a.py", HIGHER + "# c\n")
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_new_file_counts_as_improved(p: Play) -> None:
    _base(p)
    p.write("pkg/new.py", HIGH).commit("add")
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_backfills_a_missing_row(p: Play) -> None:
    p.write("pkg/a.py", LOW).write("pkg/b.py", LOW).seed()
    p.write(".oo-coupling-baseline.json", '{"pkg/a.py": {"public_names": 1}}\n')
    p.commit("base").tag("base")
    p.write("pkg/a.py", LOW + "# c\n")
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_drops_a_deleted_file(p: Play) -> None:
    p.write("pkg/a.py", LOW).write("pkg/b.py", LOW).seed().commit("base").tag("base")
    p.remove("pkg/b.py")
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_drops_a_file_created_and_deleted_in_the_branch(p: Play) -> None:
    _base(p)
    p.write("pkg/gone.py", LOW).seed().commit("add and baseline")
    p.remove("pkg/gone.py").commit("delete")
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_carries_a_rename(p: Play) -> None:
    _base(p)
    p.move("pkg/a.py", "pkg/b.py").write("pkg/b.py", HIGH).commit("rename and worsen")
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")
    p.write("pkg/b.py", LOW)
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_rename_improves(p: Play) -> None:
    _base(p, HIGH)
    p.move("pkg/a.py", "pkg/b.py").write("pkg/b.py", LOW).commit("rename and improve")
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_keeps_a_row_when_a_file_does_not_parse(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", BROKEN)
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def update_unresolvable_base(p: Play) -> None:
    _base(p)
    p.run("pkg", "--update", "--base-ref", "nope", "--allow-ci-write")
    p.run("pkg", "--update", "--base-ref", "nope", "--require-base", "--allow-ci-write")


def update_first_adoption_sweeps_the_tree(p: Play) -> None:
    p.write("pkg/a.py", LOW).write("pkg/b.py", HIGH).commit("no baseline")
    p.run("pkg", "--update", "--base-ref", "nope", "--allow-ci-write")


def update_first_adoption_with_a_parse_error(p: Play) -> None:
    p.write("pkg/a.py", LOW).write("pkg/b.py", BROKEN).commit("no baseline")
    p.run("pkg", "--update", "--base-ref", "nope", "--allow-ci-write")


def update_refused_under_ci(p: Play) -> None:
    _base(p)
    p.env("GITHUB_ACTIONS", "true")
    p.run("pkg", "--update", "--base-ref", "base")
    p.run("pkg", "--update", "--base-ref", "base", "--allow-ci-write")


def relax_succeeds_and_records_only_the_loosened_metric(p: Play) -> None:
    _base(p)
    p.write("pkg/a.py", HIGH)
    p.run(
        "pkg",
        "--relax",
        "pkg/a.py",
        "--justify",
        "debt",
        "--source",
        "PL-9",
        "--allow-ci-write",
    )


def relax_refusals(p: Play) -> None:
    _base(p)
    p.run("pkg", "--relax", "pkg/a.py", "--justify", " ", "--allow-ci-write")
    p.run("pkg", "--relax", "pkg/zzz.py", "--justify", "j", "--allow-ci-write")
    p.run("pkg", "--relax", "pkg/a.py", "--justify", "j", "--allow-ci-write")
    p.write("pkg/new.py", LOW)
    p.run("pkg", "--relax", "pkg/new.py", "--justify", "j", "--allow-ci-write")
    p.run("pkg", "--relax", "pkg/a.py", "--justify", "j")
    p.env("GITHUB_ACTIONS", "true")
    p.run("pkg", "--relax", "pkg/a.py", "--justify", "j")


def rebaseline_records_changes(p: Play) -> None:
    p.write("pkg/a.py", LOW).write("pkg/b.py", HIGH).write("pkg/c.py", LOW).seed()
    p.write("pkg/a.py", HIGH).write("pkg/b.py", LOW).remove("pkg/c.py").write(
        "pkg/d.py", LOW
    )
    p.run(
        "pkg",
        "--rebaseline",
        "--allow-ci-write",
        "--reason",
        " why ",
        "--source",
        "PL-2",
    )
    p.run("pkg", "--rebaseline", "--allow-ci-write")


def rebaseline_refused_under_ci(p: Play) -> None:
    p.write("pkg/a.py", LOW)
    p.env("GITHUB_ACTIONS", "true")
    p.run("pkg", "--rebaseline")
    p.run("pkg", "--rebaseline", "--allow-ci-write", "--reason", "r")


def bless_within_cap(p: Play) -> None:
    _hub(p, 11)
    _caps(p)
    p.seed().commit("base").tag("base")
    _hub(p, 12)
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/hub.py",
        "--reason",
        "hub grows",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )
    p.commit("bless")
    p.run(*CHECK)


def bless_over_default_cap_is_refused(p: Play) -> None:
    _hub(p, 11)
    p.seed().commit("base").tag("base")
    _hub(p, 12)
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/hub.py",
        "--reason",
        "r",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )
    p.run(
        "pkg", "--rebaseline-files", "pkg/hub.py", "--reason", "r", "--allow-ci-write"
    )


def bless_over_the_path_cap_is_refused(p: Play) -> None:
    _hub(p, 11)
    _caps(p, 12)
    p.seed().commit("base").tag("base")
    _hub(p, 13)
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/hub.py",
        "--reason",
        "r",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )


def bless_judges_against_the_base_row_not_the_in_tree_row(p: Play) -> None:
    _hub(p, 11)
    p.seed().commit("base").tag("base")
    _hub(p, 12)
    p.seed()
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/hub.py",
        "--reason",
        "r",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )
    p.run(
        "pkg", "--rebaseline-files", "pkg/hub.py", "--reason", "r", "--allow-ci-write"
    )


def bless_an_unregressed_over_cap_file(p: Play) -> None:
    _hub(p, 11)
    p.seed().commit("base").tag("base")
    p.write("pkg/m0.py", f"{HEADER}VALUE = 100\n")
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/hub.py",
        "--reason",
        "r",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )


def bless_a_renamed_file_drops_the_old_row(p: Play) -> None:
    _hub(p, 11)
    _caps(p)
    p.seed().commit("base").tag("base")
    p.move("pkg/hub.py", "pkg/wiring.py")
    p.write(
        "pkg/wiring.py", HEADER + "".join(f"from . import m{i}\n" for i in range(12))
    )
    p.write(
        "pyproject.toml",
        "[tool.oo-ratchet.coupling.caps]\n"
        '"pkg/wiring.py" = { efferent_coupling = 20 }\n',
    )
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/wiring.py",
        "--reason",
        "r",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )
    p.commit("rename and bless")
    p.run(*CHECK)


def bless_argument_errors(p: Play) -> None:
    _base(p)
    p.run("pkg", "--rebaseline-files", ",", "--reason", "r", "--allow-ci-write")
    p.run("pkg", "--rebaseline-files", "pkg/a.py", "--reason", " ", "--allow-ci-write")
    p.run("pkg", "--rebaseline-files", "pkg/a.py", "--allow-ci-write")
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/missing.py",
        "--reason",
        "r",
        "--allow-ci-write",
    )
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/a.py",
        "--reason",
        "r",
        "--base-ref",
        "nope",
        "--allow-ci-write",
    )
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/a.py",
        "--reason",
        "r",
        "--require-base",
        "--base-ref",
        "nope",
        "--allow-ci-write",
    )
    p.env("GITHUB_ACTIONS", "true")
    p.run("pkg", "--rebaseline-files", "pkg/a.py", "--reason", "r")


def bless_needs_a_base_baseline_under_require_base(p: Play) -> None:
    p.write("pkg/a.py", LOW).commit("no baseline").tag("base")
    p.seed()
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/a.py",
        "--reason",
        "r",
        "--base-ref",
        "base",
        "--require-base",
        "--allow-ci-write",
    )
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/a.py",
        "--reason",
        "r",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )


def bless_spellings_and_duplicates(p: Play) -> None:
    _base(p, HIGH)
    p.write("pkg/a.py", LOW)
    p.run(
        "pkg",
        "--rebaseline-files",
        "./pkg/a.py,pkg/a.py,pkg//a.py",
        "--reason",
        "r",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )


def bless_from_a_subdirectory(p: Play) -> None:
    _base(p, HIGH)
    p.write("pkg/a.py", LOW)
    p.chdir("pkg")
    p.run(
        "../pkg",
        "--rebaseline-files",
        "a.py",
        "--reason",
        "r",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )
    p.run(
        "../pkg",
        "--rebaseline-files",
        str(p.root / "pkg" / "a.py"),
        "--reason",
        "r",
        "--allow-ci-write",
    )


def bless_records_gains_and_waivers(p: Play) -> None:
    p.write("pkg/a.py", LOW).write("pkg/b.py", HIGH).seed().commit("base").tag("base")
    p.write("pkg/a.py", HIGH).write("pkg/b.py", LOW)
    p.run(
        "pkg",
        "--rebaseline-files",
        "pkg/a.py,pkg/b.py",
        "--reason",
        "mixed",
        "--base-ref",
        "base",
        "--allow-ci-write",
    )


def _main_module(p: Play, names: int) -> None:
    listed = repr([f"n{i}" for i in range(names)])
    p.write("pkg/__main__.py", f"{HEADER}__all__ = {listed}\n")


def main_module_has_relaxed_targets(p: Play) -> None:
    _main_module(p, 90)
    p.seed().commit("base").tag("base")
    _main_module(p, 99)
    bless = ("pkg", "--rebaseline-files", "pkg/__main__.py", "--reason", "r")
    p.run(*bless, "--base-ref", "base", "--allow-ci-write")
    _main_module(p, 101)
    p.run(*bless, "--base-ref", "base", "--allow-ci-write")


def views(p: Play) -> None:
    _base(p)
    p.write("pkg/b.py", HIGH)
    p.run("pkg")
    p.run("pkg", "--threshold")
    p.run("pkg", "--json")
    p.run("pkg", "--log")
    p.write("pkg/c.py", BROKEN)
    p.run("pkg", "--json")


def log_views(p: Play) -> None:
    p.write("pkg/a.py", LOW)
    p.run("pkg", "--log")
    p.seed()
    p.run("pkg", "--log")
    p.write(".oo-coupling-audit.jsonl", '{"verdict":"x"}\n\n[1]\n')
    p.run("pkg", "--log")
    p.write(".oo-coupling-audit.jsonl", "garbage\n")
    p.run("pkg", "--log")


def config_errors(p: Play) -> None:
    _base(p)
    p.write("pyproject.toml", "[tool.oo-ratchet.coupling]\nbogus = 1\n")
    p.run(*CHECK)
    p.write("pyproject.toml", "not = [toml")
    p.run(*CHECK)


def argument_errors(p: Play) -> None:
    _base(p)
    p.run("pkg", "--check", "--update")
    p.run("pkg", "--nonsense")


SCENARIOS: dict[str, Scenario] = {
    name: fn
    for name, fn in sorted(globals().items())
    if callable(fn)
    and fn.__module__ == __name__
    and not name.startswith("_")
    and name not in {"Scenario"}
}
