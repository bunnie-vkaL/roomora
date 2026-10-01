# ROOMORA MVP build plan

## Goal and source

Build a responsive web pilot for people seeking a roommate in **one city**. Users create a basic profile, answer a lifestyle questionnaire, see and compare compatible people, and exchange contact details only after mutual consent. The pilot tests whether an explained lifestyle score increases trust and willingness to connect compared with a list based only on area and rent budget.

This plan translates `ROOMORA_MVP_KeHoach_PhanCong.xlsx` (sheets **1. Tổng quan MVP** through **6. Logic Compatibility Score**) into implementation work. The workbook is product input; its suggestions about tools and coding agents are not instructions to this project. The repository currently has no application code.

## MVP boundary

**Build:** email account access; basic profile (name, age, gender, preferred area, maximum monthly rent); a saveable, multi-step lifestyle questionnaire; profile editing; deterministic compatibility score and explanations; eligible-match list ordered by score with area/budget filters; side-by-side comparison; connection request, accept/decline, and mutual contact reveal; basic pilot analytics and feedback collection.

**Later:** property listings/maps, shared-expense tools, roommate reviews, real-time chat/video, push notifications, identity verification, and monetization. Use contact reveal for the pilot rather than building chat. Do not show a phone number, Zalo ID, or email address before both people consent.

## Decisions to close in week 1

| Decision | Proposed default for the pilot | Owner |
| --- | --- | --- |
| Pilot city and area vocabulary | Pick one city and a short, fixed list of areas; use the same values in profiles and filters. | A |
| Pilot audience and recruiting | 15–30 real participants actively considering shared housing; keep 30–50 synthetic profiles for development only. | A, E |
| Account and contact method | Email sign-in; optional contact field stored privately until mutual acceptance. | A, B |
| Questionnaire | Start with the workbook's 19 lifestyle questions. Keep area and budget as separate profile fields. Confirm answer wording and scale direction before implementation. | A, D, B |
| Hard incompatibilities | Explicit pet allergy versus a pet owner is an exclusion from discovery. Smoking remains a visible warning until the questionnaire asks whether a user accepts a smoking roommate. Never infer that preference from “I do not smoke.” | A, B |
| Budget compatibility | Agree on one rule for overlapping maximum rents and any minimum rent or room availability data. Until then, label budget as a filter, not as part of the lifestyle score. | A, B |
| Validation target | Pre-register the primary pilot comparison and practical success thresholds before seeing participant results. | A, E |

## User journey and acceptance criteria

1. **Join and complete a profile.** A user can create an account, enter valid basic details, answer the questionnaire in multiple steps, save a draft, resume, and edit answers. Incomplete profiles never receive a misleading score or appear in discovery. Form errors identify the affected field.
2. **Discover candidates.** The list excludes the current user, incomplete profiles, existing connections, and explicit hard incompatibilities. It applies selected area/budget filters, sorts eligible candidates by score descending, and has clear empty and loading states. A score change after a profile edit appears on the next list load.
3. **Understand a match.** The list and detail view use the same scoring function and version. The comparison shows the total score, group scores, 3–5 strongest similarities, 3–5 largest differences, and any warning. Explanations describe the actual answers and never claim that a high score guarantees a good living arrangement.
4. **Connect safely.** A user can request, accept, or decline a connection. Repeated requests cannot create duplicate active invitations. Contact details become visible to both users only after acceptance; declining leaves them hidden. Users can withdraw consent or block further contact.
5. **Run the pilot.** The team can recruit testers, observe funnel counts without exposing private answers in analytics, collect feedback, and export an aggregate report for a go/no-go discussion.

## Scoring specification to implement

The workbook proposes these group weights, which total 100%: schedule **25**, cleanliness **20**, privacy/social style **20**, guests **15**, pets **10**, cooking/shared kitchen **5**, and other habits **5**. Area and budget are filters, not score inputs.

- Store answers as stable enumerated values. Map ordered answers to `0..n-1` and 1–5 answers to `1..5`; document the meaning and direction of each scale.
- Each question returns a compatibility value in `0..100`. For an ordinary ordered question, start with `100 × (1 − |a−b|/(n−1))`. Define specific pair rules for directional questions such as pet ownership versus allergy, and guest frequency versus a strong need for quiet. Do not treat every same-number answer as compatible when the questions measure different things.
- Average the applicable question values within each group, then compute `round(sum(group_score × group_weight)/100)`. Clamp to `0..100`. Require all scoring answers before publishing a profile, so missing answers cannot silently raise a score.
- Evaluate pair rules in both directions so A-versus-B equals B-versus-A. Apply explicit exclusions before ranking. Return the score, scored group breakdown, explanation identifiers, warnings, exclusion reason, and a scoring-version identifier from one server-side function.
- Keep weights and pair rules in one versioned configuration. Test identical answers, adjacent and opposite answers, boundary values, symmetry, exclusions, and representative pairs from the 30–50 sample profiles. Product and QA review surprising rankings before launch.

