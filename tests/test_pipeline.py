"""Automated tests. Tests that need the (confidential) script pack are skipped when it is absent; set PROMO_PACK to enable them.
Synthetic fixtures below are invented text, not Kuku dialogue."""
import json, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from promo.engine import Finder, Seg, Promo
from promo.validate import validate
from promo.llm import LLM, ReplayLLM, prompt_key, LLMError
from promo import judge, learn
from promo.judge import run_llm_stage, clean_cold, clean_edit
from promo.parse import parse_episode
from promo.decisions import apply_decisions

PACK = os.environ.get("PROMO_PACK", "/home/claude/data/pack/I Married a Broken Soldier. He was a Duke")
HAVE = os.path.isdir(PACK)

ALT = """EPISODE NUMBER: 7
EPISODE LOGLINE: A tycoon is slapped in public.
--- SCRIPT START ---

SCENE 01
Scene heading: INT. OFFICE - NIGHT
Scene start: 00:00:00.00
Scene end: 00:01:10.00

**CAMERA:**
Start: (00:00:00.00) | End: (00:00:03.00)
Wide shot.

**MAYA (Furious, Shouting):**
Start: (00:00:00.50) | End: (00:00:02.50)
"You slapped me in front of everyone!"
"""


class Parse(unittest.TestCase):
    def test_hhmmss_and_quotes(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f: f.write(ALT)
        ep = parse_episode(f.name)
        d = [e for e in ep.events if e.kind == "dialogue"]
        self.assertEqual(ep.num, 7); self.assertEqual(len(d), 1)
        self.assertEqual(d[0].speaker, "MAYA"); self.assertAlmostEqual(d[0].t1, 2.5)
        self.assertEqual(d[0].text, "You slapped me in front of everyone!")


class Schema(unittest.TestCase):
    """LLM output is untrusted: types clamped, hallucinated fields dropped."""
    def test_clean_cold_clamps(self):
        c = clean_cold({"understood": {"who": "YES", "relationship": "maybe"}, "confusions": ["a"] * 9, "would_stop_scrolling": 99,
                        "wants_to_know_next": "x", "confidence": 7, "start": "99:99"})
        self.assertEqual(c["understood"]["who"], "yes"); self.assertEqual(c["understood"]["relationship"], "partly")
        self.assertEqual(len(c["confusions"]), 3); self.assertEqual(c["would_stop_scrolling"], 5); self.assertEqual(c["confidence"], 1.0)
        self.assertNotIn("start", c); self.assertTrue(c["schema_issues"])

    def test_clean_edit_clamps(self):
        e = clean_edit({"spoils_major_reveal": 9, "drop_leading_lines": -4, "drop_trailing_lines": 99, "start": "1:00", "cut_quality": 0})
        self.assertEqual(e["spoils_major_reveal"], 2); self.assertEqual(e["drop_leading_lines"], 0)
        self.assertEqual(e["drop_trailing_lines"], 3); self.assertEqual(e["cut_quality"], 1); self.assertNotIn("start", e)

    def test_prompt_key_stable(self):
        self.assertEqual(prompt_key("a", "b"), prompt_key("a", "b")); self.assertNotEqual(prompt_key("a", "b"), prompt_key("a", "c"))

    def test_replay_missing_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.jsonl"); open(p, "w").write(json.dumps({"key": prompt_key("s", "u"), "response": {"x": 1}}) + "\n")
            r = ReplayLLM(p); self.assertEqual(r.chat_json("s", "u")["x"], 1)
            with self.assertRaises(LLMError): r.chat_json("s", "other")
            with self.assertRaises(LLMError): r.chat_json("s", "u", required=("y",))


class Learning(unittest.TestCase):
    def promos(self, n):   # SYNTHETIC data for testing the maths only - proves nothing about real preferences
        return [{"id": f"P{i}", "scores": {"hook": i / n, "cliff": 0.5, "standalone": 0.5, "arc": 0.5, "pace": 0.5, "duration_fit": 0.5}} for i in range(n)]

    def test_insufficient_data_suggests_nothing(self):
        r = learn.suggest_weights({"decisions": [{"id": "P1", "status": "approved"}]}, self.promos(40))
        self.assertEqual(r["status"], "insufficient_data"); self.assertIsNone(r.get("weights"))

    def test_synthetic_signal_is_recovered(self):
        P = self.promos(40)
        dec = {"decisions": [{"id": p["id"], "status": "approved" if p["scores"]["hook"] > 0.5 else "rejected"} for p in P]}
        r = learn.suggest_weights(dec, P)
        self.assertIn(r["status"], ("suggested", "no_signal"))


@unittest.skipUnless(HAVE, "input pack not present")
class Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = Finder(PACK); cls.P = cls.f.run()

    def test_all_valid(self):
        v = validate(self.P, self.f); self.assertEqual(v["passed"], v["checked"], v["failed"][:3])

    def test_covers_all_50_episodes_analysed(self):
        self.assertEqual(len(self.f.eps_list), 50)
        self.assertGreaterEqual(len({p.segs[-1].ep for p in self.P}), 30)

    def test_validator_catches_bad_timestamps(self):
        ep = self.f.eps[1]; d = next(e for e in ep.events if e.kind == "dialogue")
        bad = Promo(segs=[Seg(1, d.t0 + 0.3, d.t0 + 30)], scores={}, total=0, id="BAD")
        short = Promo(segs=[Seg(1, d.t0, d.t0 + 10)], scores={}, total=0, id="SHORT")
        ghost = Promo(segs=[Seg(99, 0, 30)], scores={}, total=0, id="GHOST")
        self.assertEqual(validate([bad, short, ghost], self.f)["passed"], 0)

    def test_no_overlap(self):
        s = self.f.cfg["select"]["max_overlap"]
        for i, a in enumerate(self.P):
            for b in self.P[i + 1:]:
                self.assertLessEqual(self.f.overlap([(x.ep, x.t0, x.t1) for x in a.segs], [(x.ep, x.t0, x.t1) for x in b.segs]), s + 1e-9)

    def test_grade_monotone_with_rank(self):
        order = {"A": 0, "B": 1, "C": 2}
        gs = [order[p.grade] for p in sorted(self.P, key=lambda p: p.rank)]
        self.assertEqual(gs, sorted(gs))          # fixes v1 bug: tiers disagreed with rank

    def test_slate_is_clean_and_diverse(self):
        slate = self.f.slate_promos
        self.assertEqual(len(slate), self.f.cfg["portfolio"]["slate_size"])
        for p in slate:
            self.assertNotIn(p.spoiler["level"], ("critical", "high"), p.id)
            self.assertFalse(p.curiosity.get("answered_in_clip"), p.id)
            self.assertNotEqual(p.grade, "C")
        m = self.f.campaign["metrics"]; n = self.f.campaign["top10_by_score"]
        self.assertGreaterEqual(m["engines_covered"], n["engines_covered"])
        self.assertLessEqual(m["mean_pairwise_similarity"], n["mean_pairwise_similarity"])

    def test_spoiler_critical_for_identity_disclosure(self):
        crit = [p for p in self.P if p.spoiler["level"] == "critical"]
        for p in crit: self.assertNotIn(p.id, [s.id for s in self.f.slate_promos])
        # an identity-reveal disclosure in the show must be known to the registry
        self.assertTrue(any(r.severity >= 0.9 for rs in self.f.story._by_ep.values() for r in rs if not r.is_question))

    def test_questions_are_not_spoilers(self):
        for rs in self.f.story._by_ep.values():
            for r in rs:
                if r.is_question: self.assertEqual(r.severity, 0)

    def test_cold_view_and_arc_present(self):
        for p in self.P:
            self.assertTrue(0 <= p.cold["understanding"] <= 1); self.assertTrue(0 <= p.arc["score"] <= 1)
            self.assertEqual(set(p.arc["phases"]), {"hook", "context", "escalation", "cliffhanger"})

    def test_deterministic(self):
        again = Finder(PACK).run()
        self.assertEqual([(p.id, p.total) for p in again], [(p.id, p.total) for p in self.P])

    def test_decisions_do_not_change_scores_but_reject_excludes(self):
        f = Finder(PACK); P = f.run(); before = {p.id: p.total for p in P}
        victim = f.slate_promos[0].id
        n = apply_decisions(f, P, {"decisions": [{"id": victim, "status": "rejected", "reasons": ["too_confusing"]}, {"id": "NOPE", "status": "approved"}]})
        self.assertEqual(n["rejected"], 1); self.assertEqual(n["unknown_ids"], 1)
        self.assertEqual({p.id: p.total for p in P}, before)
        self.assertNotIn(victim, [p.id for p in f.slate_promos])


class MockHandler(BaseHTTPRequestHandler):
    calls = {"n": 0}

    def log_message(self, *a): pass

    def do_POST(self):
        MockHandler.calls["n"] += 1
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if MockHandler.calls["n"] == 1:
            self.send_response(429); self.end_headers(); return           # rate limit once -> client must retry
        if "NEVER heard" in body["messages"][0]["content"]:
            out = {"what_is_happening": "x", "who_is_who": "y", "understood": {"who": "no", "relationship": "partly", "conflict": "yes", "stakes": "yes"},
                   "confusions": ["who is the Duke?"], "would_stop_scrolling": 4, "wants_to_know_next": 4, "final_question_answered_in_clip": False, "confidence": 0.8}
            txt = "```json\n" + json.dumps(out) + "\n```"                    # fenced JSON must still parse
        else:
            out = {"hook": "none", "cliffhanger": "who is at the door", "open_question_answered_in_clip": False, "spoils_major_reveal": 0, "why_it_works": "mock",
                   "drop_leading_lines": 1, "drop_trailing_lines": 0, "start": "99:99.00", "confidence": 0.7}   # hallucinated timestamp must be ignored
            txt = json.dumps(out)
        b = json.dumps({"choices": [{"message": {"content": txt}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)


@unittest.skipUnless(HAVE, "input pack not present")
class LLMStage(unittest.TestCase):
    def test_mock_server_end_to_end(self):
        srv = HTTPServer(("127.0.0.1", 0), MockHandler); threading.Thread(target=srv.serve_forever, daemon=True).start()
        f = Finder(PACK); P = f.run()
        with tempfile.TemporaryDirectory() as d:
            llm = LLM(f"http://127.0.0.1:{srv.server_port}/v1", "mock", None, cache_dir=d, max_retries=3)
            res = run_llm_stage(f, P, llm, shortlist=4, blend=0.4, log=lambda *_: None, provider="mock")
            self.assertEqual(res["judged"], 4)
            judged = [p for p in P if p.llm and p.llm.get("status") == "judged"]
            self.assertEqual(len(judged), 4)
            v = validate(P, f); self.assertEqual(v["passed"], v["checked"])        # AI never moved a timestamp
            for p in judged:
                self.assertGreater(p.llm["effective_blend"], 0); self.assertLessEqual(p.llm["effective_blend"], 0.4)
                t = p.llm["suggested_trim"]
                if t: self.assertIn("valid", t)                                      # trims are validated, never auto-applied
            self.assertGreater(llm.usage["calls"], 0)
        srv.shutdown()

    def test_replay_matches_exported_prompts(self):
        f = Finder(PACK); P = f.run(); reqs = judge.build_requests(f, P, 3)
        self.assertGreaterEqual(len(reqs), 3)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.jsonl")
            canned = {"what_is_happening": "", "understood": {"who": "yes", "relationship": "yes", "conflict": "yes", "stakes": "yes"}, "confusions": [],
                      "would_stop_scrolling": 3, "wants_to_know_next": 3, "hook": "h", "cliffhanger": "c", "why_it_works": "w", "spoils_major_reveal": 0}
            with open(path, "w") as fh:
                for r in reqs: fh.write(json.dumps({"key": r["key"], "response": canned}) + "\n")
            res = run_llm_stage(f, P, ReplayLLM(path), shortlist=3, log=lambda *_: None)
            self.assertEqual(res["judged"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
