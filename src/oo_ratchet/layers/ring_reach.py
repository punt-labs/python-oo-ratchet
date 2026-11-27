"""How a module reaches IO: directly, or through the modules it imports."""

from __future__ import annotations

from collections import deque
from typing import Self

from .suggest_model import ModuleFacts

OPEN_CALL = "open()"
BUILTIN_OPEN = "builtins.open"


class IoReach:
    """Shortest import chain from a module to a module that does IO itself.

    The chain ends with the IO name: ``a -> b -> open()`` means ``a`` imports
    ``b`` and ``b`` calls ``open``. A module that does IO has the chain
    ``a -> json``. Only modules of the scanned package are walked; a cycle
    cannot loop, and ties break by module name so the chain is reproducible.
    """

    _facts: dict[str, ModuleFacts]

    def __new__(cls, facts: tuple[ModuleFacts, ...]) -> Self:
        self = super().__new__(cls)
        self._facts = {f.name: f for f in facts}
        return self

    def chain(self, start: str) -> str | None:
        """Return the chain from ``start`` to IO, or ``None`` when it reaches none."""
        seen = {start}
        queue: deque[tuple[str, ...]] = deque([(start,)])
        while queue:
            path = queue.popleft()
            fact = self._facts[path[-1]]
            if fact.io:
                return " -> ".join((*path, self._label(fact.io[0])))
            for target in fact.imports:
                if target in self._facts and target not in seen:
                    seen.add(target)
                    queue.append((*path, target))
        return None

    @staticmethod
    def _label(io: str) -> str:
        return OPEN_CALL if io == BUILTIN_OPEN else io
