import pytest

from valo_gateway.runtime_adapters import (
    ClaudeRunnerMode,
    ClaudeSelfHostedExecutionContext,
    ClaudeSelfHostedRuntime,
)


def _context(**changes):
    values = {
        "environment_ref": "env:prod",
        "session_ref": "session:123",
        "runner_ref": "runner:7",
        "runner_mode": ClaudeRunnerMode.ON_DEMAND,
        "checkout_ref": "checkout:repo@abc123",
        "credential_context_fingerprint": "sha256:" + "b" * 64,
    }
    values.update(changes)
    return ClaudeSelfHostedExecutionContext(**values)


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
        "secret",
    }
    assert forbidden.isdisjoint(action)
    assert forbidden.isdisjoint(action["runtime_context"])


def test_self_hosted_action_routes_through_gateway_without_authority():
    runtime = ClaudeSelfHostedRuntime()
    proposal = runtime.normalize_action(
        context=_context(),
        source_ref="claude-code",
        operation="git.push",
        action_type="repository.push",
        target="repo:nsolland/example",
        arguments={"branch": "feat/example"},
    )

    action = proposal.to_runtime_action()
    assert action["runtime_context"]["substrate"] == "claude_code_self_hosted"
    assert action["runtime_context"]["route"] == "valo-gateway"
    assert action["runtime_context"]["runner_mode"] == "on_demand"
    assert action["execution_context_hash"].startswith("sha256:")
    _assert_non_authoritative(action)


def test_context_hash_binds_session_runner_checkout_and_arguments():
    runtime = ClaudeSelfHostedRuntime()

    def normalize(context, arguments):
        return runtime.normalize_action(
            context=context,
            source_ref="claude-code",
            operation="internal-api.call",
            action_type="record.write",
            target="internal:records/42",
            arguments=arguments,
        ).execution_context_hash

    baseline = normalize(_context(), {"b": 2, "a": 1})
    reordered = normalize(_context(), {"a": 1, "b": 2})
    assert baseline == reordered
    assert baseline != normalize(_context(session_ref="session:124"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(runner_ref="runner:8"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(checkout_ref="checkout:repo@def456"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(), {"a": 1, "b": 3})


def test_runner_mode_and_credentials_are_context_not_authority():
    runtime = ClaudeSelfHostedRuntime()
    action = runtime.normalize_action(
        context=_context(runner_mode=ClaudeRunnerMode.FIXED),
        source_ref="claude-code",
        operation="tool.call",
        action_type="tool.execute",
        target="mcp:finance/create_invoice",
    ).to_runtime_action()

    assert action["runtime_context"]["runner_mode"] == "fixed"
    assert action["runtime_context"]["credential_context_fingerprint"].startswith("sha256:")
    _assert_non_authoritative(action)


def test_required_bindings_and_credentials_fail_closed():
    with pytest.raises(ValueError, match="environment_ref"):
        _context(environment_ref="")
    with pytest.raises(ValueError, match="session_ref"):
        _context(session_ref="")
    with pytest.raises(ValueError, match="sha256 fingerprint"):
        _context(credential_context_fingerprint="raw-secret")

    runtime = ClaudeSelfHostedRuntime()
    with pytest.raises(ValueError, match="source_ref"):
        runtime.normalize_action(
            context=_context(),
            source_ref="",
            operation="exec",
            action_type="code.execute",
            target="workspace:job-1",
        )
    with pytest.raises(ValueError, match="operation"):
        runtime.normalize_action(
            context=_context(),
            source_ref="claude-code",
            operation="",
            action_type="code.execute",
            target="workspace:job-1",
        )
