import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_package_has_no_private_valo_runtime_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = " ".join(project.get("dependencies", [])).lower()

    # Public gateway packaging must not depend on private VALO runtime packages.
    # Keep this list limited to actual package dependencies; do not use the test
    # as a catalogue of unrelated private research projects.
    forbidden = (
        "valo-reht",
        "valo-kernel",
        "valo-platform",
    )
    for package in forbidden:
        assert package not in dependencies


def test_public_boundary_keeps_authorization_external() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    publication = (ROOT / "PUBLICATION_STATUS.md").read_text(encoding="utf-8").lower()

    assert "does not evaluate risk, infer authority or decide" in readme
    assert "not required python dependencies" in readme
    assert "does not decide whether an action is authorized" in publication
