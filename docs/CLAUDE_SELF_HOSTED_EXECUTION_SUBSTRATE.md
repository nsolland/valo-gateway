# Claude Code self-hosted execution substrate adoption

Status: adopted
Verified against Anthropic public beta announcement: 2026-08-07

## Decision

Claude Code self-hosted environments are adopted as a first-class execution substrate for VALO. They are not an authorization, policy or evidence authority.

Canonical separation:

```text
Claude/model proposal
-> VAIG evidence and model admissibility
-> REHT clearance + fresh one-shot execution permit
-> RACS decision contract
-> valo-gateway mechanical enforcement
-> Claude Code self-hosted runner / tool / git / internal service
-> Veritas execution observation / receipt
```

Anthropic's self-hosted environment moves agent execution onto infrastructure controlled by the customer. Repository checkouts, build artifacts, secrets and files created or modified by the session remain on that infrastructure. Prompts, responses and tool results are still sent to Anthropic for inference and the session transcript is stored by Anthropic so the session can continue across supported surfaces.

## Adopted surfaces

### Runners

Fixed and on-demand runners are mechanical execution capacity. Runner placement, lifecycle and scaling do not create authority.

### Session identity and checkout

Environment, session, runner and checkout references may be bound into VALO's deterministic execution-context digest. They are execution context only and cannot substitute for a current REHT clearance.

### Internal services and tools

A self-hosted Claude Code session may reach internal services, databases, registries, compilers, SDKs, CLIs and MCP servers available inside the customer's network. Access or transport authentication does not imply permission for the consequential action.

### Git and CI actions

Repository mutation, push, pull-request creation, CI remediation and other development actions remain governed external consequences when they cross the configured VALO authorization boundary.

## Adapter contract

`ClaudeSelfHostedRuntime` normalizes proposed runner actions into the same `valo-gateway` route used by other runtimes.

`ClaudeSelfHostedExecutionContext` binds non-authoritative runtime context into a deterministic execution hash:

- environment reference
- session reference
- runner reference
- runner mode (`fixed` or `on_demand`)
- isolated checkout reference
- credential-context fingerprint

The adapter never carries raw credentials, prompts, transcript payloads, a VALO permit, clearance, decision or policy digest as runtime context.

## Invariants

1. Claude Code may propose and execute; it cannot mint or widen VALO authority.
2. Self-hosting execution does not make inference or session transcripts fully local.
3. Network reachability, repository access, MCP discovery or possession of credentials is not authorization.
4. A runner restart, new checkout or resumed session does not revive an expired or consumed one-shot permit.
5. Every new consequential external action requires current REHT clearance and a fresh permit.
6. Credentials remain outside the governed profile; only an opaque SHA-256 credential-context fingerprint may be bound into execution context.
7. `valo-gateway` remains the mechanical point that consumes the REHT-issued permit immediately before external dispatch.
8. Veritas remains responsible for evidence of what actually occurred after dispatch.

## Reference implementation

`src/valo_gateway/runtime_adapters/claude_self_hosted.py` is the reference adapter. It intentionally contains no policy engine, clearance logic or authorization state.

## Upstream references

- Anthropic announcement: https://claude.com/blog/run-claude-code-sessions-on-your-own-compute
- Claude Code self-hosted environments documentation: https://code.claude.com/docs/en/self-hosted-environments
