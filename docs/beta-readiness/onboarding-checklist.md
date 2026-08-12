# Beta onboarding checklist

Complete this once per coach and once per athlete. Keep the signed record in an
approved private system and link it from the release/cohort record using a
non-sensitive identifier.

## Cohort preconditions

- [ ] Shared multi-coach tenant-isolation acceptance is linked, or this person
  is contained in an approved single-coach isolated deployment.
- [ ] Release acceptance is GO/CONTAINED GO and has not expired or been revoked.
- [ ] Accountable coach, support responder, urgent external contact channel,
  support hours and expected response time are communicated.
- [ ] Participant has received the beta boundaries, privacy/retention terms,
  known limitations, withdrawal route and data deletion/export limitations.
- [ ] Consent/acknowledgement is recorded outside Git; no sensitive participant
  details are copied into tickets or screenshots.
- [ ] Coach confirms the athlete is appropriate for a supervised powerlifting
  beta and that the platform is not a medical or emergency service.

## Coach setup

- [ ] Organisation/tenant assignment and coach membership were made by an
  authorized owner and independently checked by a second person.
- [ ] Coach can authenticate through the real edge, sign out and sign in again.
- [ ] Coach can see only the expected organisation, coaches and athletes.
- [ ] Direct URLs for another tenant's athlete, programme, session, check-in and
  report return 403/404 and create no observable side effect.
- [ ] Coach knows how to create an athlete, issue/revoke an invitation, publish a
  reviewed block, inspect completed sessions and respond to a check-in.
- [ ] Coach accepts the manual daily poll for completed training and knows the
  incident stop conditions.

## Athlete setup

- [ ] Coach verifies the athlete email character-for-character and confirms the
  intended tenant/coach before generating an invitation.
- [ ] Invitation delivery state and canonical HTTPS hostname are checked without
  retaining the token or full invitation URL.
- [ ] Athlete activates in the supervised window, uses a unique 12+ character
  password, signs out and signs in again.
- [ ] Used, revoked and expired invitation behavior is checked as applicable;
  disclosed or misdirected tokens are revoked immediately.
- [ ] Athlete can see only their own profile, active programme, sessions,
  results and check-ins; known other-athlete and coach URLs return 403/404.
- [ ] Athlete and coach agree the dated squat/bench/deadlift session map, missed
  session policy, warm-up instructions and external completion/urgent channel.
- [ ] Actual supported phone/browser passes the smoke checklist, including one
  non-critical save/reload before real training data is entered.
- [ ] Athlete understands that offline use is not guaranteed, completed logs are
  locked, corrections require support, and pain/injury concerns go outside the
  platform.

## Activation and follow-up

- [ ] Coach publishes only the reviewed block and athlete identifies the same
  next intended session and warm-up.
- [ ] First session is supervised; coach verifies its completion and retrieval
  the same day.
- [ ] Support checks in after first login, first completed session and first
  weekly check-in.
- [ ] Onboarding result, UTC timestamps, release ID, device/browser, failures,
  containments and owner are recorded without personal or health data.
- [ ] Any authorization ambiguity, wrong account/tenant, missing prescription,
  lost write or unreviewable completion stops activation and opens an incident.
