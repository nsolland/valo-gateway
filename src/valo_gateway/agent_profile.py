from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import canonical_digest


class ExecutionEnvironment(str, Enum):
    SANDBOX = "sandbox"
    LIVE = "live"


class BudgetWindow(str, Enum):
    ACTION = "action"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    LIFETIME = "lifetime"


class BoundResource(BaseModel):
    resource_type: str
    resource_ref: str
    scope: tuple[str, ...] = ()
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_reference(self) -> BoundResource:
        if "://" not in self.resource_ref and not self.resource_ref.startswith("urn:"):
            raise ValueError("resource_ref must be an opaque reference, never a raw secret")
        if "*" in self.scope:
            raise ValueError("resource scope must be explicit; wildcard scope is forbidden")
        return self


class AgentIdentity(BaseModel):
    principal_id: str
    actor_id: str
    issuer: str
    legal_entity_ref: str | None = None
    resources: tuple[BoundResource, ...] = ()
    legal_personhood_claimed: Literal[False] = False
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_legal_entity_reference(self) -> AgentIdentity:
        if self.legal_entity_ref is not None:
            if "://" not in self.legal_entity_ref and not self.legal_entity_ref.startswith("urn:"):
                raise ValueError("legal_entity_ref must be an opaque reference")
        return self


class GovernedToolHandle(BaseModel):
    name: str
    adapter: str
    action_types: tuple[str, ...]
    resource_scope: tuple[str, ...]
    environments: frozenset[ExecutionEnvironment]
    credential_handle_ref: str | None = None
    requires_reht_clearance: Literal[True] = True
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_handle(self) -> GovernedToolHandle:
        if not self.action_types:
            raise ValueError("tool handle must declare at least one action_type")
        if not self.environments:
            raise ValueError("tool handle must declare at least one environment")
        if "*" in self.action_types or "*" in self.resource_scope:
            raise ValueError("tool handle scope must be explicit; wildcard access is forbidden")
        if ExecutionEnvironment.LIVE in self.environments and not self.resource_scope:
            raise ValueError("live tool handles require explicit resource_scope")
        if self.credential_handle_ref is not None:
            if "://" not in self.credential_handle_ref and not self.credential_handle_ref.startswith("urn:"):
                raise ValueError("credential_handle_ref must be an opaque reference, never a credential")
        return self


class BudgetConstraint(BaseModel):
    budget_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    window: BudgetWindow
    hard_limit: Decimal = Field(gt=0)
    soft_limit: Decimal | None = Field(default=None, gt=0)
    atomic_reservation: Literal[True] = True
    shared_with_children: bool = True
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_limits(self) -> BudgetConstraint:
        if self.soft_limit is not None and self.soft_limit > self.hard_limit:
            raise ValueError("soft_limit cannot exceed hard_limit")
        return self


class ApprovalRule(BaseModel):
    rule_id: str
    action_types: tuple[str, ...]
    threshold: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    approver_scope: tuple[str, ...]
    freeze_action: Literal[True] = True
    execute_frozen_payload_only: Literal[True] = True
    reht_reclearance_required: Literal[True] = True
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_rule(self) -> ApprovalRule:
        if not self.action_types:
            raise ValueError("approval rule must declare action_types")
        if not self.approver_scope:
            raise ValueError("approval rule must declare approver_scope")
        if "*" in self.action_types or "*" in self.approver_scope:
            raise ValueError("approval scope must be explicit; wildcard access is forbidden")
        if (self.threshold is None) != (self.currency is None):
            raise ValueError("threshold and currency must be declared together")
        return self


class SessionPolicy(BaseModel):
    default_ttl_seconds: int = Field(default=900, gt=0, le=86400)
    max_ttl_seconds: int = Field(default=3600, gt=0, le=86400)
    token_transport: Literal["authorization_header"] = "authorization_header"
    secret_in_url: Literal[False] = False
    policy_refresh: Literal["every_call"] = "every_call"
    tool_catalog_refresh: Literal["every_call"] = "every_call"
    zero_standing_access: Literal[True] = True
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_ttl(self) -> SessionPolicy:
        if self.default_ttl_seconds > self.max_ttl_seconds:
            raise ValueError("default session TTL cannot exceed max TTL")
        return self


class AuditPolicy(BaseModel):
    decision_ledger: Literal["authoritative"] = "authoritative"
    execution_receipts: Literal["veritas_required"] = "veritas_required"
    activity_log: Literal["non_authoritative"] = "non_authoritative"
    deny_without_decision_id: bool = True
    model_config = ConfigDict(extra="forbid", frozen=True)


