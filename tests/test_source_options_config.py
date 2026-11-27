"""Reading `[tool.oo-ratchet]` stops at the checkout root."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from oo_ratchet.source_options import SourceOptions

OUTER_CONFIG = '[tool.oo-ratchet]\nnamespace = "app"\nroots = ["src/app"]\n'


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    SourceOptions.add(parser)
    return SourceOptions.parse(parser, argv)


def _outer_and_inner(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(OUTER_CONFIG, encoding="utf-8")
    (tmp_path / "src/app").mkdir(parents=True)
    (tmp_path / "src/app/mod.py").write_text("", encoding="utf-8")
    inner = tmp_path / "inner"
    inner.mkdir()
    return inner


def test_config_above_a_git_directory_is_not_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = _outer_and_inner(tmp_path)
    (inner / ".git").mkdir()
    monkeypatch.chdir(inner)
    with pytest.raises(SystemExit) as excinfo:
        _parse([])
    assert excinfo.value.code == 2


def test_config_above_a_git_file_is_not_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = _outer_and_inner(tmp_path)
    (inner / ".git").write_text("gitdir: ../elsewhere\n", encoding="utf-8")
    monkeypatch.chdir(inner)
    with pytest.raises(SystemExit) as excinfo:
        _parse([])
    assert excinfo.value.code == 2


def test_config_is_found_without_a_git_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = _outer_and_inner(tmp_path)
    monkeypatch.chdir(inner)
    src = _parse([]).src
    assert src.namespace == "app"


def test_config_beside_the_git_directory_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outer_and_inner(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path / "inner")
    src = _parse([]).src
    assert src.namespace == "app"
