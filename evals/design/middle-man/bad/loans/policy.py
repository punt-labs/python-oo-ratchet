"""Library-loan design evaluation fixture."""

from __future__ import annotations


class FeePolicy:
    def __init__(self, rate: int) -> None:
        self._rate = rate

    def fee(self, days: int) -> int:
        return days * self._rate

    def refundable(self, paid: int) -> int:
        return max(0, paid - self._rate)


class LoanFacade:
    def __init__(self, policy: FeePolicy) -> None:
        self._policy = policy

    def fee(self, days: int) -> int:
        return self._policy.fee(days)

    def refundable(self, paid: int) -> int:
        return self._policy.refundable(paid)
