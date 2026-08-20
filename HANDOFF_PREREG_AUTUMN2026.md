# Handoff: Autumn 2026 First-Year Pre-Registration — Final Entry and Evidence

Written 2026-08-18 for any agent continuing this work. The student is
Christian Bricker, incoming UChicago first-year (Business Economics major
planned, METI + Classical Studies minors). Pre-registration closes
Friday 2026-08-21 5:00 PM CT; the entry below was verified against the
live system on 2026-08-18 and is being submitted.

## 1. The final entry

Humanities, ranked (all verified present at these times in the live
First-Year Pre-Registration system, 118 rows):

| Rank | Section | Course | Meets |
|---|---|---|---|
| 1-4 | HUMA 11500 /11 /12 /13 /14 | Philosophical Perspectives | TTh 11:00-12:20 |
| 5 | HUMA 18000 /11 | Poetry and the Human | TTh 12:30-1:50 |
| 6-7 | HUMA 18000 /7 /8 | Poetry and the Human | TTh 9:30-10:50 |
| 8 | HUMA 18000 /12 | Poetry and the Human | TTh 2:00-3:20 |
| 9-10 | HUMA 18000 /9 /10 | Poetry and the Human | TTh 11:00-12:20 |
| 11-12 | HUMA 11500 /4 /5 | Philosophical Perspectives | MW 1:30-2:50 |
| 13-14 | HUMA 12300 /13 /14 | Human Being and Citizen | TTh 12:30-1:50 |

Language: LATN 10100 (Introduction to Classical Latin I) section 3,
Radding, MWF 10:30 — first; section 2 (MWF 9:30) alternate.
BioSci: BIOS 11144 (The Genetic Basis for Human Disorders, Gifford,
MWF 12:30) first; BIOS 13140 (The Public and Private Lives of Insects,
Larsen, MW 1:30) second. WRIT: answered Yes (College auto-places the
section). Math: skipped (AP Statistics).

Requirement satisfied: >= 8 sections from >= 3 sequences.

## 2. The student's binding rules (set explicitly, in his words or by
his confirmation)

- GPA protection is the optimization target; workload fear is real
  ("I can't get stuck with so much reading").
- No 3:30 classes. Prefers no class before 10:30 (Latin at 10:30 opens
  MWF); the rank-6/7 Poetry 9:30 sections are a knowingly accepted
  exception, insurance against administrative placement.
- Never enter/request/handle his password or second factor. He drives
  all logged-in browser work himself.
- Raw student comments never get committed/pushed to the public repo
  (comments.db and prereg dumps are gitignored; they travel by chat
  upload only).
- Never plan below 300 units. The 4th course is a hedge with the
  October 16 5:00 PM clean-drop as the exit.
- Communication: matter-of-fact, course NAMES not just numbers, no
  unsupported "easy A" labels, evidence never accusations.

## 3. Why this ballot (the decision chain)

1. Original desire: Human Being and Citizen — great books + antiquity.
   A fully verified HBC-forward ballot was built first (HBC 12:30
   sections 13-16 etc., 11/11 live-verified).
2. Workload evidence surfaced: HBC is the heaviest Hum sequence
   (7.0 hrs/wk; 20% of students report 10+ hrs — highest tail among his
   options). He balked at the reading volume.
3. A Poetry-maximizing "easiest" ballot was built (Poetry 5.8 hrs, 59%
   of students <= 5 hrs — lightest sequence in the College), but content
   analysis showed Poetry contains essentially none of what he wanted
   (in >1,000 Poetry comments, Homer appears once; catalog confirms it
   is a form/close-reading sequence).
4. Resolution: Philosophical Perspectives — autumn is Plato, Aristotle,
   and the Greek tragedians (catalog text; student comments mention
   Aristotle 70x, Plato 61x), at 6.2 hrs/wk with 46% of students
   <= 5 hrs. "Plato without the page count." Winter/spring pivot to
   Descartes/Hume/Kant — flagged to him explicitly; he accepted.
   Poetry stays as the ease-insurance block; HBC as token third
   sequence (and a welcome outcome if reached).

## 4. Evidence base (what was measured, where it lives)

