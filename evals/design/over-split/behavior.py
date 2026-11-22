"""Library-loan design evaluation fixture."""

from __future__ import annotations

import importlib
import sys
from typing import Protocol, cast


class LoanApi(Protocol):
    def quote(self, days: int) -> int: ...


def check() -> None:
    """The same observable contract must hold for either isolated package."""
    sys.path.insert(0, sys.argv[1])
    api = cast("LoanApi", importlib.import_module("loans.api"))
    for days in (0, 1, 3, 6, 8, 20, 4_999, 5_000, 5_001, 6_000):
        actual = api.quote(days)
        if actual != min(days * 2, 10_000):
            raise AssertionError((days, actual))
    try:
        api.quote(-1)
    except ValueError as error:
        if str(error) != "days must be nonnegative":
            raise AssertionError(str(error)) from error
    else:
        raise AssertionError("negative loan duration accepted")


if __name__ == "__main__":
    check()
