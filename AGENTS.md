# AGENTS.md — valo-gateway

## What this is

`valo-gateway` is **mechanical execution infrastructure** — the vendor-neutral
boundary that enforces an already-issued REHT clearance and consumes a one-shot
execution permit. It has **no LA identity** (see `LAYER_IDENTITY.md`): it does
not evaluate like VAIG, does not authorize like REHT, and does not decide
admissibility.

```text
proposal -> VAIG evidence -> REHT clearance + execution permit
         -> valo-gateway mechanical enforcement -> external consequence
         -> Veritas receipt/observation
```

## Non-negotiable invariants

- **Fail closed** on any missing or mismatched binding: authority, clearance,
  permit, action digest, authority envelope id, or clearance id. No exception.
- **Only `ALLOW` or already-materialized `MODIFY`** may issue an execution permit.
- **One-shot permit**: consumed immediately before the external call; a second
  use is replay and is blocked before invocation.
- **A failed external call still consumes the permit** and produces a failure
  receipt. The permit never "returns to the pool".
- **HALT/revocation is checked immediately before permit consumption**; a HALT
  or revoked authority/principal/actor/scope blocks execution without consuming
  the permit.
- **No adapter creates authority.** Runtime and tool plugins normalize and
  dispatch only; they never upgrade a decision or mint a clearance.
- **Protocol adapters normalize transport only**; they do not interpret policy.
- **Evidence chain**: `ExecutionReceipt.previous_receipt_hash` carries the
  chain; receipts are deterministic (`canonical_digest` over sorted JSON).
- **Vendor neutrality**: one gateway core, many protocols/harnesses/runtimes/tool
  adapters; no vendor owns the execution boundary.
- **Profiles reference authority; they never create it.** A governed agent
  profile may reference an authority envelope and policies but cannot mint a
  clearance, permit, approval attestation or credential.
- **Compiled runtime bundles contain no secrets.** Tool and resource access is
  represented by opaque handles only.
- **Every governed tool still requires REHT clearance.** Listing, compiling or
  injecting a tool into a harness is not authorization.
- **Agent Skills are context, never authority.** Discovering, loading or
  installing a `SKILL.md` package does not grant any capability. Skill identity,
  source, content hash, provenance and requested capabilities are bound into the
  action and must match the REHT clearance and one-shot permit at execution.
- **Approval freezes the exact action.** Human approval is evidence consumed by
  REHT; execution requires re-clearance and a new one-shot permit.
- **Activity logs are not proof.** Authoritative REHT decisions and Veritas
  execution receipts are required where the assurance profile demands them.
- **Child profiles only narrow.** They cannot add tools, action types, resources,
  environments, budget, session lifetime or weaker approval thresholds.

## Layout

```
src/valo_gateway/
├── contracts/      # action, authority, clearance, permit, decision-contract, receipt
├── agent_profile.py # runtime-agnostic identity/tool/budget/approval/session contract
├── cli.py           # profile validation, compilation and narrowing checks
├── gateway/        # binding validation, permit consumption, HALT/revocation, fail-closed execution
├── harness/        # routing, runtime lifecycle, event stream, checkpoint contracts
├── protocols/      # MCP, A2A, HTTP, gRPC, ext_authz ingress normalization
├── runtime_adapters/  # local, OpenAI, Claude, Google runtime adapters
├── tool_adapters/  # FunctionTool + ToolRegistry (mechanical wrappers)
├── sdk/            # GatewaySDK composition API
└── profiles/       # governed comms, agent tool use, edge/enterprise/profile references
conformance/        # vendor-neutral contract + non-bypass tests
tests/              # unit tests
```

## Conventions

- Python `>=3.11`, pydantic `>=2.6`.
- Contracts: frozen `pydantic.BaseModel` with `extra="forbid"`, lifecycle
  validators, and `ConfigDict(extra="forbid", frozen=True)`.
- Domain objects that are not contracts use frozen dataclasses.
- `from __future__ import annotations` where union syntax is used.
- No comments unless they carry intent the code does not.
- New controlled actions must be covered by tests and conformance.

## Commands

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q              # unit + conformance
.venv/bin/python -m pytest --cov=valo_gateway   # coverage report
.venv/bin/python -m compileall -q src tests conformance
.venv/bin/python -m ruff check src tests conformance

valo-gateway profile validate src/valo_gateway/profiles/governed_agent_profile.json
valo-gateway profile compile src/valo_gateway/profiles/governed_agent_profile.json \
  --runtime-id custom-loop --environment live
```

CI (`.github/workflows/ci.yml`) runs compileall + pytest on every push/PR.

## Testing expectations

- Every fail-closed path has a test: missing/inactive authority, expired or
  consumed permit, clearance/action/permit binding mismatches.
- Replay is tested by proving the tool is NOT invoked on a consumed permit.
- HALT/revocation is tested by proving the permit is NOT consumed when blocked.
- MODIFY decision path issues a permit; DENY/DEFER/HALT never do.
- Runtime adapters satisfy the adapter contract (submit → stream → checkpoint
  → result) across all backends.
- Ingress normalizers (MCP/A2A/HTTP/gRPC/ext_authz) only normalize; a policy
  field in ingress is ignored or rejected, never interpreted.
- The SDK composition path (ingress → harness → gateway → receipt) is covered.
- Conformance tests prove non-bypass: plugins cannot create authority, and a
  permit is one-shot end-to-end.
- Agent Skill tests prove the binding propagates action → clearance → permit →
  receipt, mismatches fail before invocation, and skill capabilities never
  override missing, revoked or expired authority.
- A profile compiled for two runtimes has the same profile digest and tool set.
- Live tool handles without explicit resource scope fail validation.
- Raw credential material in a profile fails validation.
- Delegated-session descriptors contain no secret and obey the profile TTL.
- Child profiles are tested for both valid narrowing and blocked expansion.

## Branch discipline

Never work on `main` directly. Create a branch per change, e.g. `hermes/`,
`fix/`, `feat/`, then open a PR. Keep the working tree clean before starting.
