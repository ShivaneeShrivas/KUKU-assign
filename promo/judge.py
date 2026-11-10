"""LLM stage v2 - ONLY the judgement code cannot make.
  cold reader : sees ONLY the clip transcript. Do the 4 pillars (who / relationship / conflict / stakes) land for a stranger?
                is the final question answered inside the clip?
  editor      : sees what happens right AFTER the cut, the episode blurb and the show premise. Is the ending genuinely unanswered?
                does the clip spoil a major reveal? is the cut at the strongest unresolved beat?
Safety model: LLM output is untrusted. It never supplies timestamps (only 'drop N lines'), every field is type-checked and clamped,
trims are validated and re-scored but NEVER auto-applied, and the AI can only DEMOTE (raise spoiler risk / lower score) - an engine hard gate cannot be overridden upward."""
from __future__ import annotations
import re
from .parse import fmt
from .llm import prompt_key

COLD_SYS = ("You are a viewer scrolling a short-drama app who has NEVER heard of this show. You see only the transcript of one promo clip. "
            "Speaker names are shown so you can tell voices apart. Judge ONLY what is on the page - do not guess backstory. Be strict; 5 is rare. "
            "Reply with ONE JSON object: {\"what_is_happening\": str, \"who_is_who\": str, "
            "\"understood\": {\"who\": \"yes|partly|no\", \"relationship\": \"yes|partly|no\", \"conflict\": \"yes|partly|no\", \"stakes\": \"yes|partly|no\"}, "
            "\"confusions\": [up to 3 short strings], \"would_stop_scrolling\": 1-5, \"wants_to_know_next\": 1-5, "
            "\"final_question_answered_in_clip\": true|false, \"open_question\": str, \"confidence\": 0-1, \"reasoning\": str (max 40 words)}")
EDIT_SYS = ("You are a short-drama promo editor. A promo must (1) hook in the first 3 seconds, (2) make sense to a stranger, (3) escalate, and "
            "(4) cut on a genuinely UNANSWERED moment so the viewer must watch on - without spoiling a major reveal. You see the numbered transcript, "
            "the lines that play immediately AFTER the cut, an episode blurb and the show premise. Reply with ONE JSON object: "
            "{\"hook\": str (quote the hooking line or 'none'), \"cliffhanger\": str (the open question left at the cut), "
            "\"open_question_answered_in_clip\": true|false, \"answered_by_what_follows\": true|false, "
            "\"spoils_major_reveal\": 0|1|2 (2 = discloses a central twist such as a hidden identity, a survival, a culprit), \"spoiler_note\": str, "
            "\"cut_quality\": 1-5, \"would_release_first\": true|false, \"why_it_works\": str (max 25 words), \"risks\": str, "
            "\"drop_leading_lines\": 0-3, \"drop_trailing_lines\": 0-3, \"confidence\": 0-1, \"reasoning\": str (max 40 words)}. "
            "Only suggest dropping lines if they weaken the hook or resolve the cliffhanger.")
COLD_REQ = ("understood", "confusions", "would_stop_scrolling", "wants_to_know_next")
EDIT_REQ = ("hook", "cliffhanger", "why_it_works", "spoils_major_reveal")
_TS = re.compile(r"^\[[0-9:.]+\] ")


def numbered(promo):
    lines, n = [], 0
    for ln in promo.transcript.splitlines():
        if ln.startswith("---"):
            lines.append("[CUT TO ANOTHER MOMENT]"); continue
        n += 1; lines.append("L%d %s" % (n, _TS.sub("", ln)))
    return "\n".join(lines)


def cold_prompt(p): return COLD_SYS, numbered(p)


def edit_prompt(finder, p):
    ep = finder.eps[p.segs[-1].ep]
    user = (f"SHOW PREMISE: {finder.title}\nEPISODE BLURB: {ep.logline}\n\nTRANSCRIPT:\n{numbered(p)}\n\n"
            f"WHAT PLAYS IMMEDIATELY AFTER THE CUT:\n{p.after_cut or '(end of available material)'}")
    return EDIT_SYS, user


def build_requests(finder, promos, shortlist):
    """deterministic: same engine output -> same prompts -> same keys. This is what makes offline/batch answering safe."""
    out = []
    for p in promos[:shortlist]:
        for kind, (s, u) in (("cold", cold_prompt(p)), ("editor", edit_prompt(finder, p))):
            out.append({"key": prompt_key(s, u), "promo_id": p.id, "kind": kind, "system": s, "user": u})
    return out


