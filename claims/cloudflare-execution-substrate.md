# Claim: Cloudflare execution substrate

Owner: ChatGPT/Codex worker
Base: c3d73047db86b7a3f1c66540b8392467de45f037
Branch: feat/cloudflare-execution-substrate

Owned files:
- src/valo_gateway/runtime_adapters/cloudflare.py
- src/valo_gateway/runtime_adapters/__init__.py
- tests/test_cloudflare_runtime_adapter.py
- docs/CLOUDFLARE_EXECUTION_SUBSTRATE.md
- claims/cloudflare-execution-substrate.md

Dependencies:
- existing runtime-agnostic execution adapter contract
- existing REHT-issued one-shot ExecutionPermit semantics
- Cloudflare Workers, MCP, Sandboxes, Workflows, AI Gateway and Durable Objects remain mechanical execution/evidence substrates only

Non-goals:
- no Cloudflare component may mint, widen or replace VALO authority
- no credential material is stored in the adapter contract
- no change to REHT/RACS/VAIG ownership boundaries
