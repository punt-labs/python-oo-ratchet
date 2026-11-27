"""The ports of the layers gate: a baseline of import edges, scoped by package."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from oo_ratchet.core.domain.edges import EdgeBook, EdgeRecord
from oo_ratchet.design.layer_config import LayerConfig
from oo_ratchet.design.layer_edges import Edge, Violation


class Survey(Protocol):
    """One package scanned under a layer config: what the tree shows."""

    @property
    def package(self) -> str:
        """Return the scanned package's name."""
        ...

    @property
    def modules(self) -> tuple[str, ...]:
        """Return the scanned module names."""
        ...

    @property
    def violations(self) -> tuple[Violation, ...]:
        """Return the edges whose source layer may not import the target layer."""
        ...

    @property
    def edges(self) -> frozenset[Edge]:
        """Return the violating edges."""
        ...

    @property
    def io_edges(self) -> frozenset[Edge]:
        """Return the domain-purity edges."""
        ...

    @property
    def unassigned(self) -> tuple[str, ...]:
        """Return the modules that match no layer."""
        ...

    @property
    def problems(self) -> tuple[str, ...]:
        """Return why the scan cannot vouch for the package."""
        ...

    @property
    def config(self) -> LayerConfig:
        """Return the layer config the scan ran under."""
        ...

    @property
    def config_path(self) -> Path | None:
        """Return the pyproject the config was read from, if one was found."""
        ...

    def under(self, config: LayerConfig) -> Survey:
        """Return the same package scanned under another layer config."""
        ...


class EdgeHistory(Protocol):
    """The repository's past: the base, its baseline and the package at it."""

    def resolve(self, ref: str | None) -> str | None:
        """Return the comparison base: ``ref``, else the merge base of main."""
        ...

    def adopted_at(self, ref: str) -> bool:
        """Return whether a layers baseline is committed at ``ref``."""
        ...

    def edges_at(self, ref: str) -> EdgeBook | None:
        """Return the baseline committed at ``ref``, ``None`` if absent."""
        ...

    def has_package(self, ref: str, package: str) -> bool:
        """Return whether the scanned package shows any trace at ``ref``."""
        ...

    def policy_at(
        self, ref: str, config_path: Path | None, *, strict: bool
    ) -> LayerConfig | None:
        """Return the layer config committed at ``ref`` where the scan read it.

        A missing config is an error under ``strict``, ``None`` otherwise.
        """
        ...

    def shared_at(self, ref: str, modules: Iterable[str], package: str) -> list[str]:
        """Return the ``modules`` that also existed at ``ref``."""
        ...

    def head(self) -> str | None:
        """Return the abbreviated HEAD commit, ``None`` outside a repo."""
        ...


class EdgeStore(Protocol):
    """The in-tree baseline: the edges last recorded."""

    @property
    def path(self) -> str:
        """Return where the baseline lives."""
        ...

    def exists(self) -> bool:
        """Return whether a baseline is present."""
        ...

    def book(self) -> EdgeBook:
        """Return the recorded edges."""
        ...

    def save(self, book: EdgeBook) -> None:
        """Replace the recorded edges."""
        ...

    def snapshot(self) -> str | None:
        """Return the file's text, ``None`` when there is no file."""
        ...

    def restore(self, text: str | None) -> None:
        """Put back what ``snapshot`` returned, deleting the file if none."""
        ...


class EdgeAudit(Protocol):
    """The append-only decision trail."""

    def append(self, record: EdgeRecord) -> None:
        """Add one record."""
        ...


class Checkout(Protocol):
    """The working tree's packages."""

    def has_package(self, name: str) -> bool:
        """Return whether a package directory ``name`` exists in the tree."""
        ...


@dataclass(frozen=True, slots=True)
class EdgePorts:
    """The four ports the layers gate's adapters fill."""

    history: EdgeHistory
    store: EdgeStore
    audit: EdgeAudit
    tree: Checkout
