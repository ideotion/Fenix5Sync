# Evidence-Based Training-Program Knowledge Base — Fenix5Sync Coaching Assistant

Phase 0 deliverable: verified citation backbone, schemas, one fully worked reference program, deterministic personalization ruleset, sourced normative tables, and a build roadmap for the remaining goal × sport matrix.

Author context: prepared for the Fenix5Sync project (local-first, offline Garmin analytics). All content is designed to ship as static bundled data plus deterministic rules — no runtime machine learning, no network calls at advice time.

> Note: this Markdown is the human-readable synthesis / audit trail. The companion
> machine-readable artefacts (bibliography.json, schema.json, normative_data.json,
> personalization_ruleset.json, program_run_marathon_intermediate_16wk.json) are the
> authoritative deliverables and are ingested separately. The structured subset that
> the app currently renders lives in `web/content/coach/overview.json`.

---

## 1. Scope and why this is staged

The source specification sets one non-negotiable rule: no fabricated citations. Every physiological claim must trace to a real source with a resolvable DOI or URL, and every recommendation must carry an evidence grade. Honouring that rule means the work cannot be a single-pass dump of one hundred plus program templates, because a credible matrix of that size cannot be citation-checked in one sitting without inventing references.

This Phase 0 therefore delivers the load-bearing foundation that everything else snaps onto: a verified bibliography (each entry flagged web-verified or pending-DOI-confirmation), a JSON Schema constraining every template/normative row/rule to carry sources and grades, one complete schema-valid reference program (intermediate marathon, 16 weeks), a deterministic personalization ruleset keyed to the exact app metric field names, sourced normative tables, and a coverage tracker / per-sport build order.

The remaining matrix cells (other running distances, cycling disciplines, cross-sport goals, muscle-gain blocks) are enumerated in the roadmap and generated sport-block by sport-block against this same verified backbone.

---

## 2. Method and evidence grading

Sources were selected to cover the physiological pillars the app must reason about: intensity distribution, threshold and heart-rate modelling, periodization and tapering, concurrent strength training, resistance-training dose, protein and fuelling, workload-injury modelling, and energy availability. Primary preference: meta-analyses, position stands, large cohort studies.

Evidence grades: **Strong** (consistent meta-analytic/multi-RCT), **Moderate** (supported, with heterogeneity / smaller samples / population-specific), **Limited** (sparse, indirect, contested), **Emerging** (early/debated), **Practice** (a coaching/textbook convention in standard use, not anchored to one high-quality trial — exists so conventional zone boundaries and heuristics can be included without a fabricated citation).

The verification convention (honesty by construction): each bibliography entry carries `web_verified_2026-06` (DOI/identifier confirmed by search this build) or `domain_knowledge_UNVERIFIED` (a real, well-known source whose exact DOI/edition the implementer should confirm before shipping — flagged, not hidden).

---

## 3. Worked reference program: intermediate marathon, 16 weeks

`program_run_marathon_intermediate_16wk.json` encodes a pyramidal intensity distribution of roughly 80% easy / 15% threshold / 5% hard, matching elite and sub-elite distance runners [ref_seiler2010] [ref_haugen2022]. Structure: four mesocycles — Base (5 wk), Build (4), Peak (4), Taper (3) — on a 3:1 loading pattern with a deload every fourth week.

- **Periodization & weekly load.** Volume rises from an entry level anchored to recent training, progressing at a capped rate with scheduled deloads, peaking before the taper (representative athlete peaks near 70 km/week with a longest run of 34 km in the peak block). *(Figure pending asset.)*
- **Intensity distribution.** The plan keeps the majority of running easy, with a controlled threshold fraction and a small hard fraction that grows modestly in the peak block; the app stores pyramidal, polarized and threshold models so a plan can shift emphasis by block [ref_seiler2010] [ref_rosenblat2019]. *(Figure pending asset.)*
- **Concurrent strength.** Two short strength sessions/week through Base and Build because heavy and explosive resistance training improves running economy and maximal strength without harming distance performance [ref_ronnestad2014] [ref_beattie2014] [ref_berryman2018]. Interference managed: separated from quality runs by ≥6 h where possible, kept heavy and low-rep rather than fatiguing, and tapered out before the race.
- **Taper.** Final two weeks cut volume ~50% while maintaining intensity and frequency, following the meta-analytic optimum [ref_bosquet2007].
- **Entry gate.** Expects a recent average of ≥35 km/week or CTL ≥40; a true beginner is routed to a base-building plan instead.

Each microcycle session in the JSON carries its own citation list and personalization links binding its targets to the athlete's metrics.

---

## 4. Deterministic personalization

