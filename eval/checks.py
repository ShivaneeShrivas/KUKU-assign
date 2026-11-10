#!/usr/bin/env python3
"""Quality checks that need no human and no API key.
  1. Silver-label test  : the show's writers end every episode on a cliffhanger. Can the *lexical* cliffhanger scorer
                          (episode-end bonus switched OFF) tell those beats apart from ordinary mid-episode line ends?
  2. Sensitivity        : jiggle the rubric weights +/-30% 200 times -> how stable is the top 10 / top 20?
  3. Ablation           : switch each signal off -> how many of the top 10 change?  (shows each signal matters)
Usage: python eval/checks.py --input <folder> --out outputs/eval"""
import argparse, copy, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from promo.engine import Finder, load_cfg


def auroc(pos, neg):
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    ranks, i = {}, 0
    vals = [v for v, _ in allv]
    # average ranks for ties
    sums = {}
    for idx, (v, _) in enumerate(allv, 1): sums.setdefault(v, []).append(idx)
    r_pos = sum(sum(sums[v]) / len(sums[v]) for v in pos)
    n1, n0 = len(pos), len(neg)
    return (r_pos - n1 * (n1 + 1) / 2) / (n1 * n0)


class Dummy:           # an 'episode' whose end never triggers the author bonus
    duration = 1e9


LEAK = __import__("re").compile(r"cut(?:s|ting)? to black|cliffhanger|fade[sd]? (?:out|to black)|holding (?:on|until)", 2)


def _clean(evs):
    out = []
    for e in evs:
        c = copy.copy(e); c.text = LEAK.sub("", e.text); out.append(c)
    return out


def silver(f):
    """positive = the writers' own episode-ending beat; negative = every other legal line-end in the episode.
    Both measured the way a promo would be cut (end_with_hold), with the literal 'cut to black'/'cliffhanger' words
    removed so the scorer cannot read the label off the page."""
    pos, neg = [], []
    for ep in f.eps_list:
        sp = [e for e in f.A.boundary_events(ep) if e.kind != "sound" and f.A.legal_end(ep, e.t1)]
        last = sp[-1]
        for e in sp:
            t1 = f.end_with_hold(ep, e)
            evs, spk = f.clip_events(ep, max(0, t1 - 40), t1)
            s, info = f.A.cliff(Dummy, _clean(evs), t1, _clean(spk))
            if e is last: pos.append(info["lex"] - info["pen"])
            elif t1 < ep.duration - 15: neg.append(info["lex"] - info["pen"])
    return pos, neg


def sig(chosen, k):
    return [tuple((s[0], round(s[1], 1)) for s in c[3]) for c in chosen[:k]]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--input", required=True); ap.add_argument("--out", default="outputs/eval")
    ap.add_argument("--trials", type=int, default=200); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    base_cfg = load_cfg(); f = Finder(a.input, base_cfg); base = f.run(); pool = f.pool
    res = {}
    pos, neg = silver(f)
    res["silver_cliff_auroc"] = round(auroc(pos, neg), 3)
    res["silver_counts"] = {"episode_end_beats": len(pos), "mid_episode_beats": len(neg)}
    res["silver_mean_score_pos_vs_neg"] = [round(sum(pos) / len(pos), 3), round(sum(neg) / len(neg), 3)]
    base_sel = f.select(pool); key10, key20 = set(sig(base_sel, 10)), set(sig(base_sel, 20))
    rnd = random.Random(7)
    hit10, hit20, jac10 = {}, {}, []
    for t in range(a.trials):
        w = {k: v * rnd.uniform(0.7, 1.3) for k, v in base_cfg["weights"].items()}
        z = sum(w.values()); w = {k: v / z for k, v in w.items()}
        sel = f.select(pool, w)
        s10, s20 = set(sig(sel, 10)), set(sig(sel, 20))
        jac10.append(len(s10 & key10) / len(s10 | key10))
        for s_ in key10: hit10[s_] = hit10.get(s_, 0) + (s_ in s10)
        for s_ in key20: hit20[s_] = hit20.get(s_, 0) + (s_ in s20)
    res["sensitivity"] = {"trials": a.trials, "perturbation": "each weight x0.7-1.3, renormalised",
                          "mean_jaccard_top10": round(sum(jac10) / len(jac10), 3),
                          "baseline_top10_still_in_top10_in_>=80%_of_trials": sum(1 for v in hit10.values() if v / a.trials >= 0.8),
                          "baseline_top20_still_in_top20_in_>=80%_of_trials": sum(1 for v in hit20.values() if v / a.trials >= 0.8)}
    res["ablation_top10_promos_that_change"] = {}
    for comp in ("hook", "cliff", "standalone", "arc", "pace", "duration"):
        w = dict(base_cfg["weights"]); w[comp] = 0.0
        z = sum(w.values()); w = {k: v / z for k, v in w.items()}
        res["ablation_top10_promos_that_change"][comp] = 10 - len(set(sig(f.select(pool, w), 10)) & key10)
    json.dump(res, open(os.path.join(a.out, "checks.json"), "w"), indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
