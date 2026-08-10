# Agent D report — V7.6 Block Factory

Implemented the coaching refinement without a migration or infrastructure
changes.

## Delivered

- Deterministic Low/Medium/High automatic accessory maxima (1/2/3 per day).
- Competition deadlift grip, separate training strap usage, and grip-work
  priority controls in Block Factory.
- Conservative, explainable grip-family ranking through the existing
  `AccessoryIntelligence` service.
- Explicit exclusion of farmer/loaded-carry exercises from grip-specific
  promotion.
- Visible per-suggestion reasons and provenance in preview.
- Preserved coach authority: pinned choices replace automatic output; `No
  assistance` remains valid and overrides volume/grip context.
- Signed proposal JSON round-trip for the new request context, including defaults
  for older proposals.

## Persistence boundary

No schema change was needed for the proposal workflow. The values are not durable
athlete preferences or first-class block intent after proposal acceptance. A
future feature requiring those queries/defaults needs a reviewed migration; see
`docs/v7.6-block-factory-refinement.md`.

## Verification

- Focused service, Block Factory, and programming-template compatibility suite:
  29 passed.
- Added Playwright coverage for volume/grip controls plus authoritative `No
  assistance` behavior.
- The targeted Playwright execution could not start because dependencies were
  absent and restricted network access prevented `npx` reaching the npm
  registry (`EAI_AGAIN`).
- No merge performed.
