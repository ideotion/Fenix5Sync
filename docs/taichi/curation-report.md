# Evidence-Based Tai Chi Curation Report
## Foundation deliverable for the Fenix5Sync guided-session knowledge base

Status: Deliverable 1 (curation report) and Deliverable 6 (benefits-by-condition table + bibliography) of the 11-part specification.
Scope of this document: the evidence and styles foundation that every downstream artifact (movement library, session library, rotation plan, video specs, personalization rules) must cite back to.
Date of evidence search: 21 June 2026. Reliability of cited findings is bounded by the publication dates listed in the bibliography.

This is a foundation pass, not the full knowledge base. The structured JSON deliverables (movement library, session/program library, rotation plan, video production spec, glossary, safety document) are built on top of this and are listed under "What this foundation feeds" at the end.

---

## 1. Method and search strategy

Databases and sources queried: PubMed / MEDLINE, the Cochrane Library (including CENTRAL records), peer-reviewed journal portals (NEJM, BMJ, JAMA Internal Medicine, Frontiers, SAGE, ScienceDirect), and governing-body / validated-program documentation (US National Council on Aging, US CDC fall-prevention listings, the Tai Chi for Health Institute, the Tai Ji Quan: Moving for Better Balance program). Searches were run in June 2026 using condition-specific terms (for example "Tai Chi falls meta-analysis", "Tai Chi blood pressure randomized", "Tai Chi knee osteoarthritis systematic review", "Tai Chi MET energy expenditure").

Evidence hierarchy applied (highest first): Cochrane reviews and meta-analyses, then randomized controlled trials, then clinical-guideline and validated public-health programs, then authoritative instructor and program documentation, then general sources.

Grading scale used in this report:
- Strong: consistent, statistically significant findings across multiple systematic reviews / meta-analyses or large, rigorous RCTs; effect direction robust.
- Moderate: a significant systematic review or meta-analysis exists, but with notable heterogeneity, modest study quality, a limited trial count, or no advantage over an active comparator.
- Limited: few, small, or low-quality trials; mixed results; or mainly indirect evidence.
- Traditional / Emerging: supported by instructor consensus or a plausible mechanism, without robust trial support. Labeled as such wherever used.

Honesty constraints honored throughout: no fabricated citations; every reference in the bibliography carries a DOI or a stable URL; effect sizes are reported in the units the source used; and Tai Chi is described as an adjunct activity, never as a treatment or cure for any disease. Where individual author strings were not captured during this search pass, the field is marked "[complete from source]" and the DOI/URL remains the authoritative locator.

A small number of author strings and the specific clinical-guideline endorsements for osteoarthritis (for example ACR/OARSI) were not directly retrieved in this pass and are flagged for verification rather than asserted.

---

## 2. Styles overview and recommendation for the target population

Major living styles and their relevance to overweight, older, or deconditioned beginners:

Yang. The most widely practiced and most studied style. Large, even, moderately-wide stances and slow continuous movement. The Simplified 24-form and the shorter 8-form derive from the Yang tradition and underpin most clinical trials. Suitable as the foundational standing target for users once balance and lower-limb tolerance are established. In one falls meta-analysis, Yang-style appeared more effective than Sun-style for fall reduction [R01]; this is balanced against tolerability and safety considerations below.

Sun. Higher, more upright stances, agile "follow-step" footwork, and an emphasis on smooth opening and closing of the body. The higher stance reduces knee loading and the follow-step trains balance continuously, which makes Sun-style the basis of the most widely deployed therapeutic program for arthritis and older adults [R13].

Chen. The oldest style, characterized by low stances, spiral "silk-reeling" movements, and bursts of explosive force (fa-jin). Demanding on the knees and balance. Not recommended for the primary population in this app.

Wu and Hao. Smaller-frame, more compact styles with less high-quality trial evidence in this population. Lower priority for an initial curation.

Recommendation, in tiers, for this app:

1. Entry and core (chair and supported, then foundational standing): Sun-style-based Tai Chi for Arthritis (TCA). Designed in 1997 by Dr Paul Lam with a team of tai chi and medical experts, built on Sun-style, taught as warm-up, Qigong breathing, a set of approximately 12 movements (a 6-movement core plus a 6-movement extension), and a wind-down. It is explicitly engineered to be safe and easy for people with arthritis and is recognized by the US CDC for fall prevention [R13]. The higher stance and slow steps make it the safest standing entry point for deconditioned users.

