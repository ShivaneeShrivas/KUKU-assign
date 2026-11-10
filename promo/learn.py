"""Human-in-the-loop learning. Editors approve / reject promos with reasons; this module turns those decisions into
(1) DESCRIPTIVE feedback (which reasons recur, which rubric component they point at) - valid from the first decision, and
(2) SUGGESTED weights - only when there is enough data to mean anything. It never edits config and never invents data:
below the threshold it says 'insufficient data' and returns no weights."""
from __future__ import annotations
import json, math, random
from collections import Counter

REASONS = {"weak_hook": ("Weak hook", "hook"), "confusing": ("Confusing for a new viewer", "standalone"), "spoiler": ("Spoils a reveal", "spoiler"),
           "no_cliffhanger": ("No real cliffhanger / already answered", "cliff"), "flat": ("Flat / no escalation", "arc"), "repetitive": ("Repeats another promo", "portfolio"),
           "bad_cut": ("Bad cut points / wrong length", "duration_fit"), "off_brand": ("Off-brand / tone mismatch", None), "other": ("Other", None)}
FEATURES = ["hook", "cliff", "standalone", "arc", "pace", "duration_fit"]


def load(path):
    with open(path, encoding="utf-8") as fh: return json.load(fh)


def feedback_summary(decisions):
    ds = decisions.get("decisions", [])
    c = Counter(d["status"] for d in ds)
    rej = Counter(r for d in ds if d["status"] == "rejected" for r in d.get("reasons", []))
    comp = Counter()
    for r, n in rej.items():
        tgt = REASONS.get(r, (None, None))[1]
        if tgt: comp[tgt] += n
    return {"counts": dict(c), "n_decided": c.get("approved", 0) + c.get("rejected", 0), "rejection_reasons": dict(rej.most_common()),
            "points_at_component": dict(comp.most_common())}


def _sigmoid(z): return 1 / (1 + math.exp(-max(-30, min(30, z))))


def _fit(X, y, l2=0.5, iters=400, lr=0.5):
    n, d = len(X), len(X[0]); w = [0.0] * d; b = 0.0
    for _ in range(iters):
        gw = [0.0] * d; gb = 0.0
        for xi, yi in zip(X, y):
            e = _sigmoid(sum(a * c for a, c in zip(w, xi)) + b) - yi
            for j in range(d): gw[j] += e * xi[j]
            gb += e
        for j in range(d): w[j] -= lr * (gw[j] / n + l2 * w[j] / n)
        b -= lr * gb / n
    return w, b


def suggest_weights(decisions, promos_payload, min_n=20, min_per_class=8, seed=3):
    """returns a dict; `status` is 'insufficient_data' | 'no_signal' | 'suggested'. Weights are SUGGESTIONS for a human to adopt."""
    by_id = {p["id"]: p for p in promos_payload}
    rows = [(d["status"], by_id[d["id"]]["scores"]) for d in decisions.get("decisions", []) if d["status"] in ("approved", "rejected") and d["id"] in by_id]
    pos = sum(1 for s, _ in rows if s == "approved"); neg = len(rows) - pos
    base = {"n": len(rows), "approved": pos, "rejected": neg, "min_n": min_n, "min_per_class": min_per_class}
    if len(rows) < min_n or min(pos, neg) < min_per_class:
        return {**base, "status": "insufficient_data", "message": f"Need >= {min_n} decisions with >= {min_per_class} approvals and rejections; have {pos} approved / {neg} rejected. No weights suggested.", "weights": None}
    X = [[sc.get(f, 0.0) for f in FEATURES] for _, sc in rows]; y = [1 if s == "approved" else 0 for s, _ in rows]
    mu = [sum(c) / len(X) for c in zip(*X)]; sd = [max(1e-6, (sum((v - m) ** 2 for v in c) / len(X)) ** 0.5) for c, m in zip(zip(*X), mu)]
    Z = [[(v - m) / s for v, m, s in zip(r, mu, sd)] for r in X]
    # leave-one-out accuracy vs majority baseline (honest check that there is any signal)
    hits = 0
    for i in range(len(Z)):
        w, b = _fit(Z[:i] + Z[i + 1:], y[:i] + y[i + 1:]); hits += (_sigmoid(sum(a * c for a, c in zip(w, Z[i])) + b) >= 0.5) == bool(y[i])
    loo = hits / len(Z); maj = max(pos, neg) / len(rows)
    rnd = random.Random(seed); boots = []
    for _ in range(100):
        idx = [rnd.randrange(len(Z)) for _ in Z]
        w, _b = _fit([Z[i] for i in idx], [y[i] for i in idx]); boots.append([max(0.0, v) for v in w])
    mean = [sum(b[j] for b in boots) / len(boots) for j in range(len(FEATURES))]
    tot = sum(mean) or 1.0
    w = {f: round(m / tot, 3) for f, m in zip(FEATURES, mean)}
    ci = {f: [round(sorted(b[j] for b in boots)[4] / tot, 3), round(sorted(b[j] for b in boots)[94] / tot, 3)] for j, f in enumerate(FEATURES)}
    if loo < maj + 0.05:
        return {**base, "status": "no_signal", "loo_accuracy": round(loo, 3), "majority_baseline": round(maj, 3), "weights": None,
                "message": "Decisions are not predicted better than always guessing the majority class; keep current weights."}
    return {**base, "status": "suggested", "weights": w, "bootstrap_ci_90": ci, "loo_accuracy": round(loo, 3), "majority_baseline": round(maj, 3),
            "message": "Suggestion only. Review, then apply with --apply-weights. Not written to config automatically."}


def _main():
    import argparse, json
    ap = argparse.ArgumentParser(description="Suggest rubric weights from editor decisions (needs enough decisions).")
    ap.add_argument("decisions"); ap.add_argument("promos"); ap.add_argument("--out", default="learned_weights.json")
    a = ap.parse_args()
    dec = json.load(open(a.decisions)); pr = json.load(open(a.promos)); pr = pr["promos"] if isinstance(pr, dict) else pr
    res = suggest_weights(dec, pr)
    json.dump(res, open(a.out, "w"), indent=2); print(json.dumps(res, indent=2)[:1500])


if __name__ == "__main__":
    _main()
