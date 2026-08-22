from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from valo_gateway.tool_adapters.base import BoundaryProof, _validate_boundary_proof


class ExecutionProtocol(str, Enum):
    ADK = "adk"
    MCP = "mcp"
    A2A = "a2a"
    CDP = "cdp"


class ExecutionMode(str, Enum):
    AGENT = "agent"
    TOOL = "tool"
    REMOTE_AGENT = "remote_agent"
    SANDBOX = "sandbox"
    BROWSER = "browser"


class ExecutionTransportContext(BaseModel):
    execution_context_hash: str
    substrate_grant_ref: str | None = None
    resume_checkpoint_ref: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("execution_context_hash")
    @classmethod
    def require_context_hash(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("execution_context_hash is required")
        return value

    @field_validator("headers")
    @classmethod
    def reject_authority_and_credentials(cls, value: dict[str, str]) -> dict[str, str]:
        forbidden = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"}
        authority_prefixes = ("x-valo-authority", "x-valo-clearance", "x-valo-permit")
        for key in value:
            normalized = key.strip().lower()
            if normalized in forbidden or normalized.startswith(authority_prefixes):
                raise ValueError(f"forbidden transport header: {key}")
        return value


class ExecutionInvocation(BaseModel):
    protocol: ExecutionProtocol
    mode: ExecutionMode
    target: str
    payload: dict[str, Any] = Field(default_factory=dict)
    transport: ExecutionTransportContext
    model_config = ConfigDict(extra="forbid", frozen=True)


ExecutionDispatcher = Callable[[ExecutionInvocation], Any]


class RuntimeAgnosticExecutionAdapter:
    def __init__(
        self,
        *,
        protocol: ExecutionProtocol,
        mode: ExecutionMode,
        target: str,
        transport: ExecutionTransportContext,
        dispatcher: ExecutionDispatcher,
    ) -> None:
        if not target.strip():
            raise ValueError("execution target is required")
        self.protocol = protocol
        self.mode = mode
        self.target = target
        self.transport = transport
        self._dispatcher = dispatcher

    def build_invocation(self, arguments: dict[str, Any]) -> ExecutionInvocation:
        return ExecutionInvocation(
            protocol=self.protocol,
            mode=self.mode,
            target=self.target,
            payload=arguments,
            transport=self.transport,
        )

    def invoke(self, arguments: dict[str, Any]) -> Any:
        raise PermissionError(
            "NO_DIRECT_EFFECT_PATH: use ValoGateway governed enforcement"
        )

    def _invoke_from_boundary(
        self,
        arguments: dict[str, Any],
        proof: BoundaryProof,
    ) -> Any:
        _validate_boundary_proof(proof)
        return self._dispatcher(self.build_invocation(arguments))
