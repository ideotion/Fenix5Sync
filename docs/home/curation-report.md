# Evidence-Based "Sports at Home" Curation Report
## Foundation deliverable for the Fenix5Sync furniture-and-objects home-training knowledge base

Status: Curation report (evidence foundation) + benefits-by-population table + bibliography for the new **Sports at Home** coaching category. This is the document every downstream artifact (movement library, object library, session library, screening logic, animation/figure specs, personalization rules) must cite back to.

Scope of this document: the evidence, taxonomy, and safety foundation for a guided home-training modality that uses furniture and ordinary household objects as the equipment. It is built to serve four populations on one ladder — fragile/deconditioned, overweight, chronically ill (stable, cleared), and experienced/fit — without changing app or method.

Date of evidence search: 22 June 2026. Reliability of cited findings is bounded by the publication dates in the bibliography.

This is a foundation pass, not the full knowledge base. The structured JSON deliverables (movement library, object library, session/program library, screening tree, figure/animation production spec, glossary, safety document) are built on top of this and are listed under "What this foundation feeds" at the end. The companion machine-readable artifact is `web/content/home/overview.json`.

---

## 1. Method and search strategy

Databases and sources queried: PubMed / MEDLINE, the Cochrane Library (including CENTRAL records), peer-reviewed journal portals (BJSM, BMJ, JAMA network, Diabetes Care, Medicine & Science in Sports & Exercise, Nature Medicine, Sports Medicine, Frontiers, MDPI), and governing-body / consensus documentation (World Health Organization, American College of Sports Medicine, American Diabetes Association, the PAR-Q+ Collaboration). Searches were run in June 2026 using population- and modality-specific terms (for example "WHO physical activity guidelines 2020", "resistance training equipment outcomes overview of reviews", "isometric exercise blood pressure network meta-analysis", "progressive resistance training older adults Cochrane", "exercise snacks cardiometabolic meta-analysis", "home-based versus centre-based cardiac rehabilitation").

Evidence hierarchy applied (highest first): Cochrane reviews and network meta-analyses, then large pairwise meta-analyses and position stands, then randomized controlled trials, then consensus and validated screening instruments, then authoritative measurement/compendium sources.

Grading scale used in this report:
- **Strong**: consistent, statistically significant findings across multiple systematic reviews / meta-analyses or large, rigorous RCTs; effect direction robust.
- **Moderate**: a significant systematic review or meta-analysis exists, but with notable heterogeneity, modest study quality, a limited trial count, or no advantage over an active comparator.
- **Limited / Emerging**: few, small, or low-quality trials; mixed results; or mainly indirect evidence.
- **Practice**: justified by prudent training practice or mechanism rather than direct trial support. Labeled as such wherever used.

Honesty constraints honored throughout: no fabricated citations; every reference in the bibliography carries a DOI or a stable URL; effect sizes are reported in the units the source used; and home training with household objects is described as a delivery format and an adjunct to good health behaviour, never as a treatment or cure for any disease. Two areas carry explicit "what the evidence does not support" notes (Section 6). Where a downstream claim cannot be tied to a reference in this list, it must be added here first or marked Practice.

A deliberate gap is named rather than hidden: most of the efficacy literature studies bodyweight, elastic bands, machines, or free weights. Direct trials of *named household objects as graded load* (water bottles, backpacks, towels, chairs) are sparse. We therefore anchor the household-object approach on a chain of established findings — equipment type is not a primary driver of resistance-training outcomes [R02], home delivery is non-inferior to centre delivery for the outcomes studied [R11], and even very small movement doses carry benefit [R12, R16, R17] — rather than on object-specific trials. This reasoning is stated openly in Section 3 and is the single most important caveat in the document.

---

## 2. The scientific premise: why furniture-and-objects training is defensible

Three independent lines of evidence converge to support a guided home modality that uses ordinary objects as equipment.

**2.1 The equipment is not the active ingredient — the training is.** The 2026 ACSM Position Stand on resistance training, an overview of reviews synthesising 137 systematic reviews and more than 30,000 participants, concluded that the largest and most reliable gains come from moving from *no* resistance training to *any* resistance training, and that several commonly emphasised variables — training to momentary failure, the specific equipment used (machines versus free weights), and complex periodization — did not consistently change outcomes for the average healthy adult [R02]. Programs are built by manipulating the FITT-VP variables (Frequency, Intensity, Time, Type, Volume, Pattern, Progression), and the earlier 2009 ACSM stand established workable ranges for general trainees: 2–3 sessions per week, 8–10 exercises across major muscle groups, 1–4 sets, ~8–20 repetitions, and progressive overload, with 10–15 repetitions advised for older and more frail people [R03]. The practical implication is direct: if equipment type is not a primary driver of adaptation, then a loaded backpack, two filled water bottles, or a sturdy chair can deliver a legitimate resistance stimulus provided load, range, and progression are managed. This is the keystone permission for the whole category.

