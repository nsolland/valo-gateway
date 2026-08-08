from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from valo_gateway.contracts import canonical_digest
from valo_gateway.harness import BaseRuntimeAdapter


class BlandExecutionSurface(str, Enum):
    CUSTOM_TOOL = "custom_tool"
    OUTBOUND_CALL = "outbound_call"
    MESSAGE = "message"
    TRANSFER = "transfer"


@dataclass(frozen=True)
class BlandExecutionContext:
    organization_ref: str
    call_ref: str | None = None
    conversation_ref: str | None = None
    persona_ref: str | None = None
    pathway_ref: str | None = None
    pathway_version_ref: str | None = None
    node_ref: str | None = None
    channel: str | None = None
    release_ref: str | None = None
    memory_context_ref: str | None = None
    credential_context_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not self.organization_ref.strip():
            raise ValueError("organization_ref is required")
        fingerprint = self.credential_context_fingerprint
        if fingerprint is not None and not fingerprint.startswith("sha256:"):
            raise ValueError("credential_context_fingerprint must be a sha256 fingerprint")

    def bind(
        self,
        *,
        surface: BlandExecutionSurface,
        source_ref: str,
        operation: str,
        action_type: str,
        target: str,
        parameters: dict[str, Any],
    ) -> str:
        value = {
            "substrate": "bland",
            "surface": surface.value,
            "organization_ref": self.organization_ref,
            "call_ref": self.call_ref,
            "conversation_ref": self.conversation_ref,
            "persona_ref": self.persona_ref,
            "pathway_ref": self.pathway_ref,
            "pathway_version_ref": self.pathway_version_ref,
            "node_ref": self.node_ref,
            "channel": self.channel,
            "release_ref": self.release_ref,
            "memory_context_ref": self.memory_context_ref,
            "credential_context_fingerprint": self.credential_context_fingerprint,
            "source_ref": source_ref,
            "operation": operation,
            "action_type": action_type,
            "target": target,
            "parameters": parameters,
        }
        return "sha256:" + canonical_digest(value)


@dataclass(frozen=True)
class BlandProposedAction:
    surface: BlandExecutionSurface
    source_ref: str
    operation: str
    action_type: str
    target: str
    execution_context_hash: str
    organization_ref: str
    parameters: dict[str, Any] = field(default_factory=dict)
    call_ref: str | None = None
    conversation_ref: str | None = None
    persona_ref: str | None = None
    pathway_ref: str | None = None
    pathway_version_ref: str | None = None
    node_ref: str | None = None
    channel: str | None = None
    release_ref: str | None = None
    memory_context_ref: str | None = None
    credential_context_fingerprint: str | None = None

    def to_runtime_action(self) -> dict[str, Any]:
        return {
            "type": self.action_type,
            "target": self.target,
            "parameters": dict(self.parameters),
            "execution_context_hash": self.execution_context_hash,
            "runtime_context": {
                "substrate": "bland",
                "surface": self.surface.value,
                "source_ref": self.source_ref,
                "operation": self.operation,
                "organization_ref": self.organization_ref,
                "call_ref": self.call_ref,
                "conversation_ref": self.conversation_ref,
                "persona_ref": self.persona_ref,
                "pathway_ref": self.pathway_ref,
                "pathway_version_ref": self.pathway_version_ref,
                "node_ref": self.node_ref,
                "channel": self.channel,
                "release_ref": self.release_ref,
                "memory_context_ref": self.memory_context_ref,
                "credential_context_fingerprint": self.credential_context_fingerprint,
                "route": "valo-gateway",
            },
        }


class BlandRuntime(BaseRuntimeAdapter):
    backend = "bland"

    def normalize_custom_tool(
        self,
        *,
        context: BlandExecutionContext,
        tool_name: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> BlandProposedAction:
        return self._normalize(
            surface=BlandExecutionSurface.CUSTOM_TOOL,
            source_ref=tool_name,
            context=context,
            operation="invoke",
            action_type=action_type,
            target=target,
            parameters=arguments or {},
        )

    def normalize_outbound_call(
        self,
        *,
        context: BlandExecutionContext,
        agent_ref: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> BlandProposedAction:
        return self._normalize(
            surface=BlandExecutionSurface.OUTBOUND_CALL,
            source_ref=agent_ref,
            context=context,
            operation="start_call",
            action_type="communication.call.start",
            target=target,
            parameters=arguments or {},
        )

    def normalize_message(
        self,
        *,
        context: BlandExecutionContext,
        agent_ref: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> BlandProposedAction:
        return self._normalize(
            surface=BlandExecutionSurface.MESSAGE,
            source_ref=agent_ref,
            context=context,
            operation="send_message",
            action_type="communication.message.send",
            target=target,
            parameters=arguments or {},
        )

    def normalize_transfer(
        self,
        *,
        context: BlandExecutionContext,
        agent_ref: str,
        target: str,
        transfer_kind: str = "warm_transfer",
        arguments: dict[str, Any] | None = None,
    ) -> BlandProposedAction:
        return self._normalize(
            surface=BlandExecutionSurface.TRANSFER,
            source_ref=agent_ref,
            context=context,
            operation=transfer_kind,
            action_type="communication.transfer",
            target=target,
            parameters=arguments or {},
        )

    @staticmethod
    def _normalize(
        *,
        surface: BlandExecutionSurface,
        source_ref: str,
        context: BlandExecutionContext,
        operation: str,
        action_type: str,
        target: str,
        parameters: dict[str, Any],
    ) -> BlandProposedAction:
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
        return BlandProposedAction(
            surface=surface,
            source_ref=source_ref,
            operation=operation,
            action_type=action_type,
            target=target,
            parameters=dict(parameters),
            execution_context_hash=execution_context_hash,
            organization_ref=context.organization_ref,
            call_ref=context.call_ref,
            conversation_ref=context.conversation_ref,
            persona_ref=context.persona_ref,
            pathway_ref=context.pathway_ref,
            pathway_version_ref=context.pathway_version_ref,
            node_ref=context.node_ref,
            channel=context.channel,
            release_ref=context.release_ref,
            memory_context_ref=context.memory_context_ref,
            credential_context_fingerprint=context.credential_context_fingerprint,
        )
