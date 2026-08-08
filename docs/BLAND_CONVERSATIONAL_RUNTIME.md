# Bland AI conversational runtime adoption

Status: implemented adapter contract; production credentials/integration remain optional provider configuration.

Canonical base: `2e6d1b46b8dfb376a0c8c96cd8aec9e0b3dd40ac`

Branch: `feat/bland-conversational-runtime-adapter`

Claim/owner: ChatGPT execution worker

## Decision

Adopt Bland as a replaceable conversational runtime and execution substrate behind existing VALO contracts. Do not copy Bland's product taxonomy into VALO architecture and do not treat Bland guardrails, authentication, releases, outcomes, memories or operator UI as execution authority.

Bland is useful because it already provides a production surface for voice and messaging agents with Pathways, custom/webhook/code tools, transfers, caller authentication, persistent memory, outcomes, test scenarios, production observability and staged releases.

Canonical placement:

```text
caller / message
→ Bland conversation runtime
→ pathway/persona/tool selection
→ proposed consequential action
→ VAIG evaluation evidence
→ REHT exact-action clearance + one-shot permit
→ valo-gateway mechanical enforcement
→ provider/source-system consequence
→ Veritas observation / receipt
```

Bland may also perform provider-native communication actions such as starting a call, sending a message or transferring a call. Where those actions are consequence-bearing under the active policy, they follow the same authorization path.

## Runtime adapter

`BlandRuntime` normalizes four execution surfaces:

- custom tool invocation;
- outbound call start;
- message send;
- call transfer.

The adapter binds the proposed action to conversational execution context including:

- organization reference;
- call and conversation references;
- persona;
- pathway and pathway version;
- node;
- channel;
- release/version reference;
- memory context reference;
- credential-context fingerprint;
- exact operation, target and parameters.

The resulting `execution_context_hash` changes when material conversational or release context changes. Bland credentials are never placed in the proposed action.

## Authority boundary

The following are evidence or provider state only:

- a Bland tool being configured or available;
- the agent deciding to invoke a tool;
- Pathway routing;
- persona identity;
- caller authentication state;
- guardrail pass/fail;
- a human-transfer decision;
- release/canary status;
- memory state;
- outcome classification;
- a successful Bland test or eval;
- Norm-generated fixes;
- possession of Bland/API credentials.

None grants or widens VALO authority.

A useful distinction is:

```text
Bland caller authentication
= evidence about who the caller is / what provider-side gates passed

REHT execution authorization
= whether this exact consequential action may happen now
```

## Factory patterns adopted from Bland

Bland contains several patterns that belong in the wider AI OS / Software Factory even when Bland is not the runtime provider.

### Production trace → reproducible defect

A real production interaction can become a structured defect/evidence object rather than a screenshot or anecdote. Preserve the originating trace, pathway/version, tool logs, outcome and relevant evidence references.

Factory mapping:

```text
production observation
→ defect/evidence package
→ reproduce against exact version
→ candidate patch
→ independent evaluation
→ governed promotion
```

### Scenario and historical regression suites

Bland's scenario testing, node-level Testbed and back-testing against historical calls reinforce the existing Factory rule that real failures become durable regression fixtures.

Adopt provider-neutral fixtures for:

- edge cases;
- adversarial/user-behavior cases;
- interruption and escalation;
- tool failures;
- authentication failures;
- policy/guardrail cases;
- historical production failures.

A test pass remains evidence, never activation authority.

### Draft/version/release separation

Keep editable candidate state separate from the committed/released version. A behavior edit, pathway edit or generated fix must have a stable digest/version identity before evaluation and rollout.

This maps directly to the existing governed-behavior lifecycle:

```text
draft/candidate
→ deterministic version/digest
→ test/eval
→ shadow
→ canary
→ active
→ observe
→ quarantine/rollback when required
```

### Canary and rollback as first-class runtime states

Bland exposes staged real-traffic releases and rapid rollback. VALO already has shadow/canary/active/quarantine/rollback semantics; Bland validates that this should be a general Factory primitive, not an agent-specific feature.

The critical VALO addition is authorization and evidence binding around activation and rollback. A provider's Promote button is not authority by itself.

### Triage / Norm fix-and-verify loop

Bland Triage can attach originating calls to an issue and use Norm to reproduce, diagnose, patch a pathway and verify it with simulations.

Adopt the workflow pattern, not self-attestation:

```text
observed defect
→ evidence-linked issue
→ discovery/diagnosis worker
→ execution worker proposes patch
→ original failure replay + regression suite
→ independent judgment/QC
→ governed promotion
```

The worker that generated the fix cannot be the sole judge of success. Provider-side verification is useful evidence but does not replace independent QC.

### Outcomes as learning labels

Bland classifies calls into outcomes such as resolution, transfer, booking or other business results. Adopt the general rule that runtime executions should produce normalized outcome references suitable for Learning Factory and ACE economics.

Do not equate a provider outcome label with verified business value. Where value is claimed, bind it to independent outcome evidence.

### Persistent memory is context, not mandate

Cross-session caller memory is operationally useful. Treat it as governed context with provenance, freshness, retention and revocation requirements. Memory may influence a proposal; it must never revive an expired permit or delegation.

### Omnichannel runtime behind one agent contract

Bland increasingly shares pathways/personas/memory across voice and messaging channels. Adopt the provider-neutral pattern: one governed agent/workflow identity may project through several channel adapters while authority remains bound to the exact channel action and target.

## What not to adopt

Do not adopt:

- Bland as a new top-level VALO layer;
- provider guardrails as REHT replacement;
- caller authentication as execution authorization;
- Norm as independent QC for its own patch;
- automatic promotion because simulations pass;
- provider memory as authority or delegation state;
- outcome labels as verified ROI;
- provider credentials as mandate;
- a Bland-specific action schema inside REHT/RACS.

## Strategic use

Bland can serve two roles simultaneously:

1. an optional production conversational runtime for customer deployments and external-production proofs;
2. an external reference implementation for how mature agent operations handle testing, releases, rollback, observability, issue triage and outcome learning.

The first belongs in `valo-gateway`. The second feeds Factory OS / Learning Factory patterns. Neither changes the canonical boundary:

```text
VAIG evaluates.
REHT authorizes.
valo-gateway mechanically enforces the cleared action.
Veritas records what actually happened.
```

## Public sources reviewed

- https://www.bland.ai/
- https://www.bland.ai/product
- https://www.bland.ai/changelog
- https://www.bland.ai/glossary
- https://www.bland.ai/pricing
