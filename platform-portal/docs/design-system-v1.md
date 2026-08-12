# Traditional Strength Design System V1

V1 is an opt-in foundation for new work and focused migrations. It does not reset global elements, replace existing brand assets, or require a JavaScript or CSS framework. Load `static/css/design-system.css` after a page's existing styles and import `design_system/components.html` where reusable markup is needed.

```jinja
{% import 'design_system/components.html' as ds %}
{% block page_styles %}
  <link rel="stylesheet" href="{{ url_for('static', filename='css/design-system.css') }}">
{% endblock %}

{{ ds.button('Save changes', type='submit') }}
{{ ds.input_field('email', 'Email', help='Used for account notices.', required=true) }}
```

All public properties and classes use the `ts-` namespace. Tokens may be consumed by a feature stylesheet, but components should normally use the supplied semantic classes or macros. The component showcase is `templates/design_system/showcase.html`; it is intentionally not registered as a production route. Tests render it inside a Flask request context.

## Foundations

### Colour

| Role | Token | Intended use |
| --- | --- | --- |
| Brand black | `--ts-color-brand-black` | Dark brand fields and high-contrast current states |
| Cream | `--ts-color-cream`, `--ts-color-cream-deep` | Page backgrounds and subtle separation |
| Gold | `--ts-color-gold` | Primary action and brand accent |
| Text | `--ts-color-text-primary`, `-secondary`, `-muted` | Reading hierarchy; muted still meets normal-text contrast on its intended surface |
| Border | `--ts-color-border`, `-strong` | Containers and interactive controls |
| Status | `--ts-color-success`, `-warning`, `-danger`, `-info` and `-soft` pairs | Status text/borders and their backgrounds |
| Interaction | `--ts-color-interactive`, `-hover`, `--ts-color-disabled*` | Links, focus-adjacent states and unavailability |

Status components include text, a border, and/or a shape in addition to colour. Do not use a bare colour token as the sole status cue. `.ts-theme-dark` changes semantic surface and text tokens for a dark container; place it on the nearest self-contained dark region rather than on arbitrary children.

### Typography

The sans stack uses Inter only when it is already available, then permitted system fonts. The display stack uses Georgia and system serif fallbacks; no font download is introduced. Responsive display, H1, H2 and H3 tokens use `clamp()`. Use `.ts-type-display` for rare editorial moments, `.ts-type-h1` through `.ts-type-h4` for hierarchy, `.ts-type-body`, `.ts-type-label`, `.ts-type-caption`, and `.ts-type-mono` for their named roles. Preserve semantic heading order independently of visual class.

### Spacing, shape and effects

Spacing follows a 4px base through `--ts-space-0`, `1`, `2`, `3`, `4`, `5`, `6`, `8`, `10`, `12`, `16`, and `20`. Prefer the nearest token over one-off values. Radius tokens are `sm`, `md`, `lg`, and `pill`; borders are `thin` and `thick`. Shadows are deliberately limited to `sm` and `md`.

Interactive primitives share `--ts-focus-ring`, timings and easing. The reduced-motion query collapses animation and transition duration while keeping state changes visible. Never remove focus styling without supplying an equally visible replacement.

### Layout

- `.ts-container` provides the standard content width and responsive gutter; add `.ts-container--wide` for data-heavy views.
- `.ts-section` applies responsive vertical rhythm.
- `.ts-stack`, `.ts-cluster`, and `.ts-grid` cover the common vertical, wrapping horizontal, and responsive grid arrangements. Tight/loose and compact variants are intentionally few.
- Contracts are documented in CSS at 40rem compact, 64rem wide, and 80rem maximum content. V1 currently needs a compact media query only.

### Coach workspace foundation

Coach templates load this stylesheet before `coach_workspace.css` and apply `.ts-theme-coach` to the body. The theme exposes a near-black, cream and restrained-gold semantic palette while the legacy `coach-` selectors consume the same tokens during incremental migration. It deliberately removes decorative gradients and raised dashboard surfaces.

- `.ts-workspace` is the desktop-first 86.25rem shell with a shared responsive gutter.
- `.ts-workspace-grid`, `.ts-workspace-main`, and `.ts-workspace-aside` create a 12-column authoring surface that collapses below 64rem. The aside uses a divider, not a nested card.
- `ds.context_bar()` renders persistent term/value context such as athlete, block, week and status as a semantic description list.
- `.ts-control-row` and `.ts-control-row__actions` keep related controls and verb-led actions together.
- `.ts-section-divider` separates workflow stages without introducing another container.

Coach surfaces should prefer these flat structures, native tables and inline editing. Use `.ts-card` only when the content is genuinely a self-contained object; do not use it as a default page-section wrapper.

## Components

### Actions

`ds.button()` supports `primary`, `secondary`, `tertiary`, and `danger`, native disabled buttons, link actions with `aria-disabled`, and `aria-busy` loading state. A loading native button is disabled to prevent repeat submission. Use primary once per decision area. Secondary is for alternatives, tertiary for low emphasis, and danger only for destructive actions. `ds.icon_button()` requires a human-readable label; its icon is hidden from assistive technology.

Do not use an anchor for an action that changes state. Do not visually disable an element without the native `disabled` attribute or the macro's link treatment. Loading labels should describe the ongoing action, for example “Saving”.

