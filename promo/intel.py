"""Promo intelligence layers on top of the deterministic signals:
  * ColdViewer  - does a stranger understand WHO / RELATIONSHIP / CONFLICT / STAKES?  -> typed context gaps
  * Curiosity   - does the cut leave a genuinely UNANSWERED question (not answered in the clip, not answered by what we already saw)?
  * Arc         - hook -> context -> escalation -> unresolved cliffhanger, scored phase by phase (weakest-link)
All numbers are heuristics computed from the script text; none is a measurement of audience behaviour."""
from __future__ import annotations
import re
from . import lex
from .signals import clip01, STOPWORDS, WORD

W4 = lambda t: {w for w in re.findall(r"[a-z]{4,}", t.lower())} - STOPWORDS


# ===================================================================== cold viewer
def cold_view(A, packs):
    """packs: [(ep_num, evs_all, spoken, t0, t1)] -> dict(understanding, dims, gaps)."""
    sp = [e for p in packs for e in p[2] if e.kind in ("dialogue", "action")]
    dl = [e for e in sp if e.kind == "dialogue"]
    txt = " ".join(e.text for e in sp)
    dtxt = " ".join(e.text for e in dl)
    debt, info = A.debt([(p[0], p[1], p[3]) for p in packs])
    speakers = {e.who for e in dl if e.who}
    gaps = []
    # WHO ------------------------------------------------------------------
    un = info["unanchored"]; dang = info.get("dangling_pronouns", 0)
    named = [c for c in A.names if A.name_rx[c].search(txt) or c in speakers]
    lead_named = [c for c in named if c in A.lead and c not in speakers and not A.name_rx[c].search(dtxt)]
    who = 0.70 if not named else clip01(1.0 - 0.30 * len(un) - 0.12 * dang - (0.15 if len(speakers) >= 3 else 0.0) - (0.20 if not any(A.name_rx[c].search(dtxt) for c in A.names) and len(speakers) >= 2 else 0.0))
    for c in un[:3]:
        gaps.append({"type": "WHO", "severity": 0.30, "detail": f"{c.title()} appears but nothing in the clip says who they are."})
    if dang:
        gaps.append({"type": "WHO", "severity": 0.15 * min(dang, 2), "detail": "Opens on 'he/she/they' before anyone is named."})
    # RELATIONSHIP -----------------------------------------------------------
    role_d = bool(lex.REL_STRICT.search(dtxt)); role_a = bool(lex.REL_STRICT.search(txt))
    addressed = sum(1 for e in dl for c in A.names if c != e.who and A.name_rx[c].search(e.text))
    rel = 1.0 if (role_d and len(speakers) >= 2 and addressed >= 1) else 0.8 if (role_d and len(speakers) >= 2) else 0.6 if role_a else 0.45 if addressed >= 1 else 0.15
    if len(speakers) < 2 and not role_a: rel = min(rel, 0.4)
    if rel < 0.6: gaps.append({"type": "RELATIONSHIP", "severity": round(0.6 - rel, 2) + 0.1, "detail": "A new viewer is never told how these people are connected (spouse, family, enemy, rank)."})
    # CONFLICT ---------------------------------------------------------------
    hot = [e for e in sp if set(e.cats) & {"confront", "physical", "stakes", "status", "reveal"}]
    hot_speakers = {e.who for e in hot if e.kind == "dialogue"}
    conflict = 1.0 if (hot and len(speakers) >= 2) else 0.6 if hot else 0.2
    if conflict < 0.6: gaps.append({"type": "CONFLICT", "severity": 0.35, "detail": "No clear opposition: the viewer cannot tell who wants what from whom."})
    # STAKES -----------------------------------------------------------------
    st = any(set(e.cats) & {"stakes", "physical", "status", "romance"} for e in sp)
    thr = bool(lex.CLIFF_THREAT.search(dtxt))
    stakes = clip01((0.8 if st else 0.3) + (0.2 if thr else 0.0))
    if stakes < 0.5: gaps.append({"type": "STAKES", "severity": 0.3, "detail": "Nothing visibly at risk (life, status, love, secret)."})
    # BACK-REFERENCES / continuation ------------------------------------------
    back = lex.BACKREF.findall(dtxt)
    first_dl = dl[0] if dl else None
    cont = bool(first_dl and (lex.CONTINUATION.search(first_dl.text) or lex.ANAPHORIC_OPEN.search(first_dl.text)))
    if back: gaps.append({"type": "BACKREF", "severity": min(0.4, 0.15 * len(back)), "detail": "Refers to earlier events: " + ", ".join(f"'{b if isinstance(b, str) else b[0]}'" for b in back[:2])})
    if cont: gaps.append({"type": "OPENING", "severity": 0.3, "detail": "Opens mid-thought ('" + first_dl.text[:28] + "…') so the first line needs a lead-in."})
    u = 0.30 * who + 0.25 * rel + 0.25 * conflict + 0.20 * stakes
    u -= min(0.24, 0.12 * len(back)) + (0.10 if cont else 0.0)
    u = clip01(u)
    gaps.sort(key=lambda g: -g["severity"])
    return {"understanding": round(u, 3), "dims": {"who": round(who, 2), "relationship": round(rel, 2), "conflict": round(conflict, 2), "stakes": round(stakes, 2)},
            "gaps": gaps[:6], "debt": round(debt, 3), "unanchored": un}


