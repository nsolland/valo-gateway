# NVIDIA NOOA adoption

Owner: nsolland
Canonical base: 440cc20141d3b672ae09b57577f5290ae4e0a590
Branch: feat/nooa-governed-harness

NOOA is adopted as an optional worker/harness substrate, not as an authority or execution-governance layer.

Invariants:

- NOOA methods are projected into typed VALO capability/action contracts before execution.
- Live-object semantics cross the boundary only as opaque references; references are resolved against fresh governed state at execution time.
- Consequence-bearing methods have no direct effect path. They must traverse VALO Gateway and the configured REHT/RACS/PEP chain.
- Agent-controlled memory or state changes that can affect later consequence-bearing decisions are treated as governed state mutation.
- The adapter does not import or require the `nooa` package. NVIDIA remains a replaceable harness provider.
- NOOA sandboxing is defense in depth; it does not replace VALO authorization or effect-path enforcement.

Source reference: https://github.com/NVIDIA-NeMo/labs-OO-Agents
