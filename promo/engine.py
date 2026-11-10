"""Candidate generation -> scoring -> context repair -> diverse selection."""
from __future__ import annotations
import re, os
try:
    import tomllib
except ImportError:          # Python < 3.11
    import tomli as tomllib
from dataclasses import dataclass, field, asdict
from .parse import load_show, fmt
from .characters import resolve
from .signals import Analyzer, clip01
from . import lex

HERE = os.path.dirname(__file__)


def load_cfg(path=None):
    with open(path or os.path.join(HERE, "config.toml"), "rb") as f:
        return tomllib.load(f)


@dataclass
class Seg:
    ep: int
    t0: float
    t1: float


@dataclass
class Promo:
    segs: list
    scores: dict
    total: float
    engine: str = ""
    hook_line: str = ""
    cliff_line: str = ""
    why: str = ""
    after_cut: str = ""
    transcript: str = ""
    evidence: dict = field(default_factory=dict)
    landing: str = ""
    cold_open: str = ""
    raw_score: float = 0.0
    grade: str = ""
    release_priority: int = 0
    wave: int = 0
    campaign_eligible: bool = True
    exclusions: list = field(default_factory=list)
    story: dict = field(default_factory=dict)
    spoiler: dict = field(default_factory=dict)
    cold: dict = field(default_factory=dict)
    curiosity: dict = field(default_factory=dict)
    arc: dict = field(default_factory=dict)
    repairs: list = field(default_factory=list)
    concept: dict = field(default_factory=dict)
    ai_why: str = ""
    human: dict = field(default_factory=dict)
    id: str = ""
    rank: int = 0
    slate: bool = False
    llm: dict = field(default_factory=dict)

    @property
    def duration(self):
        return sum(s.t1 - s.t0 for s in self.segs)


