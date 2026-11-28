"""The layers gate's io edges follow how a domain module uses ``io``."""

from __future__ import annotations

import json
from typing import cast

import pytest

from tests.layers_repo import LayersRepo
from tests.test_layers_domain_purity_round2 import _fixed, _run

FILE_IO = [
    "import io\nf = io.open('x')",
    "from io import *\nf = FileIO('x')",
    "from io import *\nf = open_code('x')",
    "import io\nf = getattr(io, 'open')('x')",
    "import io\nstream = io\nf = stream.open('x')",
]
MEMORY = [
    "import io\nb = io.StringIO()",
    "import io\nb = io.TextIOWrapper(io.BytesIO(b''))",
    "import io",
]


def _baseline(repo: LayersRepo, source: str) -> dict[str, object]:
    _fixed(repo, "pkg", {"cli": "", "cli2": "", "domain": source, "domain2": ""})
    repo.commit_as_origin_main()
    assert _run(repo, "pkg", "--update")[0] == 0
    return cast("dict[str, object]", json.loads(repo.baseline.read_text()))


@pytest.mark.parametrize("source", FILE_IO)
def test_file_io_through_io_is_an_edge(repo: LayersRepo, source: str) -> None:
    assert "pkg.domain" in _baseline(repo, source)


@pytest.mark.parametrize("source", MEMORY)
def test_in_memory_io_is_not_an_edge(repo: LayersRepo, source: str) -> None:
    assert _baseline(repo, source) == {}
