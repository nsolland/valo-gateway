# Claim: Claude Code self-hosted execution substrate

Owner: ChatGPT/Codex worker
Base: 2e6d1b46b8dfb376a0c8c96cd8aec9e0b3dd40ac
Branch: feat/claude-self-hosted-execution-substrate

Owned files:
- src/valo_gateway/runtime_adapters/claude_self_hosted.py
- src/valo_gateway/runtime_adapters/__init__.py
- tests/test_claude_self_hosted_runtime_adapter.py
- docs/CLAUDE_SELF_HOSTED_EXECUTION_SUBSTRATE.md
- claims/claude-self-hosted-execution-substrate.md

Dependencies:
- existing runtime-agnostic execution adapter contract
- existing REHT-issued one-shot ExecutionPermit semantics
- Anthropic Claude Code self-hosted environment remains an execution/runtime substrate only

Non-goals:
- no Anthropic component may mint, widen or replace VALO authority
- no raw credentials, prompts or transcript payloads are stored in the adapter contract
- no change to REHT/RACS/VAIG ownership boundaries
