# Effect Boundary Conformance

## Canonical invariants

`NO_DIRECT_EFFECT_PATH` means every consequence-bearing effect traverses the
Gateway's bounded enforcement path. This includes writes to state, memory,
configuration or instructions when the write can alter a future
consequence-bearing decision.

`NULL_EFFECT_ON_DENY` means `DENY`, `DEFER`, `STEP_UP` and `HALT` produce no
effector invocation or consequence. A non-ALLOW decision cannot mint a permit;
even a forged permit is rejected against the current decision contract.

The Structural Coupling Test asks whether an effect can still occur while its
governance basis is invalid, stale, revoked, suspended or unresolved. The
conforming answer is no: the permit remains unconsumed and the effector remains
uninvoked.

## Exclusive effectors

`ToolRegistry` retains the executable tool and only exposes an opaque
`EffectorHandle` bound to one capability, target and optional opaque credential
reference. `FunctionTool.invoke()` and consequence-bearing runtime-adapter
`invoke()` methods reject direct calls. Adapters may build a pure invocation
description, but only the Gateway can pass a sealed boundary proof to dispatch
it. Public-only legacy effectors are rejected before resources or a permit are
consumed. The Gateway validates registered handles against the exact action.
Raw credential material is not accepted by this contract.

Secret-free runtime and transport adapters remain normalizers. Possession of an
adapter, profile, session, approval, skill or handle creates no authority.

## Deterministic boundary replay

`BoundaryReplayInput` pins:

- the deterministic contract;
- Kernel/current state context;
- authority;
- evidence;
- RACS decision;
- exact action, clearance and permit.

Replay recomputes these bindings, returns a sealed `READY` or `BLOCKED` result,
and never invokes the effector. It is boundary replay, not token-level LLM
replay. Prompt, completion, token and reasoning-trace reproduction are explicit
non-goals.

## Ownership

Kernel owns governed state and contracts. REHT owns fresh exact-action
authorization. RACS owns the deterministic decision and effect-path contract.
Gateway enforces the bounded path. Veritas verifies evidence and outcome.

GATE, Microsoft AGT and z-gateway are external evidence only. This
implementation has no dependency on them.
