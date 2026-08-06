# Naïve: architecture analysis and VALO adoption

Snapshot: 2026-08-06

Sources:

- https://usenaive.ai/
- https://usenaive.ai/developers
- https://usenaive.ai/docs/architecture/governance-gateway
- https://usenaive.ai/docs/architecture/approvals
- https://usenaive.ai/docs/architecture/decision-ledger
- https://usenaive.ai/docs/architecture/sessions
- https://usenaive.ai/docs/architecture/open-core
- https://usenaive.ai/blog/the-governed-agent-profile
- https://usenaive.ai/blog/hosted-vs-bring-your-own-runtime-for-ai-agents

## Conclusion

Naïve is the strongest commercial validation yet for a runtime-independent governed-agent bundle.

Its important contribution is not another agent framework. It separates where the model runs from where real-world actions are controlled. An agent may run in LangGraph, CrewAI, a custom loop, a customer cloud or a hosted microVM. The same governed tool handles still route to a remote enforcement point that owns provider credentials and applies identity, capability, budget, approval, audit and revocation controls.

VALO adopts that distribution and product pattern, but not Naïve's authority architecture.

Canonical VALO boundary remains:

```text
runtime or harness
  -> governed tool handle
  -> VAIG evidence
  -> REHT authorization of the exact action
  -> RACS decision contract
  -> valo-gateway mechanical execution
  -> provider or Naïve primitive
  -> Veritas execution evidence
```

The governed agent profile is portable configuration and identity context. It references authority. It never creates authority.

## What Naïve gets right

### 1. Runtime and governance are independent decisions

The runtime provides the loop, state, durability, scheduling and sandbox. The governed tool layer controls external consequences. This avoids forcing a customer to replace its framework before adopting controls.

Adopted invariant:

```text
same profile + same action + same authority + same policy
=> same authorization requirements regardless of runtime
```

A compiled VALO profile may name a runtime for traceability, but the runtime does not change its profile digest, tools, limits or authorization boundary.

### 2. Tools are handles, never provider credentials

The agent receives a callable handle. The execution provider retains the real credential. A tool call is a request to act, not possession of the means to act.

Adopted invariant:

- profiles contain only opaque resource and credential references
- no raw API key, card credential, password, bearer token or private key
- the gateway or downstream provider resolves the reference only after REHT clearance
- a harness cannot convert a tool handle into authority

### 3. One agent profile gathers operational context

Naïve groups identity, money, communications, tools, limits and runtime association under one profile. This gives operators one lifecycle object for provisioning, inspection, suspension and offboarding.

VALO adopts the profile as a portable operational envelope containing:

- principal and actor identity
- issuer and legal-entity reference
- registered resource handles
- authority-envelope reference
- policy references
- governed tool handles
- budgets and exposure ceilings
- approval requirements
- session policy
- audit requirements
- revocation semantics
- parent-child relationship

The profile explicitly states that the agent is not claiming legal personhood. A legal entity or human principal delegates action to an actor; the actor does not become an autonomous legal person because it has an inbox, card or registered number.

### 4. Infrastructure as code and CLI-first operation

A versioned profile is safer and easier to review than a sequence of imperative API calls. It can be diffed, signed, validated, promoted between environments and included in deployment gates.

Adopted CLI surface:

```bash
valo-gateway profile validate profile.json
valo-gateway profile show profile.json
valo-gateway profile fingerprint profile.json
valo-gateway profile tools profile.json --environment live
valo-gateway profile compile profile.json --runtime-id langgraph --environment live
valo-gateway profile session-descriptor profile.json --runtime-id custom-loop
valo-gateway profile compare-parent parent.json child.json
```

`compile` produces a secret-free runtime bundle. It does not mint authority or an execution permit.

### 5. Short-lived delegated sessions

Naïve's per-user MCP sessions use a short TTL, can be revoked independently and put the bearer in the Authorization header rather than the URL.

Adopted and tightened:

- default TTL is 15 minutes
- maximum TTL is explicit and bounded
- secrets never appear in URLs, manifests, logs or compiled profiles
- the CLI emits only a non-secret session descriptor
- actual session credentials must be minted by an authorized control-plane service
- authority, policy, revocation and tool exposure must be re-read on every call
- zero standing access is the default

### 6. Frozen actions for approval

Naïve persists the full pending action and executes the frozen payload after approval rather than asking the model to reconstruct and retry it. This prevents payload drift and duplicate agent attempts.

VALO adopts the frozen-action invariant, with a stricter continuation:

```text
exact ActionEnvelope digest
  -> pending step-up
  -> HumanApprovalAttestationV1 bound to that digest
  -> REHT re-clearance against current authority, policy, state and time
  -> new one-shot execution permit
  -> execute the frozen payload only
```

