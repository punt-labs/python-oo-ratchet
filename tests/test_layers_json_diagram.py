"""``layers --json`` reports module rings, ring-to-ring edges, marked violations."""

from __future__ import annotations

import json
from typing import Any

from tests.layers_repo import LayersRepo

FOUR = """\
[tool.oo-ratchet.layers]
entry = ["app.cli"]
adapters = ["app.gitio"]
application = ["app.ratchet"]
domain = ["app.domain", "app.model"]
"""
FILES = {
    "cli": "import app.domain\n",
    "gitio": "",
    "ratchet": "import app.gitio\n",
    "domain": "import app.gitio\nimport app.ratchet\nimport subprocess\n",
    "model": "import app.gitio\n",
    "stray": "",
}


def _report(repo: LayersRepo, config: str = FOUR) -> dict[str, Any]:
    repo.write("pyproject.toml", config)
    for name in ("kernel", "service"):
        (repo.root / f"src/app/{name}.py").unlink()
    for name, text in FILES.items():
        repo.write(f"src/app/{name}.py", text)
    code, out = repo.run("--json")
    assert code == 0
    data: dict[str, Any] = json.loads(out)
    return data


def _mark(
    source: str, target: str, source_ring: str, target_ring: str, kind: str
) -> dict[str, str]:
    return {
        "source": source,
        "target": target,
        "source_ring": source_ring,
        "target_ring": target_ring,
        "kind": kind,
    }


class TestJsonDiagramKeys:
    """The added keys carry everything a diagram needs."""

    def test_module_rings(self, repo: LayersRepo) -> None:
        assert _report(repo)["module_rings"] == {
            "app.cli": "entry",
            "app.domain": "domain",
            "app.gitio": "adapters",
            "app.model": "domain",
            "app.ratchet": "application",
            "app.stray": None,
        }

    def test_ring_edges_count_layer_violations_only(self, repo: LayersRepo) -> None:
        assert _report(repo)["ring_edges"] == [
            {"source_ring": "application", "target_ring": "adapters", "count": 1},
            {"source_ring": "domain", "target_ring": "adapters", "count": 2},
            {"source_ring": "domain", "target_ring": "application", "count": 1},
        ]

    def test_violations_are_marked_with_kind(self, repo: LayersRepo) -> None:
        assert _report(repo)["marked_violations"] == [
            _mark("app.domain", "app.gitio", "domain", "adapters", "layer"),
            _mark("app.domain", "app.ratchet", "domain", "application", "layer"),
            _mark("app.domain", "subprocess", "domain", "io", "io"),
            _mark("app.model", "app.gitio", "domain", "adapters", "layer"),
            _mark("app.ratchet", "app.gitio", "application", "adapters", "layer"),
        ]

    def test_existing_keys_keep_their_values(self, repo: LayersRepo) -> None:
        data = _report(repo)
        assert data["modules"] == 7
        assert data["unassigned"] == ["app.stray"]
        assert data["violations"][0] == {
            "source": "app.domain",
            "target": "app.gitio",
            "source_layer": "domain",
            "target_layer": "adapters",
        }
        assert len(data["violations"]) == 5

    def test_declared_layers_report_their_names(self, repo: LayersRepo) -> None:
        declared = (
            '[tool.oo-ratchet.layers.low]\nprefixes = ["gitio", "model"]\n'
            "imports = []\n"
            '[tool.oo-ratchet.layers.high]\nprefixes = ["cli", "domain", "ratchet",'
            ' "stray"]\nimports = ["low"]\n'
        )
        data = _report(repo, declared)
        assert data["module_rings"]["app.gitio"] == "low"
        assert data["module_rings"]["app.cli"] == "high"
        assert {m["kind"] for m in data["marked_violations"]} <= {"layer"}
