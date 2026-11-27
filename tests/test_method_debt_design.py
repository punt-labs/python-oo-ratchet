"""The design scan of this package reports none of the folded method debt."""

from __future__ import annotations

import pytest

from oo_ratchet.core.domain.findings import Rules
from oo_ratchet.layers.suggest_text import SafeText
from tests.test_hollow_classes import own_findings


@pytest.mark.parametrize(
    ("rule", "symbol"),
    [
        (Rules.STATELESS_BAG, "SafeText"),
        (Rules.SPLIT_COHESION, "RingLists"),
        (Rules.FEATURE_ENVY, "ClassRules._stateless"),
        (Rules.FEATURE_ENVY, "ClumpOwners._parent"),
        (Rules.FEATURE_ENVY, "ShadowMetrics._delta"),
    ],
)
def test_method_debt_is_not_reported(rule: str, symbol: str) -> None:
    assert (rule, symbol) not in own_findings()


def test_safe_text_escapes_what_it_wraps() -> None:
    text = SafeText('a"b\ncé')
    assert text.quoted() == '"a\\"b\\nc\\u00e9"'
    assert text.comment() == 'a"b\\ncé'
