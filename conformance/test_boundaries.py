from pathlib import Path

def test_no_la_identity_claim():
    assert "has no la identity" in Path("LAYER_IDENTITY.md").read_text().lower()

def test_migration_sources_are_recorded():
    text = Path("MIGRATION_MANIFEST.json").read_text()
    for repo in ["valo-runtime-core", "valo-runtime-local", "valo-runtime-adapters", "valo-tool-adapters", "valo-platform"]:
        assert repo in text