2. Falls-focused standing core: Tai Ji Quan: Moving for Better Balance (TJQMBB). Developed by Dr Fuzhong Li at the Oregon Research Institute, this is an 8-form core (derived from Simplified 24-form Tai Ji Quan) plus a subroutine of mini therapeutic movements. It is recognized by the US CDC, the Administration for Community Living, and the National Council on Aging as a highest-tier evidence-based falls-prevention program, and it carries the strongest single RCT in this space (see Section 4) [R02, R14]. Its 8-form structure with built-in practice variations maps cleanly onto an app's progressive level/length design.

3. Progression target for fitter users: Simplified Yang 24-form, for longer and more demanding standing flows.

4. Always-available regression: seated / chair adaptations of the above movements, for the most deconditioned users or for symptom days.

Rationale summary: lead with Sun-style TCA for safety and tolerability, use TJQMBB's 8-form core as the balance-and-falls engine with the best trial support, and treat Yang 24-form as the aspirational longer-form. This tiering lets a single user move from chair to advanced flows without changing app or method.

---

## 3. Intensity profile (for session design and the intensity_met field)

Tai Chi is a low-to-moderate intensity activity. Measured energy cost places seated and gentle forms in the light-intensity band and standing simplified forms at the lower edge of the moderate band.

> Figure (pending asset): intensity ladder showing Tai Chi forms positioned against sedentary, light, moderate, and vigorous MET bands.

Verified anchors:
- Seated / chair Tai Chi: approximately 2.0 to 2.8 METs (light intensity) in measured older adults [R12].
- Standing Simplified 24-form: approximately 3 METs (lower moderate intensity) in published compendium measurement [R11].
- Walking carries a higher metabolic cost than most Tai Chi at matched duration, so Tai Chi should be positioned as a balance/mobility and conditioning modality rather than a primary calorie-burning one [see Section 5].

Practical consequence for the app: the standard low-to-moderate range (roughly 1.5 to 4 METs) used in the specification is consistent with measured data. Session intensity should be encoded per level: chair sessions near 2 METs, supported standing 2 to 2.5 METs, foundational standing 2.5 to 3 METs, advanced flows up to roughly 3 to 4 METs with added repetitions and lower stances. Optional heart-rate logging (if a strap is present) and a perceived-exertion (RPE) prompt are the appropriate in-app intensity signals.

---

## 4. Health benefits, graded by evidence

> Figure (pending asset): ordinal chart grading Tai Chi benefits by strength of evidence, from falls reduction (strong) to weight loss (limited). Bar length is ordinal (strength of evidence), not effect size; the outcomes use different units and cannot be compared on one numeric axis.

### 4.1 Falls reduction and balance — Strong [R01, R02]
Across systematic reviews and meta-analyses, Tai Chi reduces the chance of falling and the rate of falls in older adults. A meta-analysis of 18 trials (3,824 participants) found roughly a fifth fewer people falling at least once and a substantially lower fall rate, with the effect strengthening at higher practice frequency [R01]. The strongest single trial is the TJQMBB randomized clinical trial in 670 community-dwelling adults aged 70 and older at high risk of falling: twice-weekly practice for 24 weeks reduced falls markedly versus a stretching control and outperformed a multimodal exercise program [R02]. This is the best-supported benefit and the natural headline for the app's older-adult audience.

### 4.2 Balance, mobility, and lower-limb function — Strong to Moderate [R01, R02]
Functional measures used in trials (such as timed up-and-go and standing-balance tests) improve consistently, and fear of falling declines. These gains are the mechanism underlying the falls effect and are directly relevant to deconditioned users regaining everyday mobility.

### 4.3 Quality of life (physical component) — Strong to Moderate [R04, R06]
Improvements in the physical component of quality-of-life measures appear repeatedly across conditions (osteoarthritis, fibromyalgia, and others). This is one of the more reliably reproduced benefits.

