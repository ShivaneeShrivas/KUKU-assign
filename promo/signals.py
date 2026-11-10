"""Deterministic signals. Everything here is plain code: cheap, repeatable, explainable."""
from __future__ import annotations
import re
from collections import Counter, defaultdict
from . import lex

def clip01(x): return 0.0 if x < 0 else 1.0 if x > 1 else x
def sat(n, k=2.0): return clip01(n / k)

WORD = re.compile(r"[A-Za-z']+")
GENERIC_NAMES = {"LORD", "MAID", "JUDGE", "GUARD", "PRIEST", "OFF-SCREEN VOICE", "NOBLEWOMAN", "NOBLEMAN", "MATRIARCH", "CONSTABLE",
                 "INFORMANT", "HOUSEKEEPER", "VILLAGER", "TOWNSMAN", "BUTLER", "FOOTMAN", "CONSPIRATOR", "LOYALIST", "OLD WOMAN"}
STOPWORDS = set("""about above after again against almost already always another because before being below between both
could every first found great hands heart house little might never other people place right shall should since still their there
these thing think those three through under until where which while whole would young yours before herself himself myself
yourself please something nothing everything anyone anything someone really other another those their there where""".split())


def event_stop(text: str):
    """stop-power: how likely this line is to halt a scrolling thumb. returns (score, categories)."""
    hits, cats = [], []
    for cat, (w, r) in lex.STOP.items():
        n = len(r.findall(text))
        if n:
            hits.append(w * (0.75 + 0.25 * min(n, 2) / 2)); cats.append(cat)
    if not hits:
        return 0.0, cats
    hits.sort(reverse=True)
    s = hits[0] + 0.25 * sum(hits[1:3])
    return min(1.0, s), cats


def event_intensity(e) -> float:
    base = {"dialogue": 0.20, "action": 0.22, "sound": 0.08, "camera": 0.10}.get(e.kind, 0.1)
    t = e.text
    inten = base
    if e.kind == "dialogue":
        n_hi = len(lex.TONE_HI.findall(e.tone))
        n_lo = len(lex.TONE_LO.findall(e.tone))
        inten += min(0.45, 0.15 * n_hi) - min(0.2, 0.08 * n_lo)
        inten += 0.15 if "!" in t else 0
        inten += 0.06 if "?" in t else 0
    st, _ = event_stop(t)
    inten += 0.35 * st
    return clip01(inten)


