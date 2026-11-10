"""Apply human editor decisions (decisions.json exported from the dashboard) to a run. Decisions never change the score
(we have no evidence an approval means better performance); they change ELIGIBILITY and the slate, and they are stored for learning."""
from __future__ import annotations
from . import portfolio


def apply_decisions(finder, promos, dec):
    by = {p.id: p for p in promos}; n = {"approved": 0, "rejected": 0, "shortlisted": 0, "unknown_ids": 0}
    for d in dec.get("decisions", []):
        p = by.get(d["id"])
        if not p: n["unknown_ids"] += 1; continue
        p.human = {"status": d["status"], "reasons": d.get("reasons", []), "note": d.get("note", ""), "ts": d.get("ts", ""), "editor": dec.get("editor", "")}
        if d["status"] in n: n[d["status"]] += 1
    finder.finalize(promos)
    # editor-chosen slate overrides the optimizer (it is a human decision)
    if dec.get("slate"):
        ids = [i for i in dec["slate"] if i in by]
        for p in promos: p.slate = p.id in ids
        finder.slate_promos = [by[i] for i in ids]
        finder.campaign["slate_ids"] = ids; finder.campaign["source"] = "editor"
        finder.campaign["metrics"] = portfolio.diversity_metrics(finder.slate_promos, finder)
    else:
        finder.slate_promos = [p for p in promos if p.campaign_eligible and p.release_priority and p.release_priority <= finder.cfg["portfolio"]["slate_size"]]
    return n
