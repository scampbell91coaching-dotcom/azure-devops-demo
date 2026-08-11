# V7.9 Golden Programme Regression report

## Outcome

Added a durable golden programme corpus at the Block Factory
preview-to-persistence boundary. The suite protects representative low,
moderate, high, zero-assistance, competition, and manually pinned programme
shapes using deterministic structural comparisons.

## Delivered

- `platform-portal/tests/fixtures/v79_golden_programmes.json`
  - six named programme fixtures;
  - deterministic catalogue metadata and prescription defaults;
  - a high-volume session with four assistance exercises;
  - explicit automatic, none, and pinned/manual modes.
- `platform-portal/tests/test_v79_golden_programmes.py`
  - exercises the real preview and accept routes;
  - reloads persisted data before assertion;
  - checks lift slots separately from assistance rows;
  - checks order, count, positions, sets, reps, RPE, provenance, manual
    selections, and no assistance.
- `docs/v7.9-golden-programme-regressions.md`
  - records fixture provenance, contract, scope, and focused commands.

## Scope and policy

Production code was not changed. In particular, automatic accessory selection
continues to use the existing low/medium/high maxima of one/two/three per day.
The greater-than-three regression is a manually pinned programme shape and
protects preservation rather than selection-policy expansion.

## Verification

Focused golden suite:

```text
python -m pytest tests/test_v79_golden_programmes.py -q
7 passed
```

Adjacent Block Factory compatibility suite:

```text
python -m pytest tests/test_v79_golden_programmes.py \
  tests/test_block_factory_v2.py tests/test_block_factory_v3.py \
  tests/test_programming_templates.py -q
34 passed
```
