"""The layers gate's command surface: verdict reports."""

from __future__ import annotations

from typing import ClassVar

from oo_ratchet.core.domain.edges import EdgeVerdict
from oo_ratchet.core.domain.verdicts import Failure
from oo_ratchet.design.layer_edges import Edge


class EdgeCli:
    """Render an ``EdgeVerdict`` as report lines and an exit code."""

    MESSAGES: ClassVar[dict[str, str]] = {
        "base-unresolvable": "base ref unresolvable and --require-base is set",
        "base-stale": (
            "cannot resolve merge-base (origin/main unfetched or stale) "
            "with an in-tree baseline present; fetch origin/main or pass --base-ref"
        ),
        "tripwire-no-baseline": (
            "--tripwire with no baseline on main; only the "
            "adoption commit that adds the baseline may bootstrap"
        ),
        "tip-unresolvable": (
            "base has no baseline and origin/main is unresolvable "
            "with an in-tree baseline present; fetch origin/main"
        ),
        "base-predates-baseline": (
            "base commit predates baseline adoption; rebase onto current main"
        ),
        "tree-no-baseline": (
            "the base has a layers baseline but the tree has none; "
            "restore it or run --update"
        ),
        "ci-write": (
            "refusing to write layers baseline under GITHUB_ACTIONS "
            "without --allow-ci-write"
        ),
    }
    TITLES: ClassVar[dict[str, str]] = {
        "new-violations": "layer violations not in the baseline:",
        "stale-entries": "baseline entries that no longer violate (--update):",
        "baseline-grown": "baseline holds edges the base {0} did not:",
        "under-base": (
            "edges that violate under the base config, not in the base baseline:"
        ),
        "policy-widened": (
            "layer policy widened (land it alone, --allow-config-change):"
        ),
        "not-covered": "the layer contract does not cover the package:",
        "refuse-problems": "refusing to baseline a package the layers do not cover:",
        "refuse-new": "refusing to baseline new layer violations:",
    }
    PURITY: ClassVar[str] = (
        "  domain purity: move the IO behind a port in the application layer, "
        "implemented in an adapter; or accept the edge once with "
        "`oo-ratchet layers --update --allow-config-change --source <ref>`"
    )

    @staticmethod
    def exit_code(result: EdgeVerdict) -> int:
        """Return 0 for a passing verdict, 1 for a failing one."""
        return 0 if result.passed else 1

    def text(self, result: EdgeVerdict) -> list[str]:
        """Return the report lines."""
        if result.failures:
            return [line for f in result.failures for line in self._failure(f, result)]
        if result.record is not None:
            record = result.record
            return [
                f"Wrote {result.verdict.written[0]}",
                f"  violations: {record.violations} ({len(record.removed)} removed)",
            ]
        review = result.review
        if review is None:
            return []
        counts = f"{review.modules} modules scanned, {review.unassigned} unassigned"
        found = f"{review.violating} baselined layer violations, none new/stale"
        return [f"PASS: {counts}, {found}"]

    def _failure(self, failure: Failure, result: EdgeVerdict) -> list[str]:
        if failure.kind not in self.TITLES:
            what = self.MESSAGES.get(failure.kind, failure.kind)
            return [f"FAIL: {what.format(*failure.subjects)}"]
        title = self.TITLES[failure.kind].format(result.base[:10])
        rows = [f"  {row}" for row in failure.subjects]
        return [f"FAIL: {title}", *rows, *self._purity(failure.subjects, result.purity)]

    def _purity(self, shown: tuple[str, ...], purity: frozenset[Edge]) -> list[str]:
        """Return the guidance line if any shown edge text is a purity edge."""
        texts = {str(e) for e in purity}
        if any(row.split("  (")[0] in texts for row in shown):
            return [self.PURITY]
        return []
