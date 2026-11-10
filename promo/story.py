"""Story intelligence: characters, relationships, threads, episode arcs and a REVEAL REGISTRY.
Everything is derived from the screenplay itself (no outside knowledge), so it works on a new show.
The registry is what separates a *curiosity-building question* ("You're the Duke?") from a *spoiling disclosure*
("Alexander Ashburton. The rightful Duke.")."""
from __future__ import annotations
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from . import lex

SEV = {"identity": 1.00, "survival": 0.90, "culprit": 0.80, "secret": 0.45, "tease": 0.45}
LEVELS = [(0.90, "critical"), (0.60, "high"), (0.40, "medium"), (0.01, "low"), (0.0, "none")]


def level_of(sev: float) -> str:
    for th, name in LEVELS:
        if sev >= th: return name
    return "none"


@dataclass
class Reveal:
    ep: int
    t0: float
    t1: float
    kind: str            # identity | survival | culprit | secret | tease
    key: str             # the term the reveal is about (duke, alive, poisoned ...)
    line: str
    speaker: str
    severity: float      # 0..1
    first: bool          # first disclosure of this key in the show
    premise: bool        # key appears in the show title -> central twist
    is_question: bool


class StoryModel:
    def __init__(self, finder, title: str = ""):
        self.f, self.A = finder, finder.A
        self.title = title
        self.title_terms = {w for w in re.findall(r"[a-z]{4,}", title.lower())} - {"married", "broken", "he", "was"} | \
                           {w for w in re.findall(r"[a-z]{3,}", title.lower()) if re.fullmatch(lex.TITLE_ROLES, w)}
        self.n_eps = len(finder.eps_list)
        self._characters(); self._relations(); self._arcs(); self._threads(); self._reveals()

    # ------------------------------------------------------------------ characters & relations
    def _characters(self):
        ch = defaultdict(lambda: {"lines": 0, "first_ep": 10**6, "eps": set(), "scenes": set(), "intensity": 0.0})
        for ep in self.f.eps_list:
            for e in ep.events:
                if e.kind == "dialogue" and e.who:
                    c = ch[e.who]; c["lines"] += 1; c["first_ep"] = min(c["first_ep"], ep.num); c["eps"].add(ep.num)
                    c["scenes"].add((ep.num, e.scene)); c["intensity"] += e.inten
        self.chars = {k: v for k, v in ch.items() if v["lines"] >= 3}
        for k, v in self.chars.items():
            v["intensity"] = round(v["intensity"] / v["lines"], 3); v["n_eps"] = len(v["eps"])

    def _relations(self):
        co = Counter(); conflict = Counter(); romance = Counter(); spouse = Counter(); kin = {}; eps = defaultdict(set)
        for ep in self.f.eps_list:
            by_scene = defaultdict(list)
            for e in ep.events:
                if e.kind == "dialogue" and e.who in self.chars: by_scene[e.scene].append(e)
            for sc, es in by_scene.items():
                who = sorted({e.who for e in es})
                for i, a in enumerate(who):
                    for b in who[i + 1:]:
                        co[(a, b)] += 1; eps[(a, b)].add(ep.num)
                        mine = [e for e in es if e.who in (a, b)]
                        txt = " ".join(e.text for e in mine)
                        hi = sum(e.inten for e in mine) / max(1, len(mine))
                        conflict[(a, b)] += (1 if hi > 0.5 else 0) + len(lex.STOP["confront"][1].findall(txt)) * 0.3
                        romance[(a, b)] += len(lex.ENGINES2["Romance"].findall(txt)) * 0.5
                        spouse[(a, b)] += len(re.findall(r"\b(?:my|your) (?:wife|husband)\b", txt, re.I))
            for e in ep.events:
                if e.kind == "dialogue":
                    m = re.match(r"^([A-Z]+)'S ([A-Z ]+)$", e.speaker.upper().strip())
                    if m and canon(m.group(1)) in self.chars:
                        kin[(canon(m.group(1)), e.who)] = m.group(2).title()
        self.kin = kin
        self.edges = []
        for (a, b), n in co.items():
            c, r = conflict[(a, b)], romance[(a, b)]
            best_a = max((p for p in spouse if a in p), key=lambda p: spouse[p], default=None)
            best_b = max((p for p in spouse if b in p), key=lambda p: spouse[p], default=None)
            mutual = best_a == (a, b) == best_b and spouse[(a, b)] >= 3
            lab = kin.get((a, b)) or kin.get((b, a)) or ("Spouses" if mutual else "")
            typ = "romance" if (r >= 3 and r > 2.5 * c) or lab == "Spouses" else "conflict" if c >= 1.0 else "alliance"
            if lab and lab != "Spouses" and typ == "alliance": typ = "kin"
            self.edges.append({"a": a, "b": b, "weight": n, "type": typ, "label": lab, "conflict": round(c, 1), "romance": round(r, 1),
                               "eps": sorted(eps[(a, b)])})
        self.edges.sort(key=lambda x: -x["weight"])

    # ------------------------------------------------------------------ arcs & threads
    def _arcs(self):
        self.ep_arc = {}
        for ep in self.f.eps_list:
            ev = [e for e in ep.events if e.kind in ("dialogue", "action")]
            if not ev: continue
            n = int(ep.duration) + 1; curve = [0.0] * n
            for e in ev:
                for s in range(int(e.t0), min(n, int(e.t1) + 1)): curve[s] = max(curve[s], e.inten)
            pk = max(range(n), key=lambda i: curve[i])
            pos = ep.num / max(1, self.n_eps)
            self.ep_arc[ep.num] = {"mean": round(sum(e.inten for e in ev) / len(ev), 3), "peak": round(curve[pk], 2), "peak_t": pk,
                                   "act": "Act I – setup" if pos <= 0.2 else "Act II – escalation" if pos <= 0.75 else "Act III – payoff",
                                   "position": round(pos, 2), "curve": [round(x, 2) for x in curve[::2]]}

    def _threads(self):
        """story threads = the strongest character dyads (who is in conflict / love / alliance with whom, and across which episodes)."""
        self.threads = []
        for e in self.edges[:40]:
            if e["weight"] < 4: continue
            self.threads.append({"name": f"{e['a'].title()} × {e['b'].title()}", "type": e["type"], "label": e["label"], "terms": [e["a"].lower(), e["b"].lower()],
                                 "eps": e["eps"], "span": [e["eps"][0], e["eps"][-1]], "weight": e["weight"]})
            if len(self.threads) >= 10: break

    # ------------------------------------------------------------------ reveal registry
    def _reveals(self):
        raw = []
        for ep in self.f.eps_list:
            for e in ep.events:
                if e.kind not in ("dialogue", "action"): continue
                q = e.kind == "dialogue" and e.text.rstrip('"”’ ').endswith("?")
                kind = key = None
                for k, rx in lex.REVEAL_PATTERNS:
                    m = rx.search(e.text)
                    if m:
                        kind = k
                        mt = re.search(lex.TITLE_ROLES, m.group(0), re.I)
                        key = (mt.group(0).lower() if mt else ("alive" if k == "survival" else (re.findall(r"[a-z]{5,}", m.group(0).lower()) or [k])[-1]))
                        break
                if not kind and lex.TEASE_PATTERN.search(e.text) and re.search(lex.TITLE_ROLES, e.text, re.I):
                    kind, key = "tease", re.search(lex.TITLE_ROLES, e.text, re.I).group(0).lower()
                if kind and kind == "identity" and key in ("lord", "lady") and not q:   # honorifics are not identity twists
                    if not re.search(r"rightful|true|real|hidden", e.text, re.I): kind = None
                if kind:
                    raw.append((ep.num, e, kind, key, q))
        seen = {}
        self.reveals = []
        for en, e, kind, key, q in raw:
            first = (kind, key) not in seen and not q
            if not q: seen.setdefault((kind, key), (en, e.t0))
            premise = key in self.title_terms
            sev = SEV[kind] * (1.0 if (first or premise) else 0.7) * (1.0 if premise else 0.85)
            if q: sev = 0.0
            self.reveals.append(Reveal(en, e.t0, e.t1, kind, key, e.text[:140], e.who or "ACTION", round(sev, 2), first, premise, q))
        self.reveals.sort(key=lambda r: (r.ep, r.t0))
        self._by_ep = defaultdict(list)
        for r in self.reveals: self._by_ep[r.ep].append(r)

    def spoiler(self, segs):
        """segs: [(ep, t0, t1)] -> risk dict. Only DISCLOSURES inside the clip count; open questions are curiosity, not spoilers."""
        items, worst = [], 0.0
        for en, t0, t1 in segs:
            for r in self._by_ep.get(en, []):
                if r.t0 >= t0 - 0.05 and r.t1 <= t1 + 0.2 and not r.is_question and r.severity > 0:
                    items.append(r); worst = max(worst, r.severity)
        teased = [r for en, t0, t1 in segs for r in self._by_ep.get(en, []) if r.is_question and t0 - 0.05 <= r.t0 <= t1]
        lvl = level_of(worst)
        return {"level": lvl, "severity": round(worst, 2), "factor": {"critical": 0.50, "high": 0.72, "medium": 0.90}.get(lvl, 1.0),
                "items": [{"ep": r.ep, "t": r.t0, "kind": r.kind, "key": r.key, "line": r.line, "severity": r.severity, "first": r.first, "premise": r.premise} for r in items][:4],
                "curiosity_questions": [r.line for r in teased][:2]}

    # ------------------------------------------------------------------ per-promo narrative context
    def context(self, segs):
        present = Counter(); logl = []
        for en, t0, t1 in segs:
            ep = self.f.eps[en]; logl.append(ep.logline)
            for e in ep.events:
                if t0 - 0.05 <= e.t0 < t1 and e.kind == "dialogue" and e.who in self.chars: present[e.who] += 1
        names = [n for n, _ in present.most_common(4)]
        rel = [x for x in self.edges if x["a"] in names and x["b"] in names][:3]
        en = segs[-1][0]; arc = self.ep_arc.get(en, {})
        pn = set(names)
        th = [t["name"] for t in self.threads if en in t["eps"] and {x.upper() for x in t["terms"]} <= pn][:2]
        return {"characters": [{"name": n, "lines_in_clip": present[n], "first_seen_ep": self.chars[n]["first_ep"], "role": self._role(n)} for n in names],
                "relations": [{"a": r["a"], "b": r["b"], "type": r["type"], "label": r["label"]} for r in rel],
                "logline": logl[-1], "act": arc.get("act", ""), "position": arc.get("position", 0), "threads": th}

    def _role(self, n):
        for (a, b), lab in self.kin.items():
            if b == n: return f"{lab} of {a.title()}"
        return "lead" if n in self.A.lead else ""

    def summary(self):
        return {"characters": [{"name": k, **{x: (sorted(v[x])[:60] if x == "eps" else v[x]) for x in ("lines", "first_ep", "n_eps", "intensity")}} for k, v in sorted(self.chars.items(), key=lambda kv: -kv[1]["lines"])[:14]],
                "edges": [e for e in self.edges if e["a"] in list(self.chars) and e["b"] in list(self.chars)][:30],
                "threads": self.threads, "reveals": [asdict(r) for r in self.reveals if not r.is_question and r.severity >= 0.4],
                "arcs": {str(k): {x: v[x] for x in ("mean", "peak", "peak_t", "act", "position", "curve")} for k, v in self.ep_arc.items()}}


def canon(label):
    from .characters import canon_label
    return canon_label(label)
