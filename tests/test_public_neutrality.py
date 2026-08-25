import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_package_has_no_private_source_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = [str(dep).lower() for dep in project.get("dependencies", [])]

    # Public packaging must not rely on private source locations or local paths.
    for dependency in dependencies:
        assert "git+" not in dependency
        assert "@ file:" not in dependency
        assert "../" not in dependency


def test_public_boundary_keeps_authorization_external() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    publication = (ROOT / "PUBLICATION_STATUS.md").read_text(encoding="utf-8").lower()

    assert "does not evaluate risk, infer authority or decide" in readme
    assert "does not decide whether an action is authorized" in publication
