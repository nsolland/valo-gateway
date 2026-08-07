# Agent Skills adoption

Status: active implementation
Owner/claim: ChatGPT (this delivery)
Canonical base: `2db0d79edb348a4fbf08f619a290e7e13df93f29`
Branch: `feat/agent-skills-binding`

## Source

External format: Agent Skills (`SKILL.md` packages), including Google's `google/skills` repository.

VALO adopts the external format. VALO does not create a competing skill format.

## Boundary rule

A skill is executable context and capability description, not authority.

- Loading, installing, discovering or selecting a skill never grants authority.
- Skill admissibility and the decision to authorize an action remain upstream of `valo-gateway`.
- REHT remains the sole authorization boundary.
- `valo-gateway` only verifies that the skill binding attached to the action is the same binding cleared upstream and carried by the one-shot execution permit.
- Veritas-compatible execution receipts carry the same binding so the executed skill can be proven after the consequence.

## Binding contract

When an action is skill-backed, the execution context carries:

- `skill_id`
- `skill_version`
- `skill_source`
- `skill_hash`
- `skill_provenance`
- `skill_requested_capabilities`

The canonical digest of that immutable context is `skill_binding_digest`.

Propagation:

`AgentSkillContext -> ActionEnvelope -> Clearance -> ExecutionPermit -> ExecutionReceipt`

The gateway fails closed if the action, clearance and permit skill bindings differ. A missing binding is valid only when all three are unbound.

## Owned files

- `docs/AGENT_SKILLS_ADOPTION.md`
- `src/valo_gateway/contracts/models.py`
- `src/valo_gateway/contracts/__init__.py`
- `src/valo_gateway/gateway/core.py`
- `tests/test_gateway_core.py`
- `AGENTS.md`

## Dependencies

No new runtime dependency. The integration uses existing Pydantic contracts and SHA-256 canonical digests.

Upstream REHT/admissibility implementations must populate and authorize the binding; that policy work is outside this mechanical gateway repository.
