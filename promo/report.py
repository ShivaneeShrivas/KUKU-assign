"""Build the single JSON payload (schema v2) that feeds every output: promos.json, CSV, markdown, campaign brief and the dashboard."""
from __future__ import annotations
import csv, json, os, datetime
from .parse import fmt
from . import lex


def seg_str(p): return " + ".join(f"Ep{s.ep} {fmt(s.t0)}–{fmt(s.t1)}" for s in p.segs)


def promo_dict(p, finder):
    ai = p.llm or {}
    d = {"id": p.id, "rank": p.rank, "grade": p.grade, "score": round(p.total, 3), "raw_score": round(p.raw_score, 3), "duration_s": round(p.duration, 1),
         "segments": [{"episode": s.ep, "start": fmt(s.t0), "end": fmt(s.t1), "start_s": s.t0, "end_s": s.t1} for s in p.segs],
         "hook": p.hook_line, "cliffhanger": p.cliff_line, "why": (p.ai_why or p.why), "why_rules": p.why, "engine": p.engine,
         "engine_secondary": p.story.get("secondary_engine", ""), "engine_vector": p.story.get("engine_vector", {}),
         "scores": p.scores, "spoiler": p.spoiler, "cold_viewer": p.cold, "curiosity": p.curiosity, "arc": p.arc, "repairs": p.repairs,
         "story": {k: v for k, v in p.story.items() if k not in ("engine_vector",)}, "concept": p.concept,
         "campaign": {"eligible": p.campaign_eligible, "exclusions": p.exclusions, "release_priority": p.release_priority, "wave": p.wave, "in_slate": p.slate},
         "landing": p.landing, "optional_cold_open": p.cold_open, "after_cut": p.after_cut, "transcript": p.transcript,
         "flags": p.evidence.get("gates", []) + (["context_setup_added"] if len(p.segs) > 1 else []) + (["spoiler_safe_recut"] if p.evidence.get("recut_from") else []),
         "recut": ({"reason": p.evidence.get("recut_reason")} if p.evidence.get("recut_from") else None),
         "ai": ai or {"status": "not_run"},
         "provenance": {"timestamps": "verified by independent validator", "scores": "rule-based heuristics (not audience data)",
                        "ai": ai.get("status", "not_run"), "human": (p.human or {}).get("status", "undecided")},
         "human": p.human or {"status": "undecided"}}
    return d


def episode_table(finder, promos):
    by = {}
    for p in promos: by.setdefault(p.segs[-1].ep, []).append(p)
    out = []
    for ep in finder.eps_list:
        a = finder.story.ep_arc.get(ep.num, {})
        ps = by.get(ep.num, [])
        out.append({"ep": ep.num, "duration": round(ep.duration, 1), "logline": ep.logline, "mean": a.get("mean"), "peak": a.get("peak"), "peak_t": a.get("peak_t"),
                    "act": a.get("act"), "curve": a.get("curve", []), "n_promos": len(ps), "best": round(max([p.total for p in ps], default=0), 3),
                    "ids": [p.id for p in ps], "reveals": [{"line": r.line[:90], "kind": r.kind, "severity": r.severity, "t": r.t0} for r in finder.story._by_ep.get(ep.num, []) if not r.is_question and r.severity >= 0.4]})
    return out


def build_payload(finder, promos, meta, validation, checks=None, failures=None):
    st = finder.story.summary()
    return {"schema": 2, "meta": meta, "validation": validation,
            "campaign": finder.campaign, "story": st,
            "episodes": episode_table(finder, promos),
            "engines": list(lex.ENGINES2) + ["General drama"],
            "promos": [promo_dict(p, finder) for p in promos],
            "evaluation": {"checks": checks, "failures": failures or []},
            "decisions_schema": {"statuses": ["approved", "rejected", "shortlisted", "undecided"], "reasons": {k: v[0] for k, v in __import__("promo.learn", fromlist=["REASONS"]).REASONS.items()}}}


