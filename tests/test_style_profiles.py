import asyncio

import pytest

from valo_gateway.style_mcp import apply_profile, get_profile, list_profiles, mcp
from valo_gateway.style_profiles import load_style_profile, prompt_prefix


def test_reht_profile_is_available():
    profile = load_style_profile("reht-visual")
    assert profile["id"] == "reht-visual"
    assert profile["version"] == "1.2.0"
    assert profile["naming_rule"].startswith("reht is always written")
    assert profile["campaign_model"]["sequence"] == [
        "premise",
        "assessment",
        "action",
    ]
    assert "Generic AI advertising aesthetics." in profile["forbidden"]
    assert (
        "Unnecessary English jargon when communicating to a Norwegian audience and a precise Norwegian term exists."
        in profile["forbidden"]
    )


def test_mcp_profile_tools_return_canonical_profile():
    assert "reht-visual" in list_profiles()
    assert get_profile()["editorial_test"].startswith("If the image could be used")


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
    result = apply_profile("Create an ad about the two-second rule.")
    assert result.startswith(prompt_prefix("reht-visual"))
    assert result.endswith("Task: Create an ad about the two-second rule.")


def test_empty_instruction_is_rejected():
    with pytest.raises(ValueError, match="instruction is required"):
        apply_profile("   ")


def test_unknown_profile_is_rejected():
    with pytest.raises(KeyError, match="unknown style profile"):
        load_style_profile("missing")
