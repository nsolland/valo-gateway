# Claim — AI security hardening Stage 2

Owner: nsolland
Base SHA: `c149b3f5046294e5777aa36389c4d0b6f3cf83c4`
Branch: `feat/ai-security-hardening-stage2`

Scope: deterministic resource and budget enforcement at the mechanical execution boundary.

Owned files: `src/valo_gateway/resource_budget.py`, `src/valo_gateway/gateway/core.py`, `src/valo_gateway/__init__.py`, `tests/test_resource_budget.py`, `conformance/test_resource_non_bypass.py`.

Implementation: resource requirements are carried inside the exact `ActionEnvelope.parameters` under the reserved `_valo_resource_budget_ids` key, so removing or changing a requirement changes the action digest and invalidates the existing clearance/permit. `ResourceBudgetLedger` performs atomic reservation and consumption before permit consumption and before tool invocation. Cumulative and maximum-per-action limits support tool calls, token/cost windows, child fan-out, recursion depth and transaction-value dimensions without putting policy inference into Gateway.

Invariants: resource controls never create authority; limits are supplied as explicit data; missing or mismatched reservations block before tool invocation; reservation consumption is atomic for one permit; consumed reservations remain consumed after an attempted external call; actions without resource requirements stay backward compatible.