Data: `analyzeCourseFeedback/getSectionTimes/times.db` (3,904 HUMA
sections 2016-2026 + BIOS/LATN Autumn 2026, scraped from the PUBLIC
Class Search guest portal; NOTE: 8 terms are truncated at the portal's
250-row cap — see ROADMAP W7), `analyzeCourseFeedback/course_feedback.db`
(ratings, 12 dimensions, per-instructor hours), comments.db (342,767
raw comments, LOCAL/gitignored), `forecasting/signals.db`,
`analyzeCourseFeedback/getCourseIDs/catalog.db`.

Tools (all in `analyzeCourseFeedback/getSectionTimes/`):
`scrape_section_times.py`, `backtest_times.py`, `slot_report.py`,
`verify_prereg.py` (user-driven browser; reads every tab/frame; TARGETS
currently set to the 14 ranked sections).

Established findings, all walk-forward / out-of-sample where applicable:

- Predicting the instructor NAME from a time slot is chance level:
  best rule 10% over 143 predictions across 10 autumns, against a 62%
  ceiling (share of returning instructors at all).
- Slot-cluster quality tilts are NOT statistically significant at any
  of four granularities (best: day x band, rho +0.11, permutation
  p = 0.077, n = 112). Ballots must not pretend otherwise.
- The real structure is individual stickiness plus turnover: only 49%
  of each autumn's Hum instructors taught the prior autumn; returners
  keep their exact time 34% (same days 68%, same band 78%); median
  career is 1-2 autumns (23 of 54 HBC instructors taught exactly one).
- Measured return hazards used in all odds: taught Autumn 25 AND Winter
  26 -> 48%; Winter-only -> 37%; Autumn-only -> 28%; lapsed -> ~15%,
  blended with per-person streaks (shrunk, pseudo-count 2).
- Sticky individuals that drive every recommendation:
  GOOD - Broughton (Poetry 9:30/11:00, 7 straight autumns, strongest
  ease testimony in the corpus), Morrissey (Poetry, 4.57 at 4.9 hrs,
  6 straight), Saltzman (Poetry 12:30 both recent years, gentlest
  grading testimony), Nooter, Hofmann, Klinger; PhilPer 11:00 2025 crew
  (Proios 4.55, Grosser 4.50, Finkelstein, Briggs 4.40 at 4.6 hrs),
  Kaspers (MW 1:30/3:00, 4.45 at 4.9 hrs, largest easy-mention count
  in PhilPer), Zimmer (fairness 4.72), Ferguson (4.72 — best teacher,
  NOT lightest: 6.9 hrs).
  AVOID - Loeffler (PhilPer 12:30 four straight autumns + 2:00;
  fairness 4.21, hard-mentions 15 vs easy 9) — this is why NO PhilPer
  12:30 or 2:00 section is ranked; Davey (PhilPer 9:30, six straight
  autumns, 4.03); Ford (PhilPer 2:00 both recent years, fairness 3.59,
  worst in either sequence); Kates (MW 4:30); Poetry MW belt (Rokem
  MW 3:00 sticky at 4.22; Gabel fairness 3.56, winter-active).
- Final per-section model (hazard x recency-weighted slot affinity /
  section count; good = rating >= 4.40 & fairness >= 4.35 or dominant
  ease evidence; avoid = rating <= 4.25 or fairness <= 4.25):
  ranks 1-4 ~40% good / 14% avoid-tail; rank 5 ~81% good with a
  ~10-13% Torres (4.17) tail; ranks 6-7 73% good / 0% avoid; rank 8
  75/8; ranks 9-10 57% good with an ~18% Gabel tail (upper bound —
  his hazard is inflated by a pre-2020 streak); ranks 11-12 37/14
  (Kaspers 33%). Known model caveats: cluster-level non-significance
  means these are tilts with wide error bars, not guarantees; ~40-60%
  of every slot is a no-history newcomer who lands at the sequence
  mean (~4.34).
