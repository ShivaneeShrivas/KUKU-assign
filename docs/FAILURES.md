# Failure analysis (v2)

Source of truth: `outputs/eval/failures.json` (shown in the dashboard's Evaluation tab).

## Fixed
- **Central identity spoiler recommended at rank #4 (v1).** Reveal registry + spoiler factor + slate exclusion + spoiler-safe recut.
- **Tier A/B/C disagreed with score rank (v1).** Grades are now a pure score band; release wave is a separate field.
- **Mid-sentence starts, off-screen openers, incoherent composites.** Continuation gate, off-screen penalty, coherence gate.
- **Cliffhanger answered inside the clip.** Curiosity gate multiplies the cliffhanger score.

## Open (honest)
- Ep45 has no spoiler-safe >=20 s recut; the tool declines rather than forcing one.
- Rules overestimate newcomer understanding: the AI cold-reader disagreed on 37 of 40 judged promos (flagged "needs human review").
- The registry misses 10 spoilers the AI saw (AI may only raise spoiler risk).
- Lexical cliffhanger scorer is ~chance on the writers' own episode endings (AUROC 0.553): cliffhangers here are staged visually.
- Blind test vs random clips: 12/17, p = 0.143, one AI rater. Not significant, not human evidence.
- No audience data exists, so nothing here claims a promo will perform.
