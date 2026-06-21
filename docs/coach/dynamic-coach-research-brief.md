# Dynamic-coach evidence brief (single-file research pass)

The **dynamic coach** is an LLM-less, fully-offline controller: it reads your own
training history (CTL/ATL/TSB, ACWR, monotony, recovery) and prescribes the next
sessions by rule. The *formulas* are settled and already implemented; what needs
anchoring is the **interpretive numbers** — the safe CTL ramp band, the ACWR
"sweet spot" and danger threshold, taper depth/duration, the easy:hard intensity
split, mesocycle structure, how to read Garmin's recovery timer, Foster
monotony/strain cut-offs, the TSB/form bands, the maintenance dose, and a
conservative beginner/return-to-training progression.

Those numbers live as **PROVISIONAL named constants** in
[`core/coach_state.py`](../../core/coach_state.py) (and, later,
`core/coach_plan.py`). This brief is the prompt for a parallel, internet-connected
research session that returns **one JSON file** — `coach-evidence.pack.json` —
which we drop into `web/content/coach/` and use to (a) replace those constants
with cited values and (b) show each recommendation's rationale + source in the UI.
A content-integrity test will assert every `citations` entry resolves to a
`bibliography` key, mirroring how the other content packs are verified.

## How to run it

Spawn an online session and paste **the entire block below** (it is
self-contained). When it returns `coach-evidence.pack.json`, send the file back
and I will wire it in.