**2.2 Home delivery works.** In coronary heart disease — a high-supervision context — home-based cardiac rehabilitation produced benefits similar to supervised centre-based rehabilitation for mortality, exercise capacity, and health-related quality of life across the trials studied [R11], while exercise-based cardiac rehabilitation as a whole reduced myocardial infarction risk and all-cause hospitalisation and likely produced a small reduction in all-cause mortality [R10]. The older-adult progressive-resistance literature likewise includes home-based and elastic-band programs among its 121 trials [R07]. If home delivery holds up in cardiac rehabilitation, it is defensible for general fitness and for lower-risk clinical populations — with the explicit boundary that the app is *not* cardiac rehabilitation (Section 7).

**2.3 Small doses count, which suits the home and the deconditioned user.** The 2020 WHO guidelines removed the old requirement that aerobic activity occur in bouts of at least 10 minutes, so short bouts accumulated through the day now count toward the targets [R01]. Wearable-device evidence from 25,241 non-exercisers found that a median of about 4.4 minutes per day of vigorous intermittent lifestyle physical activity (VILPA) — brief bursts embedded in daily life — was associated with a 26–30% lower all-cause and cancer mortality risk and a 32–34% lower cardiovascular mortality risk, in a near-linear dose–response, with effects in non-exercisers resembling those of structured vigorous activity in exercisers [R12]. Trials of structured "exercise snacks" (typically 1–5 minute bouts, 2–8 times per day, including bodyweight resistance and stair climbing) improved cardiorespiratory fitness with moderate certainty and were feasible and apparently safe across healthy adults, older adults, and people with obesity or type 2 diabetes [R16, R17]. For the most deconditioned users, this reframes the entry bar from "find 45 minutes" to "do three minutes by the kitchen counter," which is exactly what a furniture-anchored app can deliver.

---

## 3. Objects as load: the household-object taxonomy

The category's distinctive design problem is turning an unknown, uncalibrated object into a known training stimulus. The taxonomy below maps common objects to the movement role they serve. **All load figures are nominal and user-confirmed, never assumed.** Because a "litre of water ≈ 1 kg" is reliable but "a full backpack" is not, the app's load model is: (a) prefer objects the user can weigh or whose contents are countable (water = litres; books = count), (b) otherwise drive intensity by repetitions-in-reserve and rate of perceived exertion rather than by an assumed kilogram (Section 8), and (c) progress by changing leverage, range, tempo, and unilateral loading before chasing heavier objects.

| Object | Primary training role | Nominal load logic | Typical movements | Key safety note |
|---|---|---|---|---|
| Sturdy chair (no wheels, against a wall) | Support, target height, step platform | n/a (bodyweight) | Sit-to-stand, supported squat, incline push-up, step-up, balance hold | Confirm it cannot slide or tip; back to a wall |
| Wall | Isometric brace, push surface, balance aid | n/a (bodyweight) | Wall sit, wall push-up, standing balance | Clear floor; non-slip footing |
| Water bottles / jugs (sealed) | Adjustable external load | Volume → mass (1 L ≈ 1 kg); fill to titrate | Carries, rows, presses, curls, lateral raises | Check seal; start light; neutral wrist |
| Backpack (loaded with books/bottles) | Trunk-proximal load for squats/hinges/carries | Weigh on a scale if possible; else count contents | Goblet-style squat, hip hinge, loaded carry, step-up | Pack load high and tight; do not round the back |
| Bath/beach towel | Sliders, isometric "self-resistance", mobility strap | n/a (friction / own force) | Hamstring sliders, towel rows (self-isometric), shoulder mobility | On hard floor only for sliders |
| Tinned goods / filled bottles (small) | Light distal load, rehab-range | Count and weigh; small increments | Lateral raises, presses, balance perturbation | Small jumps only; protect the shoulder |
| Stairs / a single step | Aerobic "snack", power, calf and quad loading | Bodyweight × incline | Stair snacks, step-ups, calf raises | Rail within reach; one stair for beginners |
| Countertop / heavy table edge | High brace for supported standing work | n/a | Supported squat, standing balance, incline push-up | Must be immovable and weight-bearing |
| Broom / mop handle | Movement-pattern dowel, mobility, balance | n/a | Hinge grooving, overhead mobility, balance reach | Light; pattern practice, not load |

