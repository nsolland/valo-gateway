# Claim: ADK/MCP/A2A execution adapter

Owner: ChatGPT/Codex worker
Base: 2db0d79edb348a4fbf08f619a290e7e13df93f29
Branch: feat/adk-mcp-a2a-execution-adapter

Owned files:
- src/valo_gateway/runtime_adapters/execution.py
- src/valo_gateway/runtime_adapters/__init__.py
- tests/test_execution_adapter.py
- docs/ADK_MCP_A2A_ADOPTION.md

Dependencies:
- existing RuntimeAdapter/BaseRuntimeAdapter contract
- existing REHT-issued one-shot ExecutionPermit semantics
- external ADK/MCP/A2A runtimes remain mechanical execution targets only
