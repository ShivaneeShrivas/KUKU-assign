"""Optional Streamlit wrapper:  streamlit run app.py
Upload a zip of timestamped episode .txt files -> runs the same pipeline as run.py -> shows the Promo Desk dashboard.
Content is processed in a temp folder and deleted. (The dashboard itself is a single file; run.py works without Streamlit.)"""
import io, os, shutil, tempfile, zipfile
import streamlit as st, streamlit.components.v1 as components
from promo.engine import Finder, load_cfg
from promo.validate import validate
from promo.report import write_all
import time

st.set_page_config(page_title="Promo Desk", layout="wide")
title = st.text_input("Show title", "My show")
up = st.file_uploader("Zip of episode .txt files", type="zip")
if st.button("Find promos") and up:
    tmp = tempfile.mkdtemp()
    try:
        zipfile.ZipFile(io.BytesIO(up.read())).extractall(tmp)
        root = next((r for r, _, fs in os.walk(tmp) if any(x.endswith(".txt") for x in fs)), tmp)
        t0 = time.time(); cfg = load_cfg(); f = Finder(root, cfg, None, title); promos = f.run(); v = validate(promos, f)
        meta = {"show": title, "episodes": len(f.eps_list), "events": sum(len(e.events) for e in f.eps_list), "candidates_scored": f.n_candidates,
                "mode": "rules only (no AI judgement)", "generated": time.strftime("%Y-%m-%d %H:%M"), "weights": cfg["weights"], "config": cfg,
                "runtime_s": round(time.time() - t0, 1)}
        out = os.path.join(tmp, "out"); write_all(promos, f, out, meta, v, None, None)
        st.success(f"{len(promos)} promos from {len(f.eps_list)} episodes; cuts validated {v['passed']}/{v['checked']}")
        components.html(open(os.path.join(out, "dashboard.html"), encoding="utf-8").read(), height=1000, scrolling=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
