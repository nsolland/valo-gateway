# Architecture

`valo-gateway` is a horizontal execution-infrastructure boundary with no LA identity.

It normalizes ingress, validates an exact REHT clearance, consumes a one-shot execution permit, dispatches to a selected plugin, and returns deterministic execution evidence.

## Execution invariants

1. Missing authority, clearance, permit or exact action binding fails closed.
2. Only `ALLOW` or an already-materialized `MODIFY` may issue a permit.
3. A permit is one-shot and consumed before the external call.
4. A failed external call still consumes the permit and produces a failure receipt.
5. HALT or revocation is checked immediately before permit consumption.
6. Runtime and tool plugins never create authority or upgrade a decision.
7. Protocol adapters normalize transport; they do not interpret policy.
8. Receipt sinks record evidence; they do not authorize.
9. `NO_DIRECT_EFFECT_PATH`: every consequence-bearing effect, including a state
   or memory write that can alter a future consequence-bearing decision, crosses
   the governed enforcement boundary.
10. `NULL_EFFECT_ON_DENY`: `DENY`, `DEFER`, `STEP_UP` and `HALT` invoke no
    effector and produce no consequence.
11. Live effector credentials and executable capabilities exist only behind the
    governed path; callers receive opaque, exact-action-bound handles. Public
    runtime-adapter invocation is non-dispatching and fails closed.
12. Boundary replay is deterministic over pinned contract, state, authority,
    evidence and decision inputs. It validates the boundary without calling the
    effector and does not attempt token-level LLM replay.

## Governed agent profile

The governed agent profile is portable configuration, not an authorization object.

```text
profile -> runtime-specific secret-free tool bundle
action proposal -> REHT clearance + permit -> gateway execution
```

The profile may bind:

- principal and actor identity
- opaque legal-entity, communication, payment and credential references
- policy and authority-envelope references
- governed tool handles and explicit resource scopes
- hard and soft exposure limits
- approval requirements
- delegated-session limits
- audit and revocation requirements
- parent-child narrowing relationships

It cannot mint a clearance, permit, approval attestation or credential.

## Profile invariants

1. The same profile keeps the same digest, tools and authorization boundary across runtimes.
2. Tool handles contain opaque references, never provider secrets.
3. Every tool declares canonical action types, environments and explicit live resource scope.
4. Wildcard action or resource scope is forbidden.
5. Every governed tool requires REHT clearance.
6. Hard budgets require atomic reservation before execution.
7. Approval freezes the exact action; approval evidence requires REHT re-clearance before execution.
8. Delegated sessions are short-lived, revocable and carry secrets only in the Authorization header.
9. Authority, policy, revocation and tool exposure are refreshed on every call.
10. Activity logs are non-authoritative; REHT decisions and Veritas execution receipts provide evidence.
11. Revocation covers reads and writes and is checked at the execution boundary.
12. Child profiles may only narrow tools, scope, environments, budgets, sessions and approval thresholds.
13. An operational identity does not claim that an agent is a legal person.

## Two governance planes

System governance controls runtime isolation: process, network, filesystem, memory and sandbox behavior.

Execution governance controls whether a specific consequence-bearing action is authorized now.

A secure sandbox does not authorize an action. A valid execution permit does not prove the runtime is securely isolated. Both planes are required and remain separate.