```text
# ROLE
You are a sports-science research assistant. Produce an evidence-anchored
parameter pack for an offline, rule-based ("no LLM") endurance-training coach.
The coach already implements the standard models (Banister TRIMP, Coggan TSS/NP/IF,
CTL/ATL/TSB exponentially-weighted moving averages, Acute:Chronic Workload Ratio,
Foster monotony/strain). Your job is NOT to redesign the models — it is to supply,
with citations, the THRESHOLDS and PROTOCOL NUMBERS that turn those models into
safe, productive prescriptions, and to be explicit about uncertainty.

# OUTPUT — EXACTLY ONE FILE
Return a single JSON file named `coach-evidence.pack.json` and NOTHING else (no
prose outside the file). It MUST validate against the schema in "OUTPUT SCHEMA"
below. For every parameter give: a single recommended default (what the coach
should use), the range/values reported in the literature, a confidence rating
(high | moderate | low | contested), plain-language caveats, and one or more
`citations` keys. Every `citations` key MUST appear in the top-level
`bibliography`. Prefer SI / explicit units. Where a model is genuinely disputed,
set confidence to "contested" and say so in `caveats` — do not paper over it.

# SOURCE QUALITY (in priority order)
1. Peer-reviewed sports-science journals (e.g. MSSE, IJSPP, Sports Medicine,
   Eur J Appl Physiol, Front Physiol) and systematic reviews / meta-analyses.
2. Foundational texts: Coggan & Allen, *Training and Racing with a Power Meter*;
   Daniels, *Daniels' Running Formula*; Seiler's polarized-training papers;
   Bosquet et al. taper meta-analysis; Gabbett ACWR papers and the Lolli /
   Impellizzeri critiques; Foster's monotony/strain work; Firstbeat/Garmin
   white papers for the recovery-time and Training-Effect semantics.
3. Reputable practitioner sources (TrainingPeaks, Intervals.icu docs) ONLY to
   corroborate, never as the sole citation for a number.
Avoid blogs/forums for primary numbers. Note publication year; prefer recent
reviews where the science has moved.

# PARAMETERS TO ANCHOR  (map each to the code constant named in [brackets])
1. ctl_ramp_rate — safe & productive weekly rise in CTL (fitness). Give low/high
   per week. [RAMP_SAFE_LOW / RAMP_SAFE_HIGH]
2. acwr — should a coupled rolling-average ACWR be used at all? Give the
   acute/chronic window lengths, the "sweet spot" low/high, and the elevated-risk
   threshold; summarise the coupled-vs-uncoupled and EWMA-vs-rolling debate and
   the Lolli/Impellizzeri criticisms. [ACWR_ACUTE_DAYS, ACWR_CHRONIC_DAYS,
   ACWR_UNDERTRAINING_BELOW, ACWR_SWEET_SPOT_HIGH, ACWR_CAUTION_HIGH]
3. tsb_bands — interpret Training Stress Balance (form): the boundaries for
   race-ready / fresh / neutral (grey zone) / optimal-training / overreaching, and
   the target TSB on race day.
4. taper — duration (days), volume reduction (%), whether to hold intensity,
   frequency reduction (%), and decay shape (linear/step/exponential) to peak form.
5. intensity_distribution — target share of EASY vs MODERATE vs HARD for endurance
   base (polarized 80/20 vs pyramidal vs threshold); define against a 3-zone model
   (below LT1 / LT1–LT2 / above LT2) and note how it maps to 5-zone HR/power.
6. periodization — build:recovery mesocycle ratio (e.g. 3:1) and the deload
   magnitude (% load reduction) on the recovery week.
7. recovery_interpretation — how to read Garmin/Firstbeat "recovery time" (hours)
   as a gate on the next QUALITY session; what aerobic/anaerobic Training-Effect
   values mean; and resting-HR / HRV deviations that indicate incomplete recovery.
   [READINESS_RHR_ELEVATED, READINESS_BASELINE_DAYS]
8. monotony_strain — Foster training-monotony and training-strain values
   associated with elevated illness/injury/overtraining risk.
9. hard_day_definition — a defensible way to label a single day's session "hard"
   relative to current fitness (e.g. a multiple of CTL, or an IF/TSS cut-off).
   [HARD_DAY_LOAD_RATIO, HARD_DAY_MIN_LOAD]
10. maintenance_dose — the minimum frequency/intensity/volume that MAINTAINS
    endurance fitness (detraining literature): how little, for how long, before
    decline.
11. beginner_return — a conservative progression for novices and return-from-
    layoff (the status of the "10% per week" rule; safe run/walk and volume ramps).

# OUTPUT SCHEMA
{
  "schema": "fenix5sync.coach.evidence.v1",
  "generated": "YYYY-MM-DD",
  "summary": "2-4 sentences on overall confidence and the biggest caveats.",
  "parameters": {
    "<parameter_name>": {
      "recommended": { "<field>": <number|string>, "unit": "<unit>" },
      "literature_range": "<concise text or numeric range>",
      "confidence": "high | moderate | low | contested",
      "maps_to_constants": ["<CODE_CONSTANT>", "..."],
      "caveats": "<plain language>",
      "citations": ["<bibkey>", "..."]
    }
    // one entry per parameter 1..11 above, keyed by the names in PARAMETERS
  },
  "bibliography": {
    "<bibkey>": {
      "authors": "<surname et al.>",
      "year": <int>,
      "title": "<full title>",
      "venue": "<journal/publisher>",
      "identifier": "<DOI or ISBN if available>",
      "url": "<stable link if available>"
    }
    // every citations key used above MUST be defined here
  }
}

# HARD REQUIREMENTS
- One file only; valid JSON; no comments in the actual returned JSON.
- Every parameter 1..11 present. Every citations key defined in bibliography.
- Recommended defaults must be concrete numbers (or short enums), usable directly
  as code constants — not "it depends".
- Be explicit and honest where evidence is weak or contested (especially ACWR).
```

## Where the returned file lands

- File: `web/content/coach/coach-evidence.pack.json`.
- Each `parameters.*.recommended` value replaces the matching PROVISIONAL constant
  in `core/coach_state.py` / `core/coach_plan.py` (the `maps_to_constants` field
  makes the mapping explicit).
- The pack is rendered in the coach UI so every recommendation can show its
  rationale, confidence and source — keeping the coach scientific and auditable.
- A content-integrity test will assert: schema version matches, all 11 parameters
  are present, and every `citations` key resolves in `bibliography`.
