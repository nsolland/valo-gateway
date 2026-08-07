# Google ADK Go v2.1.0 adoption

Status: active implementation
Upstream: `google/adk-go` tag `v2.1.0`, released 2026-07-23, tag commit `f4c7670`
VALO issue: #3
Canonical base: `217ee7cf92efebfa0880eaad5e348e8897cde43c`

## Canonical boundary

ADK Go is a runtime/harness and integration surface. It does not become an authority source.

```text
ADK agent / workflow
  -> ADK discovery + model/tool declaration + credential resolution
  -> VALO proposal normalization
  -> VAIG evidence (optional smart evaluation)
  -> REHT clearance + one-shot execution permit
  -> RACS decision contract
  -> valo-gateway mechanical enforcement
  -> ADK TaskRunner / MCP / remote agent / tool execution
  -> ExecutionReceipt -> Veritas
```

The invariant is explicit:

```text
credential != authority
authenticated != authorized
tool confirmation != REHT clearance
TaskRunner scheduling != execution authorization
registry discovery != admissibility
analytics/logging != execution evidence
```

## v2.1.0 change-by-change disposition

### Adopt as first-class integration seams

1. TaskRunner seam for caller-controlled tool fan-out (#1050)
   - Treat TaskRunner as the mechanical execution seam after REHT authorization.
   - Preserve concurrency, deadline, cancellation and sequential-execution metadata in the normalized execution context.
   - Every consequence-bearing tool item requires its own exact action binding and one-shot permit unless REHT explicitly clears a compound action.
   - Parallel fan-out must not share/replay one permit across children.

2. Name-based model registry `Register/NewLLM` (#1057)
   - Consume model identity as runtime metadata only.
   - Model selection does not grant tool/action authority.
   - Bind resolved model identity/version into execution context and receipts when supplied.

3. Public `PackTool` declaration packer (#1055)
   - Consume packed declarations for discovery/tool exposure.
   - Tool declaration is non-authoritative and must map to canonical VALO action types and explicit resource scope before live use.

4. Stable tool-confirmation ordering (#1053)
   - Preserve deterministic confirmation ordering as evidence/context.
   - Confirmation is evidence for REHT, never a substitute for REHT re-clearance.

5. Confirmation wrapper `ProcessRequest` propagation and packing interception (#1130)
   - Ensure wrapped tools cannot bypass the same action normalization and REHT gate.
   - Repacking/confirmation wrappers may transform transport metadata only; they cannot upgrade authority.

6. Agent Registry REST foundation (#1122)
   - Consume registry records as discovery metadata.
   - Registry availability is not admissibility or authorization.

7. Agent Registry discovery for agents, MCP servers and endpoints (#1124)
   - Normalize discovered agent/MCP/model endpoint metadata into non-authoritative discovery descriptors.
   - Require explicit mapping from discovered tool/resource identifiers to canonical action/resource scope before execution.

8. `RemoteAgent` and `McpToolset` factory helpers (#1127)
   - Treat factory output as runtime/tool exposure only.
   - Remote-agent and MCP calls traverse the same REHT/gateway boundary as local tools.

9. Core credential/provider package (#1143)
   - Resolve credentials per invocation/user and pass only opaque credential references through VALO context.
   - Never persist raw credential material in governed profiles or receipts.
   - Credential resolution authenticates a principal/provider relationship; it does not create authority.

10. MCP per-request auth via `Config.Auth` (#1148)
    - Preserve per-request identity/credential provenance to the execution boundary.
    - Bind principal, actor, credential reference, authority-envelope reference and exact action digest independently.
    - REHT remains the authority source.

11. OpenAI support (#1178)
    - Treat ADK Go as multi-model runtime infrastructure.
    - Keep governance model-provider-neutral; Gemini/OpenAI/model registry selection cannot change authority semantics.

### Adopt as evidence and runtime-safety inputs

12. Parallel worker `invoke_node` spans (#1134)
    - Correlate span/run/node identifiers with proposal, clearance, permit and receipt identifiers where available.
    - Tracing is observability, not authoritative proof.

13. Await parallel sub-agent teardown on early stop (#1186)
    - Carry cancellation/teardown state into execution outcome metadata.
    - A cancelled or stopped child must not retain a reusable permit.
    - Any already-consumed permit remains consumed even if downstream execution fails or is cancelled.

14. BigQuery Agent Analytics Plugin (#738)
    - Treat analytics as non-authoritative telemetry.
    - Do not let analytics success imply execution success.
    - Veritas-compatible execution receipts remain the evidence source for what actually executed.

15. Temporary state-delta mutation fix (#1128)
    - Preserve immutable input/context semantics when normalizing ADK events.
    - Runtime state mutation must never mutate signed/bound action inputs after REHT clearance.

16. A2A cleanup/teardown test fixes (#1131, #1145)
    - Retain A2A as a protocol normalization path only.
    - Cleanup behavior must not create or restore authority.

### Compatibility / developer-surface changes to track

17. Runner node-runtime behavior coverage (#1103)
    - Add adapter contract coverage for submit/stream/checkpoint/result and cancellation behavior.

18. `runner.NewInMemory` convenience constructor (#1133)
    - Useful for conformance/reference demos only; in-memory runtime does not weaken authorization requirements.

19. AgentEngine deployment changes (#1162)
    - Track deployment metadata as runtime context; deployment platform is not an authority source.

20. Multi-module Go development/CI support (#1155)
    - Required when a native Go adapter package is split into a dedicated module/repository.

21. Workflow example/docs index (#1113), v1/v2 branch docs (#1114), CI branch coverage (#1117), repository-layout docs (#1118), test-context cleanup (#1132), dependency bumps (#1021, #1144)
    - No runtime authority semantics change.
    - Pin/test against `v2.1.x` compatibility in the native Go adapter when created.

## Integration contract

The Python gateway carries the vendor-neutral contract. A native Go package can implement the same contract without moving the boundary.

ADK runtime context may supply these non-authoritative fields when available:

- `runtime = "google-adk-go"`
- `runtime_version`
- `agent_name` / `agent_ref`
- `registry_ref`
- `model_ref`
- `tool_name` / `tool_ref`
- `mcp_server_ref`
- `remote_agent_ref`
- `principal_ref`
- `actor_ref`
- `credential_ref` (opaque only)
- `task_run_id`
- `node_id`
- `span_id`
- `deadline_ns`
- `cancellation_state`
- `confirmation_ref`

The following are VALO execution-binding fields and must never be supplied or minted by ADK runtime metadata:

- `action_digest`
- `authority_envelope_id`
- `clearance_id`
- `permit_id`

They are produced or bound by the VALO action/authority/REHT path and are validated again at the gateway execution boundary.

Unknown ADK metadata may be retained as non-authoritative metadata, but it cannot be promoted into authority fields by an adapter.

## Fan-out rule

For a TaskRunner fan-out of `N` consequence-bearing actions:

```text
proposal_i -> REHT_i -> permit_i -> execute_i -> receipt_i
```

for every `i`.

One permit cannot authorize multiple independently consequence-bearing child actions. A compound permit is allowed only when the compound action itself is the exact REHT-authorized action and the gateway can prove its full child set is frozen into the action digest.

## Confirmation rule

ADK tool confirmation may be used as human/interactive evidence, but:

1. confirmation freezes the exact action proposal;
2. confirmation evidence is presented to REHT;
3. REHT re-evaluates current authority/state;
4. a fresh one-shot permit is issued only on `ALLOW` or materialized `MODIFY`;
5. gateway consumes that permit immediately before the external call.

## Credential rule

ADK CredentialProvider and MCP `Config.Auth` supply authentication material/provenance. VALO stores only an opaque reference in governed configuration and evidence. Raw tokens, API keys or passwords must never enter a governed profile, action digest or receipt.

Credential rotation between decision and execution requires re-binding/re-clearance when identity/provenance is part of the authorized action context.

## Registry/discovery rule

Discovery answers what exists. Admissibility answers what may be considered. Authorization answers whether this exact action may execute now.

```text
ADK Registry discovery -> VALO metadata/admissibility mapping -> REHT exact authorization -> gateway enforcement
```

Registry or factory helpers cannot mint authority, expand resource scope or bypass explicit live scope.

## Evidence rule

ADK spans, analytics and runtime events are supplementary observations. They may be correlated with VALO identifiers but cannot replace:

- authoritative REHT decision/clearance evidence; and
- gateway/Veritas-compatible execution receipts proving the external call outcome.

A workflow being green, a span completing, or analytics being emitted must never be interpreted as proof that the intended consequence occurred.

## Native adapter target

A future `valo-adk-go` native package should be intentionally thin:

- TaskRunner wrapper/interceptor
- proposal/action normalizer
- opaque CredentialProvider bridge
- Agent Registry metadata mapper
- MCP auth/context mapper
- confirmation-evidence mapper
- receipt correlation hook
- conformance tests against the vendor-neutral gateway contract

It must not contain policy judgment, VAIG logic, REHT authorization logic or an alternate decision engine.

## Acceptance criteria

- ADK Go is represented explicitly as a runtime adapter target.
- ADK metadata normalization is deterministic and rejects authority-like fields supplied by runtime metadata.
- credentials remain opaque references.
- TaskRunner fan-out produces independent action bindings/permit requirements.
- tool confirmation cannot execute without fresh REHT clearance + permit.
- MCP/RemoteAgent paths cannot bypass the gateway.
- runtime/model/registry identity cannot mint or upgrade authority.
- cancellation/failure does not restore consumed permits.
- analytics/tracing are explicitly non-authoritative.
- tests and conformance prove these boundaries.
