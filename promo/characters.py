from __future__ import annotations
"""Resolve speaker labels to canonical characters.
Auto rule: strip honorifics (LADY/LORD/THE/ELDER...) and merge labels that reduce to the same
token. Optional aliases.json (human-in-the-loop) handles role labels like THE FORMER GROOM -> GERALD."""
import json, os, re
from collections import Counter, defaultdict

TITLES = {"LADY", "LORD", "THE", "ELDER", "NOBLE", "SIR", "DAME", "MR", "MRS", "MS", "DR", "OLD", "YOUNG"}


def canon_label(label: str) -> str:
    toks = [t for t in re.split(r"\s+", label.upper().strip()) if t]
    core = [t for t in toks if t not in TITLES]
    return " ".join(core) if core else label.upper().strip()


def resolve(episodes, alias_path: str | None = None):
    aliases = {}
    if alias_path and os.path.exists(alias_path):
        aliases = {k.upper(): v.upper() for k, v in json.load(open(alias_path)).items()}
    counts = Counter()
    for ep in episodes:
        for e in ep.events:
            if e.kind == "dialogue":
                e.who = aliases.get(e.speaker.upper(), aliases.get(canon_label(e.speaker), canon_label(e.speaker)))
                counts[e.who] += 1
    # merge "JULIANA" variants like "JULIANA'S MAID"? keep distinct; just return counts
    return counts


def character_index(episodes, min_lines=3):
    """first appearance (ep, t) and number of lines per canonical character; also name regexes."""
    first, lines = {}, Counter()
    for ep in episodes:
        for e in ep.events:
            if e.kind == "dialogue" and e.who:
                lines[e.who] += 1
                first.setdefault(e.who, (ep.num, e.t0))
    names = {c for c, n in lines.items() if n >= min_lines and len(c) > 2 and c not in {"LORD", "MAID", "JUDGE", "GUARD", "PRIEST", "OFF-SCREEN VOICE", "NOBLEWOMAN", "NOBLEMAN"}}
    return first, lines, names
