from __future__ import annotations

from typing import Any

from valo_gateway.contracts import ActionEnvelope
from valo_gateway.runtime_adapters.adk_go import ADKGoInvocationContext


class ADKGoIngress:
    protocol = "google-adk-go"

    def normalize(self, payload: dict[str, Any]) -> ActionEnvelope:
        action, _ = self.normalize_with_context(payload)
        return action

    def normalize_with_context(self, payload: dict[str, Any]) -> tuple[ActionEnvelope, ADKGoInvocationContext]:
        required = {"valo_action", "adk"}
        missing = sorted(required - payload.keys())
        if missing:
            raise ValueError(f"missing ADK Go ingress fields: {', '.join(missing)}")
        extra = sorted(payload.keys() - required)
        if extra:
            raise ValueError(f"unexpected ADK Go ingress fields: {', '.join(extra)}")
        action_payload = payload["valo_action"]
        context_payload = payload["adk"]
        if not isinstance(action_payload, dict):
            raise TypeError("valo_action must be an object")
        if not isinstance(context_payload, dict):
            raise TypeError("adk must be an object")
        action = ActionEnvelope(**action_payload)
        context = ADKGoInvocationContext(**context_payload)
        return action, context
