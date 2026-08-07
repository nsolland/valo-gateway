# Cloudflare execution substrate adoption

Status: adopted
Verified against Cloudflare documentation: 2026-08-07

## Decision

Cloudflare is adopted as a first-class execution substrate for VALO, not as an authorization or governance authority.

Canonical separation:

```text
proposal / model output
-> VAIG evidence and model admissibility
-> REHT clearance + fresh one-shot execution permit
-> RACS decision contract
-> valo-gateway mechanical enforcement
-> Cloudflare execution surface
-> Veritas execution observation / receipt
```

Cloudflare AI Gateway may sit earlier in the chain around model access, routing and observability. Its routing, guardrails, rate limits, retries and fallback decisions are operational/model-infrastructure signals. They do not create REHT clearance.

## Adopted Cloudflare surfaces

### Workers

Workers are mechanical execution targets. A Worker may receive an already-governed action after the permit is consumed by `valo-gateway`. Worker identity, deployment and routing metadata are execution context only.

### MCP

Cloudflare-hosted or Cloudflare-consumed MCP tools remain ordinary governed tool targets. Tool discovery and transport authentication do not imply permission to perform the consequential action.

### Sandbox

Cloudflare Sandbox is adopted for isolated execution of model-generated or otherwise untrusted code. Isolation answers where code may run; REHT still decides whether an external consequence may occur.

### Workflows

Cloudflare Workflows are adopted for durable multi-step execution, retry, recovery and waits. A resumed Workflow does not revive a consumed or expired permit. Every new external consequence requires current clearance and a fresh one-shot permit.

### Durable Objects

Durable Objects are adopted as state/identity/coordination substrate. Durable state may be bound into the execution-context digest so the governed action is tied to the expected agent/session state. Durable Objects do not hold VALO authority.

### AI Gateway

AI Gateway is adopted as model-routing and evidence infrastructure. Provider/model selection, logging, token/cost metrics, retries, fallbacks, caching, rate limits and route identity may feed VAIG/MAL/evidence handling. AI Gateway does not replace VAIG evaluation, REHT clearance or RACS expression.

## Adapter contract

`CloudflareRuntime` normalizes Worker, MCP, Sandbox and Workflow proposals into the same `valo-gateway` route used by other runtimes.

`CloudflareExecutionContext` binds non-authoritative Cloudflare context into a deterministic execution hash:

- account reference
- deployment reference
- Durable Object reference
- AI Gateway reference
- Workflow instance reference
- Sandbox reference
- resume checkpoint reference
- credential-context fingerprint

The adapter never transports raw credentials and never carries a VALO permit, clearance, decision or policy digest as Cloudflare runtime context.

## Invariants

1. Cloudflare can execute; it cannot mint or widen authority.
2. AI Gateway model routing is not authorization.
3. Durable Object state is not authorization state.
4. Sandbox isolation is not authorization.
5. MCP discovery or OAuth/token transport is not authorization.
6. Workflow retry/resume cannot reuse an old one-shot permit for a new external consequence.
7. Credentials remain outside the governed profile; only an opaque SHA-256 credential-context fingerprint may be bound into execution context.
8. `valo-gateway` remains the mechanical point that consumes the REHT-issued permit immediately before external dispatch.
9. Veritas remains responsible for evidence of what actually occurred after dispatch.

## Reference implementation

`src/valo_gateway/runtime_adapters/cloudflare.py` is the reference Cloudflare substrate adapter. It intentionally does not contain a policy engine, clearance logic or authorization state.

## Upstream references

- Cloudflare Agents: https://developers.cloudflare.com/agents/
- Cloudflare MCP: https://developers.cloudflare.com/agents/tools/mcp/
- Cloudflare Sandbox: https://developers.cloudflare.com/agents/tools/sandbox/
- Cloudflare Workflows with Agents: https://developers.cloudflare.com/agents/concepts/workflows/
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare AI Gateway: https://developers.cloudflare.com/ai-gateway/
