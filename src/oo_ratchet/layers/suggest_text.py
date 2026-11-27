"""Make dynamic text safe to print inside a TOML comment or a quoted string."""

from __future__ import annotations

import json
import unicodedata


class SafeText:
    """Render names and explanations so they can never start a new TOML line.

    The suggestion is meant to be pasted into ``pyproject.toml``. A file name or
    script key holding a newline would otherwise end the ``#`` comment and turn
    what follows into active TOML.
    """

    @staticmethod
    def comment(text: str) -> str:
        """Return ``text`` with control characters and line breaks shown escaped."""
        return "".join(SafeText._char(ch) for ch in text)

    @staticmethod
    def quoted(text: str) -> str:
        """Return ``text`` as a TOML basic string with every control escaped.

        JSON escapes the C0 controls and, with ASCII output, every other
        non-ASCII character as ``\\uXXXX``; only DEL needs escaping by hand.
        """
        return json.dumps(text).replace("\x7f", "\\u007f")

    @staticmethod
    def _char(ch: str) -> str:
        if unicodedata.category(ch) in {"Cc", "Zl", "Zp"}:
            return ch.encode("unicode_escape").decode("ascii")
        return ch
