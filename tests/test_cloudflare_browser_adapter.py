from datetime import UTC, datetime, timedelta

import pytest

from valo_gateway import (
    ActionEnvelope,
    AuthorityEnvelope,
    AuthoritySource,
    Clearance,
    Decision,
    DecisionContract,
    ValoGateway,
    issue_execution_permit,
)
from valo_gateway.runtime_adapters import (
    CloudflareBrowserBackend,
    CloudflareBrowserContext,
    CloudflareBrowserRunAdapter,
    ExecutionMode,
    ExecutionProtocol,
)


def governed_fixture():
    now = datetime.now(UTC)
    authority = AuthorityEnvelope(
        principal_id="human:owner",
        actor_id="agent:speider",
        source=AuthoritySource.INTERNAL,
        issuer="valo",
        issued_at=now,
        capability_grants=["browser.navigate"],
        resource_scope=["browser:https://example.com"],
        valid_until=now + timedelta(minutes=10),
    )
    action = ActionEnvelope(
        action_type="browser.navigate",
        target="browser:https://example.com",
        parameters={"url": "https://example.com"},
        context_digest="ctx",
        policy_digest="policy",
        authority_envelope_id=authority.envelope_id,
    )
    contract = DecisionContract(
        decision=Decision.ALLOW,
        principal_id=authority.principal_id,
        actor_id=authority.actor_id,
        action_type=action.action_type,
        target=action.target,
    )
    clearance = Clearance(
        action_digest=action.digest,
        authority_envelope_id=authority.envelope_id,
        decision_contract=contract,
        valid_until=now + timedelta(minutes=5),
        reht_ref="reht:cloudflare-browser-test",
    )
    permit = issue_execution_permit(
        clearance=clearance,
        authority=authority,
        action=action,
        expires_at=now + timedelta(minutes=1),
        now=now,
    )
    return now, authority, action, clearance, permit


def test_cloudflare_adapter_is_browser_cdp_execution_substrate():
    seen = []
    context = CloudflareBrowserContext(
        account_ref="cloudflare-account:primary",
        backend=CloudflareBrowserBackend.KITESURF,
        session_ref="session:ephemeral-1",
        recording_ref="recording:1",
    )
    adapter = CloudflareBrowserRunAdapter(
        context=context,
        execution_context_hash="sha256:browser-context",
        dispatcher=lambda invocation: seen.append(invocation) or {"ok": True},
    )

    result = adapter.invoke({"operation": "navigate", "url": "https://example.com"})

    assert result == {"ok": True}
    assert len(seen) == 1
    invocation = seen[0]
    assert invocation.protocol is ExecutionProtocol.CDP
    assert invocation.mode is ExecutionMode.BROWSER
    assert invocation.payload["provider"] == "cloudflare-browser-run"
    assert invocation.payload["browser_context"]["backend"] == "kitesurf"
    assert invocation.payload["browser_context"]["authority_effect"] == "none"
    assert invocation.payload["arguments"]["operation"] == "navigate"


@pytest.mark.parametrize(
    "authority_field",
    [
        "authority_envelope_id",
        "authority_grant",
        "clearance_id",
        "decision_contract",
        "execution_permit",
        "permit_id",
        "reht_clearance",
        "reht_decision",
    ],
)
def test_cloudflare_payload_rejects_authority_injection(authority_field):
    adapter = CloudflareBrowserRunAdapter(
        context=CloudflareBrowserContext(account_ref="cloudflare-account:primary"),
        execution_context_hash="sha256:browser-context",
        dispatcher=lambda invocation: invocation,
    )

    with pytest.raises(ValueError, match="cannot carry authority field"):
        adapter.invoke({"nested": {authority_field: "forged"}})


def test_cloudflare_operational_state_is_non_authoritative():
    context = CloudflareBrowserContext(
        account_ref="cloudflare-account:primary",
        session_ref="session:1",
        recording_ref="recording:1",
        live_view_ref="live-view:1",
        human_intervention_ref="human-intervention:1",
    )

    assert context.authority_effect == "none"
    assert not hasattr(context, "authorize")
    assert not hasattr(context, "to_execution_permit")


def test_gateway_remains_the_execution_gate_for_cloudflare():
    now, authority, action, clearance, permit = governed_fixture()
    seen = []
    adapter = CloudflareBrowserRunAdapter(
        context=CloudflareBrowserContext(account_ref="cloudflare-account:primary"),
        execution_context_hash="sha256:browser-context",
        dispatcher=lambda invocation: seen.append(invocation) or {"navigated": True},
    )

    result = ValoGateway().execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="adapter:cloudflare-browser-run",
        tool=adapter,
        arguments={"url": "https://example.com"},
        now=now,
    )

    assert result.response == {"navigated": True}
    assert len(seen) == 1

    with pytest.raises(ValueError, match="already consumed"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="adapter:cloudflare-browser-run",
            tool=adapter,
            arguments={"url": "https://example.com"},
            now=now,
        )
    assert len(seen) == 1