class RevocationPolicy(BaseModel):
    check_at_execution_boundary: Literal[True] = True
    cascade_to_children: Literal[True] = True
    revoke_sessions: Literal[True] = True
    revoke_reads: Literal[True] = True
    provider_cancellation_when_supported: Literal[True] = True
    external_side_effects_are_not_reversible: Literal[True] = True
    model_config = ConfigDict(extra="forbid", frozen=True)


class GovernedAgentProfile(BaseModel):
    schema_id: Literal["valo.gateway.governed-agent-profile.v1"] = (
        "valo.gateway.governed-agent-profile.v1"
    )
    profile_id: str
    profile_version: int = Field(default=1, ge=1)
    identity: AgentIdentity
    authority_envelope_ref: str
    policy_refs: tuple[str, ...]
    parent_profile_id: str | None = None
    runtime_agnostic: Literal[True] = True
    authority_semantics: Literal["reference_only"] = "reference_only"
    default_environment: ExecutionEnvironment = ExecutionEnvironment.SANDBOX
    tools: tuple[GovernedToolHandle, ...] = ()
    budgets: tuple[BudgetConstraint, ...] = ()
    approvals: tuple[ApprovalRule, ...] = ()
    sessions: SessionPolicy = Field(default_factory=SessionPolicy)
    audit: AuditPolicy = Field(default_factory=AuditPolicy)
    revocation: RevocationPolicy = Field(default_factory=RevocationPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_profile(self) -> GovernedAgentProfile:
        if self.parent_profile_id == self.profile_id:
            raise ValueError("profile cannot be its own parent")
        if "://" not in self.authority_envelope_ref and not self.authority_envelope_ref.startswith("urn:"):
            raise ValueError("authority_envelope_ref must be an opaque reference")
        if not self.policy_refs:
            raise ValueError("at least one policy_ref is required")
        for ref in self.policy_refs:
            if "://" not in ref and not ref.startswith("urn:"):
                raise ValueError("policy_refs must be opaque references")
        tool_names = [tool.name for tool in self.tools]
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("tool names must be unique")
        budget_ids = [budget.budget_id for budget in self.budgets]
        if len(budget_ids) != len(set(budget_ids)):
            raise ValueError("budget ids must be unique")
        rule_ids = [rule.rule_id for rule in self.approvals]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("approval rule ids must be unique")
        secret_terms = ("secret", "password", "token", "api_key", "private_key")
        for key in self.metadata:
            if any(term in key.lower() for term in secret_terms):
                raise ValueError("metadata cannot contain secret-bearing fields")
        return self

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))

    def tools_for(self, environment: ExecutionEnvironment) -> tuple[GovernedToolHandle, ...]:
        return tuple(tool for tool in self.tools if environment in tool.environments)

    def compile_for_runtime(
        self,
        *,
        runtime_id: str,
        environment: ExecutionEnvironment | None = None,
    ) -> CompiledRuntimeProfile:
        selected_environment = environment or self.default_environment
        return CompiledRuntimeProfile(
            profile_id=self.profile_id,
            profile_digest=self.digest,
            runtime_id=runtime_id,
            environment=selected_environment,
            identity=self.identity,
            authority_envelope_ref=self.authority_envelope_ref,
            policy_refs=self.policy_refs,
            tools=self.tools_for(selected_environment),
            default_session_ttl_seconds=self.sessions.default_ttl_seconds,
            max_session_ttl_seconds=self.sessions.max_ttl_seconds,
        )


class CompiledRuntimeProfile(BaseModel):
    schema_id: Literal["valo.gateway.compiled-runtime-profile.v1"] = (
        "valo.gateway.compiled-runtime-profile.v1"
    )
    profile_id: str
    profile_digest: str
    runtime_id: str
    environment: ExecutionEnvironment
    identity: AgentIdentity
    authority_envelope_ref: str
    policy_refs: tuple[str, ...]
    tools: tuple[GovernedToolHandle, ...]
    default_session_ttl_seconds: int
    max_session_ttl_seconds: int
    authorization_boundary: Literal["REHT"] = "REHT"
    contains_secrets: Literal[False] = False
    model_config = ConfigDict(extra="forbid", frozen=True)


