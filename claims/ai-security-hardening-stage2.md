# Claim — AI security hardening Stage 2

Owner: nsolland
Base SHA: `c149b3f5046294e5777aa36389c4d0b6f3cf83c4`
Branch: `feat/ai-security-hardening-stage2`

Scope: deterministic resource and budget enforcement at the mechanical execution boundary.

Owned files: `src/valo_gateway/resource_budget.py`, `src/valo_gateway/contracts/models.py`, `src/valo_gateway/gateway/core.py`, `src/valo_gateway/__init__.py`, `tests/test_resource_budget.py`, `conformance/test_resource_non_bypass.py`.

Invariants: resource controls never create authority; limits are supplied as explicit data; missing or mismatched reservations block before tool invocation; reservation consumption is atomic for one permit; consumed reservations remain consumed after an attempted external call; actions without resource requirements stay backward compatible.