class Analyzer:
    """Holds per-show indexes: character first appearances, story terms, per-event features."""

    def __init__(self, episodes, cfg):
        self.cfg = cfg
        self.eps = {e.num: e for e in episodes}
        self.order = sorted(self.eps)
        for ep in episodes:
            for e in ep.events:
                e.inten = event_intensity(e)
                e.stop, e.cats = event_stop(e.text)
                if e.kind == "dialogue" and lex.TONE_LO.search(e.tone) and not lex.TONE_HI.search(e.tone):
                    e.stop *= 0.55; e.inten *= 0.75      # soft/tender delivery: keyword is probably not a shock
        # character names
        lines = Counter(e.who for ep in episodes for e in ep.events if e.kind == "dialogue" and e.who)
        self.lead = {c for c, _ in lines.most_common(2)}
        names = {c for c, n in lines.items() if n >= 3 and " " not in c and "'" not in c and len(c) > 2
                 and c not in GENERIC_NAMES and not lex.ROLE_WORDS.search(c)}
        self.names = names
        self.name_rx = {c: re.compile(r"\b" + re.escape(c) + r"\b", re.I) for c in names}
        # first appearance (speaking OR mentioned) and per-term episode df
        self.first = {}
        tf, df = Counter(), defaultdict(set)
        for ep in episodes:
            for e in ep.events:
                if e.kind not in ("dialogue", "action"):
                    continue
                present = set()
                if e.kind == "dialogue" and e.who in names:
                    present.add(e.who)
                for c, r in self.name_rx.items():
                    if r.search(e.text):
                        present.add(c)
                for c in present:
                    self.first.setdefault(c, (ep.num, e.t0))
                for w in WORD.findall(e.text.lower()):
                    if len(w) >= 5 and w not in STOPWORDS:
                        tf[w] += 1; df[w].add(ep.num)
        n_eps = max(1, len(episodes))
        self.terms = {w for w, c in tf.items()
                      if 2 <= len(df[w]) <= max(3, int(0.22 * n_eps)) and c >= 5 and c / len(df[w]) >= 2.2
                      and w.upper() not in names}
        self.term_first = {}
        for ep in episodes:
            for e in ep.events:
                if e.kind in ("dialogue", "action"):
                    for w in set(WORD.findall(e.text.lower())):
                        if w in self.terms:
                            self.term_first.setdefault(w, (ep.num, e.t0))

    # ---------- boundaries -------------------------------------------------------
    def boundary_events(self, ep):
        return [e for e in ep.events if e.kind in ("dialogue", "action", "sound")]

    def legal_start(self, ep, t0):
        for e in ep.events:
            if e.kind == "dialogue" and abs(e.t0 - t0) < 0.06 and lex.CONTINUATION.search(e.text):
                return False
            if e.kind == "dialogue" and e.t0 < t0 - 0.05 and e.t1 > t0 + 0.15:
                return False
        return True

    def legal_end(self, ep, t1):
        for e in ep.events:
            if e.kind == "dialogue" and e.t0 < t1 - 0.05 and e.t1 > t1 + 0.15:
                return False
        return True

    # ---------- hook -------------------------------------------------------------
    def hook(self, evs, t0):
        win = [e for e in evs if e.kind in ("dialogue", "action") and e.t0 <= t0 + 3.0]
        if not win:
            return 0.0, {"dead_open": True}
        stops = sorted((e.stop for e in win), reverse=True)
        stop = min(1.0, (stops[0] + 0.25 * sum(stops[1:3])))
        peak = max(e.inten for e in win)
        first = win[0]
        words = len(WORD.findall(first.text))
        punch = 1.0 if words <= 9 else 0.55 if words <= 14 else 0.25
        if first.kind == "dialogue" and re.search(r"[!?]\"?$", first.text.strip()):
            punch = min(1.0, punch + 0.15)
        pen = 0.0
        txt = " ".join(e.text for e in win if e.kind == "dialogue")
        if lex.GREETING.search(first.text): pen += 0.25
        if lex.EXPOSITION.search(txt): pen += 0.15
        if first.kind == "dialogue" and lex.ANAPHORIC_OPEN.search(first.text): pen += 0.12
        if first.kind == "dialogue" and first.off_screen: pen += 0.15      # viewer cannot see who is speaking
        if lex.BACKREF.search(first.text): pen += 0.10
        if first.kind == "action" and first.stop == 0 and not any(e.kind == "dialogue" for e in win): pen += 0.15
        h = clip01(0.50 * stop + 0.30 * peak + 0.20 * punch - pen)
        return h, {"stop": round(stop, 2), "peak": round(peak, 2), "punch": round(punch, 2), "pen": round(pen, 2),
                   "cats": sorted({c for e in win for c in e.cats}), "line": (first.text if first.kind else "")}

    # ---------- cliffhanger ------------------------------------------------------
    def cliff(self, ep, evs_all, t1, evs_spoken):
        """evs_all: every event in clip (incl. camera); evs_spoken: dialogue/action/sound in clip."""
        W = [e for e in evs_all if e.t1 >= t1 - 6.0]
        dl = [e for e in evs_spoken if e.kind == "dialogue"]
        last_d = dl[-1] if dl else None
        last2 = " ".join(e.text for e in dl[-2:])
        la_txt = " ".join(e.text for e in W if e.kind in ("action", "camera"))
        q = 0.30 if last_d and last_d.text.rstrip('"”’ ').endswith("?") else 0.0
        ell = 0.08 if last_d and re.search(r"(\.\.\.|—|-)\"?$", last_d.text.strip()) else 0.0
        rev = 0.30 * sat(len(lex.CLIFF_REVEAL.findall(la_txt)), 3.0)
        thr = 0.30 * sat(len(lex.CLIFF_THREAT.findall(last2)), 2.0)
        snd_txt = " ".join(e.text for e in evs_all if e.kind in ("sound", "camera") and e.t1 >= t1 - 3.0)
        snd = (0.12 if lex.CLIFF_SOUND.search(snd_txt) else 0.0) + (0.10 if re.search(r"cliffhanger|cuts? to black", snd_txt, re.I) else 0.0)
        end_heat = 0.25 * max([e.inten for e in evs_spoken[-3:]] or [0])
        react_txt = " ".join(e.text for e in W if e.kind in ("camera", "action") and e.t1 >= t1 - 4.0)
        react = 0.30 * sat(len(lex.CLIFF_REACT.findall(react_txt)), 3.0)
        lex_score = q + ell + rev + thr + snd + end_heat + react
        pen = 0.0
        tail_txt = " ".join(e.text for e in evs_spoken[-2:]) + " " + " ".join(e.tone for e in dl[-2:])
        if lex.RESOLVE.search(tail_txt): pen += 0.30
        if dl:  # answered-question check
            qi = [i for i, e in enumerate(dl) if e.text.rstrip('"”’ ').endswith("?")]
            if qi and qi[-1] < len(dl) - 1 and not any(re.search(r"\?|\.\.\.$", e.text.strip()) for e in dl[qi[-1] + 1:]):
                if dl[qi[-1] + 1].who != dl[qi[-1]].who:
                    pen += 0.12
        author = 0.25 if (t1 >= ep.duration - 1.5 and pen == 0) else 0.0    # episode end only counts if it isn't a resolution
        score = clip01(lex_score + author - pen)
        return score, {"lex": round(clip01(lex_score), 2), "author": author, "pen": round(pen, 2),
                       "open_question": bool(q), "ep_end": t1 >= ep.duration - 1.5, "react": round(react, 2)}

    # ---------- context debt -----------------------------------------------------
    def debt(self, segs, ep_lookup=None):
        """segs: list of (ep_num, evs_all, t0). returns (debt, details)."""
        present, anchored, text_all = set(), set(), []
        speakers = []
        first_dl = None
        d = 0.0
        missing = []
        for k, (en, evs, t0) in enumerate(segs):
            sp = [e for e in evs if e.kind in ("dialogue", "action")]
            if first_dl is None:
                first_dl = next((e for e in sp if e.kind == "dialogue"), None)
            for i, e in enumerate(sp):
                text_all.append(e.text)
                found = set()
                if e.kind == "dialogue" and e.who in self.names:
                    found.add(e.who); speakers.append(e.who)
                elif e.kind == "dialogue":
                    speakers.append(e.who)
                for c, r in self.name_rx.items():
                    if r.search(e.text):
                        found.add(c)
                if found:
                    # a name is "anchored" only if the VIEWER can learn who it is: a relationship/role word spoken or
                    # described next to it. (A speaker label is not visible to a viewer, so it only anchors its own speaker.)
                    ctx = " ".join(x.text for x in sp[max(0, i - 1): i + 2])
                    role_here = bool(lex.ROLE_WORDS.search(ctx))
                    for c in found:
                        present.add(c)
                        if role_here: anchored.add(c)
        # which characters/terms are introduced inside the clip?
        def intro_inside(c):
            f = self.first.get(c)
            if not f: return True
            for (en, evs, t0) in segs:
                if f[0] == en and evs and evs[0].t0 - 0.1 <= f[1] <= evs[-1].t1 + 0.1:
                    return True
            return False
        for c in sorted(present):
            if intro_inside(c) or c in anchored:
                continue
            w = 0.04 if c in self.lead else 0.12
            d += w
            if c not in self.lead: missing.append(c)
        # third-person pronouns used before any person is named/described inside the clip
        dangling, named_yet = 0, False
        for (en, evs, t0) in segs:
            for e in [x for x in evs if x.kind in ("dialogue", "action")]:
                if any(r.search(e.text) for r in self.name_rx.values()) or lex.ROLE_WORDS.search(e.text) or (e.kind == "action"):
                    named_yet = True
                if not named_yet and lex.PRONOUN3.search(e.text):
                    dangling += 1
        d += min(0.15, 0.05 * dangling)
        # story-dependency prior: later episodes lean on more earlier plot
        d += min(0.12, 0.0025 * (segs[-1][0] - 1))
        n_sp = len({s for s in speakers if s})
        d += 0.06 * max(0, n_sp - 3)
        joined = " ".join(text_all)
        back = lex.BACKREF.findall(joined)
        d += min(0.30, 0.07 * len(back)) + (0.06 if first_dl and lex.BACKREF.search(first_dl.text) else 0)
        if first_dl and lex.ANAPHORIC_OPEN.search(first_dl.text): d += 0.08
        tset = set(WORD.findall(joined.lower())) & self.terms
        tdebt = 0.0
        for w in tset:
            f = self.term_first.get(w)
            inside = f and any(f[0] == en and evs and evs[0].t0 - 0.1 <= f[1] <= evs[-1].t1 + 0.1 for (en, evs, t0) in segs)
            if not inside: tdebt += 0.03
        d += min(0.12, tdebt)
        credit = (0.06 if lex.PREMISE.search(joined) else 0) + (0.03 if lex.ROLE_WORDS.search(joined) else 0)
        d = max(0.0, d - credit)
        return d, {"unanchored": missing, "backrefs": [b if isinstance(b, str) else b[0] for b in back][:4],
                   "speakers": n_sp, "terms": sorted(tset)[:5], "dangling_pronouns": dangling}

    # ---------- pace / escalation ------------------------------------------------
    def pace(self, evs_spoken, t0, t1):
        if t1 <= t0: return 0.0
        iv = sorted((max(e.t0, t0), min(e.t1, t1)) for e in evs_spoken if e.kind in ("dialogue", "action"))
        cov, cur_s, cur_e = 0.0, None, None
        for s, e in iv:
            if cur_e is None or s > cur_e:
                if cur_e is not None: cov += cur_e - cur_s
                cur_s, cur_e = s, e
            else:
                cur_e = max(cur_e, e)
        if cur_e is not None: cov += cur_e - cur_s
        coverage = cov / (t1 - t0)
        L = t1 - t0
        late = [e.inten for e in evs_spoken if e.t0 >= t1 - 0.35 * L] or [0]
        mid = [e.inten for e in evs_spoken if t0 + 0.25 * L <= e.t0 < t1 - 0.35 * L] or [0.2]
        esc = clip01(0.5 + (sum(late) / len(late) - sum(mid) / len(mid)))
        return clip01(0.6 * clip01((coverage - 0.45) / 0.4) + 0.4 * esc), {"coverage": round(coverage, 2), "esc": round(esc, 2)}

    def duration_fit(self, d):
        c = self.cfg["duration"]
        if d < c["min"] or d > c["max"]: return 0.0
        if c["sweet_lo"] <= d <= c["sweet_hi"]: return 1.0
        if d < c["sweet_lo"]: return 0.6 + 0.4 * (d - c["min"]) / (c["sweet_lo"] - c["min"])
        return 0.6 + 0.4 * (c["max"] - d) / (c["max"] - c["sweet_hi"])

    def engine_tag(self, text):
        best, bn = "General drama", 0
        for name, r in lex.ENGINES.items():
            n = len(r.findall(text))
            if n > bn: best, bn = name, n
        return best, bn
