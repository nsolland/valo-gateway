# Collaboration and Communication Channel Adapter Adoption

Status: implemented
Source signals: CopilotKit Channels SDK, Inkbox identity and communications substrate
Sources:
- https://www.copilotkit.ai/channels
- https://inkbox.ai/docs/get-started/introduction

## What VALO adopts

Channels are provider-neutral interaction surfaces for an existing governed runtime. Slack, Teams, email, SMS/MMS, voice, iMessage and later channels may carry messages, commands, forms, approval interactions and durable conversation identifiers through one normalized evidence contract.

Persistent provider identity and verified transport integrity may also be preserved as evidence.

VALO adopts the adapter pattern, not a dependency on any specific channel or identity vendor.

## Boundary

A channel event is evidence of an interaction. It is never authority.

- channel identity is evidence only;
- persistent agent identity is evidence only;
- verified webhook or WebSocket transport is evidence only;
- workspace, conversation and thread state are evidence only;
- an approval click or reply is approval evidence only;
- channel credentials do not create VALO authority;
- channel payloads cannot carry a VALO clearance, permit or REHT decision;
- any consequence-bearing action must be separately constructed, evaluated and cleared through the normal VAIG -> REHT path;
- `valo-gateway` remains mechanical enforcement after a valid one-shot permit exists.

## Contract

`src/valo_gateway/protocols/channels.py` provides:

- `ChannelEventEvidence` — frozen, extra-forbid evidence contract;
- `ChannelEvidenceNormalizer` — transport normalization only;
- stable collaboration and communications channel enums;
- optional `agent_identity_id` for provider-scoped persistent identity evidence;
- `transport_verified` for upstream integrity-verification evidence;
- deterministic evidence digest;
- recursive rejection of authority-shaped fields in channel payloads.

The contract intentionally has no method that converts identity, a verified transport, an approval or a message into an execution permit.

## Conformance

`tests/test_channel_adapter.py` proves that:

- a Slack/Teams-style approval remains `authority_effect=none`;
- email, SMS, MMS, voice and iMessage identity-channel events remain `authority_effect=none` even when transport verification succeeded;
- durable thread and agent identity evidence survives normalization;
- evidence digests are deterministic;
- nested or top-level attempts to inject clearance/permit/REHT authority fail closed;
- the channel evidence object exposes no execution or authorization path.

Inkbox-specific adoption and the Hermes placement are recorded in `docs/INKBOX_IDENTITY_CHANNEL_SUBSTRATE.md`.

## Canonical rule

Channels transport identity, intent and approval evidence. REHT authorizes consequence-bearing execution immediately before action. No channel UI, identity provider, bot framework, verified signature or SDK can shorten that path.
