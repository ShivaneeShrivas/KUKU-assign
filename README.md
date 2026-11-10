# Promo Desk — story-aware promo intelligence for microdrama

Finds 20–60 s promo cuts in timestamped screenplays and answers the questions an editor actually has:
*Is it understandable to a stranger? Does it spoil the show? Is the ending genuinely unanswered? Which ten should we release, in what order?*

**Signature features:** (1) the **campaign-slate builder** (diversity-optimised, drag-to-reorder, editor has the final word) and
(2) the **spoiler-aware cold-viewer evaluation** (reveal registry + typed context gaps + a real LLM cold reader).

**Confidentiality.** This repo contains code only. Do **not** commit episode scripts, outputs (`promos.json`, `dashboard.html`, `*.jsonl`) — they contain Kuku dialogue. `.gitignore` blocks them.

## Run (Python 3.9+, standard library only for the core)
```bash
# 1. rules only (no key, ~6 s for 50 episodes)
python run.py --input "<folder of episode .txt>" --out outputs/run --title "Show name"
open outputs/run/dashboard.html            # single file, works offline

# 2. real LLM, live API (any OpenAI-compatible endpoint)
export PROMO_LLM_API_KEY=...
python run.py --input <folder> --out outputs/run --llm --base-url https://api.openai.com/v1 --model <model> --shortlist 40

# 3. any model / any chat tool, no API plumbing: export -> answer -> replay
python run.py --input <folder> --llm-export prompts.jsonl --shortlist 40
#    answer each line {"key","system","user"} with ANY model; write {"key","response":{...JSON...}} per line to answers.jsonl
python run.py --input <folder> --out outputs/run --llm-replay answers.jsonl --shortlist 40

# 4. editor decisions -> next run (decisions never change scores; they change eligibility + slate)
#    in the dashboard: Campaign builder -> "Export decisions + slate"
python run.py --input <folder> --out outputs/run --decisions decisions.json
python -m promo.learn decisions.json outputs/run/promos.json     # weight suggestions only if >=20 decisions, >=8 per class, and it beats the baseline
python run.py ... --apply-weights learned_weights.json            # explicit opt-in

# 5. evaluation + tests
python eval/checks.py --input <folder> --out outputs/eval
python eval/blind_ab.py make --input <folder> --out outputs/eval   # give the sheet (not answer_key.json) to human raters; then `score`
python run.py ... --checks outputs/eval/checks.json --failures outputs/eval/failures.json
PROMO_PACK=<folder> python -m unittest discover -s tests            # 20 tests; 13 need the (private) pack and skip without it
```
New show: just point `--input` at its folder; optional `promo/aliases.json` maps speaker labels to characters; tune `promo/config.toml`.

## Try it in 10 seconds (invented demo show, safe to share)
```bash
python run.py --input examples/demo_show --out outputs/demo --title "Demo show"
```
Open `outputs/demo/dashboard.html`. The **Studio** tab has live weight sliders (re-ranking), a 9:16 script replay with a cold-viewer panel, and keyboard review (A/R, arrows, J/K in the drawer).

## How it works
`parse` → legal cut points (never inside a spoken line) → hook×cliffhanger pair search → `story.py` (characters, relationships, reveal registry) →
`intel.py` (cold-viewer gaps, curiosity gate, 4-phase arc) → score = weighted components × spoiler factor → `portfolio.py` (engine diversity, release waves) →
optional `judge.py` (cold-reader + editor LLM prompts; output schema-validated, can only *raise* spoiler risk, trims validated but never auto-applied) → `report.py` dashboard.

Provenance is shown everywhere: ✓ verified by code · ◦ rules heuristic · ✦ AI judgement · ● human decision.

## What this does not claim
No audience data was used. Nothing says a promo will convert or retain. Evidence is in `outputs/eval/` and `docs/FAILURES.md` (blind test 12/17, p=0.14, one AI rater; cliffhanger scorer ≈ chance on silver labels).
