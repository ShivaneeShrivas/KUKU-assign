"""Independent hard-rule checker. Re-derives everything from the parsed screenplay, so a bug in the
engine (or a hallucinated timestamp from an LLM) cannot pass silently."""
from __future__ import annotations
from .parse import fmt


def validate(promos, finder, dmin=None, dmax=None):
    cfg = finder.cfg
    dmin = dmin or cfg["duration"]["min"]; dmax = dmax or cfg["duration"]["max"]
    A, eps = finder.A, finder.eps
    rows = []
    for p in promos:
        issues = []
        dur = sum(s.t1 - s.t0 for s in p.segs)
        if not (dmin - 0.01 <= dur <= dmax + 0.01): issues.append(f"duration {dur:.1f}s outside {dmin}-{dmax}")
        prev = None
        for s in p.segs:
            ep = eps.get(s.ep)
            if ep is None: issues.append(f"episode {s.ep} missing"); continue
            if s.t1 - s.t0 < 2.0: issues.append(f"ep{s.ep} segment <2s")
            if s.t0 < 0 or s.t1 > ep.duration + 0.05: issues.append(f"ep{s.ep} outside episode bounds")
            if not A.legal_start(ep, s.t0): issues.append(f"ep{s.ep} start {fmt(s.t0)} cuts a dialogue line")
            if not A.legal_end(ep, s.t1): issues.append(f"ep{s.ep} end {fmt(s.t1)} cuts a dialogue line")
            first = [e for e in ep.events if e.kind in ("dialogue", "action") and s.t0 - 0.06 <= e.t0 <= s.t0 + 1.0]
            if not first: issues.append(f"ep{s.ep} no spoken/action beat within 1s of start (dead open)")
            if prev and (s.ep, s.t0) < (prev.ep, prev.t1): issues.append("segments out of order / overlapping")
            prev = s
        rows.append({"id": p.id, "ok": not issues, "issues": issues})
    n_ok = sum(r["ok"] for r in rows)
    return {"checked": len(rows), "passed": n_ok, "failed": [r for r in rows if not r["ok"]]}
