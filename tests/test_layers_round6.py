"""Quoted git paths, unbounded export chains, and the audit lock."""

from __future__ import annotations

import fcntl
import os
import threading
from pathlib import Path

import pytest

from oo_ratchet.core.adapters.edgefiles import EdgeAuditFile
from oo_ratchet.core.adapters.packagetrees import PackageTree
from oo_ratchet.core.adapters.treeviews import WorkingTree
from oo_ratchet.core.domain.edges import EdgeRecord
from oo_ratchet.core.domain.layer_edges import Edge
from oo_ratchet.layers.scan import LayerScan
from tests.conftest import GitSandbox

QUOTED = 'weird"dir/app/__init__.py'


class TestQuotedPaths:
    """Paths git would quote are compared as real paths (NUL-separated output)."""

    def test_working_tree_sees_a_package_under_a_quoted_directory(
        self, git_sandbox: GitSandbox
    ) -> None:
        git_sandbox.write(QUOTED, "")
        git_sandbox.commit("one")
        assert WorkingTree(git_sandbox.root).has_package("app")

    def test_base_tree_sees_a_package_under_a_quoted_directory(
        self, git_sandbox: GitSandbox
    ) -> None:
        git_sandbox.write(QUOTED, "")
        sha = git_sandbox.commit("one")
        tree = PackageTree.base(sha, git_sandbox.root)
        assert tree.package_at("app")
        assert tree.path_at('weird"dir')


CARRIAGE_RETURN = "weird\rdir/app/__init__.py"


class TestExactPaths:
    """NUL-separated output keeps carriage returns and other bytes as they are."""

    def test_working_tree_keeps_a_carriage_return(
        self, git_sandbox: GitSandbox
    ) -> None:
        git_sandbox.write(CARRIAGE_RETURN, "")
        git_sandbox.commit("one")
        assert WorkingTree(git_sandbox.root).has_package("app")

    def test_base_tree_keeps_a_carriage_return(self, git_sandbox: GitSandbox) -> None:
        git_sandbox.write(CARRIAGE_RETURN, "")
        sha = git_sandbox.commit("one")
        assert PackageTree.base(sha, git_sandbox.root).path_at("weird\rdir")


class TestUndecodablePaths:
    """A filename that is not valid UTF-8 still resolves on disk (POSIX)."""

    def _write(self, root: Path) -> str:
        folder = os.fsdecode(b"weird\xffdir")
        try:
            (root / folder / "app").mkdir(parents=True)
            (root / folder / "app" / "__init__.py").write_text("")
        except OSError:
            pytest.skip("filesystem rejects non-UTF-8 names")
        return folder

    def test_working_tree_finds_the_package(self, git_sandbox: GitSandbox) -> None:
        self._write(git_sandbox.root)
        git_sandbox.commit("one")
        assert WorkingTree(git_sandbox.root).has_package("app")

    def test_base_tree_finds_the_directory(self, git_sandbox: GitSandbox) -> None:
        folder = self._write(git_sandbox.root)
        sha = git_sandbox.commit("one")
        assert PackageTree.base(sha, git_sandbox.root).path_at(folder)


class TestDeepChains:
    """Every origin is followed to a fixed point, however deep."""

    def test_a_chain_of_twelve_wildcard_packages_reaches_the_service(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.oo-ratchet.layers.kernel]\nprefixes = ["kernel"]\nimports = []\n'
            '[tool.oo-ratchet.layers.service]\nprefixes = ["service"]\nimports = []\n'
        )
        pkg = tmp_path / "src" / "app"
        pkg.mkdir(parents=True)
        (pkg / "service.py").write_text("thing = 1\n")
        (pkg / "kernel.py").write_text("from app import thing\n")
        here = pkg
        (here / "__init__.py").write_text("from .a1 import *\n")
        for level in range(1, 13):
            here = here / f"a{level}"
            here.mkdir()
            last = level == 12
            body = (
                "from app.service import *\n"
                if last
                else f"from .a{level + 1} import *\n"
            )
            (here / "__init__.py").write_text(body)
        assert Edge("app.kernel", "app.service") in LayerScan(pkg).edges


class TestAuditLock:
    """An append holds an exclusive lock on the audit file."""

    def test_append_waits_for_a_held_lock(self, tmp_path: Path) -> None:
        audit = EdgeAuditFile(tmp_path / ".oo-layers-audit.jsonl")
        path = tmp_path / ".oo-layers-audit.jsonl"
        path.write_text("")
        held = os.open(path, os.O_RDWR)
        fcntl.flock(held, fcntl.LOCK_EX)
        done = threading.Event()

        def append() -> None:
            audit.append(EdgeRecord("pass", 1, 0, frozenset(), frozenset(), None, None))
            done.set()

        worker = threading.Thread(target=append)
        worker.start()
        assert not done.wait(0.3)
        os.close(held)
        assert done.wait(5)
        worker.join()
        assert len(path.read_text().splitlines()) == 1
