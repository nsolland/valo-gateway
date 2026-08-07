# ADK / MCP / A2A adoption

Status: adopted

## Decision

VALO does not create an ADK-specific governance component.

Google ADK, MCP and A2A are execution substrates and transport protocols behind the same vendor-neutral gateway contract. They may discover agents and tools, provide sandboxes, carry runtime metadata and resume work, but they do not create authority and they do not replace REHT.

Canonical path:

```text
agent / tool proposal
-> VAIG evidence
-> REHT clearance + one-shot execution permit
-> RACS decision contract
-> valo-gateway mechanical enforcement
-> ADK / MCP / A2A execution
-> Veritas execution receipt / observation
```

## External signal adopted

Google ADK Python v2.5.0, released 2026-07-16, added:

- Agent Registry migration and search for agents and MCP servers.
- `to_mcp_server`, allowing an ADK agent to be served over MCP.
- remote MCP support for ManagedAgent with runtime header callbacks.
- Cloud Run sandbox support for code executors.
- strict input schema validation for LlmAgent workflow nodes.

ADK Python v2.6.0, released 2026-07-29, further added per-invocation A2A auth headers, agent identity/OAuth work, mTLS handling in Agent Registry and workflow resumability checkpoints. v2.6.2, released 2026-08-03, is the latest release at adoption time.

These changes strengthen the case for a single runtime-agnostic execution boundary rather than vendor-specific governance.

## VALO contract

`RuntimeAgnosticExecutionAdapter` covers ADK, MCP and A2A through the same mechanical invocation contract.

It carries only non-authoritative execution metadata:

- `execution_context_hash`
- optional `substrate_grant_ref`
- optional `resume_checkpoint_ref`
- non-secret transport headers such as correlation or trace identifiers

It explicitly rejects credential-bearing headers and VALO authority/clearance/permit headers. Credentials must be injected by the execution substrate or secret manager outside the compiled governance profile. An opaque grant reference is context, not authority.

## Invariants

1. Registry discovery is capability discovery, not authorization.
2. Tool schemas and workflow validation are precondition checks, not authorization.
3. Sandboxing defines where code can run, not whether a consequential action is allowed.
4. Runtime headers may carry correlation/context only; they cannot mint or upgrade authority.
5. Agent-as-tool and tool-as-agent representations do not change the execution boundary.
6. Resumption from a checkpoint does not revive an old permit. Any new external consequence requires a currently valid REHT clearance and a fresh one-shot execution permit.
7. The adapter implements the existing `ExecutableTool.invoke` shape so `ValoGateway.execute` remains the only path that consumes the permit immediately before external dispatch.
8. Veritas remains responsible for proving what actually happened after execution.

## Mapping

| ADK / protocol capability | VALO treatment |
| --- | --- |
| Agent Registry | discovery / registry input |
| MCP server discovery | discovery / registry input |
| `to_mcp_server` | same governed execution target as any MCP tool |
| ManagedAgent remote MCP | runtime target behind gateway |
| runtime header callback | transport metadata only; no authority |
| Cloud Run sandbox | harness/runtime isolation |
| strict workflow schema | input validity / admissibility precondition |
| A2A per-invocation auth | substrate credential handling; REHT authority remains separate |
| workflow checkpoint/resume | lifecycle metadata; re-clear external consequences |

## Non-goals

- no ADK-owned authorization state
- no MCP-owned authorization state
- no A2A-owned authorization state
- no permit encoded into transport headers
- no credentials stored in VALO profiles or adapter transport context
- no duplicate policy engine inside the adapter

The result is one execution-governance boundary across ADK, MCP, A2A and future runtimes.
