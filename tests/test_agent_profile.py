from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from valo_gateway.agent_profile import (
    AgentIdentity,
    ApprovalRule,
    BoundResource,
    BudgetConstraint,
    BudgetWindow,
    DelegatedSessionDescriptor,
    ExecutionEnvironment,
    GovernedAgentProfile,
    GovernedToolHandle,
    SessionPolicy,
    assert_child_profile_narrower,
    build_session_descriptor,
    load_profile,
)
from valo_gateway.cli import _run, main


PROFILE_PATH = (
    Path(__file__).parents[1]
    / "src"
    / "valo_gateway"
    / "profiles"
    / "governed_agent_profile.json"
)


def _profile_dict() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _child_dict(parent: GovernedAgentProfile) -> dict:
    raw = _profile_dict()
    raw["profile_id"] = "child-operations-agent"
    raw["parent_profile_id"] = parent.profile_id
    return raw


def _assert_invalid(raw: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        GovernedAgentProfile.model_validate(raw)


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
    assert profile.compile_for_runtime(runtime_id="default").environment is ExecutionEnvironment.SANDBOX


def test_resource_and_identity_references_are_closed() -> None:
    with pytest.raises(ValidationError, match="opaque reference"):
        BoundResource(resource_type="email", resource_ref="raw-secret")
    with pytest.raises(ValidationError, match="wildcard"):
        BoundResource(resource_type="email", resource_ref="resource://mail/a", scope=("*",))
    with pytest.raises(ValidationError, match="opaque reference"):
        AgentIdentity(principal_id="p", actor_id="a", issuer="i", legal_entity_ref="plain")


def test_tool_handle_validation_paths() -> None:
    base = {
        "name": "tool",
        "adapter": "mcp:tool",
        "action_types": ["read"],
        "resource_scope": ["resource:a"],
        "environments": ["sandbox"],
    }
    for field, value, match in (
        ("action_types", [], "at least one action_type"),
        ("environments", [], "at least one environment"),
        ("action_types", ["*"], "wildcard access"),
        ("resource_scope", ["*"], "wildcard access"),
    ):
        raw = dict(base)
        raw[field] = value
        with pytest.raises(ValidationError, match=match):
            GovernedToolHandle.model_validate(raw)

    raw = dict(base, environments=["live"], resource_scope=[])
    with pytest.raises(ValidationError, match="explicit resource_scope"):
        GovernedToolHandle.model_validate(raw)

    raw = dict(base, credential_handle_ref="nv_sk_live_secret")
    with pytest.raises(ValidationError, match="opaque reference"):
        GovernedToolHandle.model_validate(raw)


def test_budget_approval_and_session_validation_paths() -> None:
    with pytest.raises(ValidationError, match="soft_limit cannot exceed"):
        BudgetConstraint(
            budget_id="b",
            currency="USD",
            window=BudgetWindow.MONTH,
            hard_limit="10",
            soft_limit="11",
        )

    approval = {
        "rule_id": "r",
        "action_types": ["payment.charge"],
        "approver_scope": ["role:risk"],
    }
    for field, value, match in (
        ("action_types", [], "must declare action_types"),
        ("approver_scope", [], "must declare approver_scope"),
        ("action_types", ["*"], "wildcard access"),
        ("approver_scope", ["*"], "wildcard access"),
    ):
        raw = dict(approval)
        raw[field] = value
        with pytest.raises(ValidationError, match=match):
            ApprovalRule.model_validate(raw)

    with pytest.raises(ValidationError, match="declared together"):
        ApprovalRule.model_validate(dict(approval, threshold="10"))
    with pytest.raises(ValidationError, match="default session TTL"):
        SessionPolicy(default_ttl_seconds=61, max_ttl_seconds=60)


def test_profile_validation_paths() -> None:
    parent = load_profile(PROFILE_PATH)

    cases: list[tuple[dict, str]] = []
    raw = _profile_dict()
    raw["parent_profile_id"] = raw["profile_id"]
    cases.append((raw, "own parent"))
    raw = _profile_dict()
    raw["authority_envelope_ref"] = "authority"
    cases.append((raw, "authority_envelope_ref"))
    raw = _profile_dict()
    raw["policy_refs"] = []
    cases.append((raw, "at least one policy_ref"))
    raw = _profile_dict()
    raw["policy_refs"] = ["plain"]
    cases.append((raw, "policy_refs must be opaque"))
    raw = _profile_dict()
    raw["tools"].append(dict(raw["tools"][0]))
    cases.append((raw, "tool names must be unique"))
    raw = _profile_dict()
    raw["budgets"].append(dict(raw["budgets"][0]))
    cases.append((raw, "budget ids must be unique"))
    raw = _profile_dict()
    raw["approvals"].append(dict(raw["approvals"][0]))
    cases.append((raw, "approval rule ids must be unique"))

    for raw, match in cases:
        _assert_invalid(raw, match)

    assert parent.digest == load_profile(PROFILE_PATH).digest


def test_session_descriptor_is_secret_free_and_ttl_bounded() -> None:
    profile = load_profile(PROFILE_PATH)
    compiled = profile.compile_for_runtime(runtime_id="claude-code")
    now = datetime(2026, 8, 6, tzinfo=UTC)

    descriptor = build_session_descriptor(compiled, ttl_seconds=600, now=now)
    default_descriptor = build_session_descriptor(compiled, now=now)

    assert descriptor.contains_secret is False
    assert descriptor.token_transport == "authorization_header"
    assert descriptor.expires_at.isoformat() == "2026-08-06T00:10:00+00:00"
    assert default_descriptor.expires_at == now + timedelta(seconds=900)

    for ttl in (0, compiled.max_session_ttl_seconds + 1):
        with pytest.raises(ValueError, match="exceeds"):
            build_session_descriptor(compiled, ttl_seconds=ttl)

    with pytest.raises(ValidationError, match="later than issued_at"):
        DelegatedSessionDescriptor(
            profile_id="p",
            profile_digest="d",
            runtime_id="r",
            tool_names=(),
            issued_at=now,
            expires_at=now,
        )


def test_child_profile_can_narrow_parent() -> None:
    parent = load_profile(PROFILE_PATH)
    child_raw = _child_dict(parent)
    child_raw["tools"] = child_raw["tools"][:2]
    child_raw["budgets"][0]["hard_limit"] = "1000.00"
    child_raw["budgets"][0]["soft_limit"] = "100.00"
    child_raw["sessions"]["default_ttl_seconds"] = 300
    child_raw["sessions"]["max_ttl_seconds"] = 900
    child_raw["approvals"] = [child_raw["approvals"][1]]

    child = GovernedAgentProfile.model_validate(child_raw)
    assert_child_profile_narrower(parent=parent, child=child)


def test_child_identity_and_policy_cannot_widen() -> None:
    parent = load_profile(PROFILE_PATH)

    mutations = [
        (lambda r: r.update(parent_profile_id="wrong"), "does not bind"),
        (lambda r: r["identity"].update(principal_id="other"), "changes principal"),
        (lambda r: r["identity"].update(issuer="other"), "changes identity issuer"),
        (lambda r: r["identity"].update(legal_entity_ref="urn:other"), "changes legal entity"),
        (lambda r: r.update(policy_refs=[r["policy_refs"][0]]), "removes inherited policy"),
        (lambda r: r.update(default_environment="live"), "promotes default environment"),
        (
            lambda r: r["identity"]["resources"].append(
                {"resource_type": "database", "resource_ref": "resource://db/a", "scope": ["table:a"]}
            ),
            "introduces resource",
        ),
        (lambda r: r["identity"]["resources"][0]["scope"].append("tenant:other"), "expands resource scope"),
    ]

    for mutate, match in mutations:
        raw = _child_dict(parent)
        mutate(raw)
        child = GovernedAgentProfile.model_validate(raw)
        with pytest.raises(ValueError, match=match):
            assert_child_profile_narrower(parent=parent, child=child)


def test_child_tool_cannot_widen() -> None:
    parent = load_profile(PROFILE_PATH)

    mutations = [
        (lambda r: r["tools"].append({
            "name": "new.tool", "adapter": "mcp:new", "action_types": ["new.action"],
            "resource_scope": ["resource:new"], "environments": ["sandbox"]
        }), "introduces tool"),
        (lambda r: r["tools"][0].update(adapter="mcp:other"), "changes adapter"),
        (lambda r: r["tools"][0].update(credential_handle_ref="credential://vault/other"), "changes credential"),
        (lambda r: r["tools"][0]["action_types"].append("search.private"), "expands action_types"),
        (lambda r: r["tools"][0]["resource_scope"].append("network:private"), "expands resource_scope"),
    ]

    for mutate, match in mutations:
        raw = _child_dict(parent)
        mutate(raw)
        child = GovernedAgentProfile.model_validate(raw)
        with pytest.raises(ValueError, match=match):
            assert_child_profile_narrower(parent=parent, child=child)

    parent_raw = _profile_dict()
    parent_raw["tools"][0]["environments"] = ["sandbox"]
    sandbox_parent = GovernedAgentProfile.model_validate(parent_raw)
    raw = _child_dict(sandbox_parent)
    raw["tools"][0]["environments"] = ["sandbox", "live"]
    child = GovernedAgentProfile.model_validate(raw)
    with pytest.raises(ValueError, match="expands environments"):
        assert_child_profile_narrower(parent=sandbox_parent, child=child)


def test_child_budget_and_session_cannot_widen() -> None:
    parent = load_profile(PROFILE_PATH)

    mutations = [
        (lambda r: r.update(budgets=[]), "removes budget domains"),
        (lambda r: r["budgets"].append({
            "budget_id": "new", "currency": "USD", "window": "month", "hard_limit": "1"
        }), "introduces budget domain"),
        (lambda r: r["budgets"][0].update(currency="EUR"), "changes budget semantics"),
        (lambda r: r["budgets"][0].update(hard_limit="6000"), "raises hard limit"),
        (lambda r: r["budgets"][0].pop("soft_limit"), "weakens soft limit"),
        (lambda r: r["budgets"][0].update(soft_limit="600"), "weakens soft limit"),
        (lambda r: r["sessions"].update(default_ttl_seconds=1000), "raises default session TTL"),
        (lambda r: r["sessions"].update(max_ttl_seconds=4000), "raises maximum session TTL"),
    ]

    for mutate, match in mutations:
        raw = _child_dict(parent)
        mutate(raw)
        child = GovernedAgentProfile.model_validate(raw)
        with pytest.raises(ValueError, match=match):
            assert_child_profile_narrower(parent=parent, child=child)


def test_child_approval_cannot_weaken() -> None:
    parent = load_profile(PROFILE_PATH)

    raw = _child_dict(parent)
    raw["approvals"] = [raw["approvals"][1]]
    child = GovernedAgentProfile.model_validate(raw)
    with pytest.raises(ValueError, match="removes approval for payment.charge"):
        assert_child_profile_narrower(parent=parent, child=child)

    raw = _child_dict(parent)
    raw["approvals"][1]["threshold"] = "1"
    raw["approvals"][1]["currency"] = "USD"
    child = GovernedAgentProfile.model_validate(raw)
    with pytest.raises(ValueError, match="weakens always-approval"):
        assert_child_profile_narrower(parent=parent, child=child)

    for mutation in (
        lambda r: r["approvals"][0].update(threshold="501"),
        lambda r: r["approvals"][0].update(currency="EUR"),
    ):
        raw = _child_dict(parent)
        mutation(raw)
        child = GovernedAgentProfile.model_validate(raw)
        with pytest.raises(ValueError, match="raises approval threshold"):
            assert_child_profile_narrower(parent=parent, child=child)

    raw = _child_dict(parent)
    raw["approvals"][0].pop("threshold")
    raw["approvals"][0].pop("currency")
    child = GovernedAgentProfile.model_validate(raw)
    assert_child_profile_narrower(parent=parent, child=child)


def test_cli_all_commands_and_error_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["profile", "validate", str(PROFILE_PATH)]) == 0
    assert json.loads(capsys.readouterr().out)["authorization_boundary"] == "REHT"

    assert main(["profile", "show", str(PROFILE_PATH)]) == 0
    assert json.loads(capsys.readouterr().out)["profile_id"] == "reference-operations-agent"

    assert main(["profile", "tools", str(PROFILE_PATH), "--environment", "live"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 3

    assert main(["profile", "compile", str(PROFILE_PATH), "--runtime-id", "openai-agents"]) == 0
    assert json.loads(capsys.readouterr().out)["contains_secrets"] is False

    assert main([
        "profile", "session-descriptor", str(PROFILE_PATH),
        "--runtime-id", "custom", "--ttl-seconds", "60"
    ]) == 0
    assert json.loads(capsys.readouterr().out)["runtime_id"] == "custom"

    parent = load_profile(PROFILE_PATH)
    child_raw = _child_dict(parent)
    child_path = tmp_path / "child.json"
    child_path.write_text(json.dumps(child_raw), encoding="utf-8")
    assert main(["profile", "compare-parent", str(PROFILE_PATH), str(child_path)]) == 0
    assert json.loads(capsys.readouterr().out)["relationship"] == "narrower_or_equal"

    assert main(["profile", "fingerprint", str(PROFILE_PATH)]) == 0
    assert capsys.readouterr().out.strip() == parent.digest

    missing = tmp_path / "missing.json"
    assert main(["profile", "validate", str(missing)]) == 2
    assert "error:" in capsys.readouterr().err

    malformed = tmp_path / "bad.json"
    malformed.write_text("{", encoding="utf-8")
    assert main(["profile", "validate", str(malformed)]) == 2
    assert "error:" in capsys.readouterr().err

    with pytest.raises(RuntimeError, match="unsupported command"):
        _run(argparse.Namespace(profile_command="unknown"))

    with pytest.raises(SystemExit):
        main(["profile", "tools", str(PROFILE_PATH), "--environment", "invalid"])
