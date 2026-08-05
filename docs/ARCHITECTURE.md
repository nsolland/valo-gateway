# Architecture

`valo-gateway` is a horizontal execution-infrastructure boundary with no LA identity.

It normalizes ingress, validates an exact REHT clearance, consumes a one-shot execution permit, dispatches to a selected plugin, and returns deterministic execution evidence.

## Invariants

1. Missing authority, clearance, permit or exact action binding fails closed.
2. Only `ALLOW` or an already-materialized `MODIFY` may issue a permit.
3. A permit is one-shot and consumed before the external call.
4. A failed external call still consumes the permit and produces a failure receipt.
5. HALT or revocation is checked immediately before permit consumption.
6. Runtime and tool plugins never create authority or upgrade a decision.
7. Protocol adapters normalize transport; they do not interpret policy.
8. Receipt sinks record evidence; they do not authorize.