class Finder:
    def __init__(self, folder, cfg=None, alias_path=None, title=None):
        self.cfg = cfg or load_cfg()
        self.eps_list = load_show(folder)
        resolve(self.eps_list, alias_path or os.path.join(HERE, "aliases.json"))
        self.A = Analyzer(self.eps_list, self.cfg)
        self.eps = self.A.eps
        self._windows = None
        from .story import StoryModel
        self.title = title or os.path.basename(os.path.normpath(folder))
        self.story = StoryModel(self, self.title)

    # ---------- helpers ----------------------------------------------------------
    def clip_events(self, ep, t0, t1):
        evs = [e for e in ep.events if e.t0 >= t0 - 0.05 and e.t0 < t1 - 0.05 and (e.kind != "dialogue" or e.t1 <= t1 + 0.2)]
        sp = [e for e in evs if e.kind in ("dialogue", "action", "sound")]
        return evs, sp

    def end_with_hold(self, ep, e):
        """end on the line, plus a short reaction hold if the shot continues and nothing new starts."""
        if e.t1 >= ep.duration - 1.5:
            return ep.duration
        nxt = min([x.t0 for x in ep.events if x.kind in ("dialogue", "action") and x.t0 > e.t0 + 0.05 and x.t0 >= e.t1 - 0.05] or [ep.duration])
        cam = [c for c in ep.events if c.kind == "camera" and c.t0 <= e.t1 <= c.t1 + 0.01]
        hold = min(2.5, max(0.0, (cam[0].t1 - e.t1) if cam else 0.0), max(0.0, nxt - e.t1 - 0.05))
        return round(e.t1 + hold, 2)

    # ---------- scoring ----------------------------------------------------------
    def score_segments(self, segs_t, cliff_ep=None):
        """segs_t: [(ep, t0, t1)] in playback order. hook <- first segment, cliffhanger/curiosity <- last, everything else <- all."""
        from . import intel
        A, w, cfg = self.A, self.cfg["weights"], self.cfg
        packs = []
        for (en, t0, t1) in segs_t:
            ep = self.eps[en]
            evs, sp = self.clip_events(ep, t0, t1)
            packs.append((en, evs, sp, t0, t1, ep))
        en0, evs0, sp0, t00, _, ep0 = packs[0]
        hook, hinfo = A.hook(sp0, t00)
        enL, evsL, spL, t0L, t1L, epL = packs[-1]
        cliff_raw, cinfo = A.cliff(epL, evsL, t1L, spL)
        after = [e for e in epL.events if e.kind in ("dialogue", "action") and e.t0 >= t1L - 0.05][:3]
        if not after and (enL + 1) in self.eps:
            after = [e for e in self.eps[enL + 1].events if e.kind in ("dialogue", "action")][:3]
        cur = intel.curiosity(A, evsL, spL, t1L, after)
        cliff = clip01(cliff_raw * cur["factor"])
        cv = intel.cold_view(A, [(p[0], p[1], p[2], p[3], p[4]) for p in packs])
        standalone = 0.5 * (1.0 - clip01(cv["debt"])) + 0.5 * cv["understanding"]
        pace_num = pace_den = 0.0
        for (en, evs, sp, t0, t1, ep) in packs:
            p, pinfo = A.pace(sp, t0, t1)
            pace_num += p * (t1 - t0); pace_den += (t1 - t0)
        pace = pace_num / max(pace_den, 1e-9)
        dur = sum(s[2] - s[1] for s in segs_t)
        dfit = A.duration_fit(dur)
        spo = self.story.spoiler(segs_t)
        main_sp = [e for p in packs for e in p[2]]
        ar = intel.arc(A, main_sp, segs_t[0][1], segs_t[-1][2] if len(segs_t) == 1 else sum(s[2] - s[1] for s in segs_t) + segs_t[0][1], hook, cliff, cv)
        raw = (w["hook"] * hook + w["cliff"] * cliff + w["standalone"] * standalone + w["arc"] * ar["score"] + w["pace"] * pace + w["duration"] * dfit)
        gates = []
        if dfit == 0: gates.append("duration")
        if hinfo.get("dead_open"): gates.append("dead_open")
        if hook < 0.20: gates.append("weak_hook")
        if cliff < 0.15: gates.append("no_cliffhanger")
        if gates: raw *= 0.4
        total = raw * spo["factor"]
        scores = {"hook": round(hook, 3), "cliff": round(cliff, 3), "standalone": round(standalone, 3), "arc": ar["score"],
                  "pace": round(pace, 3), "duration_fit": round(dfit, 3)}
        ev = {"hook": hinfo, "cliff": cinfo, "debt": {"unanchored": cv["unanchored"]}, "gates": gates, "debt_value": cv["debt"],
              "cold": cv, "curiosity": cur, "arc": ar, "spoiler": spo, "raw_total": round(raw, 4)}
        return round(total, 4), scores, ev, packs

    # ---------- candidate generation --------------------------------------------
    def candidates_for_episode(self, ep):
        A, cfg = self.A, self.cfg
        d = cfg["duration"]; s = cfg["select"]
        sp = A.boundary_events(ep)
        starts = [e for e in sp if e.kind in ("dialogue", "action") and A.legal_start(ep, e.t0)]
        hs = {}
        for e in starts:
            win = [x for x in sp if x.t0 >= e.t0 - 0.01 and x.t0 <= e.t0 + 3.0]
            hs[e.idx] = A.hook(win, e.t0)[0]
        top_s = sorted(starts, key=lambda e: -hs[e.idx])[: s["top_k_starts"]]
        first = starts[:1]
        scene_first = []
        for (_, _, st, _) in ep.scenes:
            nxt = [e for e in starts if e.t0 >= st - 0.05]
            if nxt: scene_first.append(nxt[0])
        S = {e.idx: e for e in top_s + first + scene_first}
        ends = []
        for e in sp:
            t1 = self.end_with_hold(ep, e)
            if not A.legal_end(ep, e.t1) or e.kind == "sound" and e.t1 < ep.duration - 3:
                continue
            ends.append((e, t1))
        es = {}
        for e, t1 in ends:
            evs, spk = self.clip_events(ep, max(0, t1 - 40), t1)
            es[e.idx] = A.cliff(ep, evs, t1, spk)[0]
        top_e = sorted(ends, key=lambda x: -es[x[0].idx])[: s["top_k_ends"]]
        last = ends[-1:] if ends else []
        E = {e.idx: (e, t1) for e, t1 in top_e + last}
        out, seen = [], set()
        for si in S.values():
            for (ei, t1) in E.values():
                t0 = si.t0
                dur = t1 - t0
                if dur < d["min"] or dur > d["max"]: continue
                key = (round(t0, 1), round(t1, 1))
                if key in seen: continue
                seen.add(key)
                total, scores, evid, packs = self.score_segments([(ep.num, t0, t1)])
                out.append((total, scores, evid, [(ep.num, t0, t1)]))
        return out

    # ---------- setup windows (cross-segment repair) -----------------------------
    def build_windows(self):
        A, cfg = self.A, self.cfg["setup"]
        W = []
        for en in A.order:
            ep = self.eps[en]
            sp = [e for e in A.boundary_events(ep) if e.kind in ("dialogue", "action")]
            for i in range(len(sp)):
                for n in (1, 2, 3):
                    grp = sp[i:i + n]
                    if len(grp) < n: break
                    t0, t1 = grp[0].t0, max(g.t1 for g in grp)
                    if t1 - t0 > cfg["max_len"] or t1 - t0 < 2.0: continue
                    if grp[0].scene != grp[-1].scene: continue
                    if not A.legal_start(ep, t0) or not A.legal_end(ep, t1): continue
                    first = grp[0]
                    if first.kind == "dialogue" and (lex.ANAPHORIC_OPEN.search(first.text) or lex.GREETING.search(first.text)): continue
                    txt = " ".join(g.text for g in grp)
                    if lex.BACKREF.search(txt): continue
                    h = A.hook(grp, t0)[0]
                    if h < 0.45: continue
                    covered = set()
                    for g in grp:
                        for c, r in A.name_rx.items():
                            if r.search(g.text) or (g.kind == "dialogue" and g.who == c): covered.add(c)
                    anchored = covered if (lex.ROLE_WORDS.search(txt) or any(lex.ROLE_WORDS.search(g.speaker) for g in grp if g.kind == "dialogue")) else set()
                    wt = set(re.findall(r"[a-z']+", txt.lower())) & A.terms
                    W.append({"ep": en, "t0": t0, "t1": t1, "hook": h, "covered": covered, "anchored": anchored, "terms": wt})
        self._windows = W

    LOC_STOP = {"INT", "EXT", "DAY", "NIGHT", "CONTINUOUS", "DAWN", "DUSK", "LATER", "MORNING", "EVENING", "PRE-DAWN", "THE", "OF", "AND", "-", "–"}

    def loc_words(self, en, t):
        ep = self.eps[en]
        for (_, head, a, b) in ep.scenes:
            if a - 0.1 <= t <= b + 0.1:
                return {w for w in re.findall(r"[A-Z']+", head.upper()) if w not in self.LOC_STOP}
        return set()

    def main_profile(self, en, t0, t1):
        evs, sp = self.clip_events(self.eps[en], t0, t1)
        names, terms = set(), set()
        for e in sp:
            if e.kind == "dialogue" and e.who in self.A.names: names.add(e.who)
            for c, r in self.A.name_rx.items():
                if r.search(e.text): names.add(c)
            terms |= set(re.findall(r"[a-z']+", e.text.lower())) & self.A.terms
        return names, terms

    def repair_options(self, segs, k=3, min_gain=0.0):
        """context-repair candidates: <=9s earlier moments, SAME people and thread, evaluated by re-scoring the whole promo."""
        if len(segs) != 1: return []
        en, t0, t1 = segs[0]
        if self._windows is None: self.build_windows()
        base_total, bsc, bev, _ = self.score_segments(segs)
        bcv = bev["cold"]
        if not bcv["gaps"] or bcv["understanding"] >= 0.97: return []
        miss = set(bcv["unanchored"]); m_names, m_terms = self.main_profile(en, t0, t1); m_loc = self.loc_words(en, t0)
        cands = []
        for w in self._windows:
            if (w["ep"], w["t0"]) >= (en, t0 - 5.0) or en - w["ep"] > 8: continue
            if len(m_names & w["covered"]) < min(2, len(m_names)): continue
            if not ((m_terms & w.get("terms", set())) or (m_loc & self.loc_words(w["ep"], w["t0"]))): continue
            dur = (t1 - t0) + (w["t1"] - w["t0"])
            if dur > self.cfg["duration"]["max"]: continue
            pre = w["hook"] + 0.15 * len(miss & w["covered"]) + (0.08 if w["anchored"] else 0) - 0.003 * (en - w["ep"])
            cands.append((pre, w))
        cands.sort(key=lambda x: -x[0])
        out = []
        for _, w in cands[:14]:
            ns = [(w["ep"], w["t0"], w["t1"]), (en, t0, t1)]
            nt, nsc, nev, _ = self.score_segments(ns)
            ug = nev["cold"]["understanding"] - bcv["understanding"]
            fixed = sorted({g["type"] for g in bcv["gaps"]} - {g["type"] for g in nev["cold"]["gaps"]})
            if nt >= base_total + min_gain and (ug > 0.015 or fixed):
                out.append({"segs": ns, "total": nt, "total_before": base_total, "understanding_before": bcv["understanding"],
                            "understanding_after": nev["cold"]["understanding"], "gaps_fixed": fixed, "scores": nsc, "ev": nev,
                            "setup_covers": sorted(miss & w["covered"]), "setup_hook": round(w["hook"], 2)})
        out.sort(key=lambda o: -o["total"])
        return out[:k]

    def safe_recut(self, cand):
        """a clip that DISCLOSES a major reveal is re-cut to end just BEFORE the disclosure line, turning the reveal into the open question."""
        total, sc, ev, segs = cand
        if len(segs) != 1 or not ev["spoiler"]["items"]: return None
        en, t0, t1 = segs[0]; ep = self.eps[en]
        first = min(i["t"] for i in ev["spoiler"]["items"])
        spoken = [e for e in self.A.boundary_events(ep) if e.kind != "sound" and t0 <= e.t0 and e.t1 <= first + 0.05]
        dmin = self.cfg["duration"]["min"]
        for e in reversed(spoken):
            nt1 = min(self.end_with_hold(ep, e), first - 0.05)
            if nt1 - t0 < dmin: break
            if not self.A.legal_end(ep, nt1) and not self.A.legal_end(ep, e.t1): continue
            nt1 = nt1 if self.A.legal_end(ep, nt1) else e.t1
            t, nsc, nev, _ = self.score_segments([(en, t0, nt1)])
            if not nev["gates"]:
                nev["recut_from"] = [round(t1, 2)]; nev["recut_reason"] = "ended before the disclosure at " + fmt(first)
                return (t, nsc, nev, [(en, t0, nt1)])
        return None

    def repair(self, cand):
        """pool-time auto repair: accept the single best option only if the TOTAL score improves."""
        total, scores, evid, segs = cand
        if len(segs) != 1 or evid["cold"]["understanding"] >= 0.9 and evid["debt_value"] < self.cfg["setup"]["min_debt"]: return None
        opts = self.repair_options(segs, k=1, min_gain=self.cfg["setup"]["min_gain"])
        if not opts: return None
        o = opts[0]; ev = o["ev"]; ev["setup_covers"] = o["setup_covers"]
        return (o["total"], o["scores"], ev, o["segs"])

    # ---------- selection --------------------------------------------------------
    @staticmethod
    def overlap(a, b):
        tot = 0.0
        for (e1, s1, t1) in a:
            for (e2, s2, t2) in b:
                if e1 == e2:
                    tot += max(0.0, min(t1, t2) - max(s1, s2))
        shorter = min(sum(t - s for _, s, t in a), sum(t - s for _, s, t in b))
        return tot / max(shorter, 1e-9)

    def generate(self):
        """candidate pool (+ context-repaired variants). Weights are NOT baked in beyond the stored component scores."""
        cfg = self.cfg
        allc = []
        for ep in self.eps_list:
            allc += self.candidates_for_episode(ep)
        self.n_candidates = len(allc)
        allc.sort(key=lambda c: -c[0])
        if cfg["setup"]["enabled"]:
            repaired = []
            for c in allc[:200]:
                if c[2]["debt_value"] >= cfg["setup"]["min_debt"] or c[2]["cold"]["understanding"] < 0.8:
                    r = self.repair(c)
                    if r: repaired.append(r)
            allc += repaired
        extra = []
        for c in allc:
            if c[2]["spoiler"]["level"] in ("critical", "high"):
                r = self.safe_recut(c)
                if r: extra.append(r)
        allc += extra
        self.pool = allc
        return allc

    def rescore(self, c, weights):
        total, sc, ev, segs = c
        raw = (weights["hook"] * sc["hook"] + weights["cliff"] * sc["cliff"] + weights["standalone"] * sc["standalone"] + weights["arc"] * sc["arc"]
               + weights["pace"] * sc["pace"] + weights["duration"] * sc["duration_fit"])
        if ev["gates"]: raw *= 0.4
        return (round(raw * ev["spoiler"]["factor"], 4), sc, ev, segs)

    def select(self, pool, weights=None):
        """rank by spoiler-adjusted score; keep spoiler-flagged clips in the library (so the editor can see them) but never above clean ones."""
        s = self.cfg["select"]
        w = weights or self.cfg["weights"]
        allc = sorted((self.rescore(c, w) for c in pool), key=lambda c: -c[0])
        chosen, per_ep = [], {}
        for c in allc:
            total, scores, evid, segs = c
            raw = total / max(evid["spoiler"]["factor"], 1e-9)
            if raw < s["min_score"] or evid["gates"]: continue
            main_ep = segs[-1][0]
            if per_ep.get(main_ep, 0) >= s["per_episode"]: continue
            if any(self.overlap(segs, o[3]) > s["max_overlap"] for o in chosen): continue
            chosen.append(c); per_ep[main_ep] = per_ep.get(main_ep, 0) + 1
        return chosen

    @staticmethod
    def make_id(p):
        last = p.segs[-1]
        return f"E{last.ep:02d}-{int(round(last.t0 * 10)):04d}" + ("+" if len(p.segs) > 1 else "")

    def finalize(self, promos):
        """re-rank / re-grade / re-optimise after AI or human signals change scores. IDs stay stable."""
        from . import portfolio
        promos.sort(key=lambda p: -p.total)
        for i, p in enumerate(promos, 1):
            p.rank = i; p.grade = self.grade(p.total)
        self.slate_promos = portfolio.optimise(promos, self, self.cfg)
        self.campaign = {"slate_ids": [p.id for p in self.slate_promos], "metrics": portfolio.diversity_metrics(self.slate_promos, self),
                         "top10_by_score": portfolio.diversity_metrics([p for p in promos if p.campaign_eligible][:10], self)}
        for p in promos: p.slate = p in self.slate_promos
        return promos

    def grade(self, total):
        g = self.cfg["grades"]
        return "A" if total >= g["A"] else "B" if total >= g["B"] else "C"

    def run(self, progress=None):
        from . import portfolio
        pool = self.generate()
        chosen = self.select(pool)
        promos = [self.build_promo(c) for c in chosen]
        promos.sort(key=lambda p: -p.total)
        for i, p in enumerate(promos, 1):
            p.rank = i; p.id = self.make_id(p); p.grade = self.grade(p.total)
            segs = [(s.ep, s.t0, s.t1) for s in p.segs]
            p.repairs = [self._repair_view(o) for o in self.repair_options(segs, k=3)] if len(segs) == 1 else []
            p.concept = portfolio.concept(p, self)
        self.slate_promos = portfolio.optimise(promos, self, self.cfg)
        self.all_candidates = sorted(pool, key=lambda c: -c[0])
        self.campaign = {"slate_ids": [p.id for p in self.slate_promos], "metrics": portfolio.diversity_metrics(self.slate_promos, self),
                         "top10_by_score": portfolio.diversity_metrics([p for p in promos if p.campaign_eligible][:10], self)}
        for p in promos: p.slate = p in self.slate_promos
        return promos

    def _repair_view(self, o):
        return {"segments": [{"episode": e, "start": round(a, 2), "end": round(b, 2)} for e, a, b in o["segs"]], "total_before": o["total_before"], "total_after": o["total"],
                "understanding_before": o["understanding_before"], "understanding_after": o["understanding_after"], "gaps_fixed": o["gaps_fixed"],
                "setup_hook": o["setup_hook"], "setup_covers": o["setup_covers"],
                "setup_transcript": self.transcript(self.eps[o["segs"][0][0]], o["segs"][0][1], o["segs"][0][2])}

    # ---------- presentation -----------------------------------------------------
    def transcript(self, ep, t0, t1):
        _, sp = self.clip_events(ep, t0, t1)
        out = []
        for e in sp:
            if e.kind == "dialogue":
                tone = f" ({e.tone})" if e.tone else ""
                out.append(f"[{fmt(e.t0)}] {e.who or e.speaker}{tone}: {e.text}")
            elif e.kind == "action":
                out.append(f"[{fmt(e.t0)}] (action) {e.text}")
            elif e.kind == "sound":
                out.append(f"[{fmt(e.t0)}] (sound) {e.text}")
        return "\n".join(out)

    def after_cut(self, ep, t1, n=3):
        sp = [e for e in ep.events if e.kind in ("dialogue", "action") and e.t0 >= t1 - 0.05]
        src = ep.num
        if not sp and ep.num + 1 in self.eps:
            nxt = self.eps[ep.num + 1]
            sp = [e for e in nxt.events if e.kind in ("dialogue", "action")]
            src = nxt.num
        lines = []
        for e in sp[:n]:
            lines.append(f"(ep{src} {fmt(e.t0)}) " + (f"{e.who}: " if e.kind == "dialogue" else "[action] ") + e.text)
        return "\n".join(lines)

    def build_promo(self, c):
        total, scores, evid, segs_t = c
        segs = [Seg(en, round(a, 2), round(b, 2)) for en, a, b in segs_t]
        A = self.A
        text_parts = []
        for sg in segs:
            text_parts.append(f"--- Episode {sg.ep} {fmt(sg.t0)}-{fmt(sg.t1)} ---\n" + self.transcript(self.eps[sg.ep], sg.t0, sg.t1))
        transcript = "\n".join(text_parts)
        joined = " ".join(l.split(": ", 1)[-1] for l in transcript.splitlines() if not l.startswith("---"))
        engine, _ = A.engine_tag(joined)
        ep0 = self.eps[segs[0].ep]
        _, sp0 = self.clip_events(ep0, segs[0].t0, segs[0].t1)
        win = [e for e in sp0 if e.kind in ("dialogue", "action") and e.t0 <= segs[0].t0 + 3.0]
        hook_line = " / ".join((f'{e.who}: "{e.text}"' if e.kind == "dialogue" else f"[action] {e.text}") for e in win[:2])
        epL = self.eps[segs[-1].ep]
        _, spL = self.clip_events(epL, segs[-1].t0, segs[-1].t1)
        tail = [e for e in spL if e.kind in ("dialogue", "action")][-2:]
        cliff_line = " / ".join((f'{e.who}: "{e.text}"' if e.kind == "dialogue" else f"[action] {e.text}") for e in tail)
        if evid["cliff"]["ep_end"] and evid["cliff"]["author"]: cliff_line += "  [cuts at the episode's own cliffhanger]"
        h, cl, dbt = evid["hook"], evid["cliff"], evid["debt"]
        bits = []
        if h.get("cats"): bits.append(f"hook lands inside 3s ({'+'.join(h['cats'])})")
        else: bits.append("hook is a punchy opening line")
        if cl["open_question"]: bits.append("cuts on an unanswered question")
        elif cl["ep_end"] and cl["author"]: bits.append("cuts at the episode's own cliffhanger")
        else: bits.append("cuts on a high-tension beat")
        und = evid["cold"]["understanding"]
        if und >= 0.88 and not evid["cold"]["gaps"]: bits.append("a new viewer can follow it")
        elif evid["cold"]["gaps"]: bits.append("new-viewer gap: " + evid["cold"]["gaps"][0]["detail"].rstrip("."))
        else: bits.append("mostly self-contained")
        if len(segs) > 1: bits.append("setup segment added to introduce " + ", ".join(n.title() for n in evid.get("setup_covers", [])))
        why = "; ".join(bits).capitalize() + "."
        # landing point: where the story picks up exactly after the cut (deep-link target for "watch the full episode")
        if segs[-1].t1 >= epL.duration - 1.5 and (epL.num + 1) in self.eps: landing = f"Ep{epL.num + 1} 00:00.00 (continues straight from the cut)"
        else: landing = f"Ep{epL.num} {fmt(segs[-1].t1)} (continues straight from the cut)"
        # optional cold-open: if the strongest line is NOT in the first 3s, suggest opening on it (not counted as the promo itself)
        cold = ""
        if scores["hook"] < 0.75 and len(segs) == 1:
            late = [e for e in spL if e.kind == "dialogue" and e.t0 > segs[0].t0 + 6 and e.t1 <= segs[0].t1 - 4 and e.stop * (0.5 + e.inten) >= 0.8
                    and self.A.legal_start(epL, e.t0) and self.A.legal_end(epL, e.t1) and e.t1 - e.t0 <= 5]
            if late:
                b = max(late, key=lambda e: e.stop * (0.5 + e.inten))
                cold = f'Ep{epL.num} {fmt(b.t0)}–{fmt(b.t1)} — {b.who}: "{b.text}" (open on this line, then play the promo from the start)'
        from . import portfolio
        prim, sec, vec = portfolio.engine_vector(joined)
        engine = prim
        story_ctx = self.story.context(segs_t)
        story_ctx["engine_vector"] = vec; story_ctx["secondary_engine"] = sec
        bits2 = []
        cur, ar, spo = evid["curiosity"], evid["arc"], evid["spoiler"]
        bits2.append(f"arc: {ar['label'].lower()}")
        bits2.append("ending " + ("is genuinely open" if cur["open"] else "is answered in the clip" if cur["answered_in_clip"] else "has no clear open loop") + f" ({cur['type']})")
        if spo["level"] not in ("none",): bits2.append(f"spoiler risk {spo['level']}")
        if evid["cold"]["gaps"]: bits2.append("context gap: " + evid["cold"]["gaps"][0]["type"].lower())
        why = why.rstrip(".") + "; " + "; ".join(bits2) + "."
        return Promo(segs=segs, scores=scores, total=total, engine=engine, landing=landing, cold_open=cold,
                     raw_score=evid["raw_total"], story=story_ctx, spoiler=spo, cold=evid["cold"], curiosity=cur, arc=ar, hook_line=hook_line, cliff_line=cliff_line, why=why,
                     after_cut=self.after_cut(epL, segs[-1].t1), transcript=transcript, evidence=evid)
