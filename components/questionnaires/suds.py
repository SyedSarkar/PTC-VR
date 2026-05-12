"""
components/questionnaires/suds.py
==================================
Subjective Units of Distress Scale (0-100) — single rating with visual anchors.
Used pre/post each VR session and pre/post each Real Exposure session.
"""

import streamlit as st

import config
from utils.helpers import now_iso
from utils.data_logger import get_logger


def render(code: str, base_path: str, label: str = "SUDS", on_complete=None):
    """
    Render a single SUDS slider and save the rating.

    Args:
        code: participant code
        base_path: e.g. 'vr_exposure/session_1/pre_suds'  (a leaf path)
        label: page label e.g. "Pre-VR SUDS"
    """
    logger = get_logger()
    existing = logger.get(code, base_path)

    # Use safe key (no slashes) for widget keys
    safe_key = base_path.replace("/", "_")

    if existing and isinstance(existing, dict) and existing.get("value") is not None:
        st.success(f"✅ {label} already recorded: {existing['value']}/100")
        if on_complete:
            if st.button("Continue ➜", type="primary", key=f"{safe_key}_continue"):
                on_complete()
        return

    st.markdown(f"## {label} — Subjective Units of Distress Scale")
    st.markdown(
        f"<div class='form-text'>{config.SUDS_INSTRUCTIONS}</div>",
        unsafe_allow_html=True,
    )

    # Visual scale legend
    with st.expander("📖 View Scale Anchors"):
        for val in sorted(config.SUDS_ANCHORS.keys(), reverse=True):
            desc = config.SUDS_ANCHORS[val]
            st.markdown(f"**{val}** — {desc}")

    st.divider()

    # Slider in steps of 5 for finer granularity
    rating = st.slider(
        "Your current distress level (0–100):",
        min_value=0, max_value=100, value=50, step=5,
        key=f"{safe_key}_slider",
    )

    # Show the closest anchor description
    nearest_anchor = min(config.SUDS_ANCHORS.keys(), key=lambda x: abs(x - rating))
    desc = config.SUDS_ANCHORS[nearest_anchor]
    if desc and desc != "—":
        st.markdown(
            f"<div class='scale-text' style='font-size:18px;color:#2c3e50;'>"
            f"<b>{rating}</b> — <i>{desc}</i></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div class='scale-text' style='font-size:18px;color:#2c3e50;'>"
            f"<b>{rating}</b></div>", unsafe_allow_html=True,
        )

    cols = st.columns([1, 1, 1])
    with cols[1]:
        if st.button("Submit ➜", type="primary",
                     use_container_width=True, key=f"{safe_key}_submit"):
            logger.set(code, base_path, {
                "value": int(rating),
                "anchor_label": desc,
                "timestamp": now_iso(),
            })
            logger.log_event(code, "suds", {
                "path": base_path,
                "value": int(rating),
                "label": label,
            })
            st.rerun()
