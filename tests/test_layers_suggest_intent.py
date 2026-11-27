"""``layers --suggest`` takes rings from declared or named intent, never a guess."""

from __future__ import annotations

import re

import pytest

from oo_ratchet.design.layer_config import LayerConfig
from tests.layers_repo import LayersRepo
from tests.test_layers_suggest import PROJECT, rings, start

HEADINGS = (
    "# Ring from declaration, name or entry evidence:",
    "# Conflicts:",
    "# Unclassified:",
)


def sections(out: str) -> dict[str, list[str]]:
    """Return the three lists of the output, keyed by heading."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in out.splitlines():
        if line in HEADINGS:
            current = found.setdefault(line, [])
        elif current is not None and line.startswith("#   "):
            current.append(line)
        elif not line.strip():
            current = None
    return found


def ringed(out: str) -> list[str]:
    """Return the lines of the ring list."""
    return sections(out)[HEADINGS[0]]


def conflicts(out: str) -> list[str]:
    """Return the lines of the conflict list."""
    return sections(out)[HEADINGS[1]]


def unclassified(out: str) -> list[str]:
    """Return the lines of the unclassified list."""
    return sections(out)[HEADINGS[2]]


def ring_of(out: str, module: str) -> str | None:
    """Return the ring the printed table gives ``module``, as the gate reads it."""
    return LayerConfig(dict(rings(out))).layer(module)


def package(repo: LayersRepo, files: dict[str, str]) -> None:
    """Start an unconfigured package, then add ``files`` under ``src/app``."""
    start(repo)
    for rel, text in files.items():
        repo.write(f"src/app/{rel}", text)


class TestNoGuessing:
    """A pure-looking module with no declared or named intent stays unclassified."""

    def test_pure_module_without_intent_is_unclassified(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("kernel", "X = 1\n")
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.kernel") is None
        assert any("app.kernel" in line for line in unclassified(out))

    def test_io_module_without_intent_is_unclassified(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("service", "import json\n")
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.service") is None
        assert any("app.service" in line for line in unclassified(out))

    def test_protocol_rule_is_gone(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("kernel", "from typing import Protocol\n\n\nclass S(Protocol): ...\n")
        repo.edit("service", "import json\nimport app.kernel\n")
        out = repo.run("--suggest")[1]
        assert rings(out)["application"] == []
        assert any("app.kernel" in line for line in unclassified(out))


class TestIntent:
    """Ring intent comes from a declaration, then a package name."""

    def test_marker_declares_the_ring(self, repo: LayersRepo) -> None:
        package(repo, {"util.py": '__ring__ = "domain"\n'})
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.util") == "domain"
        assert any("app.util: domain (__ring__ marker" in x for x in ringed(out))

    def test_marker_on_an_adapter(self, repo: LayersRepo) -> None:
        package(repo, {"store.py": '__ring__: str = "adapters"\nimport json\n'})
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.store") == "adapters"

    def test_marker_is_never_imported(self, repo: LayersRepo) -> None:
        package(
            repo, {"util.py": 'raise SystemExit("imported")\n__ring__ = "domain"\n'}
        )
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.util") == "domain"

    def test_invalid_marker_is_unclassified(self, repo: LayersRepo) -> None:
        package(repo, {"util.py": '__ring__ = "core"\n'})
        out = repo.run("--suggest")[1]
        assert any("app.util" in x and "__ring__" in x for x in unclassified(out))

    def test_non_literal_marker_is_unclassified(self, repo: LayersRepo) -> None:
        package(repo, {"util.py": 'R = "domain"\n__ring__ = R\n'})
        out = repo.run("--suggest")[1]
        assert any("app.util" in x for x in unclassified(out))

    def test_existing_layers_table_is_a_declaration(self, repo: LayersRepo) -> None:
        package(repo, {"util.py": ""})
        repo.write(
            "pyproject.toml",
            PROJECT + '\n[tool.oo-ratchet.layers]\ndomain = ["app.util"]\n',
        )
        out = repo.run("--suggest")[1]
        assert any(
            "app.util: domain ([tool.oo-ratchet.layers]" in x for x in ringed(out)
        )

    def test_marker_and_table_disagreeing_is_not_guessed(
        self, repo: LayersRepo
    ) -> None:
        package(repo, {"util.py": '__ring__ = "domain"\n'})
        repo.write(
            "pyproject.toml",
            PROJECT + '\n[tool.oo-ratchet.layers]\nadapters = ["app.util"]\n',
        )
        out = repo.run("--suggest")[1]
        assert any("app.util" in x and "disagree" in x for x in unclassified(out))

    @pytest.mark.parametrize(
        ("path", "ring"),
        [
            ("domain/a.py", "domain"),
            ("model/a.py", "domain"),
            ("core/a.py", "domain"),
            ("adapters/a.py", "adapters"),
            ("infra/a.py", "adapters"),
        ],
    )
    def test_package_name_convention(
        self, repo: LayersRepo, path: str, ring: str
    ) -> None:
        package(repo, {path.split("/")[0] + "/__init__.py": "", path: ""})
        out = repo.run("--suggest")[1]
        module = "app." + path.removesuffix(".py").replace("/", ".")
        assert ring_of(out, module) == ring
        assert any(f"{module}: {ring} (name convention" in x for x in ringed(out))

    def test_ambiguous_names_are_not_guessed(self, repo: LayersRepo) -> None:
        package(
            repo,
            {
                "infra/__init__.py": "",
                "infra/domain/__init__.py": "",
                "infra/domain/a.py": "",
            },
        )
        out = repo.run("--suggest")[1]
        assert any("app.infra.domain.a" in x for x in unclassified(out))

    def test_name_table_is_configurable(self, repo: LayersRepo) -> None:
        package(
            repo,
            {
                "logic/__init__.py": "",
                "logic/a.py": "",
                "domain/__init__.py": "",
                "domain/b.py": "",
            },
        )
        repo.write(
            "pyproject.toml",
            PROJECT + '\n[tool.oo-ratchet.suggest]\ndomain = ["logic"]\n',
        )
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.logic.a") == "domain"
        assert ring_of(out, "app.domain.b") != "domain"

    def test_unknown_suggest_key_fails(self, repo: LayersRepo) -> None:
        package(repo, {})
        repo.write(
            "pyproject.toml", PROJECT + '\n[tool.oo-ratchet.suggest]\nbogus = ["x"]\n'
        )
        code, out = repo.run("--suggest")
        assert code == 1
        assert "bogus" in out

    def test_entry_rule_stays(self, repo: LayersRepo) -> None:
        start(repo)
        repo.edit("cli", "import argparse\n")
        out = repo.run("--suggest")[1]
        assert rings(out)["entry"] == ["app", "app.cli"]
        assert any("app.cli: entry (imports argparse" in x for x in ringed(out))


class TestNeverDomainWhenIoIsReached:
    """No module that reaches IO is ever suggested domain, directly or in hops."""

    def test_direct_io_in_a_domain_package_is_a_conflict(
        self, repo: LayersRepo
    ) -> None:
        package(repo, {"domain/__init__.py": "", "domain/m.py": "import json\n"})
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.domain.m") != "domain"
        assert any(
            "app.domain.m: CONFLICT" in x and "app.domain.m -> json" in x
            for x in conflicts(out)
        )

    def test_transitive_io_is_a_conflict_with_the_path(self, repo: LayersRepo) -> None:
        package(
            repo,
            {
                "domain/__init__.py": "",
                "domain/m.py": "import app.helper\n",
                "helper.py": "import app.store\n",
                "store.py": "def read(p):\n    return open(p)\n",
            },
        )
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.domain.m") != "domain"
        assert any(
            "app.domain.m -> app.helper -> app.store -> open()" in x
            for x in conflicts(out)
        )

    def test_marker_domain_with_transitive_io_is_a_conflict(
        self, repo: LayersRepo
    ) -> None:
        package(
            repo,
            {
                "m.py": '__ring__ = "domain"\nimport app.helper\n',
                "helper.py": "import subprocess\n",
            },
        )
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.m") != "domain"
        assert any("app.m -> app.helper -> subprocess" in x for x in conflicts(out))

    def test_cycle_does_not_hang(self, repo: LayersRepo) -> None:
        package(
            repo,
            {
                "domain/__init__.py": "",
                "domain/a.py": "import app.domain.b\n",
                "domain/b.py": "import app.domain.a\nimport json\n",
            },
        )
        out = repo.run("--suggest")[1]
        assert "app.domain.a -> app.domain.b -> json" in "\n".join(conflicts(out))

    def test_domain_importing_an_adapter_is_a_conflict(self, repo: LayersRepo) -> None:
        package(
            repo,
            {
                "domain/__init__.py": "",
                "domain/m.py": "import app.adapters.db\n",
                "adapters/__init__.py": "",
                "adapters/db.py": "X = 1\n",
            },
        )
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.domain.m") != "domain"
        assert any(
            "app.domain.m: CONFLICT" in x and "app.adapters.db" in x
            for x in conflicts(out)
        )

    def test_pure_domain_package_is_domain(self, repo: LayersRepo) -> None:
        package(
            repo,
            {
                "domain/__init__.py": "",
                "domain/a.py": "import app.domain.b\n",
                "domain/b.py": "",
            },
        )
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.domain.a") == ring_of(out, "app.domain.b") == "domain"
        assert any("reaches no IO" in x for x in ringed(out) if "app.domain.a" in x)

    @pytest.mark.parametrize(
        "body",
        [
            "import json\n",
            "import pathlib\n",
            "import app.helper\n",
            "import app.helper2\n",
            "from app import helper\n",
            "def f(p):\n    return open(p)\n",
            "import importlib\nimportlib.import_module('subprocess')\n",
        ],
    )
    def test_property_no_io_reaching_module_is_domain(
        self, repo: LayersRepo, body: str
    ) -> None:
        package(
            repo,
            {
                "domain/__init__.py": "",
                "domain/m.py": body,
                "helper.py": "import app.helper2\n",
                "helper2.py": "import socket\n",
            },
        )
        out = repo.run("--suggest")[1]
        assert ring_of(out, "app.domain.m") != "domain"
        assert any("app.domain.m" in x for x in conflicts(out))


class TestEveryLineHasAReason:
    """Each listed module carries a parenthesised reason."""

    def test_all_lists_carry_reasons(self, repo: LayersRepo) -> None:
        package(
            repo,
            {
                "domain/__init__.py": "",
                "domain/a.py": "import json\n",
                "domain/b.py": "",
                "free.py": "",
                "cli2.py": "import argparse\n",
            },
        )
        out = repo.run("--suggest")[1]
        listed = [
            x for name in HEADINGS for x in sections(out)[name] if "none" not in x
        ]
        assert len(listed) >= 4
        assert all(re.search(r": [A-Za-z]+ \(.+\)$", x) for x in listed), listed

    def test_empty_lists_say_none(self, repo: LayersRepo) -> None:
        start(repo)
        out = repo.run("--suggest")[1]
        assert conflicts(out) == ["#   none"]

    def test_summary_counts(self, repo: LayersRepo) -> None:
        package(repo, {"domain/__init__.py": "", "domain/a.py": "", "free.py": ""})
        out = repo.run("--suggest")[1]
        assert re.search(r"# Summary: \d+ of \d+ modules", out)
