"""The guide in docs/CONFIGURING.md, "Adopting Clean Architecture with oo-ratchet" stays true.

Every `oo-ratchet` command in the guide's ```bash blocks names a real gate and
only flags that gate's parser knows, and the guide covers the adoption path.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from oo_ratchet.gates import GATES

ROOT = Path(__file__).resolve().parent.parent
HEADING = "## Adopting Clean Architecture with oo-ratchet"
PLACEHOLDER_FLAGS = {"-h", "--help"}


def _guide() -> str:
    text = (ROOT / "docs" / "CONFIGURING.md").read_text(encoding="utf-8")
    start = text.find(HEADING + "\n")
    assert start != -1, f"CONFIGURING.md has no section {HEADING!r}"
    nxt = re.search(r"^## ", text[start + len(HEADING) :], re.MULTILINE)
    end = len(text) if nxt is None else start + len(HEADING) + nxt.start()
    return text[start:end]


def _commands(guide: str) -> list[list[str]]:
    commands: list[list[str]] = []
    for block in re.findall(r"```bash\n(.*?)```", guide, re.DOTALL):
        joined = block.replace("\\\n", " ")
        for line in joined.splitlines():
            words = shlex.split(line, comments=True)
            if "oo-ratchet" in words:
                commands.append(words[words.index("oo-ratchet") + 1 :])
    return commands


def _known_flags(help_text: str) -> set[str]:
    return set(re.findall(r"(?<![\w-])--?[A-Za-z][\w-]*", help_text))


def _help(gate: str, capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit):
        GATES[gate](["--help"])
    return capsys.readouterr().out


def test_guide_section_exists() -> None:
    assert _guide()


def test_guide_has_commands() -> None:
    assert len(_commands(_guide())) >= 8


def test_guide_covers_the_adoption_path() -> None:
    commands = {" ".join(words) for words in _commands(_guide())}
    joined = "\n".join(sorted(commands))
    for needle in (
        "layers src/shop/ --suggest",
        "layers src/shop/ --update",
        "--allow-config-change",
        "layers src/shop/ --check",
        "design src/shop/ --shadow-check",
        "--enforce",
        "--tripwire",
    ):
        assert needle in joined, needle


def test_guide_names_state_files_and_ci_targets() -> None:
    guide = _guide()
    for needle in (
        ".oo-layers-baseline.json",
        ".oo-layers-audit.jsonl",
        "check-layers",
        "check-design",
        "__ring__",
        "[tool.oo-ratchet.suggest]",
        "docs/architecture/b4-design-precision.md",
    ):
        assert needle in guide, needle


def test_every_guide_command_uses_real_gates_and_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for words in _commands(_guide()):
        gate = words[0]
        assert gate in GATES, words
        known = _known_flags(_help(gate, capsys))
        for word in words[1:]:
            if word.startswith("-") and word not in PLACEHOLDER_FLAGS:
                assert word in known, f"{gate}: unknown flag {word} in {words}"