# ===================================================================== curiosity
def curiosity(A, evs_all, spoken, t1, after_events=()):
    dl = [e for e in spoken if e.kind == "dialogue"]
    sp = [e for e in spoken if e.kind in ("dialogue", "action")]
    tail_txt = " ".join(e.text for e in sp[-2:]) + " " + " ".join(e.text for e in evs_all if e.kind in ("camera", "sound") and e.t1 >= t1 - 3)
    out = {"open": False, "type": "none", "text": "", "answered_in_clip": False, "visual_answer": False, "reason": "", "confidence": 0.5,
           "payoff_after_cut": None, "factor": 0.8}
    qs = [i for i, e in enumerate(dl) if e.text.rstrip('"”’ ').endswith("?")]
    last_sp = sp[-1] if sp else None
    if qs:
        qi = qs[-1]; q = dl[qi]
        replies = [r for r in dl[qi + 1:] if r.who != q.who]
        if not replies:
            out.update(open=True, type="question", text=q.text, confidence=0.80, reason="Final question has no reply inside the clip.", factor=1.0)
        else:
            r = replies[0]
            overlap = W4(q.text) & W4(r.text)
            if not r.text.rstrip().endswith("?") and (lex.ANSWER_OPEN.search(r.text) or overlap):
                out.update(open=False, type="question", text=q.text, answered_in_clip=True, confidence=0.60,
                           reason=f"{r.who or 'Another speaker'} replies inside the clip: “{r.text[:60]}”.", factor=0.45)
            else:
                out.update(open=True, type="question", text=q.text, confidence=0.55, reason="Reply deflects or asks another question.", factor=0.95)
        # the 'fire' case: a generic question whose answer the viewer has already SEEN in the clip
        if out["open"] and lex.GENERIC_Q.match(q.text.strip()):
            before = [e for e in evs_all if e.kind in ("action", "camera") and q.t0 - 10 <= e.t0 < q.t0]
            if any(lex.DANGER_VISUAL.search(e.text) for e in before):
                out.update(open=False, visual_answer=True, answered_in_clip=True, confidence=0.6, factor=0.45,
                           reason=f"“{q.text}” is already answered by what the viewer just saw on screen.")
    if not out["open"] and not out["answered_in_clip"]:
        if lex.RESOLVE.search(tail_txt):
            out.update(type="resolution", reason="Ends on a resolved/soft beat.", factor=0.6, confidence=0.6)
        elif lex.CLIFF_THREAT.search(tail_txt) or lex.CLIFF_REACT.search(tail_txt) or lex.CLIFF_REVEAL.search(tail_txt):
            out.update(open=True, type="tease", text=(last_sp.text[:90] if last_sp else ""), reason="Ends on a threat / reveal / reaction beat with no answer.", factor=0.95, confidence=0.5)
        else:
            out.update(reason="No identifiable open loop at the cut.", factor=0.75, confidence=0.45)
    if after_events:
        nxt = next((e for e in after_events if e.kind == "dialogue"), None)
        if nxt is not None:
            out["payoff_after_cut"] = bool(not nxt.text.rstrip().endswith("?") and (lex.ANSWER_OPEN.search(nxt.text) or (out["text"] and W4(out["text"]) & W4(nxt.text))))
    return out


# ===================================================================== arc
def arc(A, evs_spoken, t0, t1, hook, cliff_final, cv):
    L = max(1.0, t1 - t0)
    ev = [e for e in evs_spoken if e.kind in ("dialogue", "action")]
    # phase windows
    p_ctx = [e for e in ev if t0 + 3.0 <= e.t0 < t0 + 0.45 * L]
    p_esc = [e for e in ev if t0 + 0.30 * L <= e.t0 <= t1]
    ctx_txt = " ".join(e.text for e in p_ctx)
    ctx = clip01(0.45 * cv["dims"]["relationship"] + 0.30 * cv["dims"]["who"] + 0.25 * cv["dims"]["stakes"]) if p_ctx else 0.25 * cv["dims"]["relationship"] + 0.2
    # escalation: does intensity rise (slope) and peak late?
    pts = [((e.t0 - t0) / L, e.inten) for e in ev if e.t0 >= t0 + 3.0]
    esc = 0.3
    if len(pts) >= 4:
        n = len(pts); mx = sum(x for x, _ in pts) / n; my = sum(y for _, y in pts) / n
        den = sum((x - mx) ** 2 for x, _ in pts) or 1e-9
        slope = sum((x - mx) * (y - my) for x, y in pts) / den
        late = [y for x, y in pts if x >= 0.6] or [my]; early = [y for x, y in pts if x < 0.45] or [my]
        esc = clip01(0.35 + 1.1 * slope + 0.8 * (sum(late) / len(late) - sum(early) / len(early)) + 0.15 * (max(y for _, y in pts) >= 0.7))
    phases = {"hook": round(hook, 3), "context": round(ctx, 3), "escalation": round(esc, 3), "cliffhanger": round(cliff_final, 3)}
    v = list(phases.values())
    score = clip01(0.4 * sum(v) / 4 + 0.6 * min(v))
    weakest = min(phases, key=phases.get)
    label = "Complete arc" if min(v) >= 0.45 else {"hook": "Weak opening", "context": "No context beat", "escalation": "Flat middle", "cliffhanger": "No unresolved ending"}[weakest]
    # intensity curve for the UI (every ~2 s)
    curve = []
    for k in range(int(L // 2) + 1):
        a, b = t0 + 2 * k, t0 + 2 * k + 2
        m = [e.inten for e in ev if e.t0 < b and e.t1 > a]
        curve.append(round(max(m) if m else 0.0, 2))
    return {"score": round(score, 3), "phases": phases, "weakest": weakest, "label": label, "curve": curve}