### 4.4 Fibromyalgia — Strong to Moderate [R06, R07]
Two rigorous randomized trials support Tai Chi for fibromyalgia. A single-blind RCT of Yang-style Tai Chi showed clinically meaningful improvement in the Fibromyalgia Impact Questionnaire that was maintained at 24 weeks [R06]. A larger 52-week comparative-effectiveness RCT (226 adults) found Tai Chi at least as effective as aerobic exercise, the current core standard, with longer programs tending to do better [R07]. No serious adverse events were reported.

### 4.5 Knee osteoarthritis — Moderate [R04]
Systematic review and meta-analysis evidence shows short-term improvement in pain, stiffness, and physical function (for example pain standardized mean difference around minus 0.69 and physical function around minus 0.92), with low-to-moderate study quality and no reported serious adverse events [R04]. Tai Chi is appropriately offered as an adjunct for symptom management, with the higher-stance Sun-style preferred to limit knee loading. Note: specific clinical-guideline endorsements (for example ACR/OARSI) are commonly cited in this area but were not directly verified in this pass and should be confirmed before being stated in user-facing copy.

### 4.6 Blood pressure — Moderate [R03]
A meta-analysis of 24 RCTs found Tai Chi lowered systolic blood pressure by approximately 6 mmHg and diastolic by approximately 4 mmHg compared with inactivity, with no significant advantage over other aerobic exercise [R03]. The reduction is real but modest, and Tai Chi should be framed as a supportive lifestyle activity for blood-pressure management, not a substitute for prescribed treatment.

### 4.7 COPD (exercise capacity and respiratory quality of life) — Moderate [R05]
In a meta-analysis of 23 studies (1,663 participants), Tai Chi improved six-minute walking distance by approximately 41 metres (exceeding the usual minimal clinically important difference) and improved respiratory quality-of-life scores [R05]. Quality of included evidence is variable. Relevant only for users who flag COPD; not a core target benefit.

### 4.8 Depression, anxiety, and mood — Moderate [R09]
A systematic review and meta-analysis reported reductions in stress, anxiety, and depressive symptoms and improved mood (effect sizes roughly 0.5 to 0.66), across healthy participants and people with chronic conditions, though with heterogeneity and modest study quality [R09]. Reasonable to present as a likely wellbeing benefit, stated without overclaiming.

### 4.9 Cognition — Moderate [R10]
Meta-analytic evidence indicates benefits for executive function, and for global cognition in older adults with mild cognitive impairment, with longer cumulative practice associated with larger effects [R10]. Trial quality is modest. Present cautiously as an emerging-to-moderate benefit.

### 4.10 Type 2 diabetes (glycaemic markers) — Moderate to Limited [R08]
Meta-analysis shows reductions in fasting glucose and in HbA1c of roughly 0.5 to 0.7 percentage points versus controls, with high heterogeneity, predominantly Chinese trials, and limited or no advantage over aerobic exercise for several markers [R08]. Appropriate as an adjunct to standard diabetes care, explicitly not a glucose-lowering treatment.

### 4.11 Sleep and fatigue — Limited
Some trials report improvements, but findings are mixed and this domain was not the subject of a dedicated search in this pass. Treat as Emerging until a focused review is added; do not make sleep claims in user-facing copy yet.

### 4.12 Weight loss as a standalone outcome — Limited
This matters for an overweight target population, so it is stated plainly. Tai Chi's energy cost is low (Section 3), and some trials found body-mass index unchanged after Tai Chi. Tai Chi can support weight management indirectly (sustainable low-impact activity, high adherence, stress reduction, and as a gateway to more activity), but it is not an effective standalone weight-loss intervention and should not be marketed as one. Pair it with the app's endurance tracking and, where relevant, professional dietary guidance.

---

## 5. What the evidence does not support (explicit honesty)

- Tai Chi does not cure or treat any disease; benefits are adjunctive.
- Tai Chi is not a primary weight-loss method (low MET cost; BMI often unchanged).
- For blood pressure and several diabetes markers, Tai Chi is not superior to ordinary aerobic exercise; its advantages are accessibility, low impact, balance training, and adherence.
- Several benefits (cognition, mood, diabetes) rest on heterogeneous, modest-quality trials and should be communicated with that uncertainty intact.
- Sleep benefit is not yet substantiated in this curation.

---

## 6. Benefits-by-condition table