Design rule: every exercise in the library names at least one **default object**, at least one **regression object** (usually "support" or "lighter/none"), and at least one **progression lever** (heavier object, longer lever, slower tempo, or single-side). The figure/animation for each exercise must render the object in place (Section 10) so the user copies the *setup*, not only the *pose*.

---

## 4. Populations, screening, and the one-ladder model

The category serves four populations on a single progression ladder, gated by a screening step modelled on the PAR-Q+, the international standard for self-administered pre-participation screening and risk stratification [R14]. The PAR-Q+ logic — seven general questions; if all "no," self-clear for unrestricted activity; if any "yes," targeted follow-up; if follow-up flags remain, refer to a qualified professional or the ePARmed-X+ — maps cleanly onto a digital onboarding tree [R14]. The app implements the screen, never overrides a "see a professional" outcome, and re-screens when the user reports a new condition, symptom, pregnancy, injury, or a long lay-off.

**Tier ladder (every user can move up or drop down a rung at any time):**

1. **Seated / supported (entry).** All work done seated or holding a chair, counter, or wall. The safest start for the most deconditioned, for symptom days, and for the first session of anyone unsure. Aerobic dose can be met by VILPA-style movement breaks [R01, R12].
2. **Standing, supported-to-free.** Bodyweight patterns with a hand on support, progressing to unassisted, plus light external load (bottles). Builds standing tolerance, balance, and the squat/hinge/push/pull foundations.
3. **Loaded home strength.** Backpack- and bottle-loaded compound patterns with managed progression, balance and functional work retained.
4. **Conditioning / advanced.** Higher volume, circuits, stair and tempo work, unilateral and power-biased variations for fit users wanting a real challenge.

**Population notes layered on top of the ladder:**

- **Fragile / deconditioned / older.** Lead with seated and supported tiers. Crucially, the falls-prevention evidence shows that **balance and functional exercise is the active ingredient** — programs centred on balance and functional tasks cut the rate of falls by about 24% (high-certainty), and multi-component programs that add resistance by about 34% (moderate-certainty), whereas resistance training *alone* has uncertain effect on falls [R08]. Strength still matters for the underlying capacity: progressive resistance training in older adults reliably increases strength and improves everyday tasks such as walking, stair climbing, and rising from a chair [R07]. Design consequence: the fragile track must always pair strength with balance/functional work, not strength alone.
- **Overweight.** Use the same ladder, joint-sparing variations (chair/wall support, incline rather than floor push-ups, seated or supported squats early), and a **function-and-health framing, not a weight-loss framing** (rationale and guardrail in Sections 6 and 7). Physical-activity targets here follow the weight-management evidence at the population level [R04], but the app surfaces strength, stamina, and how-you-feel as the visible outcomes.
- **Chronically ill (stable, cleared).** Supported for stable, professionally cleared conditions where home exercise has an evidence base — type 2 diabetes [R05], hypertension [R06], knee osteoarthritis [R13], and cancer survivorship [R09] — always as an adjunct to medical care, never replacing it, and with the cardiac boundary in Section 7. Type 2 diabetes additionally benefits from breaking up sitting: the ADA recommends 3+ minutes of light activity (the examples given include leg extensions and overhead arm stretches — both furniture-free) every 30 minutes of prolonged sitting [R05].
- **Experienced / fit.** Tiers 3–4, where the constraint becomes progression and variety rather than safety. The honest message to this group: household objects cap absolute load, so beyond a point hypertrophy and maximal-strength progress slow; the value proposition is convenience, consistency, and conditioning, with progression via tempo, unilateral loading, range, and density (Section 6).

---

## 5. Movement-pattern model (the spine of the library)

Exercises are organised by fundamental movement pattern rather than by muscle, so the library stays small, teachable, and animatable, and so each session can be balanced. Each pattern lists an entry object and a progression direction.

- **Sit-to-stand / squat** — chair (entry) → supported bodyweight → backpack-loaded → unilateral. Trains the single most functional pattern; the 30-second sit-to-stand is also a usable home capacity check.
- **Hip hinge** — broom-handle groove (pattern) → bodyweight → backpack hinge → single-leg. Protects the back by teaching the pattern before loading it.
- **Push (horizontal/incline)** — wall push-up (entry) → counter → chair-incline → floor. Joint-friendly entry for overweight and deconditioned users.
- **Pull** — towel self-isometric / bottle rows → backpack rows → table rows (advanced). The hardest pattern to load at home; named as such honestly.
- **Carry / loaded gait** — bottle or backpack carries. High transfer to daily life; gentle on joints; scalable trivially by fill level.
- **Rotation / anti-rotation** — bottle or light-load trunk work. Trunk stability for daily tasks.
- **Balance / gait** — supported single-leg stance → tandem stand → reaching and stepping tasks. The falls-prevention core for fragile users [R08].
- **Aerobic "snacks"** — stairs, marching, sit-to-stand intervals. Delivers the accumulated aerobic dose [R01, R12, R16].

