# Public architecture

`valo-gateway` is a vendor-neutral mechanical execution boundary.

It normalizes ingress, validates an externally produced exact-action authorization/decision binding, consumes the required one-shot execution capability, dispatches to a selected public adapter, and returns deterministic execution evidence.

## Execution invariants

1. Missing required authority basis, decision binding, permit or exact action binding fails closed.
2. Only a positively admitted exact action may progress to execution.
3. A one-shot permit is consumed immediately before the external call and cannot be reused.
4. A failed external call still consumes the permit and produces failure evidence.
5. Revocation or halt state is checked at the execution boundary.
6. Runtime and tool adapters never create authority or upgrade a decision.
7. Protocol adapters normalize transport; they do not interpret governing policy.
8. Receipt sinks record evidence; they do not authorize.
9. `NO_DIRECT_EFFECT_PATH`: consequence-bearing effects cross the governed enforcement boundary.
10. `NULL_EFFECT_ON_DENY`: a non-admitted decision invokes no effector and creates no consequence.
11. Live credentials and executable capabilities remain behind the governed path; callers receive bounded references or handles.
12. Boundary replay verifies pinned public contract inputs without re-executing the external effect.

## Governed agent profile

A governed agent profile is portable configuration, not an authorization object. It may describe identity references, bounded tools/resources, budgets, approval requirements, session limits, audit requirements and revocation semantics.

A profile cannot mint authority, a permit, an approval attestation or a provider credential.

## Public profile invariants

- tool/resource scope is explicit and bounded;
- secret material is not embedded in portable profile artifacts;
- child profiles may only narrow their parent where delegation is supported;
- live execution still requires the configured external authorization and enforcement contract;
- activity logs are evidence inputs, not execution authority.

## Separate concerns

Runtime isolation and consequence authorization are distinct. A secure sandbox does not authorize an action, and a valid action binding does not by itself prove that the runtime is securely isolated.

This public architecture describes only the gateway's observable contract. Private portfolio topology, private component identities, unpublished orchestration and internal research architecture are intentionally outside this repository.
