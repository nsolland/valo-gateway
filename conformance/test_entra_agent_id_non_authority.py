from datetime import UTC, datetime, timedelta

from valo_gateway.identity_adapters import (
    ConditionalAccessDecision,
    EntraAgentAccessMode,
    EntraAgentIdContext,
)


def test_entra_access_state_cannot_mint_gateway_authority():
    issued = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    context = EntraAgentIdContext(
        tenant_id="tenant-1",
        agent_identity_id="agent-123",
        access_mode=EntraAgentAccessMode.AUTONOMOUS,
        audience="https://graph.microsoft.com",
        application_permissions=["User.Read.All"],
        conditional_access=ConditionalAccessDecision.ALLOW,
        token_issued_at=issued,
        token_expires_at=issued + timedelta(hours=1),
    )

    evidence = context.to_reht_evidence()

    assert evidence["authoritative"] is False
    assert not hasattr(context, "issue_clearance")
    assert not hasattr(context, "issue_execution_permit")
    assert not hasattr(context, "authorize")