Every session template draws across patterns (e.g., a balanced 12–15 minute session = warm-up + squat + push + pull + carry + balance + cool-down), with population presets selecting tier, object defaults, and whether balance work is mandatory (it is, for the fragile track).

---

## 6. Benefits and limits, graded by evidence

Claims below are about the *components* this category delivers (resistance training, balance/functional work, aerobic movement, isometrics) applied at home with objects. Effect sizes are reported in source units. Each row cites the bibliography.

### 6.1 Muscle strength, mass, and physical performance — Strong [R02, R03, R07]
Progressive resistance training improves strength, hypertrophy, power, and physical function; the dominant determinant of benefit is doing it at all rather than the equipment or program complexity [R02]. In older adults specifically, it reliably increases strength and improves walking, stair climbing, and chair rises [R07].

### 6.2 Falls and balance in older adults — Strong (for balance/functional and multi-component programs) [R08]
Balance and functional exercise reduces the rate of falls by ~24% (high-certainty); multi-component programs (balance + functional + resistance) by ~34% (moderate-certainty). Effect is larger when programs are professionally guided. **Resistance training alone has uncertain effect on falls** — a key limit that shapes the fragile track [R08].

### 6.3 Resting blood pressure — Strong (isometrics notably effective) [R06]
A network meta-analysis of 270 RCTs (15,827 participants) found all exercise modes lowered resting blood pressure, with isometric exercise training producing the largest reductions (~8.2/4 mmHg), and the wall squat ranked the single most effective sub-mode for systolic blood pressure [R06]. The wall sit is, conveniently, the most furniture-native exercise there is. **Caveat:** these are *resting* reductions from regular training; high-intensity static holds and breath-holding (Valsalva) can transiently raise blood pressure during the effort, which matters for uncontrolled hypertension and cardiac disease (Section 7).

### 6.4 Glycaemic control and type 2 diabetes — Strong (as adjunct) [R05]
Regular activity improves blood-glucose control, reduces cardiovascular risk factors, and contributes to weight management in type 2 diabetes; breaking up prolonged sitting every 30 minutes with brief light activity improves glucose handling [R05]. Adjunct to medical care, not a replacement.

### 6.5 Knee osteoarthritis — Moderate [R13]
Land-based therapeutic exercise produces a moderate immediate reduction in knee pain (≈12 points/100) and improvement in physical function (≈10 points/100), sustained for 2–6 months after formal treatment ends; no serious adverse events were reported, with events limited to transient increases in joint pain [R13]. Favour supported, controlled-range, joint-sparing variations.

### 6.6 Cancer survivorship — Strong (for QoL, fatigue, function) [R09]
For people living with and beyond cancer, exercise is generally safe (with medical clearance advised in specific situations) and improves anxiety, depressive symptoms, fatigue, physical function, and quality of life; survivors are advised to avoid inactivity [R09]. Adjunct to oncology care.

### 6.7 Cardiovascular outcomes context — Strong (in supervised CR), boundary-flagged [R10, R11]
Exercise-based cardiac rehabilitation reduces myocardial-infarction risk and all-cause hospitalisation and likely yields a small reduction in all-cause mortality, with home delivery non-inferior to centre delivery for studied outcomes [R10, R11]. This is cited to justify home delivery in general and to set the boundary in Section 7, not to position the app as cardiac rehabilitation.

### 6.8 All-cause / cardiovascular / cancer mortality from accumulated movement — Strong (observational) [R12]
In non-exercisers, ~4.4 min/day of vigorous intermittent lifestyle activity was associated with 26–30% lower all-cause and cancer mortality and 32–34% lower cardiovascular mortality, near-linearly [R12]. Observational and so not causal, but robust to sensitivity analyses and directly relevant to the most sedentary users.

### 6.9 Cardiorespiratory fitness from short home bouts — Moderate [R16, R17]
Structured exercise snacks improve cardiorespiratory fitness (moderate certainty) and are feasible and apparently safe across mixed populations including older adults and people with obesity or type 2 diabetes [R16, R17]. Effects on muscular endurance and broader outcomes are less certain [R16].

---

## 7. What the evidence does not support (explicit honesty)

