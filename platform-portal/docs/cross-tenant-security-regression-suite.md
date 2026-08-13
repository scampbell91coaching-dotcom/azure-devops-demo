# Cross-tenant security regression suite

`tests/test_cross_tenant_security.py` is the pre-enforcement contract for the
multi-coach rollout. It creates two authenticated coaches and two identically
named athletes, then describes two organisation memberships in `TenantSeed`.
The organisation objects are intentionally test-only because production has no
organisation, membership, or coach-to-athlete ownership model yet.

Strict `xfail` is used only for that known schema/authorization gap. An enforced
route unexpectedly passing is reported by pytest as an XPASS failure, requiring
the marker to be removed. Authentication and CSRF remain active in every test.
The existing meal-plan template direct-object owner check is a normal passing
test and is not weakened.

## Coverage and current blockers

| Surface | Read contract | Mutation contract | Current blocker |
| --- | --- | --- | --- |
| Athlete profile | direct athlete ID and list disclosure | onboarding goals by athlete ID | athletes have no organisation/coach ownership |
| Programming | block, week and session IDs | archive block ID | ownership resolves only to athlete, not caller tenant |
| Check-ins | check-in ID | review check-in ID | coach queries are global |
| Nutrition/macros | athlete macro history | create prescription | coach role is the only coach-side boundary |
| Meal plans | list/PDF-metadata disclosure; template ID | existing template edits are owner-scoped | list repository is global; assignment ownership is athlete-only |
| PDF/file access | tenant-scoped adapter contract | tenant-scoped adapter contract | no PDF metadata model or file-store abstraction exists |
| Performance/dashboard API | athlete ID charts request | no mutation endpoint exists | API trusts globally privileged coach role |
| Competition/bodyweight | included in athlete profile direct-ID denial | no dedicated mutation endpoint exists | composed from globally readable athlete/meet/check-in data |
| Coach list/search | similarly named athlete disclosure | athlete creation is global | list is unscoped; no search endpoint exists |

Before removing expected-failure markers, add a safe forward migration that
creates a default organisation, assigns existing coaches and athletes to it,
and makes membership non-null only after backfill. Every resource lookup must
derive tenant scope from the authenticated principal and return `404` for an
out-of-tenant object ID. File keys or signed-download claims must carry an
immutable tenant/athlete owner and be resolved through a tenant-aware adapter;
paths supplied by clients are not authorization evidence.
