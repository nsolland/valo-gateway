from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from valo_gateway.contracts import (
    ActionEnvelope,
    AuthorityEnvelope,
    Clearance,
    ExecutionPermit,
)
from valo_gateway.gateway import ToolExecutionResult, ValoGateway
from valo_gateway.harness import BaseRuntimeAdapter

_FORBIDDEN_AUTHORITY_KEYS = {
    "authority_envelope_id",
    "clearance",
    "clearance_id",
    "decision",
    "decision_contract",
    "execution_permit",
    "permit",
    "permit_id",
    "reht_ref",
}

_FORBIDDEN_SECRET_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "bearer_token",
    "client_secret",
    "password",
    "refresh_token",
    "secret",
}


def _reject_forbidden_runtime_material(value: Any, *, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_AUTHORITY_KEYS:
                raise ValueError(f"ADK runtime metadata cannot supply authority field: {path}.{key}")
            if normalized in _FORBIDDEN_SECRET_KEYS:
                raise ValueError(f"ADK runtime metadata cannot carry raw credential material: {path}.{key}")
            _reject_forbidden_runtime_material(nested, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_forbidden_runtime_material(nested, path=f"{path}[{index}]")


class ADKCredentialBinding(BaseModel):
    credential_ref: str
    provider_ref: str | None = None
    principal_ref: str | None = None
    user_ref: str | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)


class ADKRegistryRecord(BaseModel):
    kind: Literal["agent", "mcp_server", "model_endpoint", "tool"]
    ref: str
    name: str | None = None
    endpoint_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def reject_authority_or_secrets(self) -> ADKRegistryRecord:
        _reject_forbidden_runtime_material(self.metadata, path="registry.metadata")
        return self


class ADKGoInvocationContext(BaseModel):
    runtime: Literal["google-adk-go"] = "google-adk-go"
    runtime_version: str = "2.1.x"
    agent_name: str | None = None
    agent_ref: str | None = None
    registry_ref: str | None = None
    model_ref: str | None = None
    tool_name: str | None = None
    tool_ref: str | None = None
    mcp_server_ref: str | None = None
    remote_agent_ref: str | None = None
    principal_ref: str | None = None
    actor_ref: str | None = None
    credential: ADKCredentialBinding | None = None
    task_run_id: str | None = None
    node_id: str | None = None
    span_id: str | None = None
    deadline_ns: int | None = Field(default=None, ge=0)
    cancellation_state: Literal["none", "requested", "cancelled", "completed", "unknown"] = "unknown"
    confirmation_ref: str | None = None
    registry_records: tuple[ADKRegistryRecord, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def reject_authority_or_secrets(self) -> ADKGoInvocationContext:
        _reject_forbidden_runtime_material(self.metadata)
        return self


class ADKToolConfirmation(BaseModel):
    confirmation_ref: str
    action_digest: str
    model_config = ConfigDict(extra="forbid", frozen=True)


class ADKTaskBinding(BaseModel):
    child_id: str
    action_digest: str
    permit_id: str
    tool_ref: str | None = None
    confirmation_ref: str | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)


def assert_confirmation_matches(action_digest: str, confirmation: ADKToolConfirmation) -> None:
    if confirmation.action_digest != action_digest:
        raise ValueError("ADK tool confirmation action binding mismatch")


def validate_task_fanout(bindings: Sequence[ADKTaskBinding]) -> tuple[ADKTaskBinding, ...]:
    child_ids = [binding.child_id for binding in bindings]
    if len(child_ids) != len(set(child_ids)):
        raise ValueError("ADK TaskRunner fan-out child ids must be unique")
    permit_ids = [binding.permit_id for binding in bindings]
    if len(permit_ids) != len(set(permit_ids)):
        raise ValueError("ADK TaskRunner fan-out cannot reuse one execution permit across children")
    return tuple(bindings)


class ADKTaskRunnerGate:
    def __init__(self, gateway: ValoGateway | None = None) -> None:
        self._gateway = gateway or ValoGateway()

    def execute_authorized(
        self,
        *,
        authority: AuthorityEnvelope,
        clearance: Clearance,
        permit: ExecutionPermit,
        action: ActionEnvelope,
        context: ADKGoInvocationContext,
        tool: Any,
        arguments: dict[str, Any] | None = None,
        confirmation: ADKToolConfirmation | None = None,
        now: datetime | None = None,
        previous_receipt_hash: str | None = None,
    ) -> ToolExecutionResult:
        if confirmation is not None:
            assert_confirmation_matches(action.digest, confirmation)
            if context.confirmation_ref is not None and context.confirmation_ref != confirmation.confirmation_ref:
                raise ValueError("ADK confirmation reference mismatch")
        executor = context.agent_ref or context.agent_name or "runtime"
        return self._gateway.execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id=f"google-adk-go:{executor}",
            tool=tool,
            arguments=arguments,
            now=now,
            previous_receipt_hash=previous_receipt_hash,
        )


class ADKGoRuntime(BaseRuntimeAdapter):
    backend = "google-adk-go"

    def submit_with_context(self, action: dict[str, Any], context: ADKGoInvocationContext) -> str:
        payload = dict(action)
        payload["adk_context"] = context.model_dump(mode="json", exclude_none=True)
        return super().submit(payload)