### Forms

`input_field`, `textarea_field`, and `select_field` connect labels, help, errors, required state, `aria-errormessage` and `aria-describedby`. `input_field` accepts a separate `id` when several controls submit under the same name. Error text precedes optional help so the corrective action is read first. `choice` uses native checkbox and radio inputs and browser focus/keyboard behaviour. Options passed to `select_field` are `(value, label)` pairs.

```jinja
{{ ds.input_field(
  'email', 'Email', value=form.email,
  help='Used for account notices.', error=errors.get('email'),
  required=true, autocomplete='email'
) }}
```

Do not put placeholder text in place of a label. Do not create a `div` checkbox, custom select, or click-only radio. On server validation, pass the error back to the macro so `aria-invalid` and the error ID remain associated.

For forms with more than one error, render `form_errors` before the fields. Pass `(field_id, message)` pairs so each summary link moves focus to the relevant control. Move focus to the summary after a client-side validation response; server-rendered pages should place it at the start of the form. Use direct corrections such as “Enter an email address”, not “Invalid input” or a second explanatory paragraph.

### Content and feedback

- `card` is a shadowed grouping and `panel` is a quieter bordered section. Both are call blocks.
- `metric_card` pairs a metric with a mandatory label and optional context.
- `badge` communicates `success`, `warning`, `danger`, or `info` with text, a dot and a border.
- `alert` uses `role="alert"` for danger or explicitly live feedback, otherwise polite `role="status"`. Its message is optional when the title already communicates the outcome.
- `empty_state` names the empty collection and may include one useful explanation and one recovery action. Its message is optional; select `heading_level` to preserve the page outline.
- `table_wrapper` gives wide tables a named, keyboard-scrollable region. Tables still need a caption or region label and scoped header cells.
- `pagination` exposes current and unavailable states. Keep page counts modest; a future ranged variant should be introduced before using hundreds of links.
- `tabs` is for navigation and renders links. For in-page JavaScript tab panels, implement the full ARIA tabs keyboard pattern rather than relabelling this navigation macro.
- `skeleton` exposes one busy status while hiding decorative lines. Prefer meaningful loading labels.

### Dialog

`dialog` styles the native HTML `<dialog>` element and includes a labelled close control. It is supplied because modern browsers provide an accessible modal primitive. The owning feature remains responsible for calling `showModal()`, returning focus to the opener, providing a non-JavaScript route for critical actions, and testing keyboard dismissal. Do not reproduce a modal with a generic positioned `div`.

### Headers

`page_header` provides one H1, eyebrow, description and optional action slot. `section_header` accepts `heading_level` for correct document hierarchy. Avoid selecting these components to style all page headings globally.

## Migration guidance

Adopt one bounded component at a time:

1. Load `design-system.css` after the feature stylesheet.
2. Import the macros under the `ds` namespace.
3. Replace one repeated markup pattern and verify normal, focus, disabled, error, loading, compact and dark-context states.
4. Remove the old feature rule only after all consumers have moved.
5. Run focused tests and the full portal suite. Run Playwright whenever a live template changes.

Candidate mappings for later owner-led migrations:

| Existing selector pattern | V1 destination | Notes |
| --- | --- | --- |
| `.coach-primary-button`, `.primary-action` | `.ts-button--primary` / `ds.button` | Check local sizing and submit type |
| `.coach-button`, `.secondary-action` | `.ts-button--secondary` | Preserve link versus button semantics |
| `.coach-panel`, `.programme-panel`, legacy `.card` | `.ts-panel` or `.ts-card` | Choose panel for structural regions, card for discrete items |
| `.programme-alert`, `.flash`, `.note` | `ds.alert` | Select role based on urgency, not colour |
| `.programme-help`, `.field-error` | field help/error macro output | Migrate label and control as one unit |
| `.coach-empty-state` | `ds.empty_state` | Retain task-specific explanation/action |
| `.table-wrap` | `ds.table_wrapper` | Supply a specific accessible label |
| local `.badge`, `.PASS`, `.WARN`, `.FAIL` | `ds.badge` | Use readable status text; do not pass machine codes unchanged |

These are migration targets, not permission to mass-replace classes. Public pages, authentication, the coach header, Meet Day, Block Factory and athlete features remain owner-controlled.

## Anti-patterns

- Do not load V1 and then override most tokens for a single page; introduce a documented semantic variant when a product need repeats.
- Do not use token names as HTML utility classes or add one class per CSS property.
- Do not nest component selectors under page IDs. The namespace is sufficient and keeps specificity flat.
- Do not place clickable elements inside a clickable card.
- Do not communicate required, selected, success or error state through colour alone.
- Do not disable zoom, hide focus, or animate essential information.
- Do not copy macro markup into feature templates. Extend the macro API when a repeated, broadly useful need is demonstrated.

## Maintenance

Changes should remain backward-compatible where practical. Add a component only when it represents a repeated interface pattern, document its semantics and failure modes, include states in the showcase, and add focused rendering/accessibility coverage. Token changes require checking cream and `.ts-theme-dark` contexts. V1 has no global reset by design, which limits collision risk while active feature branches converge.