- **This is not a weight-loss program, and must not be framed as one.** Physical activity's role in weight is mainly to prevent weight gain and weight regain; exercise alone typically produces modest weight change, and meaningful loss requires combined lifestyle change [R04]. Health and functional benefits accrue largely independent of the number on a scale. The app therefore measures strength, stamina, balance, and adherence — not weight — and the overweight track is framed around function and health. The app does **not** prescribe calorie targets, energy deficits, or weight goals.
- **This is not cardiac rehabilitation, disease treatment, or physiotherapy.** Home exercise is non-inferior to centre-based *cardiac rehabilitation* for the outcomes studied [R11], but supervised, risk-stratified rehabilitation remains standard for higher-risk cardiac disease and major comorbidity [R10]. Users with cardiac disease, recent cardiac events, uncontrolled symptoms, or a "see a professional" screening outcome are routed to clinical care, not enrolled in a tier.
- **Objects are not calibrated weights.** The category cannot tell a user their exact load from a "full backpack." Intensity is governed by perceived effort and repetitions-in-reserve, with weighable/countable objects preferred (Section 3, Section 8).
- **Isometrics are not universally benign.** The resting-blood-pressure benefit is strong [R06], but high-intensity static holds with breath-holding can transiently spike blood pressure; users with uncontrolled hypertension or cardiac disease get the wall-sit only after clearance, with breathing cues and conservative holds.
- **Resistance training alone is not a falls program.** Falls reduction requires balance and functional content; strength alone is uncertain for falls [R08].
- **Household-object training has thin object-specific trial evidence.** The approach is justified by transfer from equipment-agnostic, home-delivery, and minimal-dose findings (Sections 2–3), not by trials of named objects. Stated plainly so downstream copy never over-claims.

---

## 8. Intensity and autoregulation (object-agnostic dosing)

Because objects are uncalibrated, the category dose-controls by perception and reserve rather than by load:
- **Rate of perceived exertion (RPE)** on the Borg scale is the primary intensity signal, validated as a complement to physiological measures and well suited to self-regulation [R15]. The app uses a simple 0–10 effort prompt with plain anchors ("could talk easily" → "could not say more than a word").
- **Repetitions in reserve (RIR)** sets resistance intensity: beginners and the fragile train at ~3–4 RIR (stop well short of failure), general users at ~2–3 RIR; training to failure is explicitly *not* required for benefit [R02].
- **The talk test** gates aerobic snacks: able to speak in full sentences = light; able to speak only short phrases = the vigorous band associated with the VILPA mortality findings [R12].
- **MET context** for session labelling: seated/light home movement sits in the light band, standing compound and loaded work in the moderate band, and stair/tempo snacks in the vigorous band, consistent with how the WHO targets are accumulated [R01].
- **Progression** is capped and patient: change one variable at a time (reps → range → tempo → unilateral → heavier object), hold technique quality as the gate, and deload on symptom days by dropping a tier.

---

## 9. Safety framework

**Pre-start:** PAR-Q+-style screen [R14]; clear, weight-bearing, immovable support confirmed; non-slip footing; water to hand; a chair within reach for every standing session (entry tiers).

**Object-specific:** sealed/secured loads; load packed high and tight in backpacks; neutral spine cues for all hinges and loaded squats; small load increments; sliders on hard floors only; no wheeled chairs; counters and tables must be immovable.

**Stop-and-seek-care red flags (surfaced every session):** chest pain or pressure; severe or unusual breathlessness; dizziness, light-headedness, or faintness; palpitations; new or worsening joint pain; sudden weakness or numbness. These mirror the conservative red-flag set already used in the Tai Chi knowledge base and the apparently-healthy-adult assumption in the Coach module.

**Population guards:** mandatory balance content in the fragile track [R08]; breathing cues and post-clearance gating for isometrics in hypertension/cardiac contexts [R06]; cardiac/high-risk routing to clinical care [R10]; adjunct-not-treatment language for all clinical conditions [R05, R09, R13]; function-not-weight framing and no diet/calorie prescriptions for the overweight track [R04]; and a wellbeing guard that routes any user signalling disordered eating or compulsive-exercise patterns away from intensity/volume escalation and toward gentler, health-framed content and professional resources.

Adverse-event context from the cited literature is reassuring when programs are scaled appropriately: serious events were rare across the resistance, falls, osteoarthritis, and cancer-survivor trials, with most reported events being transient muscle or joint soreness [R07, R08, R09, R13].

---

## 10. Feature set (what to build)

Features are grouped and prioritised. Priority reflects evidence-anchoring strength and user impact; it is an input to ICE scoring, not a final backlog.