def write_all(promos, finder, out, meta, validation, checks=None, failures=None, dashboard=True):
    os.makedirs(out, exist_ok=True)
    payload = build_payload(finder, promos, meta, validation, checks, failures)
    with open(os.path.join(out, "promos.json"), "w", encoding="utf-8") as fh: json.dump(payload, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(out, "promos.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "rank", "grade", "score", "release_priority", "wave", "in_slate", "campaign_eligible", "segments", "duration_s", "engine", "spoiler_level", "cold_viewer_understanding",
                    "ending_open", "arc_label", "hook", "cliffhanger", "why", "ai_status", "human_status", "exclusions"])
        for d in payload["promos"]:
            w.writerow([d["id"], d["rank"], d["grade"], d["score"], d["campaign"]["release_priority"], d["campaign"]["wave"], d["campaign"]["in_slate"], d["campaign"]["eligible"],
                        " + ".join(f"Ep{s['episode']} {s['start']}-{s['end']}" for s in d["segments"]), d["duration_s"], d["engine"], d["spoiler"]["level"],
                        d["cold_viewer"]["understanding"], d["curiosity"]["open"], d["arc"]["label"], d["hook"], d["cliffhanger"], d["why"], d["ai"].get("status"), d["human"]["status"], "; ".join(d["campaign"]["exclusions"])])
    byid = {d["id"]: d for d in payload["promos"]}
    L = [f"# Campaign brief — {meta['show']}", "", f"Mode: **{meta['mode']}**. Quality rank is individual; release priority is campaign-aware (diversity + spoiler safety).", "",
         "| Release # | Wave | Promo | Segments | Engine | Score | Grade | Spoiler | Hook | Ending |", "|---|---|---|---|---|---|---|---|---|---|"]
    for pid in finder.campaign["slate_ids"]:
        d = byid[pid]
        L.append(f"| {d['campaign']['release_priority']} | {d['campaign']['wave']} | {pid} | " + " + ".join(f"Ep{s['episode']} {s['start']}–{s['end']}" for s in d["segments"]) +
                 f" | {d['engine']} | {d['score']} | {d['grade']} | {d['spoiler']['level']} | {d['hook'][:60]} | {d['cliffhanger'][:60]} |")
    m, b = finder.campaign["metrics"], finder.campaign["top10_by_score"]
    L += ["", f"Diversity: slate covers {m['engines_covered']} engines (naive top-10-by-score: {b['engines_covered']}); mean score {m['mean_score']} vs {b['mean_score']}; mean pairwise similarity {m['mean_pairwise_similarity']} vs {b['mean_pairwise_similarity']}.",
          "", "_No performance data exists for these promos. Scores are rule-based and AI-assisted judgements, not predictions of audience response._"]
    with open(os.path.join(out, "campaign_brief.md"), "w", encoding="utf-8") as fh: fh.write("\n".join(L))
    L = [f"# Ranked promos — {meta['show']}", ""]
    for d in payload["promos"]:
        L += [f"## #{d['rank']} · {d['id']} · grade {d['grade']} · {d['score']} · {d['duration_s']}s · {d['engine']}",
              "**Segments:** " + " + ".join(f"Ep{s['episode']} {s['start']}–{s['end']}" for s in d["segments"]), f"**Hook:** {d['hook']}", f"**Cliffhanger:** {d['cliffhanger']}", f"**Why:** {d['why']}",
              f"**Spoiler risk:** {d['spoiler']['level']} · **Cold-viewer understanding:** {d['cold_viewer']['understanding']} · **Arc:** {d['arc']['label']}", "", "```", d["transcript"], "```", ""]
    with open(os.path.join(out, "PROMOS.md"), "w", encoding="utf-8") as fh: fh.write("\n".join(L))
    if dashboard:
        from .dashboard import write_dashboard
        write_dashboard(payload, os.path.join(out, "dashboard.html"))
    return payload
