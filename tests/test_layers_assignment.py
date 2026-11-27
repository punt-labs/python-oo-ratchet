"""Moving a module outward, or out of ``domain``, widens the layer policy."""

from __future__ import annotations

from tests.layers_repo import LayersRepo

BASE = """\
[tool.oo-ratchet.layers]
entry = ["app.cli"]
adapters = ["app.store"]
domain = ["app.domain", "app.thing"]
"""
PROMOTED = BASE.replace(
    'adapters = ["app.store"]', 'adapters = ["app.store", "app.thing"]'
)
DEMOTED = BASE.replace(
    'adapters = ["app.store"]\ndomain = ["app.domain", "app.thing"]',
    'adapters = ["app.store", "app.thing"]\ndomain = ["app.domain"]',
)


def _setup(repo: LayersRepo, table: str) -> None:
    """Make ``app`` a clean fixed-form package, adopted and committed as main."""
    repo.write("pyproject.toml", table)
    for name in ("kernel", "service"):
        (repo.root / "src/app" / f"{name}.py").unlink()
    repo.write("src/app/cli.py", "import app.domain\n")
    repo.write("src/app/domain.py", "X = 1\n")
    repo.write("src/app/thing.py", "Y = 1\n")
    repo.write("src/app/store.py", "Z = 1\n")
    repo.adopt()
    repo.commit_as_origin_main()


class TestModuleAssignment:
    """The check compares which layer each module is assigned to."""

    def test_unchanged_table_passes(self, repo: LayersRepo) -> None:
        _setup(repo, BASE)
        assert repo.run("--check")[0] == 0

    def test_promoting_a_domain_module_fails(self, repo: LayersRepo) -> None:
        _setup(repo, BASE)
        repo.write("pyproject.toml", PROMOTED)
        code, out = repo.run("--check")
        assert code == 1
        assert "app.thing" in out
        assert "--allow-config-change" in out

    def test_promotion_passes_with_the_flag(self, repo: LayersRepo) -> None:
        _setup(repo, BASE)
        repo.write("pyproject.toml", PROMOTED)
        assert repo.run("--check", "--allow-config-change")[0] == 0

    def test_moving_inward_passes(self, repo: LayersRepo) -> None:
        _setup(repo, DEMOTED)
        repo.write("pyproject.toml", BASE)
        assert repo.run("--check")[0] == 0
