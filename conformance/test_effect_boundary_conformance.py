from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from tests.conftest import make_chain
from valo_gateway import (
    BoundaryReplayInput,
    BoundaryReplayOutcome,
    Decision,
    ExecutionPermit,
    GovernanceBasisState,
    ValoGateway,
    issue_execution_permit,
    replay_effect_boundary,
)
from valo_gateway.tool_adapters import EffectorHandle, FunctionTool, ToolRegistry

NON_ALLOW = (Decision.DENY, Decision.DEFER, Decision.STEP_UP, Decision.HALT)
INVALID_BASIS = (
    GovernanceBasisState.INVALID,
    GovernanceBasisState.STALE,
    GovernanceBasisState.REVOKED,
    GovernanceBasisState.SUSPENDED,
    GovernanceBasisState.UNRESOLVED,
)


def _fake_permit(now, authority, action, clearance) -> ExecutionPermit:
    return ExecutionPermit(
        clearance_id=clearance.clearance_id,
        action_digest=action.digest,
        authority_envelope_id=authority.envelope_id,
        issued_at=now,
        expires_at=now + timedelta(minutes=1),
    )


def _memory_write_chain():
    now, authority, action, clearance, _ = make_chain()
    authority = authority.model_copy(
        update={
            "capability_grants": ["memory.write"],
            "resource_scope": ["memory:decision-context"],
        }
    )
    action = action.model_copy(
        update={
            "action_type": "memory.write",
            "target": "memory:decision-context",
            "parameters": {"value": "candidate"},
        }
    )
    decision_contract = clearance.decision_contract.model_copy(
        update={
            "action_type": action.action_type,
            "target": action.target,
        }
    )
    clearance = clearance.model_copy(
        update={
            "action_digest": action.digest,
            "decision_contract": decision_contract,
        }
    )
    permit = issue_execution_permit(
        clearance=clearance,
        authority=authority,
        action=action,
        expires_at=now + timedelta(minutes=1),
        now=now,
    )
    return now, authority, action, clearance, permit


@pytest.mark.parametrize("decision", NON_ALLOW)
def test_null_effect_on_non_allow_decisions(decision: Decision) -> None:
    now, authority, action, clearance, _ = make_chain(decision=decision)
    permit = _fake_permit(now, authority, action, clearance)
    replay_input = BoundaryReplayInput.capture(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        governance_basis_state=GovernanceBasisState.VALID,
        evaluated_at=now,
    )
    replay = replay_effect_boundary(
        replay_input,
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
    )
    assert replay.outcome is BoundaryReplayOutcome.BLOCKED
    assert replay.reason == "NULL_EFFECT_ON_DENY"
    assert replay.effect_allowed is False

    calls: list[int] = []
    with pytest.raises(ValueError, match="clearance is no longer valid"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="effector:payment",
            tool=FunctionTool("payment", lambda: calls.append(1)),
            now=now,
            boundary_replay=replay_input,
        )
    assert calls == []
    assert permit.consumed_at is None


@pytest.mark.parametrize("decision", NON_ALLOW)
def test_non_allow_cannot_issue_permit(decision: Decision) -> None:
    now, authority, action, clearance, _ = make_chain(decision=decision)
    with pytest.raises(ValueError, match="decision cannot issue"):
        issue_execution_permit(
            clearance=clearance,
            authority=authority,
            action=action,
            expires_at=now + timedelta(minutes=1),
            now=now,
        )


@pytest.mark.parametrize("basis_state", INVALID_BASIS)
def test_structural_coupling_blocks_non_current_governance_basis(
    basis_state: GovernanceBasisState,
) -> None:
    now, authority, action, clearance, permit = make_chain()
    replay_input = BoundaryReplayInput.capture(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        governance_basis_state=basis_state,
        evaluated_at=now,
    )
    calls: list[int] = []

    with pytest.raises(ValueError, match=f"GOVERNANCE_BASIS_{basis_state.value}"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="effector:payment",
            tool=FunctionTool("payment", lambda: calls.append(1)),
            now=now,
            boundary_replay=replay_input,
        )

    assert calls == []
    assert permit.consumed_at is None


def test_boundary_replay_is_deterministic_and_never_reexecutes_effect() -> None:
    now, authority, action, clearance, permit = make_chain()
    replay_input = BoundaryReplayInput.capture(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        governance_basis_state=GovernanceBasisState.VALID,
        evaluated_at=now,
    )

    first = replay_effect_boundary(
        replay_input,
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
    )
    second = replay_effect_boundary(
        replay_input,
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
    )

    assert first == second
    assert first.result_digest == second.result_digest
    assert first.effect_allowed is True
    assert {
        "contract_digest",
        "state_digest",
        "authority_digest",
        "evidence_digest",
        "decision_digest",
    }.issubset(BoundaryReplayInput.model_fields)
    assert not {
        "prompt",
        "completion",
        "tokens",
        "transcript",
        "reasoning_trace",
    }.intersection(BoundaryReplayInput.model_fields)


