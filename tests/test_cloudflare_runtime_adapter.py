import pytest

from valo_gateway.runtime_adapters import (
    CloudflareExecutionContext,
    CloudflareExecutionSurface,
    CloudflareRuntime,
)


def _context(**changes):
    values = {
        "account_ref": "account:primary",
        "deployment_ref": "deployment:prod",
        "durable_object_ref": "do:agent-42",
        "ai_gateway_ref": "aig:default",
        "workflow_instance_ref": "workflow-instance:123",
        "sandbox_ref": "sandbox:build-7",
        "resume_checkpoint_ref": "checkpoint:9",
        "credential_context_fingerprint": "sha256:" + "a" * 64,
    }
    values.update(changes)
    return CloudflareExecutionContext(**values)


def _assert_non_authoritative(action):
    forbidden = {
        "authority_envelope_id",
        "clearance_id",
        "permit_id",
        "decision",
        "policy_digest",
        "authorization",
        "api_token",
        "api_key",
    }
    assert forbidden.isdisjoint(action)
    assert forbidden.isdisjoint(action["runtime_context"])


def test_worker_normalizes_to_gateway_without_authority():
    runtime = CloudflareRuntime()
    proposal = runtime.normalize_worker(
        context=_context(),
        worker_name="billing-worker",
        operation="fetch",
        action_type="invoice.create",
        target="ledger:customer-8",
        arguments={"amount": 900, "currency": "EUR"},
    )

    action = proposal.to_runtime_action()
    assert proposal.surface is CloudflareExecutionSurface.WORKER
    assert action["runtime_context"]["substrate"] == "cloudflare"
    assert action["runtime_context"]["surface"] == "worker"
    assert action["runtime_context"]["route"] == "valo-gateway"
    assert action["execution_context_hash"].startswith("sha256:")
    _assert_non_authoritative(action)


def test_mcp_sandbox_and_workflow_share_same_boundary_contract():
    runtime = CloudflareRuntime()
    context = _context()

    mcp = runtime.normalize_mcp(
        context=context,
        server_name="finance-mcp",
        tool_name="create_invoice",
        action_type="invoice.create",
        target="ledger:customer-8",
    ).to_runtime_action()
    sandbox = runtime.normalize_sandbox(
        context=context,
        sandbox_name="code-runner",
        operation="exec",
        action_type="code.execute",
        target="workspace:job-9",
    ).to_runtime_action()
    workflow = runtime.normalize_workflow(
        context=context,
        workflow_name="settlement",
        operation="start",
        action_type="settlement.run",
        target="settlement:42",
    ).to_runtime_action()

    assert mcp["runtime_context"]["surface"] == "mcp"
    assert sandbox["runtime_context"]["surface"] == "sandbox"
    assert workflow["runtime_context"]["surface"] == "workflow"
    for action in (mcp, sandbox, workflow):
        assert action["runtime_context"]["route"] == "valo-gateway"
        _assert_non_authoritative(action)


def test_context_hash_binds_state_routing_and_execution_metadata():
    runtime = CloudflareRuntime()

    def normalize(context, arguments):
        return runtime.normalize_worker(
            context=context,
            worker_name="records-worker",
            operation="fetch",
            action_type="record.write",
            target="records:42",
            arguments=arguments,
        ).execution_context_hash

    baseline = normalize(_context(), {"b": 2, "a": 1})
    reordered = normalize(_context(), {"a": 1, "b": 2})
    assert baseline == reordered
    assert baseline != normalize(_context(durable_object_ref="do:agent-43"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(ai_gateway_ref="aig:restricted"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(resume_checkpoint_ref="checkpoint:10"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(), {"a": 1, "b": 3})


def test_ai_gateway_and_durable_object_are_context_not_authority():
    runtime = CloudflareRuntime()
    action = runtime.normalize_worker(
        context=_context(),
        worker_name="agent-worker",
        operation="fetch",
        action_type="agent.execute",
        target="agent:42",
    ).to_runtime_action()

    context = action["runtime_context"]
    assert context["ai_gateway_ref"] == "aig:default"
    assert context["durable_object_ref"] == "do:agent-42"
    _assert_non_authoritative(action)


def test_resume_checkpoint_never_encodes_or_revives_a_permit():
    runtime = CloudflareRuntime()
    action = runtime.normalize_workflow(
        context=_context(resume_checkpoint_ref="checkpoint:recovered"),
        workflow_name="long-running-job",
        operation="resume",
        action_type="job.continue",
        target="job:88",
    ).to_runtime_action()

    assert action["runtime_context"]["resume_checkpoint_ref"] == "checkpoint:recovered"
    assert "permit_id" not in action
    assert "permit_id" not in action["runtime_context"]


def test_credentials_and_required_bindings_fail_closed():
    with pytest.raises(ValueError, match="account_ref"):
        _context(account_ref="")
    with pytest.raises(ValueError, match="sha256 fingerprint"):
        _context(credential_context_fingerprint="raw-cloudflare-token")

    runtime = CloudflareRuntime()
    with pytest.raises(ValueError, match="source_ref"):
        runtime.normalize_worker(
            context=_context(),
            worker_name="",
            operation="fetch",
            action_type="x",
            target="y",
        )
    with pytest.raises(ValueError, match="operation"):
        runtime.normalize_sandbox(
            context=_context(),
            sandbox_name="sandbox",
            operation="",
            action_type="x",
            target="y",
        )
