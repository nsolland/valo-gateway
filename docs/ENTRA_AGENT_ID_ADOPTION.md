# Microsoft Entra Agent ID adoption

Status: first-class upstream identity/access context adapter.

Canonical base: `a4ebad202003e16a4107cf5bc818d3c795c082c2`

Branch: `feat/entra-agent-id-authority-context`

PR: `#15`

## Decision

Adopt Microsoft Entra Agent ID as an upstream identity, entitlement, session and access-control evidence source. Do not treat Entra identity, roles, OAuth permissions, Conditional Access, access packages, risk state or token issuance as authorization for a concrete consequential action.

Canonical placement:

```text
Microsoft Entra Agent ID
→ identity / blueprint / sponsor / owner
→ delegated or autonomous access grants
→ Conditional Access / risk / token-session state
→ normalized EntraAgentIdContext evidence
→ VAIG evaluation evidence
→ REHT exact-action authorization
→ RACS decision contract
→ valo-gateway mechanical enforcement
→ external consequence
→ Veritas observation / receipt
```

Entra answers whether an agent identity can authenticate and access a resource under Microsoft Entra controls. REHT remains responsible for whether the exact proposed action may occur now.

## Provider facts consumed

The adapter can bind:

- tenant and agent identity ID;
- agent identity blueprint and blueprint principal references;
- autonomous versus on-behalf-of access mode;
- user subject for delegated/on-behalf-of execution;
- token audience and target resource;
- delegated OAuth scopes;
- application permissions;
- Microsoft Entra roles;
- Azure roles;
- access-package references;
- owners and sponsors;
- Conditional Access result;
- agent risk signal;
- token issue/expiry state;
- session reference;
- disable/revocation state;
- provider evidence references.

The complete normalized context receives a deterministic `binding_digest`. Any material change to identity, scope, role, resource, token lifecycle or runtime access state changes that digest.

## Authority boundary

The following are evidence only and never create VALO execution authority:

- existence of an Entra agent identity;
- membership in an agent identity blueprint;
- owner or sponsor assignment;
- a Microsoft Entra or Azure role;
- a delegated OAuth scope;
- an application permission;
- an access package;
- successful token acquisition;
- a Conditional Access allow result;
- a low-risk identity state;
- possession of an active session or token.

Likewise, a Conditional Access block, disabled identity, revocation or expired token is sufficient provider state to make the normalized access context unusable. This fail-closed provider state still does not make the adapter a REHT policy engine.

`EntraAgentIdContext.to_reht_evidence()` therefore emits `authoritative: false` explicitly and exposes no method that can issue a REHT clearance or one-shot execution permit. Arbitrary metadata is recursively rejected if it attempts to carry REHT authority-shaped fields such as a decision, clearance or permit.

## Delegated and autonomous modes

Microsoft Entra Agent ID supports both delegated/on-behalf-of and autonomous application access patterns.

For on-behalf-of access, the adapter requires a user `subject_id` and binds that subject separately from the agent identity. The agent identity remains the acting agent; the user is the delegated subject.

For autonomous access, application permissions and agent identity state are bound directly without inventing a human subject.

Neither mode changes the REHT execution boundary.

## Conditional Access

Conditional Access is upstream access control. Agent-specific policies can evaluate agent context and risk and can block token/resource access. A provider-side allow result is not a permit to perform a particular business action.

The distinction is intentional:

```text
Conditional Access
= may this identity obtain/use access to this resource under Entra policy?

REHT
= may this exact action against this exact target execute now under the active mandate and runtime state?
```

## Least-privilege alignment

Microsoft's least-privilege guidance for AI agents states that agent security must define identity, scope, tool access and auditability before autonomy expands. It recommends unique lifecycle-managed agent identities, named owners/sponsors, task-scoped roles, time-limited/JIT privileges, tool/action allowlists, revocation paths and end-to-end logging.

It also requires authorization to be revalidated through the chain rather than trusted only at the orchestrator. That maps directly to the VALO boundary:

```text
Entra identity / roles / scopes / JIT state
→ upstream authority facts and access evidence
→ REHT exact-action authorization
→ valo-gateway one-shot mechanical enforcement
→ downstream system revalidation
→ Veritas receipt
```

The integration rule is therefore:

`Entra supplies identity, entitlement and access facts. REHT decides action admissibility.`

Microsoft Entra can independently deny identity/resource access. A successful Entra access decision can never substitute for a REHT clearance and one-shot execution permit.

## Microsoft authorization constraints

Microsoft Entra Agent ID applies additional least-privilege safeguards to agent identities. Agent identities can use Microsoft Entra roles and Microsoft Graph delegated/application permissions, but Microsoft blocks a set of high-privilege directory roles and Graph permissions for agents. Blueprint-level inheritable permissions can also project grants to agent identities created from a blueprint.

These controls are retained as provider evidence rather than copied into VALO's canonical authorization model. The allowed/blocked Microsoft permission set can evolve without changing REHT semantics.

## Non-bypass invariant

A configured Entra identity adapter cannot:

- create an `AuthorityEnvelope`;
- issue a REHT `Clearance`;
- issue an `ExecutionPermit`;
- upgrade DENY/DEFER/STEP_UP/HALT to ALLOW;
- widen resource or purpose scope;
- convert a provider token into execution authority;
- smuggle authority-shaped fields through provider metadata.

The adapter only normalizes upstream facts for evaluation and binding.

## Sources

- Microsoft Learn: Least privilege for AI agents (agentic identities + RBAC) — https://learn.microsoft.com/en-us/security/zero-trust/sfi/least-privilege-for-ai-agents
- Microsoft Learn: Authorization in Microsoft Entra Agent ID — https://learn.microsoft.com/en-us/entra/agent-id/authorization-agent-id
- Microsoft Learn: Conditional Access for agents — https://learn.microsoft.com/en-us/entra/identity/conditional-access/agent-id
- Microsoft Learn: Agent identities in Microsoft Entra Agent ID — https://learn.microsoft.com/en-us/entra/agent-id/agent-identities
- Microsoft Learn: Governing Agent Identities — https://learn.microsoft.com/en-us/entra/id-governance/agent-id-governance-overview
