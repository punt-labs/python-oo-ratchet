"""Unit tests for the in-tree baseline load/query."""

from __future__ import annotations

from pathlib import Path

import pytest

from oo_ratchet.core.adapters.oostore import OoBaselineStore
from oo_ratchet.core.domain.errors import StateError

FILENAME = ".oo-baseline.json"


class TestBaselineLoad:
    """Loading is fail-closed but readable on a corrupt file."""

    def test_absent_file_is_empty(self, tmp_path: Path) -> None:
        store = OoBaselineStore(tmp_path / FILENAME)
        assert store.rows() == {}
        assert store.exists() is False

    def test_valid_file_loads(self, tmp_path: Path) -> None:
        (tmp_path / FILENAME).write_text('{"a.py": {"module_size": 3.0}}')
        assert OoBaselineStore(tmp_path / FILENAME).rows()["a.py"] == {
            "module_size": 3.0
        }

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("{ not valid json", "unreadable baseline file"),
            # A list is valid JSON but not an object: a controlled error, not an
            # AttributeError on .get() downstream.
            ("[1, 2, 3]", "non-dict baseline file"),
            # {"a.py": "garbage"} passes the top-level check but the value is not
            # a metric dict; without the nested guard `metric not in "garbage"` is
            # a substring test that skips every metric -> fail-OPEN.
            ('{"a.py": "garbage"}', "non-dict entry in baseline file"),
            # A bool is an int subclass that would compare as 0/1: fail-open.
            ('{"a.py": {"module_size": true}}', "non-numeric metric"),
            # A string would raise TypeError in the numeric comparison.
            ('{"a.py": {"module_size": "5"}}', "non-numeric metric"),
        ],
    )
    def test_corrupt_file_raises_state_error(
        self, tmp_path: Path, content: str, message: str
    ) -> None:
        (tmp_path / FILENAME).write_text(content)
        with pytest.raises(StateError, match=message):
            OoBaselineStore(tmp_path / FILENAME).rows()

    def test_non_utf8_file_raises_state_error(self, tmp_path: Path) -> None:
        # A non-UTF8 baseline file raises UnicodeDecodeError on read_text; the
        # store must turn it into the typed error, not a traceback.
        (tmp_path / FILENAME).write_bytes(b"\xff\xfe\x00")
        with pytest.raises(StateError, match="unreadable baseline file"):
            OoBaselineStore(tmp_path / FILENAME).rows()