| Condition / outcome | Direction and magnitude (source units) | Evidence grade | Ref |
|---|---|---|---|
| Falls (fallers; rate) | ~20% fewer fallers (RR 0.80); ~30% lower fall rate; TJQMBB RCT large reduction vs control | Strong | R01, R02 |
| Balance / mobility / fear of falling | Consistent functional gains (TUG, balance scales); reduced fear of falling | Strong–Moderate | R01, R02 |
| Quality of life (physical) | Repeated improvement across conditions | Strong–Moderate | R04, R06 |
| Fibromyalgia (FIQ, pain, QoL) | Clinically meaningful FIQ improvement; >= aerobic exercise at 24–52 weeks | Strong–Moderate | R06, R07 |
| Knee osteoarthritis (pain, function, stiffness) | Short-term improvement (pain SMD ~ -0.69; function ~ -0.92) | Moderate | R04 |
| Blood pressure | SBP ~ -6 mmHg, DBP ~ -4 mmHg vs inactivity; not > other aerobic exercise | Moderate | R03 |
| COPD (exercise capacity, QoL) | 6MWD ~ +41 m; respiratory QoL improved | Moderate | R05 |
| Depression / anxiety / mood | Symptom reduction (ES ~0.5–0.66); heterogeneous | Moderate | R09 |
| Cognition (executive; global in MCI) | Significant; larger with longer practice; modest quality | Moderate | R10 |
| Type 2 diabetes (FBG, HbA1c) | HbA1c ~ -0.5 to -0.7 points; high heterogeneity | Moderate–Limited | R08 |
| Sleep / fatigue | Mixed; not reviewed in depth here | Limited / Emerging | — |
| Weight loss (standalone) | Low MET; BMI often unchanged | Limited | R11, R12 |

---

## 7. Safety summary (pointer)

The full safety and contraindications document and medical disclaimer are Deliverable 7. In brief, and consistent with this evidence base: trials across these conditions reported few or no serious adverse events, which supports Tai Chi's strong safety profile when taught and scaled appropriately. The app must still ship a clear medical disclaimer (not medical advice; recommend clinician clearance and PAR-Q+ screening for older or comorbid users), a per-session safety setup (stable chair within reach, clear space, footwear, hydration), explicit stop-and-seek-care red flags (chest pain, severe breathlessness, dizziness/faintness, new or worsening joint pain), and the higher-stance Sun-style default to protect knees and balance. The instructor-review quality gate for all generated videos (Deliverable 5/8) is non-negotiable, because teaching incorrect movement to this population is itself a safety risk.

---

## 8. Bibliography (Deliverable 6 source list)

All entries carry a verified DOI or stable URL. Author strings are filled where captured in this search pass; entries marked "[complete from source]" should have author lists confirmed from the locator at ingestion. Evidence grade reflects this report's use of the source.