**Tier A — foundation (build first):**
1. **Screening onboarding tree** — PAR-Q+-modelled triage that assigns a starting tier, applies population presets, and enforces "see a professional" outcomes without override [R14].
2. **Object library** — the Section 3 taxonomy as data: each object with role, nominal-load logic, default movements, and a safety note; user can mark which objects they own to filter sessions.
3. **Movement-pattern exercise library** — exercises tagged by pattern (Section 5), each with default/regression/progression objects, tier, cues, red-flag links, and a figure/animation spec.
4. **Guided session player** — assembles a balanced cross-pattern session for the user's tier and owned objects, with per-exercise animation, tempo pacing, cueing, and RPE/RIR check-ins (Section 8).
5. **Animated form-model engine** — the signature UI feature (Section 11); tempo-synced anatomical figures with the object in place, front/side/mirror views, and a reduced-motion fallback.

**Tier B — guidance and adherence:**
6. **Autoregulation engine** — RPE/RIR/talk-test driven intensity and one-variable-at-a-time progression with symptom-day deloads [R02, R15].
7. **Balance-and-falls module** — mandatory in the fragile track; balance/functional tasks with support regressions [R08].
8. **Exercise-snack mode** — 3–5 minute kitchen-counter/stair sessions and a "break up your sitting" prompt for diabetes/sedentary users [R01, R05, R12, R16].
9. **Home capacity checks** — opt-in 30-second sit-to-stand and timed standing-balance checks to personalise and to show progress without a scale.
10. **Progress surfacing** — strength/stamina/balance/adherence trends (explicitly not weight) in the overweight and general tracks [R04].

**Tier C — depth and reach:**
11. **Condition adjunct packs** — cleared, adjunct-framed presets for diabetes, hypertension (with isometric/Valsalva guards), knee OA, and cancer survivorship [R05, R06, R09, R13].
12. **Object substitution suggester** — "no backpack? use two filled bottles in a tote" mappings, all from the object library.
13. **Source transparency panel** — every benefit claim links to its bibliography entry, consistent with the existing Coach/Tai Chi pattern.
14. **Offline media packaging** — figures/animations as bundled SVG (no network), consistent with the app's local-first architecture.

---

## 11. UI and the animated form-model engine (first-class UX)

The category's defining interaction is *watching the right movement and copying it*, with the object visibly in place. The recommended approach is a lightweight, offline, dependency-free **SVG form-model engine** rather than video, for four reasons that match Fenix5Sync's constraints: it ships inside the bundle with no streaming, it themes with the existing CSS variables, it scales crisply on any screen, and a single parametric model can render the whole library by swapping pose keyframes and an object glyph.

**11.1 The model.** A figure is a small set of named joints (head, shoulders, elbows, wrists, hips, knees, ankles) as 2-D coordinates. A *movement* is a short list of **keyframe poses** (e.g., sit-to-stand: `seated → lean → mid-rise → stand`). The engine interpolates joint positions between keyframes; the body is drawn as rounded "bone" segments plus a head, deliberately a clean silhouette rather than anatomical realism, so it reads instantly and never looks uncanny.

**11.2 Tempo as the animation clock.** The interpolation speed is driven by the exercise's prescribed tempo (e.g., 3 s down / 1 s up / brief hold). The animation therefore doubles as the pacer/metronome — the user moves with the figure — and a subtle phase indicator (down / hold / up) plus optional audio ticks at phase changes reinforce the rhythm. This turns a demonstration into a guided rep.

**11.3 The object is part of the figure.** Each exercise references an object glyph (chair, wall band, water bottles, backpack, towel, stairs) drawn at an anchor point that tracks the relevant joint (bottles in the hands, backpack on the trunk, chair under the hips). Users copy the setup, not just the body — the most common home-form error is wrong object placement, so the object is never optional in the figure.

**11.4 Views and cues.** Front / side / mirror toggles (side is the default for hinge and squat patterns where back angle matters); 2–4 short cue lines synced to phases; a live RPE/RIR prompt at set end; and a persistent, quiet red-flag affordance.

**11.5 Accessibility (non-negotiable for this audience).** Respect `prefers-reduced-motion` with a static, labelled key-pose diagram (start/mid/end) and a numbered cue list as a complete substitute for animation. High-contrast strokes on the dark surface, large tap targets, optional larger figure scale, captions for any audio, and keyboard-operable controls. The fragile and older audience is the design centre of gravity here, not an afterthought.

