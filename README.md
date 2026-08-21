# valo-gateway

Vendor-neutral reference enforcement infrastructure for governed actions.

One gateway core. Many protocols, harnesses, runtimes and tool adapters. No adapter creates authority. No vendor owns the execution boundary.

## Boundary

`valo-gateway` does not evaluate risk, infer authority or decide whether an action should be allowed. It accepts an exact action plus an externally produced authorization/decision binding, validates required bindings immediately before execution, consumes one-shot execution capability, invokes the selected tool/runtime and emits an execution receipt.

```text
candidate action
      |
      v
authorization / decision provider
      |
      v
portable decision + action binding
      |
      v
valo-gateway mechanical enforcement
      |
      v
external consequence -> receipt / verifier
```

REHT and RACS are compatible authorization/protocol implementations used by VALO, but they are not required Python dependencies of the gateway. An external system may provide equivalent bindings through the public contract surface.

## Governed agent profiles

A governed agent profile is a portable, runtime-agnostic description of an agent's operational identity, resource handles, exposed tools, budgets, approval rules, delegated-session limits, audit requirements and revocation semantics.

The profile references an authority envelope. It does not grant authority. Every consequence-bearing tool still requires an exact, current authorization binding and one-shot execution capability at the gateway.

The same profile can be compiled for LangGraph, Claude Code, OpenAI Agents, Google runtimes, a custom loop or a hosted runtime without changing its profile digest or enforcement boundary. Compiled bundles contain opaque handles and references, never provider credentials.

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

## Provider integrations

Runtime, identity, MCP, A2A and tool integrations are adapters around the same enforcement boundary. Provider metadata, confirmations, credentials and runtime state remain non-authoritative inputs unless a configured upstream authorization provider explicitly establishes their governed standing.

No adapter may create authority or retain an independent consequence-bearing effect path.

## Packages

- `contracts`: action, authority, clearance/decision, permit and receipt types
- `agent_profile`: runtime-agnostic governed profiles and narrowing rules
- `gateway`: binding validation, permit consumption, replay protection, HALT/revocation and fail-closed execution
- `harness`: routing, lifecycle, event stream and checkpoint contracts
- `protocols`: MCP, A2A, HTTP, gRPC and provider ingress normalization
- `runtime_adapters`: replaceable runtime adapters
- `tool_adapters`: mechanical tool wrappers and registry
- `profiles`: reference governed-agent profiles
- `sdk`: plugin composition API
- `cli`: profile validation, inspection, compilation and session tooling
- `conformance`: vendor-neutral contract and non-bypass tests

## Publication

See `PUBLICATION_STATUS.md`. The public role is mechanical reference enforcement, not authorization or policy ownership.

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

## Consolidation sources

This repository consolidates active contracts and reference implementations from earlier VALO runtime/gateway repositories. Exact source identities are recorded in `MIGRATION_MANIFEST.json`.

## License

Apache License 2.0. See `LICENSE`.
