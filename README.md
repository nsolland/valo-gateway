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

Public compatible authorization/protocol implementations may provide bindings, but they are not required Python dependencies of the gateway. An external system may provide equivalent bindings through the public contract surface.

## Governed agent profiles

A governed agent profile is a portable, runtime-agnostic description of an agent's operational identity, resource handles, exposed tools, budgets, approval rules, delegated-session limits, audit requirements and revocation semantics.

The profile references an authority basis. It does not grant authority. Every consequence-bearing tool still requires an exact, current authorization binding and one-shot execution capability at the gateway.

Compiled bundles contain opaque handles and references, never provider credentials.

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

Runtime, identity, protocol and tool integrations are adapters around the same enforcement boundary. Provider metadata, confirmations, credentials and runtime state remain non-authoritative inputs unless a configured upstream authorization provider explicitly establishes their governed standing.

No adapter may create authority or retain an independent consequence-bearing effect path.

## Packages

- `contracts`: public action, authority-reference, decision-binding, permit and receipt types
- `agent_profile`: runtime-agnostic governed profiles and narrowing rules
- `gateway`: binding validation, permit consumption, replay protection and fail-closed execution
- `harness`: routing, lifecycle, event stream and checkpoint contracts
- `protocols`: public ingress normalization
- `runtime_adapters`: replaceable runtime adapters
- `tool_adapters`: mechanical tool wrappers and registry
- `profiles`: reference governed-agent profiles
- `sdk`: plugin composition API
- `cli`: profile validation, inspection, compilation and session tooling
- `conformance`: vendor-neutral contract and non-bypass tests

## Publication

See `PUBLICATION_STATUS.md`. The public role is mechanical reference enforcement, not authorization or policy ownership.

Internal source-repository mappings, portfolio topology, migration sequencing and unpublished implementation relationships are intentionally not part of this public surface.

## Consequence Governance reference

The enforcement boundary implemented here is one public surface used in the paper **Consequence Governance: Governing the Transition from Proposed Action to Real-World Effect** (Version 1.0, September 5, 2026).

- Zenodo record: https://zenodo.org/records/22377951
- Category reference: https://valoresearch.org/consequence-governance.html

The paper defines the broader category and the Governed Effect Path. `valo-gateway` remains the mechanical enforcement layer: it does not create authority, evaluate admissibility or widen an upstream decision.

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

## License

Apache License 2.0. See `LICENSE`.


## Governed adaptive-loop MVP

A runnable end-to-end example demonstrates learned guidance shaping a proposal
without creating authority, fresh authorization at the consequence boundary,
one-shot governed execution, effect receipts, and evidence-fed renewal.

```bash
python -m examples.governed_adaptive_loop.app
```

The same demo also revokes authority after permit issuance and verifies that the
effect path remains null at execution time.

See `examples/governed_adaptive_loop/README.md`.
