"""The layer config: fixed four-layer form and declared custom layers."""

from __future__ import annotations

from pathlib import Path

import pytest

from oo_ratchet.design.layer_config import LayerConfig, LayerConfigError


def _declared(
    layers: dict[str, list[str]], imports: dict[str, list[str]] | None = None
) -> LayerConfig:
    given = imports or {}
    return LayerConfig(
        {
            name: {"prefixes": prefixes, "imports": given.get(name, [])}
            for name, prefixes in layers.items()
        }
    )


class TestOrderedForm:
    """The four-layer form keeps parsing and ordering exactly as before."""

    def test_globs_classify_with_outer_layers_first(self) -> None:
        config = LayerConfig({"domain": ["pkg.*"], "entry": ["pkg.entry"]})
        assert config.layer("pkg.entry") == "entry"
        assert config.layer("pkg.model") == "domain"

    def test_is_ordered(self) -> None:
        assert LayerConfig({"domain": ["pkg.*"]}).is_ordered

    def test_inner_may_not_import_outer(self) -> None:
        config = LayerConfig({})
        assert config.permits("entry", "domain")
        assert not config.permits("domain", "entry")

    def test_unknown_layer_name_is_rejected(self) -> None:
        with pytest.raises(LayerConfigError, match="unknown layer keys"):
            LayerConfig({"kernel": ["pkg.*"]})


class TestDeclaredClassify:
    """Prefix matching, longest match, and the exempt modules."""

    def test_exact_prefix_matches_module_and_children(self) -> None:
        config = _declared({"kernel": ["kernel"]})
        assert config.layer("app.kernel") == "kernel"
        assert config.layer("app.kernel.sub.deep") == "kernel"

    def test_exact_prefix_does_not_match_a_longer_name(self) -> None:
        assert _declared({"kernel": ["kernel"]}).layer("app.kernelish") is None

    def test_star_prefix_matches_any_continuation(self) -> None:
        config = _declared({"kernel": ["util_*"]})
        assert config.layer("app.util_io") == "kernel"
        assert config.layer("app.util_io.sub") == "kernel"

    def test_star_prefix_needs_its_stem(self) -> None:
        assert _declared({"kernel": ["util_*"]}).layer("app.util") is None

    def test_longest_prefix_wins(self) -> None:
        config = _declared({"outer": ["svc"], "inner": ["svc.deep"]})
        assert config.layer("app.svc.deep.x") == "inner"
        assert config.layer("app.svc.other") == "outer"

    def test_exact_prefix_beats_a_star_prefix_of_equal_length(self) -> None:
        config = _declared({"exact": ["foo"], "star": ["foo*"]})
        assert config.layer("app.foo") == "exact"
        assert config.layer("app.foobar") == "star"

    def test_unassigned_module_has_no_layer(self) -> None:
        config = _declared({"kernel": ["kernel"]})
        assert config.layer("app.stray") is None
        assert not config.exempts("app.stray")

    def test_package_root_is_exempt(self) -> None:
        config = _declared({"kernel": ["*"]})
        assert config.layer("app") is None
        assert config.exempts("app")


class TestDeclaredPermits:
    """A layer may import itself and the layers its imports list names."""

    def test_same_layer_is_always_allowed(self) -> None:
        assert _declared({"a": ["a"]}).permits("a", "a")

    def test_listed_layer_is_allowed(self) -> None:
        config = _declared({"a": ["a"], "b": ["b"]}, {"b": ["a"]})
        assert config.permits("b", "a")

    def test_unlisted_layer_is_refused(self) -> None:
        config = _declared({"a": ["a"], "b": ["b"]}, {"b": ["a"]})
        assert not config.permits("a", "b")

    def test_a_declared_layer_may_reuse_a_fixed_name(self) -> None:
        config = _declared({"domain": ["m"], "entry": ["e"]}, {"domain": ["entry"]})
        assert not config.is_ordered
        assert config.permits("domain", "entry")


class TestValidation:
    """A malformed table is an error naming the problem, never a default."""

    def test_prefix_in_two_layers_is_ambiguous(self) -> None:
        with pytest.raises(LayerConfigError, match="both"):
            _declared({"a": ["x"], "b": ["x"]})

    def test_imports_must_name_declared_layers(self) -> None:
        with pytest.raises(LayerConfigError, match="undeclared"):
            _declared({"a": ["a"]}, {"a": ["ghost"]})

    def test_unknown_layer_key_is_rejected(self) -> None:
        with pytest.raises(LayerConfigError, match="prefixes and imports"):
            LayerConfig({"a": {"prefixes": ["a"], "extra": 1}})

    def test_mixing_forms_is_rejected(self) -> None:
        with pytest.raises(LayerConfigError, match="prefixes and imports"):
            LayerConfig({"a": {"prefixes": ["a"]}, "domain": ["pkg.*"]})

    def test_load_reads_the_table(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.oo-ratchet.layers.kernel]\nprefixes = ["kernel"]\n'
        )
        config = LayerConfig.load(tmp_path)
        assert config is not None
        assert config.layer("app.kernel") == "kernel"