Human approval is evidence. It is not itself execution authority and does not bypass a revoked mandate, expired scope, changed risk state or newer policy.

### 7. Atomic budget reservation

Naïve reserves hard-cap exposure before execution to avoid concurrent calls exceeding a limit. Soft caps route to approval.

Adopted invariant:

- every consequence-bearing cost or exposure domain declares a budget identifier, unit and window
- hard exposure is reserved atomically before provider invocation
- reservation is bound to the action digest and execution permit
- failed provider calls do not silently restore authority
- release or settlement is an explicit state transition with a receipt
- children may share a parent budget but cannot raise it

Budget is an exposure constraint consumed by REHT. It is not a substitute for authority, purpose, target scope or policy.

### 8. Parent-child profiles only narrow

Naïve states that sub-agent capabilities narrow and budget remains shared. This closes a confused-deputy path where a child gains capabilities unavailable to its parent.

The VALO profile contract proves that a child cannot:

- introduce a new tool
- change its adapter or credential handle
- add action types
- widen resource scope
- add an execution environment
- raise hard or soft limits
- increase session TTL
- remove or weaken an approval requirement for a retained action

### 9. Business-action governance and system governance are different planes

Naïve distinguishes action governance from container, network, filesystem and process isolation.

Canonical VALO framing:

- harness engineering controls how the model may work: runtime, tools, memory and sandbox
- VAIG evaluates the proposal and context
- REHT decides whether the exact action is authorized now
- valo-gateway enforces the permit mechanically
- Veritas proves what happened

A secure sandbox does not authorize a payment. A valid REHT permit does not prove the runtime filesystem is isolated. Both planes are required and neither should claim the other's guarantees.

## Documented Naïve gaps that validate VALO

Naïve's own documentation is unusually direct about implementation gaps. These are not reasons to dismiss the product. They show why transport-independent authorization and authoritative evidence must be architectural invariants rather than product claims.

### Legacy runtime bypass

Naïve documents that legacy orchestration containers call company-level routes using a key without an active tenant user. The profile policy is therefore stored but not enforced on those paths.

VALO rule:

```text
no runtime, transport, legacy mount or internal service may bypass the execution boundary
```

Conformance must prove non-bypass across every ingress and adapter. A declared policy that is not evaluated on a real execution path is documentation, not control.

### Incomplete MCP policy coverage

The documented MCP surface has 271 tools. Only 49 assert a kit primitive, 28 invoke the fuller capability/approval governor, and 222 assert no primitive gate.

VALO rule:

- every externally consequential tool maps to a canonical action type
- every action requires an authority envelope, REHT clearance and one-shot permit
- unknown or unmapped tools fail closed
- coverage is measured by executable conformance tests, not by catalog size

### Revocation does not cover HTTP reads

Naïve documents that profile revocation is checked on mutating HTTP methods, while GET requests continue as if the profile were active. MCP is stricter and rejects every tool call.

VALO rule:

- revocation applies to reads and writes unless an explicit break-glass observation capability is independently authorized
- read access can disclose secrets, personal data, strategy or internal state and is not inherently harmless
- action semantics, not HTTP method, determine admissibility

### Cached MCP identity and tool snapshot

Naïve documents that the SSE authentication context is resolved at connection time and the tool list is a connect-time snapshot. A client that authenticates only on connect may retain its session until disconnect, and revoked tools can remain visible even when calls are later refused.

VALO rule:

- session identity is bound to a short-lived credential
- authority and revocation are checked on every call
- policy and tool exposure are refreshed on every call or by a cryptographically bound version that is rejected when stale
- listing a tool is not authorization, but stale listings are still an unnecessary attack and confusion surface

### Human and default-user approval bypass

Naïve documents that signed-in humans are never approval-gated and that the default tenant user bypasses approval as a solo-developer convenience.

VALO explicitly rejects both exceptions.

Humans have identity and authority; they are not magical bypass channels. A human action may follow a different policy path, but a consequence-bearing action still requires valid authority, scope, purpose and state. Development convenience must use an explicit sandbox policy, never an identity-based bypass hidden in production semantics.

### Best-effort activity log

Naïve documents that `activity_events` catches insert failures so logging cannot fail the business action. It explicitly states that the activity stream is not an audit ledger and that an absent row does not prove an absent act.

This directly validates Veritas.

VALO rule:

- operational activity logs may be best-effort and useful for observability
- they are never called proof
- REHT decisions require stable decision identities and authoritative receipts
- execution evidence is emitted on the execution path and chained for Veritas
- a missing required receipt is a failed or unknown governed execution, never a green outcome

### Missing policy-decision ledger

Naïve documents that the designed `policy_decisions` table does not exist in the current build. It correctly returns no fabricated decision identifier.

VALO adopts the honesty invariant:

```text
no evidence => unknown or unavailable
never fabricate a decision id, receipt or successful control
```

