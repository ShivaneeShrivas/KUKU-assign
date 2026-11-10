"""Creative portfolio optimizer: individual score RANK is not the same thing as campaign RELEASE PRIORITY.
A campaign needs different hooks (revenge vs romance vs mystery...), different characters, spread over the story,
and no spoilers - so the next promo to release is the one with the best *marginal* value given what is already out."""
from __future__ import annotations
import math, re
from collections import Counter
from . import lex
from .intel import W4

ENGINE_ORDER = list(lex.ENGINES2)


def pretty(n):
    return n.title().replace("'S", "'s")


def engine_vector(text):
    c = {k: len(r.findall(text)) for k, r in lex.ENGINES2.items()}
    tot = sum(c.values())
    if tot == 0: return "General drama", "", {k: 0.0 for k in c}
    order = sorted(c, key=lambda k: (-c[k], ENGINE_ORDER.index(k)))
    prim = order[0]; sec = order[1] if c[order[1]] >= 0.6 * c[prim] and c[order[1]] > 0 else ""
    return prim, sec, {k: round(v / tot, 3) for k, v in c.items()}


def concept(p, finder):
    """what is this promo ABOUT: engine + who + which story thread."""
    ctx = p.story or {}
    chars = [c["name"] for c in ctx.get("characters", [])[:2]]
    return {"engine": p.engine, "chars": chars, "threads": ctx.get("threads", []),
            "terms": sorted(W4(" ".join(l.split(": ", 1)[-1] for l in p.transcript.splitlines() if not l.startswith("---")))
                            & finder.A.terms | set())[:12],
            "key": f"{p.engine} · {' × '.join(pretty(c) for c in chars) or 'ensemble'}"}


def sim(a, b):
    ca, cb = a.concept, b.concept
    j = lambda x, y: len(set(x) & set(y)) / max(1, len(set(x) | set(y)))
    return 0.40 * (ca["engine"] == cb["engine"]) + 0.30 * j(ca["chars"], cb["chars"]) + 0.15 * (bool(set(ca["threads"]) & set(cb["threads"]))) \
        + 0.15 * j(ca["terms"], cb["terms"])


def eligible(p, cfg):
    why = []
    if p.spoiler.get("level") in cfg["block_levels"]: why.append(f"spoiler risk: {p.spoiler['level']}")
    if p.curiosity.get("answered_in_clip"): why.append("ending is answered inside the clip")
    if p.grade == "C": why.append("grade C")
    if (p.human or {}).get("status") == "rejected": why.append("rejected by editor")
    if p.evidence.get("gates"): why.append("failed hard gate: " + ",".join(p.evidence["gates"]))
    return why


def optimise(promos, finder, cfg):
    """greedy marginal-gain selection over ALL promos -> release_priority; first `slate_size` eligible ones form the recommended slate."""
    pc = cfg["portfolio"]
    for p in promos:
        p.exclusions = eligible(p, pc); p.campaign_eligible = not p.exclusions
    pool = [p for p in promos if p.campaign_eligible]
    chosen, order = [], []
    while pool:
        best, bv = None, -1
        engines = {c.engine for c in chosen}; eps = [c.segs[-1].ep for c in chosen]
        for p in pool:
            ms = max((sim(p, c) for c in chosen), default=0.0)
            v = p.total * (1 - pc["lambda_similarity"] * ms) + (pc["new_engine_bonus"] if p.engine not in engines else 0) \
                + (pc["episode_spread_bonus"] if all(abs(p.segs[-1].ep - e) >= pc["min_episode_gap"] for e in eps) else 0) \
                - (0.03 if p.spoiler.get("level") == "medium" else 0)
            if v > bv: best, bv = p, v
        chosen.append(best); pool.remove(best); best.concept["marginal_value"] = round(bv, 3)
        best.concept["max_similarity_to_previous"] = round(max((sim(best, c) for c in chosen[:-1]), default=0.0), 2)
    n = len(chosen)
    for i, p in enumerate(chosen, 1):
        p.release_priority = i
        p.wave = 1 if i <= 3 else 2 if i <= 7 else 3 if i <= pc["slate_size"] else 0
    rest = [p for p in promos if not p.campaign_eligible]
    for j, p in enumerate(sorted(rest, key=lambda x: -x.total), n + 1):
        p.release_priority = j; p.wave = 0
    slate = [p for p in chosen[: pc["slate_size"]]]
    return slate


def diversity_metrics(ps, finder):
    if not ps: return {}
    ec = Counter(p.engine for p in ps); n = len(ps)
    H = -sum((c / n) * math.log(c / n) for c in ec.values()); Hn = H / math.log(len(lex.ENGINES2) + 1) if True else 0
    pair = [sim(a, b) for i, a in enumerate(ps) for b in ps[i + 1:]]
    return {"n": n, "engines_covered": len(ec), "engines_total": len(lex.ENGINES2) + 1, "engine_entropy": round(Hn, 3),
            "mean_pairwise_similarity": round(sum(pair) / max(1, len(pair)), 3), "distinct_episodes": len({p.segs[-1].ep for p in ps}),
            "episode_range": [min(p.segs[-1].ep for p in ps), max(p.segs[-1].ep for p in ps)],
            "distinct_lead_pairs": len({tuple(p.concept["chars"]) for p in ps}), "mean_score": round(sum(p.total for p in ps) / n, 3),
            "spoiler_clean": sum(1 for p in ps if p.spoiler.get("level") in ("none", "low")), "engine_counts": dict(ec)}