`personalization_ruleset.json` is twelve closed-form rules. None requires a model at runtime; each takes named app metrics in and returns concrete targets out, with a fallback when an input is missing. The field names consumed are the app's own: `max_hr, resting_hr, ftp_w, weight_kg, height_cm, sex, age, vo2max_vdot, normalized_power, intensity_factor, variability_index, tss, efficiency_factor, aerobic_decoupling, grade_adjusted_pace, hr_zone_time, power_zone_time, ctl, atl, tsb, weekly_volume_km, weekly_elevation_m, mean_max_power_curve, mean_max_pace_curve`.

Worked example (hypothetical athlete) — inputs: male, age 38, resting_hr 52, max_hr not measured, vo2max_vdot 50, weight_kg 72, weekly_volume_km ~45, ctl 55, atl 60, tsb −5:

1. **Estimate HRmax** (only because missing). Tanaka: 208 − 0.7 × 38 ≈ 181 bpm [ref_tanaka2001]; a measured value overrides; the large standard error is flagged so zones are treated as approximate [ref_shookster2020].
2. **HR zones via Karvonen** (HRR = 181 − 52 = 129) [ref_karvonen1957]: Z1 117–129, Z2 129–142, Z3 142–155, Z4 155–168, Z5 168–181 bpm.
3. **Running paces from VDOT 50** via the velocity–oxygen-cost relationship (no copyrighted table reproduced): easy ~5:15–5:50/km, marathon ~4:40/km, threshold ~4:20/km, interval ~4:00/km — formula outputs that update as `vo2max_vdot` changes.
4. **Starting volume & progression**: 45 km/week start; weekly increases capped ~8–10% with a deload every 4th week.
5. **Entry gate**: 45 km/week + ctl 55 clears the marathon gate (≥35 km/week or ctl ≥40).
6. **Readiness & taper**: tsb −5 is neutral/maintenance; the two-week taper cuts volume ~50% while holding intensity [ref_bosquet2007].
7. **Durability autoregulation**: on long runs, if `aerobic_decoupling` exceeds ~5% the session is held rather than extended.

The entire decision path is inspectable, with every numeric threshold tied to a source or labelled Practice.

---

## 5. Normative reference data

`normative_data.json` holds fifteen sourced tables, every row carrying `source_ref` and `evidence_grade`:

- HRmax prediction equations (Fox, Tanaka, Gulati) with accuracy review and SE caveats [ref_tanaka2001] [ref_gulati2010] [ref_shookster2020].
- HR zone models, %HRmax and Karvonen HRR [ref_karvonen1957] [ref_seiler2010].
- Cycling power zones, 7-zone %FTP convention [ref_cogganallen].
- TSB interpretation bands for readiness and taper timing [ref_cogganallen] [ref_banister1991].
- Intensity-distribution models — pyramidal, polarized, threshold [ref_seiler2010] [ref_haugen2022] [ref_rosenblat2019].
- Protein intake by goal and per dose [ref_morton2018] [ref_jager2017].
- Resistance-training volume and frequency landmarks [ref_schoenfeld2017vol] [ref_schoenfeld2016freq].
- %1RM to repetition relationship [ref_nsca_haff2016].
- Strength-training effects in endurance athletes [ref_ronnestad2014] [ref_beattie2014] [ref_berryman2018].
- Taper parameters [ref_bosquet2007].
- Race-time prediction (Riegel) with an ultra caveat [ref_riegel1981].
- Carbohydrate intake during prolonged exercise [ref_jeukendrup2014].
- Energy-availability thresholds for RED-S [ref_mountjoy2018].
- Safe body-mass change rates [ref_donnelly2009] [ref_jager2017].
- ACWR bands, presented as contested (see §7).

---

## 6. Coverage tracker

| Domain | Cell | Status |
|---|---|---|
| Running | Marathon, intermediate, 16 wk | COMPLETE (reference program) |
| Running | Marathon, beginner / advanced, alt durations | PLANNED |
| Running | 5k, 10k, half — all levels | PLANNED |
| Running | Trail / ultra — all levels | PLANNED |
| Cycling | Criterium, 40 km TT, gran fondo, ultra, MTB/gravel | PLANNED |
| Cross-sport | Get strong, lose weight, stay fit | PLANNED |
| Muscle gain | General hypertrophy + concurrent-training variants | PLANNED |
| Schema / bibliography / ruleset | Foundations | COMPLETE |
| Normative tables | 15 tables | COMPLETE (extensible) |
| Glossary | Full term list | PLANNED |

---

## 7. Safety, ethics, and contested evidence

