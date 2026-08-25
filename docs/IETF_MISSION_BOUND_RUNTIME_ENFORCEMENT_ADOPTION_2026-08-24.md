# Mission-Bound Runtime Enforcement — adoption note

Status: adopted as Gateway enforcement guidance, not as a new REHT architecture.

The relevant external requirement is operational: action authorization is not sufficient unless the execution boundary enforces an action-bound permit at point of use, revalidates current execution state, prevents replay, and emits evidence of the actual effect.

VALO mapping remains:

`Kernel -> reht -> Gateway -> effect -> Veritas -> Kernel admission`

REHT remains the small deterministic authorization core. Gateway is the policy-enforcement/effect boundary. RACS remains a binding contract, not a mandatory runtime hop.

## Adopted requirement

`ONE_SHOT_PERMIT` is only a strong claim when permit consumption is atomic and survives process restart. In a multi-instance deployment, all instances must use the same authoritative consumption store or an equivalent partitioning scheme that makes duplicate consumption impossible.

A process-local set or mutation of one in-memory permit object is insufficient.

## Implementation

`ValoGateway` now claims a permit through `PermitConsumptionStore.consume_once()` immediately before resource/effect execution. The default implementation is SQLite-backed and durable across process restart. Multiple Gateway instances using the same database path share the same atomic PRIMARY KEY claim.

Set `VALO_GATEWAY_PERMIT_STORE` to a durable shared path for the deployment. For multi-host deployments where a shared filesystem is not an accepted consistency boundary, supply a `PermitConsumptionStore` implementation backed by the deployment's atomic consistency service.

Failure after a successful claim remains fail-closed: the permit is not made reusable merely because downstream execution failed.

## Conformance

Negative coverage must prove:

- process restart cannot replay a consumed permit;
- a second Gateway instance cannot consume the same permit;
- the blocked replay produces zero external effect;
- invalid/stale/revoked governance basis is rejected before permit consumption;
- consumption-store uncertainty must never be interpreted as an unused permit.
