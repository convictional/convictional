# Templates (HTMX + Alpine.js)

These templates are the existing HTMX/Alpine stack. The app is migrating to React islands (see `docs/react-migration.md`), and both stacks coexist during the transition — new interactive components generally belong in `app/javascript/react/`, but the rules below govern everything still rendered here.

HTMX does not touch React island DOM: no `hx-target` or `hx-select` pointing inside an island.

## Critical Rules

1. **Never create partial-specific templates** - Routers always render full page templates. The layout is automatically selected based on `HX-Request` header (see `app/routers/dependencies.py`, `is_xhr`). Use `hx-select` to extract what you need from the response.

2. **Always use `tojson` for Alpine data** - The filter is HTML-safe (escapes `<>&"`):

   ```html
   <div x-data="{ items: {{ items|tojson }}, flag: {{ flag|tojson }} }"></div>
   ```

3. **Escape single quotes manually** - For JS string literals inside Alpine directives:

   ```html
   {% set escaped = value|replace("'", "\\'") %}
   <div x-data="component('{{ escaped }}')"></div>
   ```

4. **hx-target vs hx-select** - `hx-target` is WHERE to put content, `hx-select` is WHAT to extract from response. Often both point to the same ID:

   ```html
   <form hx-post="{{ url }}" hx-select="#my-element" hx-target="#my-element" hx-swap="outerHTML"></form>
   ```

5. **Don't check is_xhr to return different templates** - Layout selection is automatic. Just call `helpers.render("template.html.jinja", ...)`.

6. **Use morph for smooth updates** - `hx-swap="morph"` preserves Alpine state, focus, and scroll position.

## Common Mistakes

- Creating `_partial.html.jinja` files instead of using `hx-select`
- Forgetting `tojson` and getting broken HTML/JS from quotes
- Using `outerHTML` swap when element IDs differ between page and response
- Not understanding flash messages use `hx-swap-oob` automatically via `layouts/content.html.jinja`
