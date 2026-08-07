# Collaboration Channel Adapter Adoption

Status: implemented
Source signal: CopilotKit Channels SDK
Source: https://www.copilotkit.ai/channels

## What VALO adopts

Collaboration channels are useful as provider-neutral interaction surfaces for an existing agent runtime. Slack, Teams and later channels may carry messages, commands, forms, approval interactions and durable thread identifiers through one normalized evidence contract.

VALO adopts the adapter pattern, not a dependency on a specific Channels SDK.

## Boundary

A channel event is evidence of an interaction. It is never authority.

- channel identity is evidence only;
- workspace, conversation and thread state are evidence only;
- an approval click is approval evidence only;
- channel credentials do not create VALO authority;
- channel payloads cannot carry a VALO clearance, permit or REHT decision;
- any consequence-bearing action must be separately constructed, evaluated and cleared through the normal VAIG -> REHT path;
- `valo-gateway` remains mechanical enforcement after a valid one-shot permit exists.

## Contract

`src/valo_gateway/protocols/channels.py` provides:

- `ChannelEventEvidence` — frozen, extra-forbid evidence contract;
- `ChannelEvidenceNormalizer` — transport normalization only;
- stable channel and interaction enums;
- deterministic evidence digest;
- recursive rejection of authority-shaped fields in channel payloads.

The contract intentionally has no method that converts an approval into an execution permit.

## Conformance

`tests/test_channel_adapter.py` proves that:

- a Slack/Teams-style approval remains `authority_effect=none`;
- durable thread identity survives normalization;
- evidence digests are deterministic;
- nested or top-level attempts to inject clearance/permit/REHT authority fail closed;
- the channel evidence object exposes no execution or authorization path.

## Canonical rule

Channels transport intent and approval evidence. REHT authorizes consequence-bearing execution immediately before action. No channel UI, bot framework or SDK can shorten that path.
