"""The README follows the Punt Labs README standard and every doc link resolves."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
DOCS = sorted((ROOT / "docs").glob("*.md"))
GUIDES = ("CONFIGURING.md", "REFERENCE.md", "LAYERS.md", "DESIGN.md")
REQUIRED = [
    "Quick Start",
    "Features",
    "What It Looks Like",
    "Commands",
    "Setup",
    "Documentation",
    "License",
]
SMALL_WORDS = frozenset(
    {"a", "an", "and", "as", "at", "for", "in", "it", "of", "on", "or", "the", "to"}
    | {"with"}
)
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
ANY_LINK = re.compile(r"\]\(([^)\s]+)\)")
BLOB = "https://github.com/punt-labs/python-oo-ratchet/blob/main/"
FENCE = re.compile(r"```\w*\n(.*?)```", re.DOTALL)


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _h2(path: Path) -> list[str]:
    return [ln[3:] for ln in _lines(path) if ln.startswith("## ")]


def _section(path: Path, heading: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index(f"## {heading}\n")
    nxt = re.search(r"^## ", text[start + 3 :], re.MULTILINE)
    return text[start:] if nxt is None else text[start : start + 3 + nxt.start()]


def _slug(heading: str) -> str:
    slug = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return slug.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    in_fence = False
    anchors: set[str] = set()
    for line in _lines(path):
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and (m := re.match(r"#{1,6} (.+)", line)):
            anchors.add(_slug(m.group(1)))
    return anchors


def test_readme_is_short() -> None:
    assert len(_lines(README)) <= 220


def test_required_sections_in_order() -> None:
    headings = _h2(README)
    positions = [headings.index(name) for name in REQUIRED]
    assert positions == sorted(positions)


def test_headings_are_title_case() -> None:
    for heading in _h2(README):
        for i, word in enumerate(heading.split()):
            if i and word.lower() in SMALL_WORDS:
                continue
            assert word[0].isupper() or not word[0].isalpha(), heading


def test_no_development_section() -> None:
    for heading in _h2(README):
        assert heading not in {"Development", "Develop", "Contributing"}


def test_badges_follow_the_standard() -> None:
    top = "\n".join(_lines(README)[:12])
    names = re.findall(r"!\[(\w+)\]", top)
    assert names == ["License", "CI", "PyPI", "Python"]
    assert "/ci.yml?label=CI" in top
    assert "pypi/v/punt-oo-ratchet" in top


def test_quick_start_blocks_are_one_line() -> None:
    blocks = FENCE.findall(_section(README, "Quick Start"))
    assert blocks
    for block in blocks:
        assert len(block.strip().splitlines()) == 1, block


def test_readme_links_the_docs() -> None:
    text = README.read_text(encoding="utf-8")
    for target in ("docs/CONFIGURING.md", "docs/REFERENCE.md", "CONTRIBUTING.md"):
        assert f"]({BLOB}{target})" in text, target
    assert f"]({BLOB}CONTRIBUTING.md)" in _section(README, "Documentation")


def test_contributing_has_one_line_blocks() -> None:
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    blocks = FENCE.findall(text)
    assert blocks
    for block in blocks:
        assert len(block.strip().splitlines()) == 1, block


def test_docs_have_a_table_of_contents() -> None:
    for name in GUIDES:
        head = "\n".join(_lines(ROOT / "docs" / name)[:20])
        assert "Contents" in head, name


def _repo_file(path: Path, target: str) -> tuple[Path, str] | None:
    """The repo file and anchor a link names, or None for an external link."""
    if target.startswith(BLOB):
        target = target[len(BLOB) :]
        base = ROOT
    elif re.match(r"[a-z]+:", target):
        return None
    else:
        base = path.parent
    file_part, _, anchor = target.partition("#")
    return ((base / file_part).resolve() if file_part else path), anchor


def _check_link(path: Path, target: str) -> None:
    found = _repo_file(path, target)
    if found is None:
        return
    dest, anchor = found
    assert dest.exists(), f"{path.name}: {target}"
    if anchor and dest.suffix == ".md":
        assert anchor in _anchors(dest), f"{path.name}: {target}"


def test_readme_links_to_repo_files_are_absolute() -> None:
    """PyPI renders README.md as the long description; relative links break."""
    for target in ANY_LINK.findall(README.read_text(encoding="utf-8")):
        assert re.match(r"https://", target), f"README.md: relative link {target}"
        _check_link(README, target)


@pytest.mark.parametrize(
    "target",
    [
        BLOB + "docs/nope.md",
        BLOB + "docs/CONFIGURING.md#no-such-heading",
    ],
)
def test_broken_absolute_links_fail(target: str) -> None:
    with pytest.raises(AssertionError):
        _check_link(README, target)


@pytest.mark.parametrize(
    "target",
    [
        BLOB + "docs/CONFIGURING.md",
        BLOB + "docs/REFERENCE.md#baseline-and-audit-formats",
    ],
)
def test_good_absolute_links_pass(target: str) -> None:
    _check_link(README, target)


@pytest.mark.parametrize("path", [README, *DOCS], ids=lambda p: p.name)
def test_relative_links_resolve(path: Path) -> None:
    in_fence = False
    for line in _lines(path):
        if line.startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        for target in LINK.findall(line):
            _check_link(path, target)
