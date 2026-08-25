import asyncio

import pytest

from valo_gateway.style_mcp import apply_profile, get_profile, list_profiles, mcp
from valo_gateway.style_profiles import load_style_profile, prompt_prefix


def test_reht_profile_is_available():
    profile = load_style_profile("reht-visual")
    assert profile["id"] == "reht-visual"
    assert profile["version"] == "1.2.0"
    assert profile["naming_rule"].startswith("reht skrives alltid")
    assert profile["campaign_model"]["sequence"] == [
        "premiss",
        "vurdering",
        "handling",
    ]
    assert "Generisk KI-reklameestetikk." in profile["forbidden"]
    assert "Engelske fagord når et presist norsk ord finnes." in profile["forbidden"]


def test_mcp_profile_tools_return_canonical_profile():
    assert "reht-visual" in list_profiles()
    assert get_profile()["editorial_test"].startswith("Hvis bildet kunne vært brukt")


def test_mcp_2_server_registers_tools_and_resource_template():
    tools = asyncio.run(mcp.list_tools())
    templates = asyncio.run(mcp.list_resource_templates())

    assert {tool.name for tool in tools} == {
        "apply_profile",
        "get_profile",
        "list_profiles",
    }
    assert {
        str(getattr(template, "uri_template", getattr(template, "uriTemplate", None)))
        for template in templates
    } == {
        "style://{profile_id}"
    }


def test_apply_profile_binds_contract_before_instruction():
    result = apply_profile("Lag en annonse om tosekundersregelen.")
    assert result.startswith(prompt_prefix("reht-visual"))
    assert result.endswith("Oppgave: Lag en annonse om tosekundersregelen.")


def test_empty_instruction_is_rejected():
    with pytest.raises(ValueError, match="instruction is required"):
        apply_profile("   ")


def test_unknown_profile_is_rejected():
    with pytest.raises(KeyError, match="unknown style profile"):
        load_style_profile("missing")