- **Medical disclaimer.** Educational, not medical advice. Plans assume an apparently healthy adult cleared for exercise; the app surfaces a recommendation to consult a professional, and red-flag symptoms (chest pain, syncope, unusual breathlessness) route the user out of training guidance.
- **RED-S and energy availability.** Treated as a first-class safety constraint; the low-availability threshold near 30 kcal/kg fat-free mass/day triggers education and referral rather than aggressive prescription [ref_mountjoy2018]. Weight-loss content is capped at a sustainable rate and paired with elevated protein to protect lean mass [ref_donnelly2009] [ref_jager2017].
- **Anti-doping.** Content stays within nutrition, training and recovery; defer to current WADA guidance; no recommendation touching prohibited methods/substances.
- **The ACWR debate, presented both ways.** The acute-to-chronic workload ratio was proposed with a lower-risk sweet spot ~0.8–1.3 [ref_gabbett2016]; that model has since been substantively criticized for mathematical coupling, collider bias, and other artefacts [ref_impellizzeri2020]. The app treats a large acute spike relative to recent training as a reasonable prompt for caution, but does not present any ACWR number as a validated injury predictor. The template progression caps are justified by general progressive-overload prudence, not by ACWR.

---

## 8. Build roadmap for subsequent turns

One block per turn, each producing schema-valid templates plus any new sourced normative rows, all against this bibliography:

1. Remaining running distances — 5k, 10k, half — beginner/intermediate/advanced, two durations each.
2. Trail and ultra — adds `weekly_elevation_m` and `grade_adjusted_pace` emphasis, Riegel ultra caveat, fuelling tables.
3. Cycling disciplines — criterium, 40 km TT, gran fondo, ultra, MTB/gravel — keyed to `ftp_w`, power zones, `normalized_power`, `intensity_factor`, `variability_index`.
4. Cross-sport goals — get strong, lose weight, stay fit.
5. Muscle gain — general hypertrophy + sport-specific concurrent variants.
6. Glossary, final coverage-checklist closure, and confirmation of the DOIs flagged pending.

---

## 9. Bibliography

Format: ref_id — citation — evidence grade — verification state. Machine-readable detail in `web/content/coach/overview.json`.

**Web-verified this session:**

- ref_seiler2010 — Seiler S. What is best practice for training intensity and duration distribution in endurance athletes? Int J Sports Physiol Perform 2010;5(3):276–291. doi:10.1123/ijspp.5.3.276 — Strong — web_verified.
- ref_haugen2022 — Haugen T, et al. The training characteristics of world-class distance runners. Sports Med Open 2022;8(1):46. doi:10.1186/s40798-022-00438-7 — Moderate — web_verified.
- ref_rosenblat2019 — Rosenblat MA, et al. Polarized vs. threshold training intensity distribution: meta-analysis. J Strength Cond Res 2019;33(12):3491–3500. doi:10.1519/JSC.0000000000002618 — Moderate — web_verified.
- ref_bosquet2007 — Bosquet L, et al. Effects of tapering on performance: a meta-analysis. Med Sci Sports Exerc 2007;39(8):1358–1365. doi:10.1249/mss.0b013e31806010e0 — Strong — web_verified.
- ref_tanaka2001 — Tanaka H, Monahan KD, Seals DR. Age-predicted maximal heart rate revisited. J Am Coll Cardiol 2001;37(1):153–156. doi:10.1016/S0735-1097(00)01054-8 — Strong — web_verified.
- ref_gulati2010 — Gulati M, et al. Heart rate response to exercise stress testing in asymptomatic women. Circulation 2010;122:130–137. doi:10.1161/CIRCULATIONAHA.110.939249 — Moderate — web_verified.
- ref_shookster2020 — Shookster D, et al. Accuracy of commonly used age-predicted maximal heart rate equations. Int J Exerc Sci 2020;13(7):1242–1250. doi:10.70252/XFSJ6815 — Moderate — web_verified.
- ref_karvonen1957 — Karvonen MJ, Kentala E, Mustala O. The effects of training on heart rate. Ann Med Exp Biol Fenn 1957;35(3):307–315. PMID:13470504 — Moderate — web_verified.
- ref_ronnestad2014 — Rønnestad BR, Mujika I. Optimizing strength training for running and cycling endurance performance: a review. Scand J Med Sci Sports 2014;24(4):603–612. doi:10.1111/sms.12104 — Strong — web_verified.
- ref_beattie2014 — Beattie K, et al. The effect of strength training on performance in endurance athletes. Sports Med 2014;44(6):845–865. doi:10.1007/s40279-014-0157-y — Strong — web_verified.
- ref_berryman2018 — Berryman N, et al. Strength training for middle- and long-distance performance: a meta-analysis. Int J Sports Physiol Perform 2018;13(1):57–63. doi:10.1123/ijspp.2017-0032 — Moderate — web_verified.
- ref_schoenfeld2017vol — Schoenfeld BJ, Ogborn D, Krieger JW. Dose-response: weekly resistance-training volume and muscle hypertrophy. J Sports Sci 2017;35(11):1073–1082. doi:10.1080/02640414.2016.1210197 — Strong — web_verified.
- ref_schoenfeld2016freq — Schoenfeld BJ, et al. Resistance-training frequency and hypertrophy: a meta-analysis. Sports Med 2016;46(11):1689–1697. doi:10.1007/s40279-016-0543-8 — Strong — web_verified.
- ref_morton2018 — Morton RW, et al. Protein supplementation and resistance-training gains: SR & meta-analysis. Br J Sports Med 2018;52(6):376–384. doi:10.1136/bjsports-2017-097608 — Strong — web_verified.
- ref_jager2017 — Jäger R, et al. ISSN position stand: protein and exercise. J Int Soc Sports Nutr 2017;14:20. doi:10.1186/s12970-017-0177-8 — Strong — web_verified.
- ref_gabbett2016 — Gabbett TJ. The training-injury prevention paradox. Br J Sports Med 2016;50(5):273–280. doi:10.1136/bjsports-2015-095788 — Limited (contested) — web_verified.
- ref_impellizzeri2020 — Impellizzeri FM, et al. Acute:chronic workload ratio: conceptual and methodological critique. Sports Med 2020;51:581–592. doi:10.1007/s40279-020-01378-6 — Moderate — web_verified.

