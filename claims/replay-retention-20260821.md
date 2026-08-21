# Claim — replay retention conformance 2026-08-21

- Owner: ChatGPT execution worker
- Repository: `nsolland/valo-gateway`
- Canonical base SHA: `cfaf16bd96296bcbbd57cd8ad925cde3b5728f7e`
- Branch: `test/replay-retention-20260821`
- Active delivery: lock the already-implemented replay-retention property with executable tests.
- Owned files:
  - `claims/replay-retention-20260821.md`
  - `tests/test_message_security.py`
- External trigger: Microsoft Agent Governance Toolkit commit `b5705588883fac48b88cbe6fd0bd7d48c798453e`.
- Existing implementation: `InMemoryReplayStore.claim_once()` stores claims through `expires_at`; `GovernedMessageVerifier.accept()` rejects expiry before replay claim.
- Invariant: replay/consumption state MUST NOT disappear while the corresponding signed artifact remains acceptable.
- Non-goals: no new replay store, no AGT dependency, no authority logic, no runtime policy change.
