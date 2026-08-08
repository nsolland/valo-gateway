# Claim — Entra Agent ID authority context adapter

Repo: `nsolland/valo-gateway`

Canonical base-SHA: `a4ebad202003e16a4107cf5bc818d3c795c082c2`

Branch: `feat/entra-agent-id-authority-context`

Owner: ChatGPT execution worker

Owned files:
- `src/valo_gateway/identity_adapters/__init__.py`
- `src/valo_gateway/identity_adapters/entra_agent_id.py`
- `tests/test_entra_agent_id_adapter.py`
- `docs/ENTRA_AGENT_ID_ADOPTION.md`
- `claims/entra-agent-id-authority-context.md`

Dependencies:
- REHT remains the only execution authorization boundary.
- Entra Agent ID is upstream identity/access/context evidence only.
- valo-gateway performs no policy evaluation and creates no authority.
