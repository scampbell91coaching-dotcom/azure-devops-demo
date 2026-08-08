# Traditional Strength UX V7 Follow-ups

## Visual QA findings

### Coach platform

Status: GOOD BASELINE

The refreshed coach shell is a clear improvement and should remain the canonical
private-platform design direction.

Keep:
- compact Traditional Strength Platform branding
- black / cream / gold visual language
- two-level information hierarchy
- tighter navigation
- separated user identity and platform actions
- reduced oversized page-header treatment
- consistent cards, controls and spacing

## Athlete platform

Status: NEEDS ALIGNMENT

The athlete portal still looks visually separate from the coach platform.

Current issues:
- blue visual system conflicts with coach black / cream / gold system
- legacy TS square mark remains
- oversized hero text such as "WELCOME BACK, ALEX"
- excessive vertical whitespace
- dashboard information density is too low
- different navigation treatment
- card/component styling does not feel like the same product

Target:
- preserve athlete-specific workflow and simpler navigation
- move to the same Traditional Strength visual system as coach
- use canonical logo/brand treatment
- reduce hero/title scale
- improve information density
- retain clear mobile-first usability
- make Programme the primary athlete action

## Login / authentication surface

Status: NEEDS BRAND POLISH

The login layout is structurally strong but the external-facing logo lockup requires
refinement.

Current issues:
- lion/emblem is visually dominant relative to the wordmark
- emblem + Traditional Strength relationship feels more like a lifestyle-brand lockup
  than the private coaching platform
- spacing and proportions need tightening

Target:
- retain the canonical emblem
- reduce emblem dominance
- tighten emblem-to-wordmark spacing
- align typography with the internal platform
- preserve the strong split-screen login structure

## Operations / Observability

Status: FUNCTIONAL REPAIR ACCEPTED

Keep the stable observability contract and explicit telemetry states:

- AVAILABLE
- DEGRADED
- UNAVAILABLE
- UNKNOWN
- NOT_CONFIGURED

Never represent missing telemetry as healthy and never allow missing optional fields to
crash the Operations UI.

## Next visual work

Create a focused Athlete + Authentication Branding V7 pass.

Scope:
1. athlete base shell
2. athlete dashboard
3. programme/session navigation
4. login/authentication branding
5. responsive 320 / 390 / 430 validation

Do not reopen the coach shell unless a shared-token change genuinely requires it.
