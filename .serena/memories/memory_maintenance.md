# Memory Maintenance

Guidelines for maintaining the Serena memory graph.

## Discovery Model
- Progressive discovery via references: `mem:core` is the root entry point.
- References must use `mem:<path>` syntax in backticks (e.g., `mem:database`, `mem:cogs`).
- Surrounding text must indicate when and why to read the referenced memory.

## Style & Invariants
- Dense, invariant-focused agent notes.
- Focus on stable schemas, design decisions, and core boundaries.
- Update memories whenever schemas, cog additions, or integration contracts change.