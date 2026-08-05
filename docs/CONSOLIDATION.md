# Consolidation status

This bootstrap is the canonical target for the four runtime/tool repositories and the mechanical gateway code currently inside `valo-platform`.

After the repository is renamed to `valo-gateway`:

1. run conformance CI
2. make `valo-platform` consume `valo-gateway`
3. remove duplicated gateway implementation from `valo-platform`
4. replace the four old repositories with archived migration pointers
5. migrate `valo-mcp` protocol code into `protocols/mcp` after contract review

The old repositories must not be archived until active consumers have moved and the non-bypass suite is green.
