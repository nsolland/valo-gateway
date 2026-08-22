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
    ExecutionMode,
    ExecutionProtocol,
    ExecutionTransportContext,
    RuntimeAgnosticExecutionAdapter,
)


def governed_fixture():
    now = datetime.now(UTC)
    authority = AuthorityEnvelope(
        principal_id="human:owner",
        actor_id="agent:worker",
        source=AuthoritySource.INTERNAL,
        issuer="valo",
        issued_at=now,
        capability_grants=["agent.execute"],
        resource_scope=["agent:remote-1"],
        valid_until=now + timedelta(minutes=10),
    )
    action = ActionEnvelope(
        action_type="agent.execute",
        target="agent:remote-1",
        parameters={"task": "summarize"},
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
        reht_ref="reht:adapter-test",
    )
    permit = issue_execution_permit(
        clearance=clearance,
        authority=authority,
        action=action,
        expires_at=now + timedelta(minutes=1),
        now=now,
    )
    return now, authority, action, clearance, permit


def test_adapter_builds_protocol_neutral_invocation_without_dispatch():
    seen = []
    transport = ExecutionTransportContext(
        execution_context_hash="sha256:context",
        substrate_grant_ref="grant:opaque",
        resume_checkpoint_ref="cp:17",
        headers={"x-trace-id": "trace-1"},
    )
    adapter = RuntimeAgnosticExecutionAdapter(
        protocol=ExecutionProtocol.MCP,
        mode=ExecutionMode.TOOL,
        target="mcp://registry/tool-1",
        transport=transport,
        dispatcher=lambda invocation: seen.append(invocation) or {"ok": True},
    )

    invocation = adapter.build_invocation({"query": "status"})

    assert seen == []
    assert invocation.protocol is ExecutionProtocol.MCP
    assert invocation.mode is ExecutionMode.TOOL
    assert invocation.payload == {"query": "status"}
    assert invocation.transport.substrate_grant_ref == "grant:opaque"
    assert invocation.transport.resume_checkpoint_ref == "cp:17"

    with pytest.raises(PermissionError, match="NO_DIRECT_EFFECT_PATH"):
        adapter.invoke({"query": "status"})
    assert seen == []


@pytest.mark.parametrize(
    "header",
    ["Authorization", "Proxy-Authorization", "Cookie", "X-API-Key", "X-VALO-Permit-Id"],
)
def test_transport_context_rejects_credentials_and_authority_headers(header):
    with pytest.raises(ValueError, match="forbidden transport header"):
        ExecutionTransportContext(
            execution_context_hash="sha256:context",
            headers={header: "secret-or-authority"},
        )


def test_gateway_remains_the_only_execution_gate():
    now, authority, action, clearance, permit = governed_fixture()
    seen = []
    adapter = RuntimeAgnosticExecutionAdapter(
        protocol=ExecutionProtocol.ADK,
        mode=ExecutionMode.REMOTE_AGENT,
        target="adk://managed-agent/remote-1",
        transport=ExecutionTransportContext(
            execution_context_hash="sha256:context",
            substrate_grant_ref="substrate:grant:1",
        ),
        dispatcher=lambda invocation: seen.append(invocation) or {"accepted": True},
    )
    gateway = ValoGateway()

    result = gateway.execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="adapter:adk",
        tool=adapter,
        arguments={"task": "summarize"},
        now=now,
    )

    assert result.response == {"accepted": True}
    assert result.consumed_permit.consumed_at == now
    assert len(seen) == 1

    with pytest.raises(ValueError, match="already consumed"):
        gateway.execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="adapter:adk",
            tool=adapter,
            arguments={"task": "summarize again"},
            now=now,
        )
    assert len(seen) == 1


def test_same_adapter_contract_covers_adk_mcp_and_a2a():
    for protocol, mode in (
        (ExecutionProtocol.ADK, ExecutionMode.AGENT),
        (ExecutionProtocol.MCP, ExecutionMode.TOOL),
        (ExecutionProtocol.A2A, ExecutionMode.REMOTE_AGENT),
    ):
        adapter = RuntimeAgnosticExecutionAdapter(
            protocol=protocol,
            mode=mode,
            target=f"{protocol.value}://target",
            transport=ExecutionTransportContext(execution_context_hash="sha256:ctx"),
            dispatcher=lambda invocation: invocation.protocol.value,
        )
        assert adapter.build_invocation({}).protocol is protocol
        with pytest.raises(PermissionError, match="NO_DIRECT_EFFECT_PATH"):
            adapter.invoke({})
