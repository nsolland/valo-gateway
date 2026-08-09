from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from valo_gateway.contracts import canonical_digest
from valo_gateway.harness import BaseRuntimeAdapter


class ClaudeRunnerMode(str, Enum):
    FIXED = "fixed"
    ON_DEMAND = "on_demand"


@dataclass(frozen=True)
class ClaudeSelfHostedExecutionContext:
    environment_ref: str
    session_ref: str
    runner_ref: str | None = None
    runner_mode: ClaudeRunnerMode | None = None
    checkout_ref: str | None = None
    credential_context_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not self.environment_ref.strip():
            raise ValueError("environment_ref is required")
        if not self.session_ref.strip():
            raise ValueError("session_ref is required")
        fingerprint = self.credential_context_fingerprint
        if fingerprint is not None and not fingerprint.startswith("sha256:"):
            raise ValueError("credential_context_fingerprint must be a sha256 fingerprint")

    def bind(
        self,
        *,
        source_ref: str,
        operation: str,
        action_type: str,
        target: str,
        parameters: dict[str, Any],
    ) -> str:
        value = {
            "substrate": "claude_code_self_hosted",
            "environment_ref": self.environment_ref,
            "session_ref": self.session_ref,
            "runner_ref": self.runner_ref,
            "runner_mode": self.runner_mode.value if self.runner_mode else None,
            "checkout_ref": self.checkout_ref,
            "credential_context_fingerprint": self.credential_context_fingerprint,
            "source_ref": source_ref,
            "operation": operation,
            "action_type": action_type,
            "target": target,
            "parameters": parameters,
        }
        return "sha256:" + canonical_digest(value)


@dataclass(frozen=True)
class ClaudeSelfHostedProposedAction:
    source_ref: str
    operation: str
    action_type: str
    target: str
    execution_context_hash: str
    environment_ref: str
    session_ref: str
    parameters: dict[str, Any] = field(default_factory=dict)
    runner_ref: str | None = None
    runner_mode: ClaudeRunnerMode | None = None
    checkout_ref: str | None = None
    credential_context_fingerprint: str | None = None

    def to_runtime_action(self) -> dict[str, Any]:
        return {
            "type": self.action_type,
            "target": self.target,
            "parameters": dict(self.parameters),
            "execution_context_hash": self.execution_context_hash,
            "runtime_context": {
                "substrate": "claude_code_self_hosted",
                "source_ref": self.source_ref,
                "operation": self.operation,
                "environment_ref": self.environment_ref,
                "session_ref": self.session_ref,
                "runner_ref": self.runner_ref,
                "runner_mode": self.runner_mode.value if self.runner_mode else None,
                "checkout_ref": self.checkout_ref,
                "credential_context_fingerprint": self.credential_context_fingerprint,
                "route": "valo-gateway",
            },
        }


class ClaudeSelfHostedRuntime(BaseRuntimeAdapter):
    backend = "claude_code_self_hosted"

    def normalize_action(
        self,
        *,
        context: ClaudeSelfHostedExecutionContext,
        source_ref: str,
        operation: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> ClaudeSelfHostedProposedAction:
        if not source_ref.strip():
            raise ValueError("source_ref is required")
        if not operation.strip():
            raise ValueError("operation is required")
        if not action_type.strip():
            raise ValueError("action_type is required")
        if not target.strip():
            raise ValueError("target is required")

        parameters = dict(arguments or {})
        execution_context_hash = context.bind(
            source_ref=source_ref,
            operation=operation,
            action_type=action_type,
            target=target,
            parameters=parameters,
        )
        return ClaudeSelfHostedProposedAction(
            source_ref=source_ref,
            operation=operation,
            action_type=action_type,
            target=target,
            parameters=parameters,
            execution_context_hash=execution_context_hash,
            environment_ref=context.environment_ref,
            session_ref=context.session_ref,
            runner_ref=context.runner_ref,
            runner_mode=context.runner_mode,
            checkout_ref=context.checkout_ref,
            credential_context_fingerprint=context.credential_context_fingerprint,
        )
