from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from valo_gateway.contracts import canonical_digest
from valo_gateway.harness import BaseRuntimeAdapter


@dataclass(frozen=True)
class GeminiExecutionContext:
    interaction_id: str
    environment_id: str
    background: bool = False
    credential_context_fingerprint: str | None = None
    substrate_grant_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.interaction_id.strip():
            raise ValueError("interaction_id is required")
        if not self.environment_id.strip():
            raise ValueError("environment_id is required")
        fingerprint = self.credential_context_fingerprint
        if fingerprint is not None and not fingerprint.startswith("sha256:"):
            raise ValueError("credential_context_fingerprint must be a sha256 fingerprint")

    def bind(
        self,
        *,
        source_kind: str,
        tool_name: str,
        action_type: str,
        target: str,
        parameters: dict[str, Any],
        source_ref: str | None = None,
    ) -> str:
        value = {
            "substrate": "google-gemini-managed",
            "interaction_id": self.interaction_id,
            "environment_id": self.environment_id,
            "background": self.background,
            "credential_context_fingerprint": self.credential_context_fingerprint,
            "substrate_grant_ref": self.substrate_grant_ref,
            "source_kind": source_kind,
            "source_ref": source_ref,
            "tool_name": tool_name,
            "action_type": action_type,
            "target": target,
            "parameters": parameters,
        }
        return "sha256:" + canonical_digest(value)


@dataclass(frozen=True)
class GeminiProposedAction:
    source_kind: str
    tool_name: str
    action_type: str
    target: str
    execution_context_hash: str
    interaction_id: str
    environment_id: str
    background: bool
    parameters: dict[str, Any] = field(default_factory=dict)
    credential_context_fingerprint: str | None = None
    substrate_grant_ref: str | None = None
    source_ref: str | None = None

    def to_runtime_action(self) -> dict[str, Any]:
        return {
            "type": self.action_type,
            "target": self.target,
            "parameters": dict(self.parameters),
            "execution_context_hash": self.execution_context_hash,
            "runtime_context": {
                "substrate": "google-gemini-managed",
                "source_kind": self.source_kind,
                "source_ref": self.source_ref,
                "tool_name": self.tool_name,
                "interaction_id": self.interaction_id,
                "environment_id": self.environment_id,
                "background": self.background,
                "credential_context_fingerprint": self.credential_context_fingerprint,
                "substrate_grant_ref": self.substrate_grant_ref,
                "route": "valo-gateway",
            },
        }


class GeminiManagedRuntime(BaseRuntimeAdapter):
    backend = "google-gemini-managed"

    def normalize_requires_action(
        self,
        *,
        context: GeminiExecutionContext,
        tool_name: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> GeminiProposedAction:
        return self._normalize(
            source_kind="requires_action",
            source_ref=None,
            context=context,
            tool_name=tool_name,
            action_type=action_type,
            target=target,
            parameters=arguments or {},
        )

    def normalize_remote_mcp(
        self,
        *,
        context: GeminiExecutionContext,
        server_name: str,
        tool_name: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> GeminiProposedAction:
        if not server_name.strip():
            raise ValueError("server_name is required")
        return self._normalize(
            source_kind="remote_mcp",
            source_ref=server_name,
            context=context,
            tool_name=tool_name,
            action_type=action_type,
            target=target,
            parameters=arguments or {},
        )

    @staticmethod
    def _normalize(
        *,
        source_kind: str,
        source_ref: str | None,
        context: GeminiExecutionContext,
        tool_name: str,
        action_type: str,
        target: str,
        parameters: dict[str, Any],
    ) -> GeminiProposedAction:
        if not tool_name.strip():
            raise ValueError("tool_name is required")
        if not action_type.strip():
            raise ValueError("action_type is required")
        if not target.strip():
            raise ValueError("target is required")
        execution_context_hash = context.bind(
            source_kind=source_kind,
            source_ref=source_ref,
            tool_name=tool_name,
            action_type=action_type,
            target=target,
            parameters=parameters,
        )
        return GeminiProposedAction(
            source_kind=source_kind,
            source_ref=source_ref,
            tool_name=tool_name,
            action_type=action_type,
            target=target,
            parameters=dict(parameters),
            execution_context_hash=execution_context_hash,
            interaction_id=context.interaction_id,
            environment_id=context.environment_id,
            background=context.background,
            credential_context_fingerprint=context.credential_context_fingerprint,
            substrate_grant_ref=context.substrate_grant_ref,
        )