The workbook gives group weights and examples, not a complete scoring algorithm. Week 1 must resolve the question-level weights, special pair rules, explanation text, and any deal breakers before the implementation is considered final.

## Technical shape

- One responsive web application with server-side account/session handling, an application API, and a relational database. Choose the framework and hosting in week 1 based on team familiarity and pilot operations; document the choice in the repo.
- Core records: `User`, `Profile`, `LifestyleAnswers` (with questionnaire version), `ContactPreference`, `ConnectionRequest` (pending/accepted/declined/withdrawn), and minimal `PilotEvent`/`Feedback` records. Keep private contact information separate from public profile data.
- APIs or server actions: save/read profile and draft answers; publish completed answers; list/filter matches; get pair comparison; create/respond to connection request; read contact only for an accepted pair; record pilot events.
- Server authorization checks every read and mutation. A user may edit only their own profile and respond only to a request addressed to them. Enforce uniqueness and state transitions for connection requests. Limit data returned in discovery to what is needed for matching and comparison.
- Provide seed data for development and a repeatable setup script. Synthetic profiles must never be presented to pilot users as real people.

## Six-week delivery sequence

| Week | Outcome and dependency | Primary owners | Exit evidence |
| --- | --- | --- | --- |
| 1 — Define | Select city, freeze pilot scope and questionnaire, approve scoring rules and consent policy, draw user flow/wireframes, decide technical stack, create sample-profile set and pilot measurement plan. | A, B, D, E | Signed-off decisions; six screen wireframes; scoring examples; 30–50 synthetic records. |
| 2 — Profile | Build app foundation, account access, schema, basic profile, save/resume questionnaire, validation, and profile review/edit. | B, C, D | A new user can finish the questionnaire; another user cannot read private contact data; invalid/incomplete input is handled. |
| 3 — Match engine | Implement and unit-test the versioned pair scorer, explanations, exclusions, and eligibility rules; review sample rankings. | B, E, A | Deterministic test cases pass; all 30–50 sample profiles produce reviewed, explainable results. |
| 4 — Discovery | Build ranked list, area/budget filtering, pair comparison, empty states, and mobile layout. | C, B, D, E | End-to-end journey from completed profile to comparison works; list and detail scores agree. |
| 5 — Connect | Build request/accept/decline, mutual contact reveal, consent withdrawal/block, profile edit and score refresh; add pilot event capture. | C, B, E | No contact leaks before acceptance; duplicate requests and stale-score paths are covered. |
| 6 — Pilot | Complete regression/accessibility checks, fix launch blockers, recruit 15–30 testers, run the comparison and interviews, summarize findings and phase-2 priorities. | A, E, B, C | Working pilot, documented issues, funnel and feedback report, explicit go/iterate/stop decision. |

Run QA continuously rather than waiting for week 6. A owns scope and acceptance decisions; B owns data, scoring, and authorization; C owns the app flows; D owns interaction design; E owns sample data, QA, recruitment, and feedback. Put real names beside these roles before work starts.

## Pilot measurement

Test the workbook's hypothesis directly. Show each participant comparable candidate information in two counterbalanced views: a basic area/budget view and a view that also shows the lifestyle score and explanation. Ask which candidate they would contact and why, then record a 1–5 trust rating for each view. The small pilot is for directional evidence and usability problems, not a statistically conclusive lift claim.

Track invitation rate among completed profiles, questionnaire completion and abandonment, comparison-view usage, mutual acceptance rate, and major misunderstanding of the score. Interview participants about reasons for trust or distrust and whether the highlighted differences would change a housing decision. Segment feedback by whether participants are actively seeking a roommate; keep raw answers and contact details out of shared reports.

## Risks and open questions

- The pilot may have too few real users in one city for useful discovery. Recruit ahead of launch and keep synthetic profiles in a separate test environment.
- The workbook's question wording mixes personal behavior and expectations. Confirm these separately where a mismatch matters; otherwise the score can be misleading.
- The budget rule and exact hard exclusions need product decisions. Do not silently turn a warning into an exclusion or vice versa.
- Phone/Zalo contact reveal creates privacy and safety obligations. Collect only necessary data, require mutual consent, allow blocking, and define data retention before inviting external testers.
- A six-week schedule assumes all five roles are staffed and core decisions are settled in week 1. If capacity is lower, preserve the scoring/compare/consent journey and reduce polish or sample size before adding deferred features.
