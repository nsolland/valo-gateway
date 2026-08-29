from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from valo_gateway import (
    ActionEnvelope,
    AuthorityEnvelope,
    AuthoritySource,
    Clearance,
    Decision,
    DecisionContract,
    ExecutionStatus,
    ValoGateway,
    issue_execution_permit,
)
from valo_gateway.tool_adapters import FunctionTool, ToolRegistry
from valo_gateway.veritas_handoff import build_veritas_execution_observation


class AdaptiveGuidance(BaseModel):
    """Persisted learned guidance that may shape a proposal but grants no authority."""

    guidance_id: str
    action_type: str
    target: str
    parameters: dict[str, Any]
    scope_note: str
    evidence_refs: tuple[str, ...] = ()
    counterevidence_refs: tuple[str, ...] = ()
    revision: int = Field(default=1, ge=1)
    renewed_from_receipts: tuple[str, ...] = ()
    authority_effect: Literal["NONE"] = "NONE"

    model_config = ConfigDict(extra="forbid", frozen=True)

    def propose(self, *, authority_envelope_id: str) -> ActionEnvelope:
        return ActionEnvelope(
            action_type=self.action_type,
            target=self.target,
            parameters=self.parameters,
            context_digest=f"guidance:{self.guidance_id}:r{self.revision}",
            policy_digest="demo:case-resolution-policy:v1",
            authority_envelope_id=authority_envelope_id,
        )


class InMemoryPermitStore:
    """Test/demo one-shot permit consumption with no filesystem side effects."""

    def __init__(self) -> None:
        self._consumed: set[str] = set()

    def consume_once(self, permit_id: str, consumed_at: datetime) -> bool:
        del consumed_at
        if permit_id in self._consumed:
            return False
        self._consumed.add(permit_id)
        return True


@dataclass
class ResolutionLedger:
    """Observable consequence surface for the demo."""

    events: list[dict[str, Any]] = field(default_factory=list)

    def resolve(self, *, outcome: str, amount: int) -> dict[str, Any]:
        event = {"outcome": outcome, "amount": amount}
        self.events.append(event)
        return {"accepted": True, **event}


class DemoAuthorizer:
    """Demo-only upstream authorizer.

    The gateway remains mechanical enforcement. This component demonstrates
    that learned guidance is non-authoritative and that current authority is
    resolved before an exact action receives clearance.
    """

    def clear(
        self,
        *,
        action: ActionEnvelope,
        authority: AuthorityEnvelope,
        now: datetime,
    ) -> Clearance:
        amount = int(action.parameters.get("amount", 0))
        max_amount = int(authority.metadata.get("max_amount", 0))
        allowed = (
            authority.is_active(now)
            and action.action_type in authority.capability_grants
            and action.target in authority.resource_scope
            and amount <= max_amount
        )
        decision = Decision.ALLOW if allowed else Decision.DENY
        valid_until = min(authority.valid_until, now + timedelta(seconds=30))
        return Clearance(
            action_digest=action.digest,
            authority_envelope_id=authority.envelope_id,
            decision_contract=DecisionContract(
                decision=decision,
                principal_id=authority.principal_id,
                actor_id=authority.actor_id,
                action_type=action.action_type,
                target=action.target,
                constraints={"max_amount": max_amount},
            ),
            decided_at=now,
            valid_until=valid_until,
            reht_ref="demo:fresh-authority:v1",
            evidence_refs=[
                f"authority:{authority.envelope_id}",
                f"max_amount:{max_amount}",
            ],
            policy_refs=["demo:case-resolution-policy:v1"],
        )

    def permit(
        self,
        *,
        action: ActionEnvelope,
        authority: AuthorityEnvelope,
        clearance: Clearance,
        now: datetime,
    ):
        if clearance.decision_contract.decision is not Decision.ALLOW:
            return None
        return issue_execution_permit(
            clearance=clearance,
            authority=authority,
            action=action,
            expires_at=min(
                clearance.valid_until,
                authority.valid_until,
                now + timedelta(seconds=10),
            ),
            now=now,
        )


class OutcomeRenewal:
    """Feed observed successful effect evidence back into learned guidance."""

    def renew(
        self,
        *,
        guidance: AdaptiveGuidance,
        observation: dict[str, Any],
    ) -> AdaptiveGuidance:
        if observation["status"] != ExecutionStatus.SUCCEEDED.value:
            return guidance
        receipt_hash = str(observation["receipt_hash"])
        if receipt_hash in guidance.renewed_from_receipts:
            return guidance
        return guidance.model_copy(
            update={
                "revision": guidance.revision + 1,
                "evidence_refs": guidance.evidence_refs
                + (f"receipt:{receipt_hash}",),
                "renewed_from_receipts": guidance.renewed_from_receipts
                + (receipt_hash,),
            }
        )


