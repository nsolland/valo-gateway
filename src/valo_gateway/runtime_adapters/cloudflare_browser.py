from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .execution import (
    ExecutionDispatcher,
    ExecutionMode,
    ExecutionProtocol,
    ExecutionTransportContext,
    RuntimeAgnosticExecutionAdapter,
)


class CloudflareBrowserBackend(str, Enum):
    KITESURF = "kitesurf"
    BROWSER_RUN = "browser_run"


_FORBIDDEN_AUTHORITY_KEYS = {
    "authority_envelope_id",
    "authority_grant",
    "clearance",
    "clearance_id",
    "decision_contract",
    "execution_permit",
    "permit",
    "permit_id",
    "reht_clearance",
    "reht_decision",
}


def _reject_authority_claims(value: Any, path: str = "arguments") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_AUTHORITY_KEYS:
                raise ValueError(
                    f"Cloudflare browser payload cannot carry authority field: {path}.{key}"
                )
            _reject_authority_claims(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_authority_claims(nested, f"{path}[{index}]")


class CloudflareBrowserContext(BaseModel):
    account_ref: str
    backend: CloudflareBrowserBackend = CloudflareBrowserBackend.KITESURF
    session_ref: str | None = None
    recording_ref: str | None = None
    live_view_ref: str | None = None
    human_intervention_ref: str | None = None
    authority_effect: Literal["none"] = "none"
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator(
        "account_ref",
        "session_ref",
        "recording_ref",
        "live_view_ref",
        "human_intervention_ref",
    )
    @classmethod
    def reject_blank_refs(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Cloudflare browser references must be non-empty")
        return value


class CloudflareBrowserRunAdapter(RuntimeAgnosticExecutionAdapter):
    """Dispatch a governed browser invocation to Cloudflare Browser Run."""

    substrate = "cloudflare-browser-run"

    def __init__(
        self,
        *,
        context: CloudflareBrowserContext,
        execution_context_hash: str,
        dispatcher: ExecutionDispatcher,
        target: str = "cloudflare://browser-run",
        substrate_grant_ref: str | None = None,
        resume_checkpoint_ref: str | None = None,
    ) -> None:
        self.context = context
        super().__init__(
            protocol=ExecutionProtocol.CDP,
            mode=ExecutionMode.BROWSER,
            target=target,
            transport=ExecutionTransportContext(
                execution_context_hash=execution_context_hash,
                substrate_grant_ref=substrate_grant_ref,
                resume_checkpoint_ref=resume_checkpoint_ref,
            ),
            dispatcher=dispatcher,
        )

    def invoke(self, arguments: dict[str, Any]) -> Any:
        _reject_authority_claims(arguments)
        payload = {
            "provider": self.substrate,
            "browser_context": self.context.model_dump(mode="json"),
            "arguments": dict(arguments),
        }
        return super().invoke(payload)
