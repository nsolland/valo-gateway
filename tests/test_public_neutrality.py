from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_public_package_has_no_private_valo_runtime_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = " ".join(project.get("dependencies", [])).lower()

    forbidden = (
        "valo-reht",
        "valo-kernel",
        "valo-platform",
        "peace",
        "mcip",
        "synapse-lab",
    )
    for package in forbidden:
        assert package not in dependencies


def test_public_boundary_keeps_authorization_external() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    publication = (ROOT / "PUBLICATION_STATUS.md").read_text(encoding="utf-8").lower()

    assert "does not evaluate risk, infer authority or decide" in readme
    assert "not required python dependencies" in readme
    assert "does not decide whether an action is authorized" in publication
