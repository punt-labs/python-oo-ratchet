"""Domain purity edges for file IO done through methods of Path objects."""

from __future__ import annotations

import json

import pytest

from tests.layers_repo import LayersRepo
from tests.test_layers_domain_purity_round2 import _fixed, _run


def _func(*lines: str) -> str:
    return "def f():\n" + "".join(f"    {line}\n" for line in lines)


def _attr(name: str) -> str:
    return (
        f"class C:\n    {name}: Path\n\n"
        f"    def f(self):\n        return self.{name}.read_text()"
    )


GUARD = (
    "from typing import TYPE_CHECKING\n\n"
    "if TYPE_CHECKING:\n    from pathlib import Path\n"
)
FILES = {"cli": "", "cli2": "", "domain2": ""}
DOC = (
    "class Doc:\n    def read_text(self): ...\n\n\n"
    "def f(d: Doc):\n    return d.read_text()\n"
)
EDGE = {"app.domain": ["pathlib"]}
EXTRA_FORMS = [
    _attr("source"),
    _attr("parent"),
    "def f(p: Path):\n    return p.is_junction()\n",
    _func("a = Path('x')", "b = a", "c = b", "d = c", "e = d", "return e.read_text()"),
    _func("e = d", "d = c", "c = b", "b = a", "a = Path('x')", "return e.read_text()"),
    _func("p: object = Path('x')", "return p.read_text()"),
    _func("p: Final = Path('x')", "return p.read_text()"),
    _func("if (p := Path('x')):", "    return p.read_text()"),
]


@pytest.fixture(autouse=True)
def _local_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def _adopt(repo: LayersRepo, domain: str) -> object:
    _fixed(repo, "app", {**FILES, "domain": domain})
    repo.commit_as_origin_main()
    assert _run(repo, "app", "--update")[0] == 0
    return json.loads(repo.baseline.read_text())


class TestPathMethodIsAnEdge:
    """A type-only Path import does not hide file IO done on a Path object."""

    def test_check_fails_on_read_text_of_a_typed_parameter(
        self, repo: LayersRepo
    ) -> None:
        _fixed(repo, "app", {**FILES, "domain": "X = 1\n"})
        repo.commit_as_origin_main()
        assert _run(repo, "app", "--update")[0] == 0
        repo.commit()
        repo.write(
            "src/app/domain.py",
            GUARD + "\n\ndef load(path: Path) -> str:\n    return path.read_text()\n",
        )
        code, out = _run(repo, "app", "--check")
        assert code == 1
        assert "app.domain -> pathlib" in out

    @pytest.mark.parametrize(
        "method",
        [
            "read_text()",
            "read_bytes()",
            "write_text('x')",
            "write_bytes(b'x')",
            "open()",
            "iterdir()",
            "glob('*')",
            "rglob('*')",
            "exists()",
            "is_file()",
            "is_dir()",
            "stat()",
            "mkdir()",
            "unlink()",
            "rename('y')",
            "touch()",
        ],
    )
    def test_each_io_method(self, repo: LayersRepo, method: str) -> None:
        body = GUARD + f"\n\ndef f(p: Path):\n    return p.{method}\n"
        assert _adopt(repo, body) == EDGE

    @pytest.mark.parametrize(
        "body",
        [
            "def f(p: 'Path | None'):\n    return p.read_text()\n",
            "def f(p: Path | None):\n    return p.read_text()\n",
            "def f(p: Path):\n    return (p / 'a').read_text()\n",
            "def f(p: Path):\n    return p.parent.read_text()\n",
            "def f(p: Path):\n    q = p.with_suffix('.x')\n    return q.read_text()\n",
            "def f(p: Path):\n    return p.resolve().is_file()\n",
            "def f(p: Path):\n    return p.joinpath('a').exists()\n",
            "class C:\n    _p: Path\n\n    def f(self):\n        return self._p.stat()",
            *EXTRA_FORMS,
        ],
    )
    def test_evidence_forms(self, repo: LayersRepo, body: str) -> None:
        assert _adopt(repo, GUARD + "\n\n" + body) == EDGE

    def test_import_pathlib_module_form(self, repo: LayersRepo) -> None:
        body = (
            "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n"
            "    import pathlib\n\n\n"
            "def f(p: pathlib.Path):\n    return p.read_text()\n"
        )
        assert _adopt(repo, body) == EDGE

    def test_call_of_path_class_is_evidence(self, repo: LayersRepo) -> None:
        body = GUARD + "\n\ndef f(x):\n    return Path(x).read_text()\n"
        assert _adopt(repo, body) == EDGE


class TestNoFalsePositives:
    """Methods on objects with no Path evidence are not file IO."""

    @pytest.mark.parametrize(
        "body",
        [
            DOC,
            "def f(p):\n    return p.read_text()\n",
            "def f(p: object):\n    return p.exists()\n",
            "def f(p: Path):\n    return p.name, p.suffix, p / 'y'\n",
            "def f(p: Path):\n    return str(p)\n",
            "def f(path: str):\n    return path.rename\n",
        ],
    )
    def test_ignored(self, repo: LayersRepo, body: str) -> None:
        assert _adopt(repo, GUARD + "\n\n" + body) == {}

    def test_attribute_of_another_object_is_not_a_path(self, repo: LayersRepo) -> None:
        body = (
            GUARD + "\n\nclass A:\n    source: Path\n\n\n"
            "def f(document):\n    return document.source.read_text()\n"
        )
        assert _adopt(repo, body) == {}

    def test_call_under_type_checking_is_ignored(self, repo: LayersRepo) -> None:
        body = GUARD + "    P = Path('x').read_text()\n"
        assert _adopt(repo, body) == {}

    def test_other_layers_are_not_checked(self, repo: LayersRepo) -> None:
        cli = GUARD + "\n\ndef f(p: Path):\n    return p.read_text()\n"
        _fixed(repo, "app", {**FILES, "domain": "X = 1\n", "cli": cli})
        repo.commit_as_origin_main()
        assert _run(repo, "app", "--update")[0] == 0
        assert json.loads(repo.baseline.read_text()) == {}