**11.6 Build notes (matches the existing stack).** Implement as a small vanilla-JS module beside the existing `web/js/` views (e.g., `formModel.js`), consuming the same content JSON, rendering inline SVG, and theming from the existing tokens (`--accent`, `--surface`, `--text`, `--ease`, the `--sp-*` scale). No framework, no animation library, no network — consistent with the app's offline, low-dependency design. A working reference implementation ships with this deliverable at `web/prototype/form-model.html` (two exemplar exercises — a tempo-paced **chair sit-to-stand** and a **wall sit** with a hold timer — including the reduced-motion fallback) so the engine can be vibe-coded outward exercise by exercise.

---

## 12. Benefits-by-population summary table

| Population | Lead content | Strongest evidence anchors | Primary visible outcome | Hard guardrail |
|---|---|---|---|---|
| Fragile / deconditioned / older | Seated→supported tiers; **balance + functional + strength** | Falls [R08]; PRT in older adults [R07]; small-dose movement [R01, R12] | Balance, sit-to-stand capacity, confidence | Balance content mandatory; chair always present |
| Overweight | Full ladder, joint-sparing, **function framing** | Weight-management PA [R04]; fitness from snacks [R16] | Strength, stamina, how-you-feel | No weight/calorie targets; measure function not weight |
| Chronically ill (stable, cleared) | Adjunct condition packs | T2D [R05]; BP/isometrics [R06]; knee OA [R13]; cancer [R09] | Condition-relevant function & wellbeing | Adjunct-not-treatment; cardiac/high-risk routed out |
| Experienced / fit | Loaded/conditioning tiers; tempo & unilateral progression | RT prescription [R02, R03] | Conditioning, consistency | Honest absolute-load ceiling |

---

## 13. Bibliography (source list)

- **[R01]** Bull FC, Al-Ansari SS, Biddle S, et al. *World Health Organization 2020 guidelines on physical activity and sedentary behaviour.* Br J Sports Med. 2020;54(24):1451–1462. https://pubmed.ncbi.nlm.nih.gov/33239350/ — *guideline; grade: Strong.*
- **[R02]** American College of Sports Medicine. *Resistance Training Prescription for Muscle Function, Hypertrophy, and Physical Performance in Healthy Adults: An Overview of Reviews* (2026 Position Stand; 137 reviews, >30,000 participants). Med Sci Sports Exerc. 2026. https://pubmed.ncbi.nlm.nih.gov/41843416/ — *overview of reviews / position stand; grade: Strong.*
- **[R03]** American College of Sports Medicine. *Progression Models in Resistance Training for Healthy Adults* (Position Stand). Med Sci Sports Exerc. 2009;41(3):687–708. https://doi.org/10.1249/MSS.0b013e3181915670 — *position stand; grade: Strong.*
- **[R04]** Donnelly JE, Blair SN, Jakicic JM, Manore MM, Rankin JW, Smith BK. *ACSM Position Stand: Appropriate Physical Activity Intervention Strategies for Weight Loss and Prevention of Weight Regain for Adults.* Med Sci Sports Exerc. 2009;41(2):459–471. https://doi.org/10.1249/MSS.0b013e3181949333 — *position stand; grade: Strong.*
- **[R05]** Colberg SR, Sigal RJ, Yardley JE, et al. *Physical Activity/Exercise and Diabetes: A Position Statement of the American Diabetes Association.* Diabetes Care. 2016;39(11):2065–2079. https://doi.org/10.2337/dc16-1728 — *position statement; grade: Strong (adjunct).*
- **[R06]** Edwards JJ, Deenmamode AHP, Griffiths M, et al. *Exercise training and resting blood pressure: a large-scale pairwise and network meta-analysis of randomised controlled trials* (270 RCTs, 15,827 participants). Br J Sports Med. 2023;57(20):1317–1326. https://doi.org/10.1136/bjsports-2022-106503 — *network meta-analysis; grade: Strong.*
- **[R07]** Liu CJ, Latham NK. *Progressive resistance strength training for improving physical function in older adults* (121 RCTs, >6,700 participants). Cochrane Database Syst Rev. 2009;(3):CD002759. https://doi.org/10.1002/14651858.CD002759.pub2 — *Cochrane review; grade: Strong.*
- **[R08]** Sherrington C, Fairhall NJ, Wallbank GK, et al. *Exercise for preventing falls in older people living in the community* (59 studies, 12,981 participants). Cochrane Database Syst Rev. 2019;1(1):CD012424. https://doi.org/10.1002/14651858.CD012424.pub2 — *Cochrane review; grade: Strong (balance/functional & multi-component).*
- **[R09]** Campbell KL, Winters-Stone KM, Wiskemann J, et al. *Exercise Guidelines for Cancer Survivors: Consensus Statement from International Multidisciplinary Roundtable.* Med Sci Sports Exerc. 2019;51(11):2375–2390. https://doi.org/10.1249/MSS.0000000000002116 — *consensus statement; grade: Strong.*
- **[R10]** Dibben G, Faulkner J, Oldridge N, et al. *Exercise-based cardiac rehabilitation for coronary heart disease* (85 trials, 23,430 participants). Cochrane Database Syst Rev. 2021;11(11):CD001800. https://doi.org/10.1002/14651858.CD001800.pub4 — *Cochrane review; grade: Strong.*
- **[R11]** Anderson L, Sharp GA, Norton RJ, et al. *Home-based versus centre-based cardiac rehabilitation.* Cochrane Database Syst Rev. 2017;6(6):CD007130. https://doi.org/10.1002/14651858.CD007130.pub4 — *Cochrane review; grade: Moderate (non-inferiority for studied outcomes).*
- **[R12]** Stamatakis E, Ahmadi MN, Gill JMR, et al. *Association of wearable device-measured vigorous intermittent lifestyle physical activity with mortality* (UK Biobank, n=25,241 non-exercisers). Nat Med. 2022;28(12):2521–2529. https://doi.org/10.1038/s41591-022-02100-x — *prospective cohort; grade: Strong (observational).*
- **[R13]** Fransen M, McConnell S, Harmer AR, Van der Esch M, Simic M, Bennell KL. *Exercise for osteoarthritis of the knee: a Cochrane systematic review* (54 trials, ~5,300 participants). Cochrane Database Syst Rev. 2015;1:CD004376 / Br J Sports Med. 2015;49(24):1554–1557. https://doi.org/10.1002/14651858.CD004376.pub3 — *Cochrane review; grade: Moderate.*
- **[R14]** Warburton DER, Jamnik VK, Bredin SSD, Gledhill N (PAR-Q+ Collaboration). *The Physical Activity Readiness Questionnaire for Everyone (PAR-Q+) and Electronic Physical Activity Readiness Medical Examination (ePARmed-X+).* Health & Fitness Journal of Canada. 2011;4(2):3–23. https://hfjc.library.ubc.ca/index.php/HFJC/article/view/103 — *validated screening instrument; grade: standard of practice.*
- **[R15]** Borg GA. *Psychophysical bases of perceived exertion.* Med Sci Sports Exerc. 1982;14(5):377–381. https://pubmed.ncbi.nlm.nih.gov/7154893/ — *foundational methods; grade: established.*
- **[R16]** Singh B, Bennett H, Miatke A, et al. *Exercise Snacks as a Strategy to Interrupt Sedentary Behavior: A Systematic Review of Health Outcomes and Feasibility* (26 studies). Healthcare (Basel). 2025;13(24):3216. https://www.mdpi.com/2227-9032/13/24/3216 — *systematic review; grade: Moderate.*
- **[R17]** *Effects of Exercise Snacks on Cardiometabolic Health and Body Composition in Adults: A Systematic Review and Meta-Analysis.* 2025. https://pmc.ncbi.nlm.nih.gov/articles/PMC12354995/ — *systematic review & meta-analysis; grade: Moderate.*

