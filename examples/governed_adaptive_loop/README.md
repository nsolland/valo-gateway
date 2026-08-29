# Governed Adaptive Loop MVP

A minimal end-to-end demonstration of one separation:

```text
learned guidance -> proposal
                  != authority

proposal
-> fresh authorization
-> exact one-shot permit
-> gateway consequence boundary
-> effect receipt
-> observation
-> guidance renewal
```

The example intentionally keeps learned guidance non-authoritative. It may shape
an exact proposal, but only a current upstream authority decision can create the
clearance consumed by `ValoGateway`.

The second flow issues a valid permit and then revokes authority before effect.
The same proposed action is blocked at execution time and the consequence
ledger remains unchanged.

## Run

```bash
python -m examples.governed_adaptive_loop.app
```

Expected shape:

```json
{
  "allowed_flow": {
    "decision": "ALLOW",
    "effect_count": 1,
    "renewed_from_effect_evidence": true
  },
  "revoked_flow": {
    "blocked": true,
    "effect_count": 0
  }
}
```

## What this MVP proves

It demonstrates composition of existing public contracts:

- learned/persistent guidance can influence a proposal without granting authority;
- authorization binds the exact action digest;
- the one-shot permit is revalidated at the execution boundary;
- authority revocation before effect causes null effect;
- successful execution emits a receipt and Veritas observation;
- observed effect evidence can renew the learned guidance state.

It does **not** claim to implement a general learning system or to infer authority
from history, model output, confidence, or prior success.