def build_authority(
    *,
    now: datetime,
    max_amount: int = 100,
    target: str = "case:42",
) -> AuthorityEnvelope:
    return AuthorityEnvelope(
        principal_id="human:owner",
        actor_id="agent:ops",
        source=AuthoritySource.INTERNAL,
        issuer="demo-authority",
        capability_grants=["case.resolve"],
        resource_scope=[target],
        purpose_scope=["customer-remediation"],
        issued_at=now,
        valid_until=now + timedelta(minutes=5),
        evidence_refs=["mandate:customer-remediation:v1"],
        metadata={"max_amount": max_amount},
    )


def build_guidance(*, target: str = "case:42", amount: int = 80) -> AdaptiveGuidance:
    return AdaptiveGuidance(
        guidance_id="duplicate-charge-under-100",
        action_type="case.resolve",
        target=target,
        parameters={"outcome": "refund", "amount": amount},
        scope_note="verified duplicate charge with bounded refund amount",
        evidence_refs=("historical-case:17", "historical-case:29"),
        counterevidence_refs=("exception:identity-mismatch",),
    )


def _registry_for(ledger: ResolutionLedger, *, target: str) -> tuple[ToolRegistry, Any]:
    registry = ToolRegistry()
    handle = registry.register(
        FunctionTool(
            "case_resolution",
            ledger.resolve,
            capabilities=["case.resolve"],
        ),
        capability="case.resolve",
        target=target,
    )
    return registry, handle


def run_allowed_flow(*, now: datetime) -> dict[str, Any]:
    authority = build_authority(now=now, max_amount=100)
    guidance = build_guidance()
    action = guidance.propose(authority_envelope_id=authority.envelope_id)

    authorizer = DemoAuthorizer()
    clearance = authorizer.clear(action=action, authority=authority, now=now)
    permit = authorizer.permit(
        action=action,
        authority=authority,
        clearance=clearance,
        now=now,
    )
    if permit is None:
        raise RuntimeError("demo expected an allowed exact action")

    ledger = ResolutionLedger()
    registry, handle = _registry_for(ledger, target=action.target)
    gateway = ValoGateway(permit_store=InMemoryPermitStore())
    result = gateway.execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="tool:case-resolution",
        effector_registry=registry,
        effector_handle=handle,
        arguments=action.parameters,
        now=now,
    )

    observation = build_veritas_execution_observation(
        authority=authority,
        clearance=clearance,
        action=action,
        result=result,
    )
    renewed = OutcomeRenewal().renew(
        guidance=guidance,
        observation=observation,
    )
    return {
        "proposal_source": guidance.guidance_id,
        "guidance_authority_effect": guidance.authority_effect,
        "decision": clearance.decision_contract.decision.value,
        "effect_status": result.receipt.status.value,
        "effect_count": len(ledger.events),
        "receipt_hash": result.receipt.receipt_hash,
        "observation_digest": observation["observation_digest"],
        "guidance_revision_before": guidance.revision,
        "guidance_revision_after": renewed.revision,
        "renewed_from_effect_evidence": renewed.revision > guidance.revision,
    }


def run_revoked_flow(*, now: datetime) -> dict[str, Any]:
    authority = build_authority(now=now, max_amount=100)
    guidance = build_guidance()
    action = guidance.propose(authority_envelope_id=authority.envelope_id)
    authorizer = DemoAuthorizer()
    clearance = authorizer.clear(action=action, authority=authority, now=now)
    permit = authorizer.permit(
        action=action,
        authority=authority,
        clearance=clearance,
        now=now,
    )
    if permit is None:
        raise RuntimeError("demo expected a permit before revocation")

    revoked = authority.model_copy(
        update={
            "revoked_at": now + timedelta(seconds=1),
            "revocation_ref": "incident:authority-revoked",
        }
    )

    ledger = ResolutionLedger()
    registry, handle = _registry_for(ledger, target=action.target)
    gateway = ValoGateway(permit_store=InMemoryPermitStore())

    blocked_reason = ""
    try:
        gateway.execute(
            authority=revoked,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="tool:case-resolution",
            effector_registry=registry,
            effector_handle=handle,
            arguments=action.parameters,
            now=now + timedelta(seconds=2),
        )
    except ValueError as exc:
        blocked_reason = str(exc)

    return {
        "proposal_source": guidance.guidance_id,
        "decision_when_permit_issued": clearance.decision_contract.decision.value,
        "authority_revoked_before_effect": True,
        "effect_count": len(ledger.events),
        "blocked": len(ledger.events) == 0 and bool(blocked_reason),
        "blocked_reason": blocked_reason,
    }


def run_demo(*, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    return {
        "mvp": "governed-adaptive-loop",
        "allowed_flow": run_allowed_flow(now=now),
        "revoked_flow": run_revoked_flow(now=now + timedelta(minutes=1)),
        "claim": (
            "Learned guidance may shape proposals; current authority controls "
            "consequence; observed effects renew guidance."
        ),
    }


def main() -> None:
    print(json.dumps(run_demo(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