# ------------------------------------------------------------------ validation (the LLM is untrusted)
def _num(v, lo, hi, default):
    try: return max(lo, min(hi, float(v)))
    except Exception: return default


def _bool(v): return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "yes"))


def clean_cold(d):
    iss = []
    u = d.get("understood") if isinstance(d.get("understood"), dict) else {}
    und = {}
    for k in ("who", "relationship", "conflict", "stakes"):
        v = str(u.get(k, "")).lower().strip()
        if v not in ("yes", "partly", "no"): iss.append(f"understood.{k} invalid"); v = "partly"
        und[k] = v
    conf = d.get("confusions") if isinstance(d.get("confusions"), list) else []
    return {"what_is_happening": str(d.get("what_is_happening", ""))[:240], "who_is_who": str(d.get("who_is_who", ""))[:240], "understood": und,
            "confusions": [str(x)[:140] for x in conf[:3]], "would_stop_scrolling": int(round(_num(d.get("would_stop_scrolling"), 1, 5, 3))),
            "wants_to_know_next": int(round(_num(d.get("wants_to_know_next"), 1, 5, 3))),
            "final_question_answered_in_clip": _bool(d.get("final_question_answered_in_clip")), "open_question": str(d.get("open_question", ""))[:200],
            "confidence": round(_num(d.get("confidence"), 0, 1, 0.5), 2), "reasoning": str(d.get("reasoning", ""))[:300], "schema_issues": iss}


def clean_edit(d):
    return {"hook": str(d.get("hook", ""))[:200], "cliffhanger": str(d.get("cliffhanger", ""))[:220],
            "open_question_answered_in_clip": _bool(d.get("open_question_answered_in_clip")), "answered_by_what_follows": _bool(d.get("answered_by_what_follows")),
            "spoils_major_reveal": int(round(_num(d.get("spoils_major_reveal"), 0, 2, 0))), "spoiler_note": str(d.get("spoiler_note", ""))[:240],
            "cut_quality": int(round(_num(d.get("cut_quality"), 1, 5, 3))), "would_release_first": _bool(d.get("would_release_first")),
            "why_it_works": str(d.get("why_it_works", ""))[:220], "risks": str(d.get("risks", ""))[:220],
            "drop_leading_lines": int(_num(d.get("drop_leading_lines"), 0, 3, 0)), "drop_trailing_lines": int(_num(d.get("drop_trailing_lines"), 0, 3, 0)),
            "confidence": round(_num(d.get("confidence"), 0, 1, 0.5), 2), "reasoning": str(d.get("reasoning", ""))[:300]}


def llm_score(c, e):
    u = sum({"yes": 1.0, "partly": 0.5, "no": 0.0}[v] for v in c["understood"].values()) / 4
    s = (0.30 * (c["would_stop_scrolling"] - 1) / 4 + 0.22 * (c["wants_to_know_next"] - 1) / 4 + 0.25 * u + 0.15 * (e["cut_quality"] - 1) / 4
         + 0.08 * (1.0 if e["would_release_first"] else 0.0))
    s -= 0.25 * (1 if (e["open_question_answered_in_clip"] or c["final_question_answered_in_clip"]) else 0)
    s -= 0.10 * min(3, len(c["confusions"])) / 3
    s -= 0.15 * e["spoils_major_reveal"] / 2
    return max(0.0, min(1.0, s)), u


def disagreements(p, c, e):
    """where the AI and the rule engine disagree -> a human should look. (Disagreement is information, not an error.)"""
    d = []
    cur = p.curiosity
    ai_answered = e["open_question_answered_in_clip"] or c["final_question_answered_in_clip"]
    if cur.get("open") and ai_answered: d.append("Rules say the ending is open; AI says it is answered inside the clip.")
    if cur.get("answered_in_clip") and not ai_answered: d.append("Rules say the ending is answered; AI says it is still open.")
    lvl = p.spoiler.get("level", "none")
    if e["spoils_major_reveal"] >= 1 and lvl in ("none", "low"): d.append("AI sees a spoiler the reveal registry did not detect.")
    if e["spoils_major_reveal"] == 0 and lvl in ("critical", "high"): d.append("Registry flags a spoiler the AI did not see.")
    if p.cold["understanding"] >= 0.8 and len(c["confusions"]) >= 2: d.append("Rules think a stranger understands; AI lists multiple confusions.")
    if p.cold["understanding"] < 0.65 and len(c["confusions"]) == 0: d.append("Rules see context gaps; AI had no confusion.")
    return d


