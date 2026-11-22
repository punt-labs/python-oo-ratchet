"""Fee constants exposed as a bag of stateless functions."""

from __future__ import annotations


class FeeRules:
    @staticmethod
    def daily_rate() -> int:
        return 2

    @staticmethod
    def maximum_fee() -> int:
        return 10_000
