"""Adoption: a package is new only if neither its name nor its path existed."""

from __future__ import annotations

from tests.layers_repo import LayersRepo

RELATIVE_BAD_KERNEL = "from . import service\n"
RELATIVE_OK_SERVICE = "from . import kernel\n"


def _package(repo: LayersRepo, path: str, kernel: str) -> None:
    for name, text in {
        "__init__": "",
        "kernel": kernel,
        "service": RELATIVE_OK_SERVICE,
        "cli": "",
    }.items():
        repo.write(f"{path}/{name}.py", text)


class TestAdoptionMatching:
    """Matching is by top-level package name and by the scanned path."""

    def test_a_nested_package_of_the_same_name_does_not_block_adoption(
        self, repo: LayersRepo
    ) -> None:
        repo.adopt()
        repo.write("vendor/core/__init__.py", "")
        repo.write("vendor/core/utils/__init__.py", "")
        base = repo.commit_as_origin_main()
        _package(repo, "src/utils", RELATIVE_BAD_KERNEL)
        new = repo.root / "src" / "utils"
        assert repo.run_on(new, "--update")[0] == 0
        assert repo.run_on(new, "--check", "--base-ref", base)[0] == 0

    def test_a_symlink_to_an_existing_package_is_not_new(
        self, repo: LayersRepo
    ) -> None:
        _package(repo, "src/app", RELATIVE_BAD_KERNEL)
        repo.adopt()
        base = repo.commit_as_origin_main()
        (repo.root / "src" / "alias").symlink_to("app")
        alias = repo.root / "src" / "alias"
        assert repo.run_on(alias, "--update")[0] == 0
        code, out = repo.run_on(alias, "--check", "--base-ref", base)
        assert code == 1
        assert "did not" in out
