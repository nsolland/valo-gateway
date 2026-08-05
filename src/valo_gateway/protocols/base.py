from __future__ import annotations
from typing import Any, Protocol
from valo_gateway.contracts import ActionEnvelope

class IngressNormalizer(Protocol):
    protocol: str
    def normalize(self, payload: dict[str, Any]) -> ActionEnvelope: ...

class MappingIngress:
    protocol = "mapping"
    def normalize(self, payload: dict[str, Any]) -> ActionEnvelope:
        required = {"action_type", "target", "context_digest", "policy_digest", "authority_envelope_id"}
        missing = sorted(required - payload.keys())
        if missing:
            raise ValueError(f"missing ingress fields: {', '.join(missing)}")
        return ActionEnvelope(**payload)