**Domain-knowledge, DOI/edition pending confirmation before ship:**

- ref_daniels — Daniels J. Daniels' Running Formula, 3rd ed. (VDOT methodology). Confirm edition/ISBN. — Practice — UNVERIFIED.
- ref_cogganallen — Allen H, Coggan A. Training and Racing with a Power Meter, 3rd ed. (CTL/ATL/TSB; 7-zone model). — Practice — UNVERIFIED.
- ref_banister1991 — Banister EW. Modeling elite athletic performance (impulse-response). Book chapter. — Limited — UNVERIFIED.
- ref_riegel1981 — Riegel PS. Athletic records and human endurance. American Scientist 1981. Confirm stable URL. — Limited — UNVERIFIED.
- ref_kreider2017 — Kreider RB, et al. ISSN position stand: creatine. J Int Soc Sports Nutr 2017. doi:10.1186/s12970-017-0173-z (confirm). — Strong — UNVERIFIED.
- ref_kerksick2017 — Kerksick CM, et al. ISSN position stand: nutrient timing. J Int Soc Sports Nutr 2017. doi:10.1186/s12970-017-0189-4 (confirm). — Moderate — UNVERIFIED.
- ref_jeukendrup2014 — Jeukendrup A. A step towards personalized sports nutrition: carbohydrate during exercise. Sports Med 2014. doi:10.1007/s40279-014-0148-z (confirm). — Moderate — UNVERIFIED.
- ref_donnelly2009 — Donnelly JE, et al. ACSM position stand: physical activity and weight management. Med Sci Sports Exerc 2009. doi:10.1249/MSS.0b013e3181949333 (confirm). — Moderate — UNVERIFIED.
- ref_mountjoy2018 — Mountjoy M, et al. IOC consensus update: RED-S. Br J Sports Med 2018. doi:10.1136/bjsports-2018-099193 (confirm). — Moderate — UNVERIFIED.
- ref_nsca_haff2016 — Haff GG, Triplett NT (eds). Essentials of Strength Training and Conditioning, 4th ed. NSCA. — Practice — UNVERIFIED.

---

## 10. Glossary (core terms)

- **Aerobic decoupling** — drift of heart rate relative to pace/power over a steady effort; rising decoupling signals fading aerobic durability.
- **ATL** — acute training load; short-term EWMA of load; fatigue proxy.
- **CTL** — chronic training load; long-term EWMA of load; fitness proxy.
- **Efficiency factor** — output (pace/power) ÷ heart rate; tracks aerobic efficiency over time.
- **FTP** — functional threshold power; anchor for cycling power zones.
- **Intensity factor** — normalized power ÷ FTP for a session.
- **Karvonen / heart-rate reserve** — zone method using the span between resting and maximal heart rate.
- **Normalized power** — physiologically weighted average power accounting for variability.
- **Pyramidal / polarized / threshold** — the three intensity-distribution models the app stores.
- **TSB** — training stress balance; CTL − ATL; a form proxy for readiness and taper timing.
- **VDOT** — VO2-based running fitness index used to derive paces by computation.
- **Variability index** — normalized power ÷ average power; how evenly an effort was paced.
