# Bangla Cyclone and Flood Response Line: Self-Play and Persona Stress Test

Prototype supporting **Answer 3** of the Bangla NLP research-engineer assessment.
It shows that M2M dialogue self-play (Shah et al., 2018) can generate training
dialogues for a Bangla disaster-response voice line *before* a disaster, and that
the same simulator can audit whether the bot serves all callers equally.

All dialogues are **synthetic by design**: generating them is the method, since
real conversations cannot be collected in advance of a cyclone.

## Reproduce every result

**One click:** [Open in Colab](https://colab.research.google.com/github/USERNAME/bangla-cyclone-selfplay/blob/main/Q3_reproduce_results.ipynb)
then *Runtime → Run all* (under a minute). The notebook recomputes each number
claimed in Answer 3 and prints a verification table ending in
`All claims verified: True`.

**Locally** (Python 3 standard library only; fixed seed 2026, identical output every run):

    python selfplay.py            # generates outlines.jsonl (1,000 dialogues)
    python evaluate_outlines.py   # six safety invariants, outcomes, diversity
    python mutation_test.py       # proves the invariant checker catches faults
    python stress_test.py         # persona stress test, NLU v1 vs v2

Expected SHA-256 of `outlines.jsonl`:
`bb1a9bb8bf87d1a0dd0aec4fea3f11eceefca103992fd94f668882518da09276`

## Files

| File | Purpose |
|------|---------|
| `selfplay.py` | Schema, mock shelter API, scenario sampler, user simulator, system agent |
| `evaluate_outlines.py` | Six safety invariants, outcome distribution, diversity metrics |
| `mutation_test.py` | Injects one fault per invariant to validate the checker |
| `stress_test.py` | Persona stress test: four registers, dev/test phrasings, NLU v1 and v2 |
| `Q3_reproduce_results.ipynb` | Self-contained notebook reproducing and checking every claim |
| `outlines.jsonl` | The 1,000 generated dialogues |
| `stage1_results.txt`, `stress_results.txt` | Saved outputs of the scripts |

## Stage 1: self-play
Schema: household status (safe / needs shelter / needs rescue), location (five
coastal upazilas, or unknown with a landmark), household size and vulnerable
members. Mock API: shelter roster with remaining capacity, Kutubdia deliberately full.

| Result | Value |
|--------|-------|
| Safety-invariant violations | **0 / 1,000** |
| Mutation test (injected faults detected) | **6 / 6** |
| Outcomes | safe advice 33.1%, rescue 30.5%, shelter confirmed 19.3%, rescue after shelter refusal 7.5%, no capacity 6.2%, location unknown 3.4% |
| Unique transitions per turn | 0.0133 (scripted happy path: 0.0009) |

## Stage 2: persona stress test
Four caller registers: standard Bangla, Banglish, Sylheti style (approximate,
pending native validation) and noisy/panicked speech. Each register has separate
**dev** and **test** phrasings; NLU v2 was built from dev phrasings only.

Automated success on held-out test phrasings (400 dialogues per persona):

| Persona | v1 (standard Bangla only) | v2 (extended lexicon) |
|---------|-----------|-----------|
| Standard Bangla | 63.2% | 64.2% |
| Banglish | 0.0% | 63.2% |
| Sylheti style | 13.8% | 64.2% |
| Noisy / panicked | 0.0% | 57.8% |
| **Fairness gap** | **63.2 pts** | **6.5 pts** |

Unresolved callers are handed to a human operator, never dropped.

**Key finding:** v2's dialect cue *ভালা* ("well") misread
*থাকার জাগা লাগবো, হকলে ভালা আছি* ("we need a place to stay, everyone is well")
as *safe*, giving safety advice instead of shelter. Widening the lexicon closed
the fairness gap but introduced a harmful error absent in v1; any *safe*
conclusion therefore needs confirmation.

## Limitations
Phrasings are synthetic and written by one author; the Sylheti-style forms are
approximate; the keyword NLU is a deliberately simple stand-in for a trained
model. The results demonstrate the method, not a deployable system.

## Reference
P. Shah et al., "Building a conversational agent overnight with dialogue self-play," arXiv:1801.04871, 2018.
