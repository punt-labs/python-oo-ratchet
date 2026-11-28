"""The layer config: fixed four-layer form and declared custom layers."""

from __future__ import annotations

from pathlib import Path

import pytest

from oo_ratchet.core.adapters.layertablefile import LayerTableFile
from oo_ratchet.core.domain.declared_layers import DeclaredLayers
from oo_ratchet.core.domain.layer_config import LayerConfig, LayerConfigError
from oo_ratchet.core.domain.layer_table import LayerTable


def _declared(
    layers: dict[str, list[str]], imports: dict[str, list[str]] | None = None
) -> DeclaredLayers:
    given = imports or {}
    return DeclaredLayers(
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
        assert LayerConfig({"domain": ["pkg.*"]}).ORDERED

    def test_inner_may_not_import_outer(self) -> None:
        config = LayerConfig({})
        assert "domain" in config.allowed("entry")
        assert "entry" not in config.allowed("domain")

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

    def test_package_root_is_exempt(self) -> None:
        config = _declared({"kernel": ["*"]})
        assert config.layer("app") is None
        assert config.EXEMPTS_ROOT


class TestDeclaredPermits:
    """A layer may import itself and the layers its imports list names."""

    def test_same_layer_is_always_allowed(self) -> None:
        assert "a" in _declared({"a": ["a"]}).allowed("a")

    def test_listed_layer_is_allowed(self) -> None:
        config = _declared({"a": ["a"], "b": ["b"]}, {"b": ["a"]})
        assert "a" in config.allowed("b")

    def test_unlisted_layer_is_refused(self) -> None:
        config = _declared({"a": ["a"], "b": ["b"]}, {"b": ["a"]})
        assert "b" not in config.allowed("a")

    def test_a_declared_layer_may_reuse_a_fixed_name(self) -> None:
        config = _declared({"domain": ["m"], "entry": ["e"]}, {"domain": ["entry"]})
        assert not config.ORDERED
        assert "entry" in config.allowed("domain")


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
            DeclaredLayers({"a": {"prefixes": ["a"], "extra": 1}})

    def test_mixing_forms_is_rejected(self) -> None:
        with pytest.raises(LayerConfigError, match="prefixes and imports"):
            LayerTable.build({"a": {"prefixes": ["a"]}, "domain": ["pkg.*"]})

    def test_load_reads_the_table(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.oo-ratchet.layers.kernel]\nprefixes = ["kernel"]\n'
        )
        config = LayerTableFile.read(tmp_path).config()
        assert config is not None
        assert config.layer("app.kernel") == "kernel"


class TestDeclaredPrefixValidation:
    """A prefix that cannot match what it looks like is refused, not ignored."""

    def test_prefixes_are_required(self) -> None:
        with pytest.raises(LayerConfigError, match="prefixes"):
            DeclaredLayers({"a": {"imports": []}})

    def test_prefixes_may_not_be_empty(self) -> None:
        with pytest.raises(LayerConfigError, match="prefixes"):
            DeclaredLayers({"a": {"prefixes": []}})

    @pytest.mark.parametrize("prefix", ["a*b", "*a", "a.", "a.*b"])
    def test_misplaced_star_or_trailing_dot_is_refused(self, prefix: str) -> None:
        with pytest.raises(LayerConfigError, match="prefix"):
            DeclaredLayers({"a": {"prefixes": [prefix]}})

    @pytest.mark.parametrize("prefix", ["a", "a.b", "a*", "a.b_*"])
    def test_plain_and_trailing_star_prefixes_are_accepted(self, prefix: str) -> None:
        assert DeclaredLayers({"a": {"prefixes": [prefix]}}).layer_names() == ("a",)
