from __future__ import annotations

from tests.conftest import make_chain
from valo_gateway import ValoGateway
from valo_gateway.tool_adapters import FunctionTool
from valo_gateway.veritas_handoff import build_veritas_execution_observation


def _result():
    now, authority, action, clearance, permit = make_chain()
    result = ValoGateway().execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="tool:test",
        tool=FunctionTool("x", lambda: {"ok": True}),
        now=now,
    )
    return authority, action, clearance, result


def test_handoff_binds_consumed_permit_authorization_action_and_receipt():
    authority, action, clearance, result = _result()
    payload = build_veritas_execution_observation(
        authority=authority,
        clearance=clearance,
        action=action,
        result=result,
    )

    assert payload["schema"] == "valo.gateway.execution-observation.v1"
    assert payload["execution_id"] == result.receipt.execution_id
    assert payload["permit_id"] == result.consumed_permit.permit_id
    assert payload["permit_consumed_at"] == result.consumed_permit.consumed_at.isoformat()
    assert payload["clearance_id"] == clearance.clearance_id
    assert payload["authority_envelope_id"] == authority.envelope_id
    assert payload["action_digest"] == action.digest
    assert payload["receipt_hash"] == result.receipt.receipt_hash
    assert payload["boundary_replay_digest"] == result.boundary_replay.result_digest
    assert payload["observation_digest"].startswith("sha256:")
    assert payload["authority_granted"] is False


def test_handoff_fails_closed_on_receipt_action_drift():
    authority, action, clearance, result = _result()
    tampered = result.model_copy(
        update={"receipt": result.receipt.model_copy(update={"action_digest": "tampered"})}
    )

    try:
        build_veritas_execution_observation(
            authority=authority,
            clearance=clearance,
            action=action,
            result=tampered,
        )
    except ValueError as exc:
        assert "receipt action binding mismatch" in str(exc)
    else:
        raise AssertionError("tampered receipt must fail closed")
