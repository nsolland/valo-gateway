# Claim — AI security hardening Stage 3

Owner: nsolland
Base SHA: `f8102dfdec7ac37b146024b72bf22189898a23ab`
Branch: `feat/ai-security-hardening-stage3`

Scope: transport-neutral governed inter-agent message envelope with cryptographic integrity, explicit sender/recipient, purpose/scope, freshness and anti-replay.

Owned files: `src/valo_gateway/message_security.py`, `src/valo_gateway/__init__.py`, `tests/test_message_security.py`, `conformance/test_message_security_non_bypass.py`.

Invariants: a message is data/context, never authority; authority references remain references only; verification is mechanical; transport protocols cannot upgrade message standing; replay, expiry, wrong recipient, tampering and signature mismatch fail closed before message acceptance.
