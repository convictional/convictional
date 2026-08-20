## Linter Wishlist

These are things we wish we could lint, but don't have a linter for.

1. **JSONField Usage**: Always use `JSONField` from `infra/db`.
2. **Imports**: Do not use relative imports; always use absolute imports.
3. **Reserved Field Names**: The field name `source` is banned.
4. **Never use `user_id`**: It obscures the user's relationship, use `creator_id`, `decider_id`, etc.
5. **Always add the foreign key type annotation**: Add e.g. `decision_process_id: Annotated[UUID, "foreign key to decision"]` for foreign keys.
6. **Avoid runtime checks**: We like mypy, avoid solutions that require `hasattr`, we regard it as a code smell.
7. **Consistent ordering of class members**: When adding something to a class, keep members in the following order:
  - Class-level dunder methods (e.g., __init__, __str__)
  - @classmethods
  - @staticmethods
  - @property methods
  - Instance methods
  - Private or protected methods (methods starting with _ or __)
8. **Signals should not modify other rows**: When using Tortoise signals, they should only modify the instance or create new rows.