- Verification: the live pre-reg page (First-Year Pre-Registration,
  one flat 118-row grid, opens in a second browser tab) was captured
  in full; earlier ballot verified 11/11, times drift was caught
  (11500/21 moved TTh 3:30 -> MW 3:00 between scrape and live), so the
  LIVE page is always the authority. Conflict matrix: all 7 possible
  Hum landings clear all 3 Latin sections; BIOS 11144 clears every
  landing; BIOS 13140 conflicts only with the rank-11/12 landing
  (accepted; fixable at add/drop); BIOS 11140 (Biotechnology, TTh
  11:00) conflicts with the modal landings and is deliberately
  excluded from the ballot — see §5.

BIOS eliminations for the record: 15113 (Gifford's viruses course,
4.66, MWF 9:30) violates the morning rule -> moved to the winter plan;
11136 (Complex Trait Genetics, 3.0 hrs) sits exactly on Radding's
Latin and was full; 15127 (Butler) is not offered this autumn despite
the catalog's claim.

## 5. The playbook from here (dates are the contract)

- Sept 4: schedule + WRIT placement publish. Check WRIT landed in an
  open window (it must — fixed courses occupy only two midday bands).
- Sept 8: results. He pastes instructor names; deliver keep-or-act
  verdicts from the GOOD/AVOID lists above the same day. Include the
  Biotechnology decision: if his Hum landed anywhere OTHER than TTh
  11:00 and he still wants to try it, swap BIOS 11144 -> 11140 at
  add/drop (Sept 10); if Hum landed at 11:00 the question is moot.
- Weeks 1-3: four courses carried (Hum + Latin + BIOS + WRIT). The
  BIOS seat is the designated drop; October 16 5:00 PM is the free
  exit. Rush, if it happens, counts as a phantom 10 hr/wk course.
- Late autumn: winter registration has VISIBLE instructors and times —
  no forecasting needed. Winter BIOS bench, best first: BIOS 11125
  (Life Through a Genomic Lens, 4.50 @ 3.4 hrs), BIOS 13134 (It's Not
  Easy Being Green, 4.58 @ 4.0), BIOS 15127 (Butler, 4.66 @ 4.7, if it
  appears), BIOS 15113 (Gifford, 4.66 @ 5.1). Beware 000-unit traps
  (Pizza with the PIs, Collaborative Learning — zero credit).
  Winter shape: Hum II + Latin 10200 + WRIT-if-deferred + winter BIOS;
  ECON 10000 (8.6 hrs, heaviest in his set) goes in a non-pledge
  quarter.
- Data debts (ROADMAP W7): 250-row-cap backfill via weekday-partitioned
  queries; SOSC/PHIL/ECON times; my_slate_comments.py still joins by
  surname (use professor ids); LATN ratings unreadable (form variant).

## 5b. Post-critique validation (2026-08-19, prompted by an external
review): two tests the original file lacked

Newcomer quality distributions (first 3 quarters of first-time
instructors, 2019+ starters, n in parens): Poetry 50% GOOD / 25% AVOID
(32), first-year mean 4.42; PhilPer 43% / 39% (56), mean 4.32; HBC
40% / 46% (52). CONSEQUENCE: "0% avoid" claims were wrong as
realized-risk statements. Correct language: "0% IDENTIFIED-avoid mass";
every section's realized avoid risk includes its unknown share times
the sequence newcomer-avoid rate. This widens Poetry's advantage
(corrected top-Poetry sections ~83-86% good / 7-12% avoid vs corrected
PhilPer 11:00 ~60% / ~32%).

End-to-end walk-forward of the actual ranking model (hazard x load x
slot affinity + GOOD/AVOID), 2021-2025, all three sequences, 221
rated section-years: the GOOD side is real and monotonically
calibrated (predicted <15% -> realized 31% good; 15-35% -> 42%;
35-60% -> 52%; top third of sections 52% realized good vs bottom third
33%). The AVOID side does NOT discriminate (realized avoid 22-26%
regardless of prediction; sections with 0-5% identified avoid realized
24% avoid) because realized bad draws come mostly from newcomers the
model cannot see. CONSEQUENCE: the ballot genuinely raises the chance
of a good draw; it cannot lower the ~quarter baseline chance of a bad
one except by (a) avoiding sticky-bad slots and (b) choosing the
sequence with the gentlest newcomer pool - which is Poetry on both
counts. Conceded as unproven: GPA effects (no grade data; ratings/
fairness/hours are proxies), assignment-constraint modeling (marginal
probabilities only), threshold brittleness (4.40/4.25 cutoffs,
unshrunk small-n ratings), and any social/peer-composition claims.