@pytest.mark.parametrize(
    "field",
    (
        "contract_digest",
        "state_digest",
        "authority_digest",
        "evidence_digest",
        "decision_digest",
    ),
)
def test_boundary_replay_fails_closed_on_pinned_input_tampering(field: str) -> None:
    now, authority, action, clearance, permit = make_chain()
    original = BoundaryReplayInput.capture(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        governance_basis_state=GovernanceBasisState.VALID,
        evaluated_at=now,
    )
    changed = original.model_copy(update={field: "0" * 64, "input_digest": ""})
    tampered = changed.model_copy(update={"input_digest": changed.computed_digest})

    result = replay_effect_boundary(
        tampered,
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
    )

    assert result.outcome is BoundaryReplayOutcome.BLOCKED
    assert result.reason == f"PINNED_INPUT_MISMATCH:{field}"
    assert result.effect_allowed is False


def test_effector_credentials_and_capability_exist_only_behind_boundary() -> None:
    now, authority, action, clearance, permit = make_chain()
    calls: list[int] = []
    tool = FunctionTool("payment", lambda amount: calls.append(amount) or "ok")
    registry = ToolRegistry()
    handle = registry.register(
        tool,
        capability=action.action_type,
        target=action.target,
        credential_ref="vault://effectors/payments/primary",
    )

    assert registry.get("payment") == handle
    assert not hasattr(handle, "invoke")
    with pytest.raises(PermissionError, match="NO_DIRECT_EFFECT_PATH"):
        tool.invoke({"amount": 1250})
    assert calls == []

    result = ValoGateway().execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="effector:payment",
        effector_registry=registry,
        effector_handle=handle,
        arguments={"amount": 1250},
        now=now,
    )

    assert result.response == "ok"
    assert result.boundary_replay.effect_allowed is True
    assert result.receipt.boundary_replay_digest == result.boundary_replay.result_digest
    assert calls == [1250]


def test_negative_bypass_forged_effector_handle_fails_before_effect() -> None:
    now, authority, action, clearance, permit = make_chain()
    calls: list[int] = []
    registry = ToolRegistry()
    handle = registry.register(
        FunctionTool("payment", lambda: calls.append(1)),
        capability=action.action_type,
        target=action.target,
        credential_ref="credential://payments/runtime",
    )
    forged: EffectorHandle = replace(handle, target="invoice:other")

    with pytest.raises(PermissionError, match="not owned|exact action"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="effector:payment",
            effector_registry=registry,
            effector_handle=forged,
            now=now,
        )

    assert calls == []
    assert permit.consumed_at is None


def test_negative_bypass_raw_credential_material_is_rejected() -> None:
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="opaque references"):
        registry.register(
            FunctionTool("payment", lambda: None),
            capability="payment.submit",
            target="invoice:123",
            credential_ref="sk-live-secret-material",
        )


def test_decision_relevant_memory_write_uses_the_same_governed_path() -> None:
    now, authority, action, clearance, permit = _memory_write_chain()
    writes: list[str] = []
    tool = FunctionTool(
        "decision-memory",
        lambda value: writes.append(value) or "stored",
    )
    registry = ToolRegistry()
    handle = registry.register(
        tool,
        capability="memory.write",
        target="memory:decision-context",
        credential_ref="credential://kernel-memory/writer",
    )

    with pytest.raises(PermissionError, match="NO_DIRECT_EFFECT_PATH"):
        tool.invoke({"value": "candidate"})
    assert writes == []

    result = ValoGateway().execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="effector:decision-memory",
        effector_registry=registry,
        effector_handle=handle,
        arguments={"value": "candidate"},
        now=now,
    )

    assert result.response == "stored"
    assert writes == ["candidate"]


@pytest.mark.parametrize(
    ("authority_field", "expected"),
    (
        ("capability_grants", ["memory.read"]),
        ("resource_scope", ["memory:other"]),
    ),
)
def test_decision_relevant_memory_write_requires_exact_current_authority(
    authority_field: str,
    expected: list[str],
) -> None:
    now, authority, action, clearance, permit = _memory_write_chain()
    narrowed = authority.model_copy(update={authority_field: expected})
    calls: list[int] = []

    with pytest.raises(ValueError, match="outside authority"):
        ValoGateway().execute(
            authority=narrowed,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="effector:memory",
            tool=FunctionTool("memory-write", lambda: calls.append(1)),
            now=now,
        )

    assert calls == []
    assert permit.consumed_at is None