| ref_id | authors | year | title (short) | source | doi_or_url | type | evidence_grade |
|---|---|---|---|---|---|---|---|
| R01 | Huang et al. | 2017 | Tai Chi for preventing falls in older adults (SR & meta-analysis; 18 trials, 3,824) | systematic review / meta-analysis | https://pubmed.ncbi.nlm.nih.gov/28167744/ | meta-analysis | Strong |
| R02 | Li F, Harmer P, et al. | 2018 | Therapeutic Tai Ji Quan vs multimodal exercise to prevent falls (RCT, n=670) | JAMA Internal Medicine | https://pubmed.ncbi.nlm.nih.gov/30208396/ | RCT | Strong |
| R03 | Dong X, Ding M, Yi X | 2020 | Meta-analysis of RCTs: effects of Tai Chi on blood pressure (24 trials) | Evidence-Based Complementary and Alternative Medicine | https://doi.org/10.1155/2020/8503047 | meta-analysis | Moderate |
| R04 | Hu L, Wang Y, et al. | 2021 | Tai Chi for physical and mental health in knee osteoarthritis (SR & meta-analysis) | Clinical Rehabilitation | https://doi.org/10.1177/0269215520954343 | meta-analysis | Moderate |
| R05 | Liu et al. | 2021 | Tai Chi for pulmonary rehabilitation in COPD (SR & meta-analysis; 23 studies) | Annals of Palliative Medicine | https://pubmed.ncbi.nlm.nih.gov/33894710/ | meta-analysis | Moderate |
| R06 | Wang C, Schmid CH, Rones R, et al. | 2010 | A randomized trial of Tai Chi for fibromyalgia | New England Journal of Medicine | https://doi.org/10.1056/NEJMoa0912611 | RCT | Moderate |
| R07 | Wang C, Schmid CH, Fielding RA, et al. | 2018 | Tai Chi versus aerobic exercise for fibromyalgia (RCT, n=226, 52 wk) | BMJ | https://doi.org/10.1136/bmj.k851 | RCT | Strong |
| R08 | Sun Y, Li Q, Xue W | 2025 | Tai Chi and glycemic control in type 2 diabetes (meta-analysis of RCTs) | Frontiers in Endocrinology | https://doi.org/10.3389/fendo.2025.1605253 | meta-analysis | Moderate |
| R09 | Wang C, Bannuru R, Ramel J, Kupelnick B, Scott T, Schmid CH | 2010 | Tai Chi on psychological well-being (SR & meta-analysis; 40 studies) | BMC Complementary and Alternative Medicine | https://doi.org/10.1186/1472-6882-10-23 | meta-analysis | Moderate |
| R10 | Wang WT, Wang H | 2025 | Tai Chi Chuan and cognitive function in older adults with MCI (SR & meta-analysis) | Frontiers in Physiology | https://doi.org/10.3389/fphys.2025.1556622 | meta-analysis | Moderate |
| R11 | [complete from source] | 2022 | Chinese Compilation of Physical Activities (24-form simplified Tai Chi ~3 METs) | Journal of Sport and Health Science | https://www.sciencedirect.com/science/article/pii/S2666337622000403 | measurement / compendium | n/a (intensity) |
| R12 | [complete from source] | 2023 | Energy costs of chair sitting and standing video exercises in older adults (chair Tai Chi 2.0–2.8 METs) | measurement study (PubMed-indexed) | https://pubmed.ncbi.nlm.nih.gov/37649672/ | measurement | n/a (intensity) |
| R13 | Lam P / Tai Chi for Health Institute | 1997– | Tai Chi for Arthritis (Sun-style; ~12 movements; CDC-recognized for fall prevention) | Tai Chi for Health Institute / US NCOA | https://www.ncoa.org/article/evidence-based-program-tai-chi-for-arthritis-and-falls-prevention/ | validated program documentation | Moderate (program) |
| R14 | Li F / Oregon Research Institute | 2018– | Tai Ji Quan: Moving for Better Balance (8-form core; CDC highest-tier falls program) | US NCOA / program documentation | https://www.ncoa.org/article/evidence-based-program-tai-ji-quan-moving-for-better-balance/ | validated program documentation | Strong (program + R02) |

---

## 9. What this foundation feeds (next deliverables)

This report fixes the decisions that the rest of the build depends on:

- Movement library (JSON, Deliverable 2): each posture's citations field draws ref_ids from Section 8; the recommended source forms are the TCA / Sun set and the TJQMBB 8-form core, with chair regressions. Pinyin and Chinese characters for each posture will be verified at build time (Glossary, Deliverable 8).
- Session/program library (JSON, Deliverable 3): the intensity_met field uses Section 3 ranges per level; the goal and citations fields map to the graded benefits in Sections 4 and 6.
- Rotation plan (JSON, Deliverable 4): full-body coverage will be proven against movement-pattern categories (weight transfer, single-leg balance, spinal rotation, lower-limb loading, shoulder/arm mobility, breathing/Qigong).
- Video production spec (JSON + Markdown, Deliverable 5): biomechanical reference values come from the per-movement library; the instructor-review gate from Section 7.
- Safety and contraindications + medical disclaimer (Deliverable 7): expands Section 7.
- Personalization/onboarding rules (Section 9 of the spec): deterministic mapping of age, BMI/weight status, mobility, balance confidence (for example an ABC-scale-style screen), seated-versus-standing preference, available minutes, and comorbidity flags to starting level/length and rotation.

Recommended next step: build the movement library JSON for the chair and supported levels first (the safest entry tier and the one this population starts in), each entry fully populated with biomechanics, breathing, errors, alignment checkpoints, contraindications, regressions/progressions, and citations from Section 8, with verified Pinyin/Chinese.
