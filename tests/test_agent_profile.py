from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from valo_gateway.agent_profile import (
    ExecutionEnvironment,
    GovernedAgentProfile,
    assert_child_profile_narrower,
    build_session_descriptor,
    load_profile,
)
from valo_gateway.cli import main


PROFILE_PATH = (
    Path(__file__).parents[1]
    / "src"
    / "valo_gateway"
    / "profiles"
    / "governed_agent_profile.json"
)


def _profile_dict() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def test_profile_is_runtime_agnostic_but_reht_bound() -> None:
    profile = load_profile(PROFILE_PATH)

    langgraph = profile.compile_for_runtime(
        runtime_id="langgraph",
        environment=ExecutionEnvironment.LIVE,
    )
    custom = profile.compile_for_runtime(
        runtime_id="custom-loop",
        environment=ExecutionEnvironment.LIVE,
    )

    assert langgraph.profile_digest == custom.profile_digest
    assert langgraph.tools == custom.tools
    assert langgraph.runtime_id != custom.runtime_id
    assert langgraph.authorization_boundary == "REHT"
    assert langgraph.contains_secrets is False


def test_live_tool_requires_explicit_scope() -> None:
    raw = _profile_dict()
    raw["tools"][0]["resource_scope"] = []

    with pytest.raises(ValidationError, match="live tool handles require explicit resource_scope"):
        GovernedAgentProfile.model_validate(raw)


def test_profile_rejects_raw_credential_material() -> None:
    raw = _profile_dict()
    raw["tools"][0]["credential_handle_ref"] = "nv_sk_live_secret"

    with pytest.raises(ValidationError, match="opaque reference"):
        GovernedAgentProfile.model_validate(raw)


def test_session_descriptor_is_secret_free_and_ttl_bounded() -> None:
    profile = load_profile(PROFILE_PATH)
    compiled = profile.compile_for_runtime(runtime_id="claude-code")
    now = datetime(2026, 8, 6, tzinfo=UTC)

    descriptor = build_session_descriptor(compiled, ttl_seconds=600, now=now)

    assert descriptor.contains_secret is False
    assert descriptor.token_transport == "authorization_header"
    assert descriptor.expires_at.isoformat() == "2026-08-06T00:10:00+00:00"

    with pytest.raises(ValueError, match="exceeds"):
        build_session_descriptor(compiled, ttl_seconds=compiled.max_session_ttl_seconds + 1)


def test_child_profile_cannot_expand_parent() -> None:
    parent = load_profile(PROFILE_PATH)
    child_raw = _profile_dict()
    child_raw["profile_id"] = "child-operations-agent"
    child_raw["parent_profile_id"] = parent.profile_id
    child_raw["tools"][0]["resource_scope"].append("network:private")

    child = GovernedAgentProfile.model_validate(child_raw)

    with pytest.raises(ValueError, match="expands resource_scope"):
        assert_child_profile_narrower(parent=parent, child=child)


def test_child_profile_can_narrow_parent() -> None:
    parent = load_profile(PROFILE_PATH)
    child_raw = _profile_dict()
    child_raw["profile_id"] = "child-operations-agent"
    child_raw["parent_profile_id"] = parent.profile_id
    child_raw["tools"] = child_raw["tools"][:2]
    child_raw["budgets"][0]["hard_limit"] = "1000.00"
    child_raw["budgets"][0]["soft_limit"] = "100.00"
    child_raw["sessions"]["default_ttl_seconds"] = 300
    child_raw["sessions"]["max_ttl_seconds"] = 900
    child_raw["approvals"] = [child_raw["approvals"][1]]

    child = GovernedAgentProfile.model_validate(child_raw)
    assert_child_profile_narrower(parent=parent, child=child)


def test_cli_validate_and_compile(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["profile", "validate", str(PROFILE_PATH)]) == 0
    validate_output = json.loads(capsys.readouterr().out)
    assert validate_output["valid"] is True
    assert validate_output["authorization_boundary"] == "REHT"

    assert (
        main(
            [
                "profile",
                "compile",
                str(PROFILE_PATH),
                "--runtime-id",
                "openai-agents",
                "--environment",
                "live",
            ]
        )
        == 0
    )
    compile_output = json.loads(capsys.readouterr().out)
    assert compile_output["runtime_id"] == "openai-agents"
    assert compile_output["contains_secrets"] is False
    assert compile_output["tools"]


def test_child_profile_cannot_remove_budget_domain() -> None:
    parent = load_profile(PROFILE_PATH)
    child_raw = _profile_dict()
    child_raw["profile_id"] = "child-operations-agent"
    child_raw["parent_profile_id"] = parent.profile_id
    child_raw["budgets"] = []

    child = GovernedAgentProfile.model_validate(child_raw)

    with pytest.raises(ValueError, match="removes budget domains"):
        assert_child_profile_narrower(parent=parent, child=child)


def test_child_always_approval_is_stricter_than_threshold() -> None:
    parent = load_profile(PROFILE_PATH)
    child_raw = _profile_dict()
    child_raw["profile_id"] = "child-operations-agent"
    child_raw["parent_profile_id"] = parent.profile_id
    child_raw["approvals"][0].pop("threshold")
    child_raw["approvals"][0].pop("currency")

    child = GovernedAgentProfile.model_validate(child_raw)
    assert_child_profile_narrower(parent=parent, child=child)


def test_child_profile_cannot_introduce_identity_resource() -> None:
    parent = load_profile(PROFILE_PATH)
    child_raw = _profile_dict()
    child_raw["profile_id"] = "child-operations-agent"
    child_raw["parent_profile_id"] = parent.profile_id
    child_raw["identity"]["resources"].append(
        {
            "resource_type": "database",
            "resource_ref": "resource://database/finance",
            "scope": ["table:ledger"],
        }
    )

    child = GovernedAgentProfile.model_validate(child_raw)

    with pytest.raises(ValueError, match="introduces resource"):
        assert_child_profile_narrower(parent=parent, child=child)
