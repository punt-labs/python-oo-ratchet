"""Make dynamic text safe to print inside a TOML comment or a quoted string."""

from __future__ import annotations

import unicodedata

_SHORT = {
    '"': '\\"',
    "\\": "\\\\",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}
_DEL = 0x7F
_BMP = 0xFFFF


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

        Printable ASCII passes through except ``"`` and the backslash. Controls
        (DEL included) and every non-ASCII character become ``\\uXXXX``, or
        ``\\UXXXXXXXX`` above the BMP: TOML rejects the surrogate pairs that
        JSON writes for those.
        """
        return '"' + "".join(SafeText._escaped(ch) for ch in text) + '"'

    @staticmethod
    def _escaped(ch: str) -> str:
        code = ord(ch)
        if ch in _SHORT:
            return _SHORT[ch]
        if 0x20 <= code < _DEL:
            return ch
        if code > _BMP:
            return f"\\U{code:08x}"
        return f"\\u{code:04x}"

    @staticmethod
    def _char(ch: str) -> str:
        if unicodedata.category(ch) in {"Cc", "Zl", "Zp"}:
            return ch.encode("unicode_escape").decode("ascii")
        return ch
