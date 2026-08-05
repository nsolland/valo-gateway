from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, ConfigDict


class ControlEventType(str, Enum):
    REVOKE_AUTHORITY = "revoke_authority"
    REVOKE_PRINCIPAL = "revoke_principal"
    REVOKE_ACTOR = "revoke_actor"
    HALT_GLOBAL = "halt_global"
    HALT_SCOPE = "halt_scope"
    RESUME_SCOPE = "resume_scope"
    RESUME_GLOBAL = "resume_global"


class ControlEvent(BaseModel):
    event_type: ControlEventType
    issuer_id: str
    reason: str
    authority_envelope_id: str | None = None
    principal_id: str | None = None
    actor_id: str | None = None
    scope: str | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeControlPlane:
    def __init__(self) -> None:
        self._revoked_authorities: set[str] = set()
        self._revoked_principals: set[str] = set()
        self._revoked_actors: set[str] = set()
        self._halted_scopes: set[str] = set()
        self._global_halt = False

    def apply(self, event: ControlEvent) -> None:
        if event.event_type == ControlEventType.REVOKE_AUTHORITY:
            if not event.authority_envelope_id:
                raise ValueError("authority_envelope_id is required")
            self._revoked_authorities.add(event.authority_envelope_id)
        elif event.event_type == ControlEventType.REVOKE_PRINCIPAL:
            if not event.principal_id:
                raise ValueError("principal_id is required")
            self._revoked_principals.add(event.principal_id)
        elif event.event_type == ControlEventType.REVOKE_ACTOR:
            if not event.actor_id:
                raise ValueError("actor_id is required")
            self._revoked_actors.add(event.actor_id)
        elif event.event_type == ControlEventType.HALT_GLOBAL:
            self._global_halt = True
        elif event.event_type == ControlEventType.RESUME_GLOBAL:
            self._global_halt = False
        elif event.event_type == ControlEventType.HALT_SCOPE:
            if not event.scope:
                raise ValueError("scope is required")
            self._halted_scopes.add(event.scope)
        elif event.event_type == ControlEventType.RESUME_SCOPE:
            if not event.scope:
                raise ValueError("scope is required")
            self._halted_scopes.discard(event.scope)

    def assert_execution_allowed(self, *, authority_envelope_id: str,
                                 principal_id: str, actor_id: str,
                                 scopes: list[str] | None = None) -> None:
        blocked = (
            self._global_halt
            or authority_envelope_id in self._revoked_authorities
            or principal_id in self._revoked_principals
            or actor_id in self._revoked_actors
            or any(scope in self._halted_scopes for scope in (scopes or []))
        )
        if blocked:
            raise ValueError("execution blocked by revocation or HALT control state")
