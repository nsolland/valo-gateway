# SR 26-2: Model Governance Is Not Execution Governance

## Regulatory signal

On 17 April 2026, the Federal Reserve issued SR 26-2, replacing SR 11-7 for model risk management. The scope covers traditional statistical models and non-generative/non-agentic AI, while generative AI and agentic AI are explicitly outside the guidance because they are novel and rapidly evolving.

This does not remove governance obligations for those systems. It creates a boundary: model risk management does not by itself govern whether an autonomous or semi-autonomous system is entitled to take a specific action at a specific moment.

## VALO relevance

VALO treats this as an execution-governance boundary.

MRM asks whether a model is validated, monitored, documented, and fit for purpose.

Execution governance additionally asks:

- who currently has authority;
- for what purpose;
- within what scope;
- under what current conditions;
- whether this exact action is authorised now;
- whether required evidence and state are still valid at execution time;
- what actually happened after execution.

A model can be valid while the action is still invalid. Examples include stale authority, expired delegation, wrong purpose, incorrect scope, stale state, missing evidence, or an otherwise correct action performed at the wrong time.

## Architectural consequence

This supports the separation between model governance and execution governance:

Model governance -> model admissibility and model risk controls

VALO governed workspace -> bounded purpose, scope, capability and governed state

VAIG -> runtime evaluation

REHT -> right-before-action authorisation

RACS -> deterministic decision contract

External PEP / executor -> execution

Veritas -> immutable execution evidence

## Canonical statement

> Model governance != execution governance.

For agentic systems, safe deployment requires control over the execution path, not only control over the model.

## Source

Federal Reserve, SR 26-2, "Supervisory Guidance on Model Risk Management", 17 April 2026.
