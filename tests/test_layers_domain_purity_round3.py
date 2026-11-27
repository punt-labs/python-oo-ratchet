"""Domain purity edges: guarded opens, builtins aliases, and the post-merge main run."""

from __future__ import annotations

import json

from tests.layers_repo import LayersRepo
from tests.test_layers_domain_purity_round2 import _fixed, _run

GUARD = "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n"
FLAG = "--allow-config-change"
MAIN = ("--base-ref", "HEAD~1", "--require-base", "--tripwire")
FILES = {"cli": "", "cli2": "", "domain2": ""}


def _baseline(repo: LayersRepo) -> object:
    return json.loads(repo.baseline.read_text())


def _adopt(repo: LayersRepo, domain: str) -> object:
    _fixed(repo, "app", {**FILES, "domain": domain})
    repo.commit_as_origin_main()
    assert _run(repo, "app", "--update")[0] == 0
    return _baseline(repo)


class TestBareOpenUnderTypeChecking:
    """A bare open call under TYPE_CHECKING is not an edge."""

    def test_guarded_open_is_ignored(self, repo: LayersRepo) -> None:
        assert _adopt(repo, GUARD + "    open('x')\n") == {}

    def test_unguarded_open_is_an_edge(self, repo: LayersRepo) -> None:
        got = _adopt(repo, "def f():\n    return open('x')\n")
        assert got == {"app.domain": ["builtins.open"]}


class TestBuiltinsAliasUnderTypeChecking:
    """Only a runtime ``import builtins as b`` makes ``b.open`` the builtin."""

    def test_type_only_alias_does_not_match_a_port_named_like_it(
        self, repo: LayersRepo
    ) -> None:
        body = (
            GUARD + "    import builtins as b\n\n\ndef f(b):\n    return b.open('x')\n"
        )
        assert _adopt(repo, body) == {}

    def test_runtime_alias_still_matches(self, repo: LayersRepo) -> None:
        body = "import builtins as b\n\n\ndef f():\n    return b.open('x')\n"
        assert _adopt(repo, body) == {"app.domain": ["builtins.open"]}


class TestPostMergeMainRun:
    """The documented main run, with the one-time flag, passes the merge commit."""

    def _merged(self, repo: LayersRepo, domain: str) -> None:
        """Base commit with an empty baseline, then the adopter's PR on top."""
        _adopt(repo, "X = 1\n")
        repo.commit()
        repo.write("src/app/domain.py", domain)
        assert _run(repo, "app", "--update", FLAG)[0] == 0
        repo.commit()

    def test_main_run_fails_without_the_flag(self, repo: LayersRepo) -> None:
        self._merged(repo, "import subprocess\n")
        code, out = _run(repo, "app", "--check", *MAIN)
        assert code == 1
        assert "did not" in out

    def test_main_run_passes_with_the_flag(self, repo: LayersRepo) -> None:
        self._merged(repo, "import subprocess\n")
        code, out = _run(repo, "app", "--check", *MAIN, FLAG)
        assert (code, "PASS" in out) == (0, True)

    def test_flag_still_fails_on_non_io_growth(self, repo: LayersRepo) -> None:
        self._merged(repo, "import subprocess\nimport app.cli2\n")
        repo.baseline.write_text(json.dumps({"app.domain": ["app.cli2", "subprocess"]}))
        code, out = _run(repo, "app", "--check", *MAIN, FLAG)
        assert code == 1
        assert "app.domain -> app.cli2" in out

    def test_flag_still_fails_on_an_unbaselined_io_edge(self, repo: LayersRepo) -> None:
        self._merged(repo, "import subprocess\n")
        repo.write("src/app/domain.py", "import subprocess\nimport socket\n")
        code, out = _run(repo, "app", "--check", *MAIN, FLAG)
        assert code == 1
        assert "app.domain -> socket" in out