Verification note (honesty-by-construction): each entry resolves to a PubMed record, DOI, or stable repository URL retrieved during the 22 June 2026 search pass. Where an author string or volume/page detail was not directly captured in this pass, the DOI/URL remains the authoritative locator and the field should be completed from the source before publication. Items [R02] (very recent, 2026) and [R11]/[R13] (Cochrane records with live updates) should be re-checked for the latest version string at publication time.

---

## 14. What this foundation feeds (next deliverables)

1. **Object library JSON** — the Section 3 taxonomy as structured data (role, load logic, movements, safety, ownership flag).
2. **Movement-pattern exercise library JSON** — per-exercise: pattern, tier, default/regression/progression objects, cues, red-flag links, and figure/animation keyframe spec.
3. **Session/program library** — population presets and balanced cross-pattern session templates, including exercise-snack micro-sessions.
4. **Screening tree spec** — PAR-Q+-modelled triage logic, tier assignment, and routing rules.
5. **Figure/animation production spec** — joint model, keyframe authoring format, object-glyph set, view/cue conventions, and the reduced-motion fallback contract (reference engine: `web/prototype/form-model.html`).
6. **Glossary & safety document** — plain-language terms, red flags, and the population guardrails consolidated for in-app surfacing.
7. **Personalization rules** — closed-form mapping from screening + capacity checks + RPE/RIR history to tier, object defaults, and progression, in the same deterministic, source-traceable style as the Coach module.

This document ships the evidence and taxonomy backbone those artifacts cite back to. Build order should follow the Tier A → B → C feature grouping in Section 10.
