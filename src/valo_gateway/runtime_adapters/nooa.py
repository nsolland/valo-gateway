from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from valo_gateway.contracts import canonical_digest
from valo_gateway.harness import BaseRuntimeAdapter


class NOOAMethodMode(str, Enum):
    DETERMINISTIC = "deterministic"
    AGENTIC = "agentic"


@dataclass(frozen=True)
class NOOAObjectReference:
    """Opaque reference to a live object resolved from governed state at execution time."""

    ref: str
    type_name: str

    def __post_init__(self) -> None:
        if not self.ref.strip():
            raise ValueError("ref is required")
        if not self.type_name.strip():
            raise ValueError("type_name is required")

    def to_binding(self) -> dict[str, str | bool]:
        return {
            "ref": self.ref,
            "type_name": self.type_name,
            "resolver": "governed-state",
            "resolve_at_execution": True,
        }


@dataclass(frozen=True)
class NOOAExecutionContext:
    agent_class: str
    agent_ref: str
    workspace_ref: str
    state_ref: str
    source_revision: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("agent_class", self.agent_class),
            ("agent_ref", self.agent_ref),
            ("workspace_ref", self.workspace_ref),
            ("state_ref", self.state_ref),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")

    def bind(
        self,
        *,
        method_name: str,
        method_mode: NOOAMethodMode,
        signature: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any],
        object_refs: dict[str, NOOAObjectReference],
        consequence_bearing: bool,
        state_mutation: bool,
    ) -> str:
        value = {
            "substrate": "nooa",
            "agent_class": self.agent_class,
            "agent_ref": self.agent_ref,
            "workspace_ref": self.workspace_ref,
            "state_ref": self.state_ref,
            "source_revision": self.source_revision,
            "method_name": method_name,
            "method_mode": method_mode.value,
            "signature": signature,
            "action_type": action_type,
            "target": target,
            "arguments": arguments,
            "object_refs": {
                name: ref.to_binding() for name, ref in sorted(object_refs.items())
            },
            "consequence_bearing": consequence_bearing,
            "state_mutation": state_mutation,
        }
        return "sha256:" + canonical_digest(value)


@dataclass(frozen=True)
class NOOAProposedAction:
    method_name: str
    method_mode: NOOAMethodMode
    signature: str
    action_type: str
    target: str
    execution_context_hash: str
    agent_class: str
    agent_ref: str
    workspace_ref: str
    state_ref: str
    arguments: dict[str, Any] = field(default_factory=dict)
    object_refs: dict[str, NOOAObjectReference] = field(default_factory=dict)
    source_revision: str | None = None
    consequence_bearing: bool = False
    state_mutation: bool = False

    def to_runtime_action(self) -> dict[str, Any]:
        return {
            "type": self.action_type,
            "target": self.target,
            "parameters": dict(self.arguments),
            "execution_context_hash": self.execution_context_hash,
            "runtime_context": {
                "substrate": "nooa",
                "agent_class": self.agent_class,
                "agent_ref": self.agent_ref,
                "workspace_ref": self.workspace_ref,
                "state_ref": self.state_ref,
                "source_revision": self.source_revision,
                "method_name": self.method_name,
                "method_mode": self.method_mode.value,
                "signature": self.signature,
                "object_refs": {
                    name: ref.to_binding()
                    for name, ref in sorted(self.object_refs.items())
                },
                "consequence_bearing": self.consequence_bearing,
                "state_mutation": self.state_mutation,
                "resolve_object_refs_at_execution": True,
                "fresh_state_required": True,
                "state_mutation_requires_admission": self.state_mutation,
                "direct_effect_path": False,
                "route": "valo-gateway",
            },
        }


class NOOARuntime(BaseRuntimeAdapter):
    """Provider-neutral normalization boundary for NVIDIA NOOA workers."""

    backend = "nooa"

    def normalize_method(
        self,
        *,
        context: NOOAExecutionContext,
        method_name: str,
        signature: str,
        action_type: str,
        target: str,
        arguments: dict[str, Any] | None = None,
        object_refs: dict[str, NOOAObjectReference] | None = None,
        method_mode: NOOAMethodMode = NOOAMethodMode.AGENTIC,
        consequence_bearing: bool = False,
        state_mutation: bool = False,
        direct_effect: bool = False,
    ) -> NOOAProposedAction:
        if direct_effect:
            raise ValueError("NOOA direct effect path is forbidden")
        for name, value in (
            ("method_name", method_name),
            ("signature", signature),
            ("action_type", action_type),
            ("target", target),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")

        args = dict(arguments or {})
        refs = dict(object_refs or {})
        overlap = set(args).intersection(refs)
        if overlap:
            joined = ", ".join(sorted(overlap))
            raise ValueError(f"arguments and object_refs overlap: {joined}")
        if any(not name.strip() for name in refs):
            raise ValueError("object reference parameter names must be non-empty")

        execution_context_hash = context.bind(
            method_name=method_name,
            method_mode=method_mode,
            signature=signature,
            action_type=action_type,
            target=target,
            arguments=args,
            object_refs=refs,
            consequence_bearing=consequence_bearing,
            state_mutation=state_mutation,
        )
        return NOOAProposedAction(
            method_name=method_name,
            method_mode=method_mode,
            signature=signature,
            action_type=action_type,
            target=target,
            arguments=args,
            object_refs=refs,
            execution_context_hash=execution_context_hash,
            agent_class=context.agent_class,
            agent_ref=context.agent_ref,
            workspace_ref=context.workspace_ref,
            state_ref=context.state_ref,
            source_revision=context.source_revision,
            consequence_bearing=consequence_bearing,
            state_mutation=state_mutation,
        )
