---
description: Inspect model schemas (fields, relations, enums, creation order) for seed data authoring
model: sonnet
---

# Discover Models

Query the Tortoise ORM model registry for seed-relevant schema info. Filters out auto-managed fields (generated PKs, raw FK `_id` columns), reverse relations, and table metadata — only shows fields you'd actually set in seed code.

Always prefix commands with `LOG_LEVEL=info` to suppress debug output.

## Usage

### List all models

```bash
LOG_LEVEL=info make script ARGS="scripts/seeds/.claude/skills/discover-models/scripts/discover_models.py"
```

Prints all non-abstract models grouped by module, sorted alphabetically.

### Show fields, relations, and creation order for specific models

```bash
LOG_LEVEL=info make script ARGS="scripts/seeds/.claude/skills/discover-models/scripts/discover_models.py Goal Task Meeting"
```

Accepts one or more model names (exact match first, then substring). For each model, prints:

- **Required** — fields (with python type) and FK/O2O relations (with target model) that must be set
- **Optional** — fields (with type and default if non-callable) and nullable relations

Enum fields show their allowed values inline (e.g. `status (enum: draft, active, closed)`). One-to-one relations are annotated.

When multiple models are given, a **creation order** section appears at the top showing topologically sorted models with their required dependencies.
