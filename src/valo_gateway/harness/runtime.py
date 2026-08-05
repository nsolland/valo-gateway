from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
import json, time, uuid
from typing import Any, Protocol

@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str | None = None

@dataclass(frozen=True)
class Checkpoint:
    id: str
    step: int
    state_ref: str
    digest: str
    parent: str | None = None

@dataclass(frozen=True)
class RuntimeResult:
    action_id: str
    status: str
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    receipt_ref: str | None = None

class RuntimeAdapter(Protocol):
    def submit(self, action: dict[str, Any]) -> str: ...
    def stream(self, action_id: str) -> list[Event]: ...
    def checkpoint(self, action_id: str) -> Checkpoint: ...
    def restart(self, checkpoint_id: str) -> str: ...
    def result(self, action_id: str) -> RuntimeResult: ...

class BaseRuntimeAdapter:
    backend = "base"
    def __init__(self) -> None:
        self._actions: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[Event]] = {}
    def submit(self, action: dict[str, Any]) -> str:
        aid = "act-" + uuid.uuid4().hex[:12]
        self._actions[aid] = {"action": action, "state": "PENDING", "backend": self.backend}
        self._events[aid] = []
        self._emit(aid, "ACTION_REQUESTED", {"type": action.get("type"), "backend": self.backend})
        return aid
    def _emit(self, aid: str, kind: str, payload: dict[str, Any] | None = None) -> Event:
        ev = Event("ev-" + uuid.uuid4().hex[:8], kind,
                   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   payload or {}, self.backend)
        self._events[aid].append(ev)
        return ev
    def stream(self, action_id: str) -> list[Event]:
        return list(self._events.get(action_id, []))
    def checkpoint(self, action_id: str) -> Checkpoint:
        if action_id not in self._actions:
            raise KeyError(action_id)
        state = json.dumps(self._actions[action_id], sort_keys=True, default=str).encode()
        digest = "sha256:" + sha256(state).hexdigest()
        cp = Checkpoint("cp-" + uuid.uuid4().hex[:12], len(self._events[action_id]), digest, digest)
        self._emit(action_id, "CHECKPOINT", {"checkpoint": cp.id, "digest": digest})
        return cp
    def restart(self, checkpoint_id: str) -> str:
        aid = "act-" + uuid.uuid4().hex[:12]
        self._actions[aid] = {"state": "RESTARTED", "from": checkpoint_id, "backend": self.backend}
        self._events[aid] = []
        self._emit(aid, "RESTARTED", {"from": checkpoint_id})
        return aid
    def result(self, action_id: str) -> RuntimeResult:
        if action_id not in self._actions:
            raise KeyError(action_id)
        self._emit(action_id, "RESULT")
        return RuntimeResult(action_id, "SUCCESS", {"executed_by": self.backend})
