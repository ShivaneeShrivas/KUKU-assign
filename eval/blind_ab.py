#!/usr/bin/env python3
"""Blind A/B test: tool's promo vs a RANDOM valid clip (same episode, similar length, legal cut points).
  python eval/blind_ab.py make  --input <folder> --out outputs/eval --n 12     -> blind_ab_sheet.md + answer_key.json + responses.csv
  python eval/blind_ab.py score --out outputs/eval                             -> win-rate + p-value after raters fill responses.csv
Give the sheet to 2-3 people (not the answer key). Question for each pair: 'Which would make you keep watching?'"""
import argparse, csv, json, math, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from promo.engine import Finder
from promo.parse import fmt


def random_clip(f, ep, avoid, rnd, dur_target):
    sp = [e for e in f.A.boundary_events(ep) if e.kind in ("dialogue", "action") and f.A.legal_start(ep, e.t0)]
    ends = [e for e in f.A.boundary_events(ep) if e.kind != "sound" and f.A.legal_end(ep, e.t1)]
    for _ in range(500):
        s = rnd.choice(sp); e = rnd.choice(ends)
        d = e.t1 - s.t0
        if abs(d - dur_target) > 8 or d < 20 or d > 60: continue
        if f.overlap([(ep.num, s.t0, e.t1)], [avoid]) > 0.2: continue
        return (ep.num, s.t0, e.t1)
    return None


def p_two_sided(k, n):
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n) if k >= n / 2 else 1.0


def make(a):
    f = Finder(a.input); P = f.run(); rnd = random.Random(a.seed)
    picks = [p for p in P if len(p.segs) == 1][: a.n]
    os.makedirs(a.out, exist_ok=True)
    key, sheet = [], ["# Blind A/B sheet", "", "For each pair read both transcripts. Pick the one you'd keep watching if it appeared in your feed (A or B). Fill `responses.csv`.", ""]
    for i, p in enumerate(picks, 1):
        sg = p.segs[0]; ep = f.eps[sg.ep]
        r = random_clip(f, ep, (sg.ep, sg.t0, sg.t1), rnd, p.duration)
        if not r: continue
        t_tool = f.transcript(ep, sg.t0, sg.t1); t_rand = f.transcript(ep, r[1], r[2])
        tool_is_a = rnd.random() < 0.5
        A, B = (t_tool, t_rand) if tool_is_a else (t_rand, t_tool)
        key.append({"pair": i, "tool_is": "A" if tool_is_a else "B", "promo_id": p.id, "tool": [sg.ep, sg.t0, sg.t1], "random": list(r)})
        sheet += [f"## Pair {i}", "", "### A", "```", A, "```", "", "### B", "```", B, "```", ""]
    json.dump(key, open(os.path.join(a.out, "answer_key.json"), "w"), indent=1)
    open(os.path.join(a.out, "blind_ab_sheet.md"), "w", encoding="utf-8").write("\n".join(sheet))
    with open(os.path.join(a.out, "responses.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["rater", "pair", "choice(A/B)"])
    print(f"wrote {len(key)} pairs to {a.out}/ (keep answer_key.json away from raters)")


def score(a):
    key = {k["pair"]: k["tool_is"] for k in json.load(open(os.path.join(a.out, "answer_key.json")))}
    wins = n = 0
    for r in csv.DictReader(open(os.path.join(a.out, "responses.csv"))):
        c = (r.get("choice(A/B)") or "").strip().upper()
        if c in ("A", "B") and int(r["pair"]) in key:
            n += 1; wins += (c == key[int(r["pair"])])
    print(f"tool picked over random in {wins}/{n} = {wins / max(n, 1):.0%}; two-sided sign-test p = {p_two_sided(wins, n):.3f}" if n else "no responses yet")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["make", "score"]); ap.add_argument("--input"); ap.add_argument("--out", default="outputs/eval")
    ap.add_argument("--n", type=int, default=12); ap.add_argument("--seed", type=int, default=11); a = ap.parse_args()
    make(a) if a.cmd == "make" else score(a)
