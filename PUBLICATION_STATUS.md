# Publication status

Status date: 2026-08-22

`valo-gateway` is a public reference implementation of vendor-neutral mechanical enforcement for governed actions.

The gateway does not decide whether an action is authorized. It consumes an externally produced, exact-action authorization/decision binding, verifies the required bindings at the enforcement boundary, consumes one-shot execution capability, invokes the configured effector and emits a receipt.

## Public surface

The intended public surface includes:

- mechanical enforcement and one-shot permit consumption;
- replay and binding checks;
- non-bypass/effect-boundary conformance tests;
- protocol ingress normalization and replaceable runtime/tool adapters;
- portable governed-agent profiles;
- reference SDK/CLI surfaces.

## Interoperability rule

No private VALO package is a required Python dependency. REHT/RACS-compatible bindings are supported, but an external implementation may provide equivalent governed bindings through the public contract surface.

## Explicit exclusions

This repository does not contain or own:

- policy or risk evaluation;
- authority inference or resolution;
- private authoritative-state/admission logic;
- customer credentials or deployment configuration;
- unrelated private research, product architecture or commercial implementation internals.

## Publication rule

This is a public repository: a branch push is already disclosure. New substantive material must receive explicit human IP/publication review before the first public push. Merge-time CI is defense in depth, not the primary IP gate.

Repository visibility is not a release by itself. A release requires an immutable version/tag, exact commit, declared license and green conformance tests.
