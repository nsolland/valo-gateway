# Cloudflare Browser Run / Kitesurf adoption

Status: implemented
Source signal: Cloudflare Kitesurf launch on Product Hunt, 2026-08-07
Stable provider contract: Cloudflare Browser Run CDP

Sources:
- https://www.producthunt.com/products/cloudflare
- https://developers.cloudflare.com/browser-run/
- https://developers.cloudflare.com/browser-run/cdp/

## Decision

VALO adopts Cloudflare Browser Run as an execution substrate and Kitesurf as a selectable Cloudflare browser backend.

VALO does not treat Cloudflare as an authorization system.

The adapter targets the stable Browser Run / CDP boundary. It does not introduce a hard dependency on a Kitesurf SDK or an undocumented provider API. Provider credentials remain outside the agent-controlled invocation and must be injected by the dispatcher or deployment environment.

## Canonical boundary

VAIG -> REHT -> RACS -> valo-gateway -> Cloudflare Browser Run / Kitesurf -> external web -> Veritas

- VAIG evaluates.
- REHT clears the consequence-bearing action immediately before execution.
- RACS expresses the deterministic decision contract.
- `valo-gateway` mechanically enforces the one-shot execution permit.
- Cloudflare performs browser execution.
- Veritas records immutable evidence of authorized and observed execution.

Cloudflare session state, Live View, human intervention, recordings, CDP/MCP connectivity and provider credentials do not create VALO authority.

## Contract

`src/valo_gateway/runtime_adapters/cloudflare_browser.py` provides:

- `CloudflareBrowserBackend` with `kitesurf` and `browser_run`;
- `CloudflareBrowserContext` for non-authoritative provider/session evidence;
- `CloudflareBrowserRunAdapter` for CDP/browser dispatch;
- recursive fail-closed rejection of authority-shaped fields in browser arguments.

The generic execution contract now includes:

- `ExecutionProtocol.CDP`;
- `ExecutionMode.BROWSER`.

The adapter deliberately carries no `Authorization`, API token, cookie or credential header. The existing `ExecutionTransportContext` rejects those fields. Authentication is a deployment concern and must be bound out of band.

## Why

Kitesurf is positioned as a stateless, agent-first browser running on Cloudflare Workers. Browser Run already exposes stable browser automation through CDP and supports Playwright, Puppeteer and MCP-compatible clients.

That makes Cloudflare useful for scalable browser execution, especially short-lived research and web automation workloads, without changing VALO's authority model.

## Conformance

`tests/test_cloudflare_browser_adapter.py` proves:

- Cloudflare dispatch uses CDP + browser execution semantics;
- provider/session/recording/HITL state has `authority_effect=none`;
- authority-shaped browser arguments fail closed;
- the adapter has no authorization conversion path;
- a valid VALO one-shot permit is still required and cannot be replayed.

## Canonical rule

Cloudflare provides the browser. VALO decides whether the browser action is allowed to happen.
