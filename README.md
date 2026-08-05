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

## Packages

- `contracts`: action, authority, clearance, permit, decision-contract and receipt types
- `gateway`: binding validation, permit consumption, replay protection, HALT/revocation and fail-closed execution
- `harness`: routing, lifecycle, event stream and checkpoint contracts
- `protocols`: MCP, A2A, HTTP, gRPC and ext_authz ingress normalization
- `runtime_adapters`: local, OpenAI, Claude and Google runtime adapters
- `tool_adapters`: mechanical tool wrappers and registry
- `profiles`: governed communications, agent tool use, edge and enterprise sidecar profiles
- `sdk`: plugin composition API
- `conformance`: vendor-neutral contract and non-bypass tests

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

## Consolidation sources

This repository consolidates active contracts and reference implementations from `valo-runtime-core`, `valo-runtime-local`, `valo-runtime-adapters`, `valo-tool-adapters`, and the mechanical gateway code in `valo-platform`.

Exact source identities are recorded in `MIGRATION_MANIFEST.json`.
