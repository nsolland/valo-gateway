from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from valo_gateway.contracts import canonical_digest
from valo_gateway.harness import BaseRuntimeAdapter


class CloudflareExecutionSurface(str, Enum):
    WORKER = "worker"
    MCP = "mcp"
    SANDBOX = "sandbox"
    WORKFLOW = "workflow"


@dataclass(frozen=True)
class CloudflareExecutionContext:
    account_ref: str
    deployment_ref: str | None = None
    durable_object_ref: str | None = None
    ai_gateway_ref: str | None = None
    workflow_instance_ref: str | None = None
    sandbox_ref: str | None = None
    resume_checkpoint_ref: str | None = None
    credential_context_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not self.account_ref.strip():
            raise ValueError("account_ref is required")
        fingerprint = self.credential_context_fingerprint
        if fingerprint is not None and not fingerprint.startswith("sha256:"):
            raise ValueError("credential_context_fingerprint must be a sha256 fingerprint")

    def bind(
        self,
        *,
        surface: CloudflareExecutionSurface,
        source_ref: str,
        operation: str,
        action_type: str,
        target: str,
        parameters: dict[str, Any],
    ) -> str:
        value = {
            "substrate": "cloudflare",
            "surface": surface.value,
            "account_ref": self.account_ref,
            "deployment_ref": self.deployment_ref,
            "durable_object_ref": self.durable_object_ref,
            "ai_gateway_ref": self.ai_gateway_ref,
            "workflow_instance_ref": self.workflow_instance_ref,
            "sandbox_ref": self.sandbox_ref,
            "resume_checkpoint_ref": self.resume_checkpoint_ref,
            "credential_context_fingerprint": self.credential_context_fingerprint,
            "source_ref": source_ref,
            "operation": operation,
            "action_type": action_type,
            "target": target,
            "parameters": parameters,
        }
        return "sha256:" + canonical_digest(value)


@dataclass(frozen=True)
class CloudflareProposedAction:
    surface: CloudflareExecutionSurface
    source_ref: str
    operation: str
    action_type: str
    target: str
    execution_context_hash: str
    account_ref: str
    parameters: dict[str, Any] = field(default_factory=dict)
    deployment_ref: str | None = None
    durable_object_ref: str | None = None
    ai_gateway_ref: str | None = None
    workflow_instance_ref: str | None = None
    sandbox_ref: str | None = None
    resume_checkpoint_ref: str | None = None
    credential_context_fingerprint: str | None = None

    def to_runtime_action(self) -> dict[str, Any]:
        return {
            "type": self.action_type,
            "target": self.target,
            "parameters": dict(self.parameters),
            "execution_context_hash": self.execution_context_hash,
            "runtime_context": {
                "substrate": "cloudflare",
                "surface": self.surface.value,
                "source_ref": self.source_ref,
                "operation": self.operation,
                "account_ref": self.account_ref,
                "deployment_ref": self.deployment_ref,
                "durable_object_ref": self.durable_object_ref,
                "ai_gateway_ref": self.ai_gateway_ref,
                "workflow_instance_ref": self.workflow_instance_ref,
                "sandbox_ref": self.sandbox_ref,
                "resume_checkpoint_ref": self.resume_checkpoint_ref,
                "credential_context_fingerprint": self.credential_context_fingerprint,
                "route": "valo-gateway",
            },
        }


class CloudflareRuntime(BaseRuntimeAdapter):
    backend = "cloudflare"

    def normalize_worker(
        self,
        *,
        context: CloudflareExecutionContext,
        worker_name: str,
        operation: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> CloudflareProposedAction:
        return self._normalize(
            surface=CloudflareExecutionSurface.WORKER,
            source_ref=worker_name,
            context=context,
            operation=operation,
            action_type=action_type,
            target=target,
            parameters=arguments or {},
        )

    def normalize_mcp(
        self,
        *,
        context: CloudflareExecutionContext,
        server_name: str,
        tool_name: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> CloudflareProposedAction:
        return self._normalize(
            surface=CloudflareExecutionSurface.MCP,
            source_ref=server_name,
            context=context,
            operation=tool_name,
            action_type=action_type,
            target=target,
            parameters=arguments or {},
        )

    def normalize_sandbox(
        self,
        *,
        context: CloudflareExecutionContext,
        sandbox_name: str,
        operation: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> CloudflareProposedAction:
        return self._normalize(
            surface=CloudflareExecutionSurface.SANDBOX,
            source_ref=sandbox_name,
            context=context,
            operation=operation,
            action_type=action_type,
            target=target,
            parameters=arguments or {},
        )

    def normalize_workflow(
        self,
        *,
        context: CloudflareExecutionContext,
        workflow_name: str,
        operation: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> CloudflareProposedAction:
        return self._normalize(
            surface=CloudflareExecutionSurface.WORKFLOW,
            source_ref=workflow_name,
            context=context,
            operation=operation,
            action_type=action_type,
            target=target,
            parameters=arguments or {},
        )

    @staticmethod
    def _normalize(
        *,
        surface: CloudflareExecutionSurface,
        source_ref: str,
        context: CloudflareExecutionContext,
        operation: str,
        action_type: str,
        target: str,
        parameters: dict[str, Any],
    ) -> CloudflareProposedAction:
        if not source_ref.strip():
            raise ValueError("source_ref is required")
        if not operation.strip():
            raise ValueError("operation is required")
        if not action_type.strip():
            raise ValueError("action_type is required")
        if not target.strip():
            raise ValueError("target is required")

        execution_context_hash = context.bind(
            surface=surface,
            source_ref=source_ref,
            operation=operation,
            action_type=action_type,
            target=target,
            parameters=parameters,
        )
        return CloudflareProposedAction(
            surface=surface,
            source_ref=source_ref,
            operation=operation,
            action_type=action_type,
            target=target,
            parameters=dict(parameters),
            execution_context_hash=execution_context_hash,
            account_ref=context.account_ref,
            deployment_ref=context.deployment_ref,
            durable_object_ref=context.durable_object_ref,
            ai_gateway_ref=context.ai_gateway_ref,
            workflow_instance_ref=context.workflow_instance_ref,
            sandbox_ref=context.sandbox_ref,
            resume_checkpoint_ref=context.resume_checkpoint_ref,
            credential_context_fingerprint=context.credential_context_fingerprint,
        )
