"""Parse Kuku-style timestamped screenplays into a flat list of timed events.

Deliberately tolerant: it keys on the two things every file has (a header line
ending in ':' / '**' and a 'Start: (..) | End: (..)' line) instead of the exact
layout, so a new show with small format drift still loads.
"""
from __future__ import annotations
import re, glob, os
from dataclasses import dataclass, field

TS = r"(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)"          # [hh:]mm:ss[.ff]
RE_TIMES = re.compile(r"Start:\s*\(?\s*" + TS + r"\s*\)?\s*\|\s*End:\s*\(?\s*" + TS + r"\s*\)?", re.I)
RE_HEADER = re.compile(r"^\s*\*{0,2}\s*([A-Z][A-Z0-9 .,'\-]*?)\s*(?:\(([^)]*)\))?\s*(?:\(([^)]*)\))?\s*:?\s*\*{0,2}\s*:?\s*$")
RE_SCENE = re.compile(r"^\s*SCENE\s+(\d+)", re.I)
RE_HEAD = re.compile(r"^\s*Scene heading:\s*(.+)$", re.I)
NON_SPEECH = {"CAMERA", "ACTION", "SOUND FX", "SOUND", "SFX", "MUSIC", "TEXT", "SUPER", "TITLE"}


def _sec(h, m, s):
    return (int(h) if h else 0) * 3600 + int(m) * 60 + float(s)


@dataclass
class Event:
    ep: int
    idx: int
    kind: str            # dialogue | action | camera | sound
    t0: float
    t1: float
    text: str
    speaker: str = ""    # raw label
    who: str = ""        # canonical character (filled by characters.py)
    tone: str = ""
    scene: int = 0
    off_screen: bool = False


@dataclass
class Episode:
    num: int
    path: str
    logline: str = ""
    continuity: str = ""
    events: list = field(default_factory=list)
    scenes: list = field(default_factory=list)   # (scene_no, heading, t0, t1)
    duration: float = 0.0

    def spoken(self):
        return [e for e in self.events if e.kind in ("dialogue", "action", "sound")]


def parse_episode(path: str, fallback_num: int | None = None) -> Episode:
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    m = re.search(r"EPISODE NUMBER:\s*(?:Episode\s*)?(\d+)", raw, re.I)
    num = int(m.group(1)) if m else (fallback_num or 0)
    ep = Episode(num=num, path=path)
    m = re.search(r"EPISODE LOGLINE:\s*(.+)", raw, re.I)
    ep.logline = m.group(1).strip() if m else ""
    m = re.search(r"CONTINUITY NOTES:\s*(.+)", raw, re.I)
    ep.continuity = m.group(1).strip() if m else ""
    body = raw.split("SCRIPT START", 1)[-1].split("SCRIPT END", 1)[0]
    lines = [l.rstrip() for l in body.splitlines()]

    scene_no, scene_head, scene_t = 0, "", [0.0, 0.0]
    i, idx = 0, 0
    while i < len(lines):
        ln = lines[i]
        ms = RE_SCENE.match(ln)
        if ms:
            scene_no = int(ms.group(1)); i += 1; continue
        mh = RE_HEAD.match(ln)
        if mh:
            scene_head = mh.group(1).strip(); i += 1; continue
        mt = re.match(r"\s*Scene (start|end):\s*" + TS, ln, re.I)
        if mt:
            v = _sec(*mt.groups()[1:])
            if mt.group(1).lower() == "start":
                scene_t = [v, v]
            else:
                scene_t[1] = v
                ep.scenes.append((scene_no, scene_head, scene_t[0], scene_t[1]))
            i += 1; continue
        hm = RE_HEADER.match(ln) if ln.strip().startswith("**") or ln.strip().endswith(":**") else None
        if hm and i + 1 < len(lines) and RE_TIMES.search(lines[i + 1]):
            label = hm.group(1).strip()
            paren = [p for p in (hm.group(2), hm.group(3)) if p]
            tt = RE_TIMES.search(lines[i + 1]).groups()
            t0, t1 = _sec(*tt[0:3]), _sec(*tt[3:6])
            j = i + 2
            buf = []
            while j < len(lines) and lines[j].strip() and not RE_TIMES.search(lines[j]) \
                    and not (lines[j].strip().startswith("**") and j + 1 < len(lines) and RE_TIMES.search(lines[j + 1])):
                buf.append(lines[j].strip()); j += 1
            text = " ".join(buf).strip()
            if label in NON_SPEECH:
                kind = {"CAMERA": "camera", "ACTION": "action"}.get(label, "sound")
                ev = Event(ep.num, idx, kind, t0, t1, text, scene=scene_no)
            else:
                off = any("off-screen" in p.lower() or "o.s" in p.lower() for p in paren)
                tone = ", ".join(p for p in paren if "off-screen" not in p.lower())
                ev = Event(ep.num, idx, "dialogue", t0, t1, text.strip('"“” '), speaker=label,
                           tone=tone, scene=scene_no, off_screen=off)
            ep.events.append(ev); idx += 1
            i = j; continue
        i += 1
    ep.events.sort(key=lambda e: (e.t0, e.t1, e.idx))
    for k, e in enumerate(ep.events):
        e.idx = k
    ep.duration = max([e.t1 for e in ep.events] + [s[3] for s in ep.scenes] + [0])
    return ep


def load_show(folder: str) -> list[Episode]:
    files = sorted(glob.glob(os.path.join(folder, "**", "*.txt"), recursive=True))
    eps = []
    for n, f in enumerate(files, 1):
        mnum = re.search(r"episode[-_ ]?0*(\d+)", os.path.basename(f), re.I)
        ep = parse_episode(f, int(mnum.group(1)) if mnum else n)
        if ep.events:
            eps.append(ep)
    eps.sort(key=lambda e: e.num)
    return eps


def fmt(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 60):02d}:{t % 60:05.2f}"
