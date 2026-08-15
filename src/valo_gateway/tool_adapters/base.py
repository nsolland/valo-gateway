from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol
from uuid import uuid4


class BoundaryProof(Protocol):
    effect_allowed: bool
    input_digest: str
    result_digest: str
    computed_digest: str


@dataclass(frozen=True)
class EffectorHandle:
    registry_id: str
    name: str
    capability: str
    target: str
    credential_ref: str | None
    binding_digest: str


class FunctionTool:
    def __init__(
        self,
        name: str,
        function: Callable[..., Any],
        capabilities: list[str] | None = None,
    ) -> None:
        self.name = name
        self.capabilities = list(capabilities or [])
        self._function = function

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
        return self._function(**arguments)


class ToolRegistry:
    def __init__(self) -> None:
        self._registry_id = str(uuid4())
        self._tools: dict[str, FunctionTool] = {}
        self._handles: dict[str, EffectorHandle] = {}

    def register(
        self,
        tool: FunctionTool,
        *,
        capability: str | None = None,
        target: str | None = None,
        credential_ref: str | None = None,
    ) -> EffectorHandle:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        if credential_ref is not None and not _is_opaque_credential_ref(credential_ref):
            raise ValueError("effector credentials must be opaque references")
        resolved_capability = capability or (
            tool.capabilities[0] if len(tool.capabilities) == 1 else tool.name
        )
        resolved_target = target or tool.name
        if not resolved_capability or not resolved_target:
            raise ValueError("effector capability and target must be explicit")
        payload = {
            "registry_id": self._registry_id,
            "name": tool.name,
            "capability": resolved_capability,
            "target": resolved_target,
            "credential_ref": credential_ref,
            "exclusive": True,
        }
        handle = EffectorHandle(
            registry_id=self._registry_id,
            name=tool.name,
            capability=resolved_capability,
            target=resolved_target,
            credential_ref=credential_ref,
            binding_digest=_digest(payload),
        )
        self._tools[tool.name] = tool
        self._handles[tool.name] = handle
        return handle

    def get(self, name: str) -> EffectorHandle:
        try:
            return self._handles[name]
        except KeyError as exc:
            raise KeyError(f"tool not registered: {name}") from exc

    def assert_effect_binding(
        self,
        handle: EffectorHandle,
        *,
        action_type: str,
        target: str,
    ) -> None:
        registered = self._handles.get(handle.name)
        if registered != handle or handle.registry_id != self._registry_id:
            raise PermissionError("effector handle is not owned by this boundary")
        if handle.capability != action_type or handle.target != target:
            raise PermissionError("effector handle does not bind the exact action")

    def _invoke_from_boundary(
        self,
        handle: EffectorHandle,
        arguments: dict[str, Any],
        proof: BoundaryProof,
        *,
        action_type: str,
        target: str,
    ) -> Any:
        _validate_boundary_proof(proof)
        self.assert_effect_binding(
            handle,
            action_type=action_type,
            target=target,
        )
        return self._tools[handle.name]._invoke_from_boundary(arguments, proof)


def _invoke_tool_from_boundary(
    tool: object,
    arguments: dict[str, Any],
    proof: BoundaryProof,
) -> Any:
    _validate_boundary_proof(proof)
    invoke = getattr(tool, "_invoke_from_boundary", None)
    if not callable(invoke):
        raise PermissionError(
            "NO_DIRECT_EFFECT_PATH: effector lacks boundary-only dispatch"
        )
    return invoke(arguments, proof)


def _validate_boundary_proof(proof: BoundaryProof) -> None:
    if not proof.effect_allowed:
        raise PermissionError("NULL_EFFECT_ON_DENY: boundary proof blocks effect")
    if not proof.input_digest or proof.result_digest != proof.computed_digest:
        raise PermissionError("effect boundary proof is unsealed")


def _is_opaque_credential_ref(value: str) -> bool:
    if any(char.isspace() for char in value):
        return False
    return value.startswith(("credential://", "vault://", "kms://", "hsm://"))


def _digest(value: dict[str, object]) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return sha256(raw).hexdigest()