## 5c. Second validation round (2026-08-19): within-sequence power,
uncertainty propagation, robustness

- Within-sequence walk-forward (ranks computed inside each
  sequence-year): GOOD spreads top-vs-bottom third are directional but
  not significant - Poetry +29pts (p=.086, n=51), PhilPer +20pts
  (p=.075, n=83), HBC +11pts (p=.225). CONSEQUENCE: the model reliably
  picks SEQUENCES and excludes tails; its ordering WITHIN a sequence is
  a plausible tilt only, so section order below rank 1 follows the
  student's schedule preference.
- Sequence-level gaps among rated draws are large and solid: Poetry
  baseline 55% GOOD / 4% AVOID vs PhilPer 36% / 29% vs HBC 38% / 37%.
- Newcomer denominators: Poetry 8/32 AVOID (95% CI 13-42%), PhilPer
  22/56 (27-52%); P(Poetry newcomer pool safer) = 92%. Coverage audit:
  every autumn newcomer since 2021 in schedule data has rated feedback
  (0% gap) - the unrated-newcomer worst case is empirically empty.
  Propagated head-to-head: P(Poetry /11 lower corrected downside than
  a PhilPer 11:00 section) ~ 100% (Poetry /11's unknown share is ~6%,
  so the comparison is insensitive to newcomer-rate uncertainty).
