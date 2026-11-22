"""Library-loan design evaluation fixture."""

from __future__ import annotations

from .register import Register


def quote(days: int) -> int:
    if days < 0:
        raise ValueError("days must be nonnegative")
    register = Register()
    register.identify("reader")
    register.contact("reader@example.org")
    register.extend(days)
    return register.fee()