VALO tightens the runtime consequence: where the configured assurance level requires an authoritative decision ledger, absence of a decision identity fails closed.

### "Absolute mid-action revoke" is too broad

A revocation check can block an action before execution, stop a staged workflow between steps, reject the next call or invoke provider cancellation where supported. It cannot guarantee reversal of an external side effect already accepted by a bank, carrier, email server or third-party API.

VALO vocabulary:

- pre-execution revoke: deterministic block at the execution boundary
- in-flight cancellation: best effort or provider-guaranteed, explicitly classified
- post-commit compensation: a new governed action
- irreversible consequence: cannot be described as revoked retroactively

The profile therefore records both `provider_cancellation_when_supported` and `external_side_effects_are_not_reversible`.

## Canonical mapping

| Naïve concept | VALO placement |
| --- | --- |
| Agent profile | Portable governed-agent profile specification; no authority |
| Legal identity bundle | Principal/actor identity and opaque legal-entity/resource references |
| Account Kit | Policy input and profile template; consumed by REHT |
| Governed tool handle | Secret-free adapter handle exposed to a runtime |
| Naïve governor | REHT authorization boundary |
| Gateway | valo-gateway mechanical permit enforcement |
| Capability allow/deny | REHT authority, policy and resource-scope evaluation |
| Hard/soft spend cap | Exposure constraints plus atomic reservation |
| Approval queue | Frozen action plus human attestation and REHT re-clearance |
| MCP session | Short-lived delegated session bound to profile and runtime |
| Activity log | Non-authoritative operational observability |
| Decision ledger | Authoritative REHT decision record |
| Execution record | Veritas receipt and external observation |
| Hosted/BYO runtime | Harness/system-governance choice; does not alter authorization |
| Sub-agent profile | Narrower child profile with inherited constraints |
| Revoke | Dynamic authority/session/profile revocation checked at execution |

## Commercial assessment

Naïve is adjacent to VALO in product presentation and execution-boundary language, but its commercial core is different.

Naïve's moat is the operated regulated bundle: card issuing, identity and company formation relationships, registered communications, hosted runtime and a large tool catalog. Its own open-core rule is based on whether it is the regulated counterparty of record. The SDK, CLI and templates are distribution.

VALO's defensible layer is vendor-neutral authorization and proof across providers:

- independent authority semantics
- exact-action authorization at the execution boundary
- formal non-bypass invariants
- transport- and runtime-independent conformance
- deterministic one-shot permits
- authoritative decision and execution evidence
- separation of evaluator, authorizer, enforcer and evidence recorder

Naïve is therefore three things simultaneously:

1. A market validator for runtime-independent action governance.
2. A potential downstream execution provider behind REHT and valo-gateway.
3. A future competitor if it completes transport coverage, removes bypasses, adds an authoritative decision ledger and generalizes its governor beyond its own regulated primitives.

The correct integration shape is:

```text
agent runtime
  -> VALO governed tool handle
  -> REHT clearance
  -> valo-gateway permit enforcement
  -> Naïve API or MCP primitive
  -> Naïve provider result
  -> Veritas receipt and reconciliation
```

Naïve may enforce its own caps and approvals as defense in depth. Those controls do not replace REHT and do not become the authoritative VALO decision.

## Adopted in this change

- `GovernedAgentProfile` frozen contract
- operational identity without legal-personhood claim
- opaque resource and credential references
- explicit live resource scopes; no wildcard access
- runtime-independent compilation
- secret-free governed tool bundles
- hard and soft budget declarations with atomic-reservation requirement
- frozen-payload approval requirements with mandatory REHT re-clearance
- short-lived header-only delegated-session descriptors
- per-call policy and tool-catalog refresh requirement
- authoritative decision ledger and Veritas receipt requirements
- strict revocation of reads, writes, sessions and children
- child-profile narrowing proof
- CLI validation, inspection, fingerprinting, tool listing, compilation and comparison
- reference profile and executable tests

## Required follow-on implementation

These are real implementation dependencies, not changes to the canonical boundary:

1. Persistent profile registry with signed profile versions and dynamic lifecycle state.
2. Tool-catalog service that emits only profile-compatible handles and fails closed on unmapped actions.
3. Delegated-session issuer with bearer generation, revocation storage and per-call subject resolution.
4. Atomic budget reservation and settlement bound to action digest and permit id.
5. Frozen-action store producing `HumanApprovalAttestationV1` and requiring REHT re-clearance.
6. Profile and session revocation registry checked immediately before permit consumption.
7. Veritas sink that treats missing required decision or execution evidence as unknown/failed assurance.
8. Cross-protocol conformance proving identical coverage for MCP, HTTP, gRPC, A2A and direct SDK paths.

None of these permit the profile, CLI, runtime, gateway or downstream provider to create authority.