- Robustness: 17,496 specifications (pseudo-count x lapsed hazard x
  recency weight x both thresholds x mass cap x newcomer shrinkage x
  ease-rule on/off x leave-one-out dropping Broughton/Morrissey/
  Saltzman/Torres/Gabel and none): Poetry's best section beats
  PhilPer's best in 100.0% of specs; Poetry /11 is top-2 within Poetry
  in 93.3% (it is #1 in 91%; /7 or /12 lead otherwise).
- FINAL SUBMITTED ORDER (same 14 sections as section 1; only the
  order changed, so verifier targets and all conflict checks stand):
  Poetry /11 -> /12 -> /9 -> /10 -> /7 -> /8 -> PhilPer /11 -> /12 ->
  /13 -> /14 -> PhilPer /4 -> /5 -> HBC /13 -> /14. Rank 1 is the
  robust pick; ranks 2-6 are ordered by the student's schedule
  preference (protect mornings) per the within-sequence result;
  PhilPer stays as the content-bearing middle block with honestly
  stated ~60/32 corrected odds.
- Still open (post-deadline): 250-row-cap term backfill; constrained
  assignment simulation; grade-outcome validation (no grade data yet -
  all claims are about instructor experience and grading friction, not
  GPA directly).

## 5d. Final external audit (2026-08-19) — accepted corrections and
STATUS RELABEL

An external auditor (working directly against the raw databases)
accepted Poetry-first, Radding, and the BIOS ordering, and issued
corrections that are all accepted:

- RELABEL, applying to every number in 5/5b/5c and this file: all
  assignment distributions and downside percentages are HEURISTIC
  SCENARIO WEIGHTS for decision support - not calibrated probabilities.
  No held-out Brier/log score, candidate-universe audit, or
  assignment-constraint model exists. The only calibration evidence is
  the coarse GOOD-side bucket table in 5b.
- Torres meets the stated AVOID rule (4.17); counting her mass puts
  Poetry /11 downside near 10% (not 2%) and /12 near 16%. Poetry /7-8
  therefore carry the LOWEST modeled downside (~6%); /11 stays rank 1
  on expected quality and preference, not downside minimization.
- Named-but-unrated candidates are priced in neither direction; treat
  their mass as interval-widening. Newcomer estimates may double-count
  dept-split professor identities (e.g. multi-id instructors) and lack
  person/year clustering.
- HBC does NOT rise to ranks 5-6 despite its high E[rating]: ballot
  order encodes the student's deliberate content/workload/writing-track
  decision, and all Poetry sections stay above HBC by preference.
- Radding: evidence = ONE evaluated Autumn 2025 section, 11
  respondents (50 answer-rows, not 50 students); one mild downside
  (classmates with prior Latin can intimidate in whole-class
  exercises). Verdict: strong first choice, not "unconditional."
- BIOS: Gifford evidence is transferred (zero exact-course); the
  Gifford-vs-Hunter Principles comparison is cross-year; the weak
  Gifford upper-level datapoint was co-taught (Pineda-Catalan) and is
  not cleanly attributable. Hunter: one of the lowest-rated heavily
  observed BIOS instructors (not "categorically weakest"). Keep 13128
  last as capacity insurance (11144 39/40, 15128 8/35, 13128 19/60,
  13140 closed - auditor-supplied counts).

FINAL WORKING BALLOT (consensus): Poetry /11 -> (/7 -> /8 -> /12 or
/12 -> /7 -> /8 per the student's 9:30 preference) -> /9 -> /10 ->
PhilPer /11-14 -> HBC /13-14 and PhilPer /4-5 as lower preferences.
Latin: Radding /3 first. BIOS: 11144 -> 15128 -> 13128. WRIT yes.

Post-deadline debt (ROADMAP W7): a one-command reproducible artifact
(pinned constants, data hashes, deduplicated newcomer treatment,
leakage-free walk-forward, Brier/calibration) before this machinery is
reused for winter registration.

## 5e. Winter-planning corrections (2026-08-20, external audit) — and a
named fallacy

THE COVERAGE FALLACY (second offense, do not repeat): absence from our
databases was twice presented as absence from the world ("0% avoid",
then "MATH 15250 has never been taught" / "PHIL 20216 is new").
N=0 in course_feedback.db means NO COVERAGE, nothing more. Our own
corpus proved it: 21 comments mention MATH 15250 while the evaluation
tables hold zero sections of it (MATH 15xxx coverage = only 15300 and
15910 - the known intro-math dark zone). Every future "X doesn't
exist / is new" claim must be phrased "X is absent from our coverage."

Accepted corrections (externally sourced, unverifiable from this
environment, accepted on citation + known coverage gaps):
- MATH 15250: offered Autumn AND Winter AND Spring per the current
  catalog (our scrape's 'Autumn' was stale or truncated); taught
  repeatedly since ~2022; explicitly item 52 on the official BizEcon
  Perspective list. A legitimate flexible Perspective option; zero
  instructor/workload evidence in our data.
- PHIL 20216 (Proios): previously taught Spring 2023 - not new;
  planned Winter with Proios. Strong transferred instructor evidence.
- PHIL 25105: co-taught Agnes Callard + Arnold Brooks, TTh 5:00-6:20;
  Brooks's HBC record alone cannot predict a co-taught course.
- PHIL 21000: the 4.66 sections are BENJAMIN Callard; planned Spring
  2027 instructor is Candace Vogler (3.96, hours ~7.3 per-instructor).
  Fallback, not default.
- PHIL 24098: exists historically, not planned 2026-27 - off the
  operational list unless added.
- Winter-2027 registrar schedule publishes ~Nov 9; until then all
  winter listings are Tentative.

## 5f. FINAL BIOS ORDER (2026-08-20, after coverage audit)

Submitted BioSci ranking: BIOS 11144 (Genetic Basis for Human
Disorders, Gifford, MWF 12:30) -> BIOS 15128 (Outbreak, Feeney - no
evaluation record anywhere, chosen for capacity and complementary
conflict pattern) -> BIOS 11140 (Biotechnology, Bhasin 3.86
exam-heavy, covers the MW 1:30 hole 15128 leaves). This set gives >=2
time-compatible options in every (Latin section x HUMA landing) cell;
the previously recommended {11144, 15113, 15128} left a single point
of failure at (Latin /2, PhilPer MW 1:30). BIOS 15113 (Life in the
Viral World, Gifford 4.66/fair 4.66, MWF 9:30) is the FIRST add/drop
target if Latin lands /3 - best-evidenced alternative, priced at 9:30
mornings and a 10-minute transition into Latin. 13128/13132 (A.
Hunter) stay off: 3.2-3.5 across 40+ deduped reports. Max-seat-security
fallback if ever needed: 11144 -> 15128 -> 13128.

## 5g. Philosophy fourth course (Poetry branch) — FINAL (2026-08-20)

Ladder (exact entries incl. class numbers, live-verified externally):
1. PHIL 21013/1 [81851] Neo-Aristotelian Moral Philosophy, Vogler,
   TTh 11:00 + Fri 1:30 discussion 1D02 [81853] - the deliberate
   rigorous audition. Only candidate with same-course same-instructor
   evidence (one Autumn 2025 section: 4.60, fairness 4.75, feedback
   4.75, 7.5 hrs, all respondents 5-10h band; 6 comment-answer rows).
   BizEcon Perspective. Thin evidence = purposeful experiment, not
   guarantee.
2. PHIL 23000/1 [81889] M&E, Briggs, TTh 2:00 + Fri discussions
   1D04 [81893] -> 1D03 [81892] -> 1D02 [81891]. Course history
   (Callard era) light-and-fair; Briggs unobserved in this course but
   4.81/org 4.89 elsewhere.
3. PHIL 22951/1 [81883] Egalitarianism, Zimmer, TTh 11:00 +
   discussions 1D02 [81885] -> 1D01 [81884]. Strongest fairness file
   (12 reports, 4.6-5.0). BizEcon Perspective.
Ladder covers every Poetry x BIOS combination (21013 conflicts TTh 11
Poetry sections + BIOS 15128; 23000/22951 cover those corners).
In the Maroon/HBC branch WRIT replaces this course entirely.

Week-1/2 experiment: do the reading honestly + time it; write one
argument reconstruction (claim, argument, objection, reply) and take
it to office hours; audit syllabus for weights/curve/revisions.
KEEP if energizing and 4-course load sustainable; DROP-RETURN if
material yes but load no; LEAN-CLASSICS only if instruction is clear
and fair yet argument work leaves you cold. Week-3 Friday clean drop
is the backstop. No grade distributions exist for any candidate -
"GPA-safe" claims are structurally unavailable.

VERIFIED DATA CORRECTIONS (2026-08-20): PHIL 23000's 104 comments all
come from ONE Spring 2026 section; Zimmer's 182 rows = 69 distinct
comments. Root cause found: comment capture stored rows per course-row
and URL-duplicated course rows (2-3x) inflate comment counts corpus-
wide. ALL session comment counts are upper bounds. DATA DEBT: dedupe
comments by (report URL, comment text) and course rows by URL.

## 5h. SUBMISSION STATE (2026-08-20, final)

- Humanities finalized to the mornings-protected order: Poetry /11 ->
  /12 -> /7 -> /8 -> /9 -> /10 -> PhilPer /11-14 -> HBC /13-14 ->
  PhilPer /4-5.
- Known, intentional compromise: PHIL 21013 (Vogler) coexists ONLY
  with BIOS 11144 among the three Biology entries (her Fri 1:30
  discussion collides with BIOS 15128; her TTh 11:00 lecture with BIOS
  11140). Biology order stays 11144 -> 15128 -> 11140: Vogler is the
  ideal landing, Briggs (PHIL 23000) the realistic net. Alternative
  orders if priorities change: maximize-Vogler = 11144 -> 15113 ->
  15128; max capacity = 11144 -> 15128 -> 13128.
- Autumn Math: skip; MATH 15250 planned for Winter or Spring (not
  abandoning math).
- Dates: submit by Fri 2026-08-21 5:00 PM CT; results expected Mon
  2026-09-07 per College FAQ (verify portal banner that morning);
  first-year add/drop Sept 10; clean drop Fri of week 3.
- WRIT branch logic: Poetry -> Grey track (HUMA 19100 winter);
  PhilPer/HBC -> Maroon WRIT. The PHIL ladder exists only in the
  Poetry branch.

## 6. Working protocol with this student

He runs everything requiring UChicago auth or network on his laptop
(this cloud environment cannot reach *.uchicago.edu at all) and pushes
databases; code/analysis happens on branch
`claude/explore-code-data-x8tkpa` (never touch main). He responds best
to: direct verdicts first, numbers attached, honest caveats stated
once, options collapsed to a recommendation. When he says "no
shortcuts," he means recompute from raw data and show the sweep.
