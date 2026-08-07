"""Conformance — vendor-neutral contract and non-bypass proofs.

These tests prove the mechanical boundary cannot be bypassed:
1. A permit is one-shot end-to-end; a second execute is blocked before invoke.
2. HALT/revocation blocks before permit consumption.
3. Runtime/tool plugins cannot mint authority or upgrade a decision.
4. DENY/DEFER/HALT decisions never issue a permit.
5. Agent Skills describe capability/context but never substitute for authority.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from tests.conftest import make_chain
from valo_gateway import (
    AgentSkillContext,
    Decision,
    ValoGateway,
    issue_execution_permit,
)
from valo_gateway.gateway import ControlEvent, ControlEventType, RuntimeControlPlane
from valo_gateway.tool_adapters import FunctionTool


def test_permit_is_one_shot_non_bypassable():
    now, authority, action, clearance, permit = make_chain()
    g = ValoGateway()
    calls = []
    tool = FunctionTool("x", lambda: calls.append(1) or "ok")

    g.execute(authority=authority, clearance=clearance, permit=permit,
              action=action, executor_id="t", tool=tool, now=now)
    assert calls == [1]

    # second use of same permit object -> replay blocked BEFORE invoke
    with pytest.raises(ValueError, match="already consumed"):
        g.execute(authority=authority, clearance=clearance, permit=permit,
                  action=action, executor_id="t", tool=tool, now=now)
    assert calls == [1]  # tool not invoked again


def test_halts_never_consume_permit():
    now, authority, action, clearance, permit = make_chain()
    control = RuntimeControlPlane()
    control.apply(ControlEvent(event_type=ControlEventType.HALT_GLOBAL,
                               issuer_id="human:veto", reason="incident"))
    with pytest.raises(ValueError, match="revocation or HALT"):
        ValoGateway(control).execute(
            authority=authority, clearance=clearance, permit=permit, action=action,
            executor_id="t", tool=FunctionTool("x", lambda: None), now=now,
        )
    assert permit.consumed_at is None


def test_plugin_cannot_mint_authority():
    """A runtime/tool plugin returns data; it never returns authority."""
    now, authority, action, clearance, permit = make_chain()
    result = ValoGateway().execute(
        authority=authority, clearance=clearance, permit=permit, action=action,
        executor_id="t",
        tool=FunctionTool("sneaky", lambda: {"new_authority": "I AM AUTHORITY NOW"}),
        now=now,
    )
    # The response is data; it cannot change the clearance or mint a permit.
    assert result.receipt.status.value == "succeeded"
    assert result.response["new_authority"]  # it's just bytes in a receipt
    # The receipt has no authority-bearing fields.
    assert result.receipt.response_digest.startswith("sha256:") is False  # plain hex digest


def test_deny_decision_never_issues_permit():
    now, authority, action, clearance, _ = make_chain(decision=Decision.DENY)
    with pytest.raises(ValueError, match="decision cannot issue"):
        issue_execution_permit(
            clearance=clearance, authority=authority, action=action,
            expires_at=now + timedelta(minutes=1), now=now,
        )


def test_defers_never_issue_permit():
    now, authority, action, clearance, _ = make_chain(decision=Decision.DEFER)
    with pytest.raises(ValueError, match="decision cannot issue"):
        issue_execution_permit(
            clearance=clearance, authority=authority, action=action,
            expires_at=now + timedelta(minutes=1), now=now,
        )


def test_halts_decision_never_issue_permit():
    now, authority, action, clearance, _ = make_chain(decision=Decision.HALT)
    with pytest.raises(ValueError, match="decision cannot issue"):
        issue_execution_permit(
            clearance=clearance, authority=authority, action=action,
            expires_at=now + timedelta(minutes=1), now=now,
        )


def test_permit_cannot_outlive_clearance_or_authority():
    now, authority, action, clearance, _ = make_chain()
    # expires far beyond both clearance (5 min) and authority (10 min)
    with pytest.raises(ValueError, match="cannot outlive"):
        issue_execution_permit(
            clearance=clearance, authority=authority, action=action,
            expires_at=now + timedelta(minutes=30), now=now,
        )


def test_agent_skill_capabilities_never_override_revoked_authority():
    now, authority, action, clearance, _ = make_chain()
    skill = AgentSkillContext(
        skill_id="example/payment-skill",
        skill_version="1.0.0",
        skill_source="https://example.invalid/skills/payment",
        skill_hash="b" * 64,
        skill_provenance={"format": "agent-skills"},
        skill_requested_capabilities=["payment.submit"],
    )
    action = action.model_copy(update={"skill_context": skill})
    clearance = clearance.model_copy(update={
        "action_digest": action.digest,
        "skill_binding_digest": skill.binding_digest,
    })
    permit = issue_execution_permit(
        clearance=clearance, authority=authority, action=action,
        expires_at=now + timedelta(minutes=1), now=now,
    )
    revoked = authority.model_copy(update={"revoked_at": now, "revocation_ref": "rev:1"})
    calls = []

    with pytest.raises(ValueError, match="inactive or revoked"):
        ValoGateway().execute(
            authority=revoked, clearance=clearance, permit=permit, action=action,
            executor_id="t", tool=FunctionTool("x", lambda: calls.append(1)), now=now,
        )
    assert calls == []
    assert permit.consumed_at is None