class DelegatedSessionDescriptor(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    profile_id: str
    profile_digest: str
    runtime_id: str
    tool_names: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    token_transport: Literal["authorization_header"] = "authorization_header"
    contains_secret: Literal[False] = False
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> DelegatedSessionDescriptor:
        if self.expires_at <= self.issued_at:
            raise ValueError("session expires_at must be later than issued_at")
        return self


def build_session_descriptor(
    compiled: CompiledRuntimeProfile,
    *,
    ttl_seconds: int | None = None,
    now: datetime | None = None,
) -> DelegatedSessionDescriptor:
    now = now or datetime.now(UTC)
    ttl = ttl_seconds or compiled.default_session_ttl_seconds
    if ttl <= 0 or ttl > compiled.max_session_ttl_seconds:
        raise ValueError("session TTL exceeds the compiled profile maximum")
    return DelegatedSessionDescriptor(
        profile_id=compiled.profile_id,
        profile_digest=compiled.profile_digest,
        runtime_id=compiled.runtime_id,
        tool_names=tuple(tool.name for tool in compiled.tools),
        issued_at=now,
        expires_at=now + timedelta(seconds=ttl),
    )


def assert_child_profile_narrower(
    *,
    parent: GovernedAgentProfile,
    child: GovernedAgentProfile,
) -> None:
    if child.parent_profile_id != parent.profile_id:
        raise ValueError("child parent_profile_id does not bind to parent")

    parent_tools = {tool.name: tool for tool in parent.tools}
    for child_tool in child.tools:
        parent_tool = parent_tools.get(child_tool.name)
        if parent_tool is None:
            raise ValueError(f"child introduces tool {child_tool.name}")
        if child_tool.adapter != parent_tool.adapter:
            raise ValueError(f"child changes adapter for {child_tool.name}")
        if child_tool.credential_handle_ref != parent_tool.credential_handle_ref:
            raise ValueError(f"child changes credential handle for {child_tool.name}")
        if not set(child_tool.action_types).issubset(parent_tool.action_types):
            raise ValueError(f"child expands action_types for {child_tool.name}")
        if not set(child_tool.resource_scope).issubset(parent_tool.resource_scope):
            raise ValueError(f"child expands resource_scope for {child_tool.name}")
        if not child_tool.environments.issubset(parent_tool.environments):
            raise ValueError(f"child expands environments for {child_tool.name}")

    parent_budgets = {budget.budget_id: budget for budget in parent.budgets}
    for child_budget in child.budgets:
        parent_budget = parent_budgets.get(child_budget.budget_id)
        if parent_budget is None:
            raise ValueError(f"child introduces budget domain {child_budget.budget_id}")
        if child_budget.currency != parent_budget.currency or child_budget.window != parent_budget.window:
            raise ValueError(f"child changes budget semantics for {child_budget.budget_id}")
        if child_budget.hard_limit > parent_budget.hard_limit:
            raise ValueError(f"child raises hard limit for {child_budget.budget_id}")
        if parent_budget.soft_limit is not None:
            if child_budget.soft_limit is None or child_budget.soft_limit > parent_budget.soft_limit:
                raise ValueError(f"child weakens soft limit for {child_budget.budget_id}")

    if child.sessions.default_ttl_seconds > parent.sessions.default_ttl_seconds:
        raise ValueError("child raises default session TTL")
    if child.sessions.max_ttl_seconds > parent.sessions.max_ttl_seconds:
        raise ValueError("child raises maximum session TTL")

    retained_actions = {
        action_type
        for tool in child.tools
        for action_type in tool.action_types
    }
    child_rules = [
        rule
        for rule in child.approvals
        if retained_actions.intersection(rule.action_types)
    ]
    for parent_rule in parent.approvals:
        covered_actions = retained_actions.intersection(parent_rule.action_types)
        for action_type in covered_actions:
            candidates = [rule for rule in child_rules if action_type in rule.action_types]
            if not candidates:
                raise ValueError(f"child removes approval for {action_type}")
            if parent_rule.threshold is None:
                if all(rule.threshold is not None for rule in candidates):
                    raise ValueError(f"child weakens always-approval rule for {action_type}")
            elif all(
                rule.threshold is None
                or rule.currency != parent_rule.currency
                or rule.threshold > parent_rule.threshold
                for rule in candidates
            ):
                raise ValueError(f"child raises approval threshold for {action_type}")


def load_profile(path: str | Path) -> GovernedAgentProfile:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return GovernedAgentProfile.model_validate(raw)