def suggested_trim(finder, p, e):
    lead, trail = e["drop_leading_lines"], e["drop_trailing_lines"]
    if (lead == 0 and trail == 0) or len(p.segs) != 1: return None
    sg = p.segs[0]; ep = finder.eps[sg.ep]
    _, sp = finder.clip_events(ep, sg.t0, sg.t1)
    sp = [x for x in sp if x.kind in ("dialogue", "action")]
    out = {"drop_leading_lines": lead, "drop_trailing_lines": trail, "valid": False, "reason": ""}
    if len(sp) - lead - trail < 3: out["reason"] = "would leave <3 lines"; return out
    t0 = sp[lead].t0 if lead else sg.t0
    t1 = sg.t1 if not trail else finder.end_with_hold(ep, sp[len(sp) - trail - 1])
    d = finder.cfg["duration"]
    if not (d["min"] <= t1 - t0 <= d["max"]): out["reason"] = f"duration {t1 - t0:.1f}s outside {d['min']}-{d['max']}"; return out
    if not (finder.A.legal_start(ep, t0) and finder.A.legal_end(ep, t1)): out["reason"] = "cut would split a spoken line"; return out
    tot, sc, ev, _ = finder.score_segments([(sg.ep, t0, t1)])
    out.update(valid=True, start=round(t0, 2), end=round(t1, 2), projected_total=tot, projected_delta=round(tot - p.total, 3),
               projected_spoiler=ev["spoiler"]["level"], reason="validated by code; NOT applied - editor decides")
    return out


def run_llm_stage(finder, promos, llm, shortlist=40, blend=0.40, log=print, provider=""):
    done = missing = 0
    for p in promos[:shortlist]:
        try:
            c = clean_cold(llm.chat_json(*cold_prompt(p), required=COLD_REQ))
            e = clean_edit(llm.chat_json(*edit_prompt(finder, p), required=EDIT_REQ))
        except Exception as ex:
            p.llm = {"status": "unavailable", "error": str(ex)[:160]}; missing += 1; continue
        ls, und = llm_score(c, e)
        dis = disagreements(p, c, e)
        conf = round(((c["confidence"] + e["confidence"]) / 2) * (0.85 if dis else 1.0), 2)
        eff = blend * conf                                  # low-confidence AI moves the score less
        before = p.total
        p.total = round((1 - eff) * p.total + eff * ls, 4)
        # AI may only RAISE spoiler risk, never lower a rule-based flag
        if e["spoils_major_reveal"] == 2 and p.spoiler["level"] in ("none", "low", "medium"):
            prev = p.spoiler.get("factor", 1.0)
            p.spoiler = {**p.spoiler, "level": "high", "level_source": "ai", "factor": 0.72, "ai_note": e["spoiler_note"]}
            p.total = round(p.total * 0.72 / max(prev, 1e-9), 4)
        elif e["spoils_major_reveal"] == 1 and p.spoiler["level"] == "none":
            p.spoiler = {**p.spoiler, "level": "low", "level_source": "ai", "ai_note": e["spoiler_note"]}
        if c["final_question_answered_in_clip"] or e["open_question_answered_in_clip"]:
            p.curiosity = {**p.curiosity, "ai_says_answered": True}
        p.llm = {"status": "judged", "provider": provider or getattr(llm, "provider", ""), "model": getattr(llm, "model", ""), "cold": c, "editor": e,
                 "llm_score": round(ls, 3), "understood_mean": round(und, 2), "engine_score": before, "effective_blend": round(eff, 3), "confidence": conf,
                 "disagreements": dis, "suggested_trim": suggested_trim(finder, p, e), "needs_human_review": bool(dis) or conf < 0.5}
        if e["why_it_works"]: p.ai_why = e["why_it_works"]
        done += 1
    finder.finalize(promos)
    return {"judged": done, "unavailable": missing}
