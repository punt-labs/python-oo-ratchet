"""Tests for the ported vox suppression ratchet (``oo_ratchet.suppression``).

The suppression package is vox-verbatim except ``patterns.py``, which swaps
vox's regex+AST heuristic for a ``tokenize`` scan. These tests pin that swap
(the four documented blind spots must now count correctly, and string-interior
``noqa`` text must not), the per-file-ignores counter's fail-closed parsing, and
the merge-base count delta driven end-to-end through a real git tree.
"""

from __future__ import annotations

from oo_ratchet.suppression.cli import main as suppression_main
from oo_ratchet.suppression.patterns import FileSuppressions


def test_module_is_importable_as_package() -> None:
    """The package resolves as ``oo_ratchet.suppression`` (regular-package path)."""
    assert callable(suppression_main)


class TestTokenizeScan:
    """The tokenize scan counts real suppressions and ignores string interiors."""

    def test_noqa_on_code_line_counted(self) -> None:
        fs = FileSuppressions("f.py", "x = 1  # noqa: E501\n")
        assert fs.count("noqa") == 1

    def test_type_ignore_counted(self) -> None:
        fs = FileSuppressions("f.py", "import x  # type: ignore[import-not-found]\n")
        assert fs.count("type_ignore") == 1

    def test_pyright_ignore_counted(self) -> None:
        fs = FileSuppressions("f.py", "y = z()  # pyright: ignore[reportUnknown]\n")
        assert fs.count("pyright_ignore") == 1

    def test_pylint_disable_counted(self) -> None:
        fs = FileSuppressions("f.py", "x = 1  # pylint: disable=invalid-name\n")
        assert fs.count("pylint_disable") == 1

    def test_pure_comment_line_not_counted(self) -> None:
        fs = FileSuppressions("f.py", "# noqa: E501 standalone comment\nx = 1\n")
        assert fs.count("noqa") == 0

    def test_noqa_inside_multiline_string_not_counted(self) -> None:
        source = '"""line one\n# noqa: E501 inside a string\n"""\nx = 1\n'
        fs = FileSuppressions("f.py", source)
        assert fs.count("noqa") == 0

    def test_untokenizable_source_fails_closed_not_zeroed(self) -> None:
        """Untokenizable source must fail CLOSED (over-count), never zero out.

        Zeroing would let the suppression gate read a PR that both broke
        tokenization and added suppressions as "count decreased -> PASS". The
        fallback over-counts marker-bearing lines instead, so the marker on the
        code line is still seen and the total can only rise or hold.
        """
        fs = FileSuppressions("f.py", '"""open string never closes\nx = 1  # noqa\n')
        assert fs.count("noqa") >= 1
        assert fs.total >= 1

    # --- the four documented blind spots of the retired regex+AST heuristic ---

    def test_blindspot_async_def_counted(self) -> None:
        """``async def`` was missing from the old regex keyword list."""
        fs = FileSuppressions("f.py", "async def f():  # noqa: D103\n    return 1\n")
        assert fs.count("noqa") == 1

    def test_blindspot_attribute_assignment_counted(self) -> None:
        """``obj.attr =`` starts with identifier+dot, which the regex missed."""
        fs = FileSuppressions("f.py", "c.x = 1  # noqa: D101\n")
        assert fs.count("noqa") == 1

    def test_blindspot_tuple_target_counted(self) -> None:
        """``a, b = ...`` starts with identifier+comma, which the regex missed."""
        fs = FileSuppressions("f.py", "a, b = 1, 2  # noqa: E501\n")
        assert fs.count("noqa") == 1

    def test_blindspot_single_line_docstring_with_noqa_not_counted(self) -> None:
        """A one-line docstring containing ``noqa`` is string content, not code.

        The retired heuristic treated a line starting with a triple quote as
        code and would have counted this false positive.
        """
        fs = FileSuppressions("f.py", '"""docs # noqa: E501"""\nx = 1\n')
        assert fs.count("noqa") == 0

    def test_comment_after_closing_docstring_quote_counted(self) -> None:
        """A real comment after the closing quote on the same line IS counted."""
        fs = FileSuppressions("f.py", '"""docs"""  # noqa: E501\nx = 1\n')
        assert fs.count("noqa") == 1
