from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import uuid4

RiskClass = Literal["read", "effect"]
VerificationPolicy = Literal["mechanical", "pre", "pre_post"]
AuthorityCheck = Callable[..., bool]
CapabilityHandler = Callable[[dict[str, object]], Any]
SemanticPreVerifier = Callable[["CapabilityDescriptor", dict[str, object], "PrincipalContext"], bool]
SemanticPostVerifier = Callable[["CapabilityDescriptor", dict[str, object], Any, "PrincipalContext"], bool]
IdentityResolver = Callable[[str], "PrincipalContext | None"]

_TOKEN_RE = re.compile(r"[a-z0-9_.:-]+")


@dataclass(frozen=True)
class PrincipalContext:
    handle: str
    principal_id: str
    account_ref: str | None = None
    authenticated: bool = True


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    provider: str
    description: str
    verbs: tuple[str, ...] = ()
    nouns: tuple[str, ...] = ()
    risk: RiskClass = "effect"
    verification: VerificationPolicy = "mechanical"

    def __post_init__(self) -> None:
        if not self.capability_id or not self.provider:
            raise ValueError("capability_id and provider are required")
        if self.risk not in {"read", "effect"}:
            raise ValueError("risk must be 'read' or 'effect'")
        if self.verification not in {"mechanical", "pre", "pre_post"}:
            raise ValueError("verification must be 'mechanical', 'pre', or 'pre_post'")


@dataclass(frozen=True)
class CapabilityRequest:
    intent: str
    limit: int = 5

    def __post_init__(self) -> None:
        if not self.intent.strip():
            raise ValueError("intent is required")
        if not 1 <= self.limit <= 20:
            raise ValueError("limit must be between 1 and 20")


class StagedEffectHandler(Protocol):
    def stage(self, payload: dict[str, object]) -> object: ...

    def commit(self, stage_ref: object) -> Any: ...


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
        return [capability for score, _, capability in ranked if score >= cutoff][
            : request.limit
        ]


class CapabilityFrontDoor:
    def __init__(
        self,
        catalog: CapabilityCatalog | None = None,
        *,
        authorize: AuthorityCheck | None = None,
        resolve_identity: IdentityResolver | None = None,
        pre_verify: SemanticPreVerifier | None = None,
        post_verify: SemanticPostVerifier | None = None,
    ) -> None:
        self.catalog = catalog or CapabilityCatalog()
        self._authorize = authorize
        self._resolve_identity = resolve_identity
        self._pre_verify = pre_verify
        self._post_verify = post_verify
        self._bindings: dict[str, object] = {}
        self._records: dict[str, dict[str, object]] = {}

    def bind(self, capability_id: str, handler: object) -> None:
        capability = self.catalog.get(capability_id)
        if capability_id in self._bindings:
            raise ValueError(f"capability already bound: {capability_id}")
        if capability.risk == "read" and not callable(handler):
            raise TypeError("read capability handler must be callable")
        if capability.risk == "effect" and not _is_staged_handler(handler):
            raise TypeError("effect capability requires stage/commit handler")
        self._bindings[capability_id] = handler

    def discover(self, request: CapabilityRequest) -> list[CapabilityDescriptor]:
        return self.catalog.discover(request)

    def invoke(
        self,
        capability_id: str,
        payload: dict[str, object],
        *,
        principal_handle: str | None = None,
    ) -> dict[str, object]:
        capability = self.catalog.get(capability_id)
        handler = self._bindings.get(capability_id)
        if handler is None:
            raise RuntimeError(f"capability is not bound: {capability_id}")

        if capability.risk == "read":
            response = handler(payload)  # type: ignore[operator]
            receipt_id = f"receipt_{uuid4().hex}"
            record = {
                "receipt_id": receipt_id,
                "capability_id": capability_id,
                "status": "succeeded",
                "response": response,
            }
            self._records[receipt_id] = record
            return record

        principal = self._principal(principal_handle)
        self._assert_authority(capability_id, payload, principal)
        if capability.verification in {"pre", "pre_post"}:
            if self._pre_verify is None or not self._pre_verify(
                capability, payload, principal
            ):
                raise PermissionError("pre-verification denied effect capability")

        stage_ref = handler.stage(payload)  # type: ignore[attr-defined]
        receipt_id = f"receipt_{uuid4().hex}"
        record = {
            "receipt_id": receipt_id,
            "capability_id": capability_id,
            "status": "staged",
            "principal_handle": principal.handle,
            "principal_id": principal.principal_id,
            "account_ref": principal.account_ref,
            "payload": dict(payload),
            "stage_ref": stage_ref,
        }
        self._records[receipt_id] = record
        return record

    def commit(self, record_id: str) -> dict[str, object]:
        record = self.status(record_id)
        if record.get("status") != "staged":
            raise ValueError("only staged effects can be committed")

        capability = self.catalog.get(str(record["capability_id"]))
        handler = self._bindings[capability.capability_id]
        principal = self._principal(str(record["principal_handle"]))
        payload = dict(record["payload"])  # type: ignore[arg-type]

        self._assert_authority(capability.capability_id, payload, principal)
        response = handler.commit(record["stage_ref"])  # type: ignore[attr-defined]

        mechanical_verify = getattr(handler, "verify", None)
        if callable(mechanical_verify) and not mechanical_verify(
            record["stage_ref"], response
        ):
            record.update(
                status="verification_failed",
                response=response,
                verification="mechanical_failed",
            )
            return record

        if capability.verification == "pre_post":
            if self._post_verify is None or not self._post_verify(
                capability, payload, response, principal
            ):
                record.update(
                    status="verification_failed",
                    response=response,
                    verification="semantic_post_failed",
                )
                return record

        record.update(status="succeeded", response=response, verification="verified")
        return record

    def status(self, record_id: str) -> dict[str, object]:
        try:
            return self._records[record_id]
        except KeyError as exc:
            raise KeyError(f"record not found: {record_id}") from exc

    def event(
        self, source: str, event_type: str, payload: dict[str, object]
    ) -> dict[str, object]:
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

    def _principal(self, handle: str | None) -> PrincipalContext:
        if not handle:
            raise PermissionError(
                "authenticated principal handle required for effect capability"
            )
        if self._resolve_identity is None:
            return PrincipalContext(handle=handle, principal_id=handle, authenticated=True)
        principal = self._resolve_identity(handle)
        if principal is None or not principal.authenticated:
            raise PermissionError("principal authentication failed")
        if principal.handle != handle:
            raise PermissionError("principal handle binding mismatch")
        return principal

    def _assert_authority(
        self,
        capability_id: str,
        payload: dict[str, object],
        principal: PrincipalContext,
    ) -> None:
        if self._authorize is None:
            raise PermissionError("authority required for effect capability")
        parameters = inspect.signature(self._authorize).parameters.values()
        accepts_varargs = any(
            item.kind == inspect.Parameter.VAR_POSITIONAL for item in parameters
        )
        positional = [
            item
            for item in parameters
            if item.kind
            in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }
        ]
        allowed = (
            self._authorize(capability_id, payload, principal)
            if accepts_varargs or len(positional) >= 3
            else self._authorize(capability_id, payload)
        )
        if not allowed:
            raise PermissionError("authority required for effect capability")


def _is_staged_handler(handler: object) -> bool:
    return callable(getattr(handler, "stage", None)) and callable(
        getattr(handler, "commit", None)
    )


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
