#!/usr/bin/env python3
"""Story-aware promo intelligence for timestamped screenplays.

  python run.py --input <folder of episode .txt> --out outputs/run                 # rules only, no key, ~5 s
  python run.py ... --llm-export outputs/llm_requests.jsonl --shortlist 40         # write prompts for ANY model (offline/batch)
  python run.py ... --llm-replay outputs/llm_responses.jsonl                       # ingest that model's answers
  PROMO_LLM_API_KEY=... python run.py ... --llm --model gemini-2.0-flash           # live API (any OpenAI-compatible endpoint)
  python run.py ... --decisions decisions.json                                     # apply editor approvals/rejections
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from promo.engine import Finder, load_cfg
from promo.validate import validate
from promo.report import write_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--out", default="outputs/run"); ap.add_argument("--title")
    ap.add_argument("--config"); ap.add_argument("--aliases"); ap.add_argument("--min-score", type=float)
    ap.add_argument("--llm", action="store_true", help="live API judge"); ap.add_argument("--llm-export"); ap.add_argument("--llm-replay")
    ap.add_argument("--base-url"); ap.add_argument("--model"); ap.add_argument("--api-key-env"); ap.add_argument("--shortlist", type=int)
    ap.add_argument("--decisions", help="editor decisions.json"); ap.add_argument("--apply-weights", help="learned_weights.json (explicit opt-in)")
    ap.add_argument("--checks", help="eval/checks.json to embed"); ap.add_argument("--failures", help="failures.json to embed")
    a = ap.parse_args()
    cfg = load_cfg(a.config)
    if a.min_score is not None: cfg["select"]["min_score"] = a.min_score
    if a.apply_weights:
        lw = json.load(open(a.apply_weights))
        if lw.get("status") != "suggested": sys.exit(f"refusing: weights status is {lw.get('status')}")
        cfg["weights"].update({k: v for k, v in lw["weights"].items()}); z = sum(cfg["weights"].values()); cfg["weights"] = {k: v / z for k, v in cfg["weights"].items()}
    t0 = time.time()
    f = Finder(a.input, cfg, a.aliases, a.title)
    promos = f.run()
    short = a.shortlist or cfg["llm"]["shortlist"]
    meta = {"show": f.title, "episodes": len(f.eps_list), "events": sum(len(e.events) for e in f.eps_list), "candidates_scored": f.n_candidates,
            "mode": "rules only (no AI judgement)", "generated": time.strftime("%Y-%m-%d %H:%M"), "weights": cfg["weights"], "config": cfg}
    from promo import judge
    if a.llm_export:
        reqs = judge.build_requests(f, promos, short)
        with open(a.llm_export, "w", encoding="utf-8") as fh:
            for r in reqs: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {len(reqs)} prompts ({short} promos x cold+editor) to {a.llm_export}"); return
    llm = None
    if a.llm_replay:
        from promo.llm import ReplayLLM
        llm = ReplayLLM(a.llm_replay)
    elif a.llm:
        from promo.llm import LLM
        L = cfg["llm"]
        llm = LLM(a.base_url or os.environ.get("PROMO_LLM_BASE_URL") or L["base_url"], a.model or os.environ.get("PROMO_LLM_MODEL") or L["model"],
                  a.api_key_env or L["api_key_env"], cache_dir=os.path.join(a.out, ".llm_cache"))
    if llm:
        r = judge.run_llm_stage(f, promos, llm, short, cfg["llm"]["blend"])
        meta["mode"] = f"rules + AI judgement ({getattr(llm, 'provider', 'live API')}: {llm.model}) on top {short}"
        meta["llm"] = {**r, "usage": llm.usage, "provider": getattr(llm, "provider", "live API"), "model": llm.model}
        print("AI stage:", r, llm.usage)
    if a.decisions:
        from promo.decisions import apply_decisions
        meta["decisions"] = apply_decisions(f, promos, json.load(open(a.decisions)))
    v = validate(promos, f)
    meta["runtime_s"] = round(time.time() - t0, 1)
    checks = json.load(open(a.checks)) if a.checks and os.path.exists(a.checks) else None
    failures = json.load(open(a.failures)) if a.failures and os.path.exists(a.failures) else None
    write_all(promos, f, a.out, meta, v, checks, failures)
    print(f"{len(promos)} promos / {len(f.eps_list)} episodes in {meta['runtime_s']}s; validation {v['passed']}/{v['checked']}; slate {f.campaign['slate_ids']}; wrote {a.out}/")
    if v["failed"]: print("VALIDATION FAILURES:", v["failed"][:5]); sys.exit(1)


if __name__ == "__main__":
    main()
