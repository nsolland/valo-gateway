# Inkbox Identity and Channel Substrate

Status: adopted as optional external substrate
Source: https://inkbox.ai/
Docs: https://inkbox.ai/docs/get-started/introduction
Hermes integration: https://inkbox.ai/docs/plugins/hermes-agent
Signing keys: https://inkbox.ai/docs/signing-keys

## Decision

Inkbox is an optional, replaceable identity and communications substrate around a governed agent runtime. It is not an authority, policy, admissibility or execution-governance layer.

VALO adopts the substrate pattern and adapter boundary, not a strategic dependency on Inkbox.

## Adopted capabilities

The adapter may normalize Inkbox-backed:

- persistent agent identity;
- email;
- SMS and MMS;
- voice calls;
- iMessage;
- public tunnel reachability;
- per-identity signed webhook and WebSocket transport evidence;
- Hermes integration as one optional runtime attachment.

Inkbox identity is preserved as `ChannelEventEvidence.agent_identity_id`. A successfully verified upstream transport signature may be preserved as `transport_verified=true`. Neither field changes `authority_effect=none`.

Supported communication kinds in the provider-neutral channel contract are `email`, `sms`, `mms`, `voice` and `imessage` in addition to the existing collaboration channels.

## Authority boundary

Inkbox may establish transport identity, reachability and message integrity. Those facts are evidence only.

It cannot:

- create or extend an authority envelope;
- mint a REHT clearance or execution permit;
- convert a human reply, message, contact rule or verified signature into authorization;
- bypass fresh authority evaluation before a consequence-bearing action;
- make an external effect reversible merely because the communication session is persistent;
- place raw Inkbox API keys, signing secrets or vault material in a compiled governed profile.

Authority-shaped fields remain recursively rejected from normalized channel payloads.

## Canonical placement

```text
Inkbox identity / email / SMS / voice / iMessage / tunnel
  -> provider-neutral ChannelEventEvidence
  -> governed workspace / worker
  -> fresh authoritative state + Authority State
  -> REHT
  -> one-shot permit
  -> valo-gateway mechanical enforcement
  -> external consequence
  -> Veritas receipt/observation
```

Inkbox can prove that a communication arrived through a particular configured identity and transport. REHT still answers whether the proposed consequence is authorized now.

## Hermes

The Inkbox Hermes plugin is treated as an optional communications attachment to Hermes. Hermes remains a worker/runtime substrate. Inkbox remains an identity/channel substrate. Neither owns the VALO execution boundary.

A worker or plugin may receive and construct intent from Inkbox events, but every consequence-bearing tool call still requires the normal REHT-bound one-shot permit before gateway invocation.

## A2A

No Inkbox A2A dependency is assumed by this adoption. The current Inkbox documentation reviewed on 2026-08-16 documents identity, email, phone/SMS/MMS/voice, iMessage, tunnels and harness plugins, but does not expose A2A as a canonical capability in the current documentation surface.

VALO's existing provider-neutral A2A protocol remains independent of Inkbox.

## Canonical rule

Persistent identity is not authority. Verified communication is not authorization. Inkbox transports identity and interaction evidence; VALO governs consequence.
