# valo-gateway

Vendor-neutral execution infrastructure and mechanical enforcement SDK for VALO.

One gateway core. Many protocols, harnesses, runtimes and tool adapters. No adapter creates authority. No vendor owns the execution boundary.

## Boundary

`valo-gateway` does not evaluate like VAIG and does not authorize like REHT. It accepts an exact action that has already been cleared, validates all bindings immediately before execution, consumes the one-shot permit, invokes the selected tool or runtime, and emits an execution receipt for Veritas.

```text
proposal -> VAIG evaluation evidence -> REHT clearance + execution permit
         -> valo-gateway mechanical enforcement -> external consequence
         -> Veritas receipt/observation
```

RACS is immutable decision-contract data carried by the clearance. It is not an active service or execution step.

## Governed agent profiles

A governed agent profile is a portable, runtime-agnostic description of an agent's operational identity, resource handles, exposed tools, budgets, approval rules, delegated-session limits, audit requirements and revocation semantics.

The profile references an authority envelope. It does not grant authority. Every governed tool still requires an exact REHT clearance and one-shot execution permit.

The same profile can be compiled for LangGraph, Claude Code, OpenAI Agents, a custom loop or a hosted runtime without changing its profile digest or authorization boundary. Compiled bundles contain opaque handles and references, never provider credentials.

```bash
valo-gateway profile validate src/valo_gateway/profiles/governed_agent_profile.json
valo-gateway profile fingerprint src/valo_gateway/profiles/governed_agent_profile.json
valo-gateway profile tools src/valo_gateway/profiles/governed_agent_profile.json --environment live
valo-gateway profile compile src/valo_gateway/profiles/governed_agent_profile.json \
  --runtime-id custom-loop --environment live
valo-gateway profile session-descriptor src/valo_gateway/profiles/governed_agent_profile.json \
  --runtime-id custom-loop --ttl-seconds 900
valo-gateway profile compare-parent parent.json child.json
```

The Naïve architecture assessment and exact adoption decisions are recorded in `docs/NAIVE_ADOPTION.md`.

## Packages

- `contracts`: action, authority, clearance, permit, decision-contract and receipt types
- `agent_profile`: runtime-agnostic governed profile, tool, budget, approval, session, audit and revocation contracts
- `gateway`: binding validation, permit consumption, replay protection, HALT/revocation and fail-closed execution
- `harness`: routing, lifecycle, event stream and checkpoint contracts
- `protocols`: MCP, A2A, HTTP, gRPC and ext_authz ingress normalization
- `runtime_adapters`: local, OpenAI, Claude and Google runtime adapters
- `tool_adapters`: mechanical tool wrappers and registry
- `profiles`: governed communications, agent tool use, edge, enterprise sidecar and governed-agent reference profiles
- `sdk`: plugin composition API
- `cli`: profile validation, inspection, compilation, session descriptors and parent-child narrowing checks
- `conformance`: vendor-neutral contract and non-bypass tests

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

## Consolidation sources

This repository consolidates active contracts and reference implementations from `valo-runtime-core`, `valo-runtime-local`, `valo-runtime-adapters`, `valo-tool-adapters`, and the mechanical gateway code in `valo-platform`.

Exact source identities are recorded in `MIGRATION_MANIFEST.json`.
