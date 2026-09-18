from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

RiskClass = Literal["read", "effect"]
AuthorityCheck = Callable[[str, dict[str, object]], bool]
CapabilityHandler = Callable[[dict[str, object]], Any]

_TOKEN_RE = re.compile(r"[a-z0-9_.:-]+")


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    provider: str
    description: str
    verbs: tuple[str, ...] = ()
    nouns: tuple[str, ...] = ()
    risk: RiskClass = "effect"

    def __post_init__(self) -> None:
        if not self.capability_id or not self.provider:
            raise ValueError("capability_id and provider are required")
        if self.risk not in {"read", "effect"}:
            raise ValueError("risk must be 'read' or 'effect'")


@dataclass(frozen=True)
class CapabilityRequest:
    intent: str
    limit: int = 5

    def __post_init__(self) -> None:
        if not self.intent.strip():
            raise ValueError("intent is required")
        if not 1 <= self.limit <= 20:
            raise ValueError("limit must be between 1 and 20")


class CapabilityCatalog:
    def __init__(self, capabilities: Iterable[CapabilityDescriptor] = ()) -> None:
        self._capabilities: dict[str, CapabilityDescriptor] = {}
        for capability in capabilities:
            self.register(capability)

    def register(self, capability: CapabilityDescriptor) -> None:
        if capability.capability_id in self._capabilities:
            raise ValueError(f"capability already registered: {capability.capability_id}")
        self._capabilities[capability.capability_id] = capability

    def get(self, capability_id: str) -> CapabilityDescriptor:
        try:
            return self._capabilities[capability_id]
        except KeyError as exc:
            raise KeyError(f"capability not registered: {capability_id}") from exc

    def discover(self, request: CapabilityRequest) -> list[CapabilityDescriptor]:
        query = _tokens(request.intent)
        ranked: list[tuple[int, str, CapabilityDescriptor]] = []
        for capability in self._capabilities.values():
            score = _score(query, capability)
            if score > 0:
                ranked.append((score, capability.capability_id, capability))
        if not ranked:
            return []
        ranked.sort(key=lambda item: (-item[0], item[1]))
        best = ranked[0][0]
        cutoff = max(1, (best + 1) // 2)
        return [
            capability
            for score, _, capability in ranked
            if score >= cutoff
        ][: request.limit]


class CapabilityFrontDoor:
    def __init__(
        self,
        catalog: CapabilityCatalog | None = None,
        *,
        authorize: AuthorityCheck | None = None,
    ) -> None:
        self.catalog = catalog or CapabilityCatalog()
        self._authorize = authorize
        self._bindings: dict[str, CapabilityHandler] = {}
        self._records: dict[str, dict[str, object]] = {}

    def bind(self, capability_id: str, handler: CapabilityHandler) -> None:
        self.catalog.get(capability_id)
        if capability_id in self._bindings:
            raise ValueError(f"capability already bound: {capability_id}")
        self._bindings[capability_id] = handler

    def discover(self, request: CapabilityRequest) -> list[CapabilityDescriptor]:
        return self.catalog.discover(request)

    def invoke(self, capability_id: str, payload: dict[str, object]) -> dict[str, object]:
        capability = self.catalog.get(capability_id)
        handler = self._bindings.get(capability_id)
        if handler is None:
            raise RuntimeError(f"capability is not bound: {capability_id}")
        if capability.risk == "effect":
            if self._authorize is None or not self._authorize(capability_id, payload):
                raise PermissionError("authority required for effect capability")

        receipt_id = f"receipt_{uuid4().hex}"
        try:
            response = handler(payload)
        except Exception as exc:
            record = {
                "receipt_id": receipt_id,
                "capability_id": capability_id,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
            self._records[receipt_id] = record
            raise

        record = {
            "receipt_id": receipt_id,
            "capability_id": capability_id,
            "status": "succeeded",
            "response": response,
        }
        self._records[receipt_id] = record
        return record

    def status(self, record_id: str) -> dict[str, object]:
        try:
            return self._records[record_id]
        except KeyError as exc:
            raise KeyError(f"record not found: {record_id}") from exc

    def event(self, source: str, event_type: str, payload: dict[str, object]) -> dict[str, object]:
        if not source.strip() or not event_type.strip():
            raise ValueError("event source and type are required")
        event_id = f"event_{uuid4().hex}"
        record = {
            "event_id": event_id,
            "source": source,
            "type": event_type,
            "payload": payload,
            "status": "received",
        }
        self._records[event_id] = record
        return record


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.lower().replace("/", " ")))


def _score(query: set[str], capability: CapabilityDescriptor) -> int:
    identity = _tokens(capability.capability_id.replace(".", " "))
    provider = _tokens(capability.provider)
    verbs = {token for value in capability.verbs for token in _tokens(value)}
    nouns = {token for value in capability.nouns for token in _tokens(value)}
    description = _tokens(capability.description)
    return (
        4 * len(query & identity)
        + 3 * len(query & provider)
        + 2 * len(query & verbs)
        + 2 * len(query & nouns)
        + len(query & description)
    )
