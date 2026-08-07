# Gemini Managed Agents adapter

Status: active implementation
Owner: ChatGPT/Codex worker for Njål
Canonical base: `2db0d79edb348a4fbf08f619a290e7e13df93f29`
Branch: `feat/gemini-managed-agents-adapter`

Owned files for this delivery:

- `src/valo_gateway/runtime_adapters/gemini_managed.py`
- `src/valo_gateway/runtime_adapters/__init__.py`
- `tests/test_gemini_managed_runtime.py`
- `conformance/test_plugins.py`
- `docs/GEMINI_MANAGED_AGENTS.md`

## Purpose

Treat Google Gemini Managed Agents as an execution substrate, not as a new governance layer.

Canonical path:

```text
Gemini Managed Agent
  -> VALO runtime adapter
  -> normalized proposed action
  -> VAIG evidence
  -> REHT clearance + one-shot execution permit
  -> valo-gateway mechanical enforcement
  -> MCP/function/API consequence
  -> Veritas receipt
```

The adapter never creates authority, clearance, permits or policy decisions.

## Adopted substrate bindings

The adapter preserves Google runtime identity and state as execution context:

- `interaction_id`
- `environment_id`
- background execution state
- proposed function or MCP tool call
- credential-context fingerprint
- substrate grant reference
- execution-context hash

`execution_context_hash` is VALO-owned and deterministic. It binds the runtime context to the proposed effect without making Google identifiers authoritative.

`substrate_grant_ref` is an opaque reference only. It is not itself authorization and cannot replace a REHT permit.

## `requires_action` boundary

Custom function calls exposed as `requires_action` are normalized into a proposed action for REHT processing. The adapter does not execute the function and does not translate `requires_action` into ALLOW.

For remote MCP, the governed deployment topology is:

```text
Gemini -> valo-gateway -> internal MCP
```

Direct Gemini-to-internal-MCP execution is outside the governed topology because it bypasses the execution boundary.

## Background and persistent execution

A clearance obtained when a background job starts is not sufficient for later effects. Each external consequence still requires a valid one-shot permit at the effect boundary.

Persistent environments are security-relevant state. A change to environment, credentials, action, target, parameters or other bound execution context changes `execution_context_hash` and therefore requires fresh authorization material.

## Non-negotiable invariants

- No Google runtime event can mint or upgrade authority.
- No `requires_action` event can execute directly through this adapter.
- Remote MCP is treated as an external consequence and must remain behind the gateway.
- Credentials are represented only by a fingerprint/opaque reference, never raw secret material.
- Background execution does not extend permit lifetime or permit reuse.
- Persistent runtime state is evidence/context, not authority.
