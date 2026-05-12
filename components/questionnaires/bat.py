"""
components/questionnaires/bat.py
=================================
Behavioral Avoidance Task (BAT).
Each scenario rated 0-10 (Not willing — Completely willing).
Slider-based; uses Previous/Next nav like the other scales but does NOT
auto-advance on slider drag (a slider fires on every step, which would be
unusable as an auto-advance trigger).
"""

import streamlit as st

import config
from utils.helpers import safe_progress
from utils.questionnaire_engine import (
    _load_existing_responses,
    _first_unanswered_index,
    _save_item_response,
    _save_completion,
    _view_idx,
    _set_view_idx,
)


def render(code: str, base_path: str, on_complete=None):
    items = config.BAT_SCENARIOS
    total = len(items)
    existing = _load_existing_responses(code, base_path)
    default_idx = _first_unanswered_index(existing, total)

    safe_key = base_path.replace("/", "_")
    view_idx = _view_idx(safe_key, default_idx, total)

    st.markdown("## Behavioral Avoidance Task")
    st.markdown(
        f"<div class='form-text'>{config.BAT_INSTRUCTIONS}</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    if view_idx >= total:
        st.success("✅ Behavioral Avoidance Task already complete.")
        if on_complete:
            if st.button("Continue ➜", type="primary", key=f"{safe_key}_continue"):
                on_complete()
        return

    st.progress(safe_progress(view_idx, total))
    st.markdown(
        f"<div class='progress-text'>Scenario {view_idx + 1} of {total}</div>",
        unsafe_allow_html=True,
    )

    scenario = items[view_idx]
    st.markdown(f"<div class='item-title'>{scenario}</div>", unsafe_allow_html=True)

    # Pre-fill with saved value if this scenario was rated before
    saved_entry = existing.get(str(view_idx)) or existing.get(view_idx) or {}
    saved_value = saved_entry.get("willingness") if isinstance(saved_entry, dict) else None
    default_value = int(saved_value) if isinstance(saved_value, (int, float)) else 5

    rating = st.slider(
        "Your willingness to attempt this right now:",
        min_value=0, max_value=10, value=default_value, step=1,
        key=f"{safe_key}_slider_{view_idx}",
    )

    anchors = st.columns(3)
    anchors[0].markdown(
        "<div style='color:#555;font-size:13px;'>0 = Not willing at all</div>",
        unsafe_allow_html=True,
    )
    anchors[2].markdown(
        "<div style='text-align:right;color:#555;font-size:13px;'>10 = Completely willing</div>",
        unsafe_allow_html=True,
    )

    def _save_and_advance():
        _save_item_response(code, base_path, view_idx, {
            "item_index": view_idx,
            "scenario": scenario,
            # Aliases so the dashboard's generic scale-table reader and the
            # BAT-specific reader both find the data they expect.
            "willingness": int(rating),
            "raw_value": int(rating),
            "scored_value": int(rating),
            "item_text": scenario,
            "label": f"{int(rating)} / 10",
        })
        refreshed = _load_existing_responses(code, base_path)
        if _first_unanswered_index(refreshed, total) >= total:
            total_score = sum(int(v.get("willingness", v.get("raw_value", 0)))
                              for v in refreshed.values() if isinstance(v, dict))
            _save_completion(code, base_path, total_score=total_score)
        _set_view_idx(safe_key, view_idx + 1)

    # Nav row: Previous / Save & Next
    cols = st.columns([2, 4, 2])
    with cols[0]:
        if st.button("← Previous", disabled=(view_idx == 0),
                     use_container_width=True,
                     key=f"{safe_key}_prev_{view_idx}"):
            _set_view_idx(safe_key, view_idx - 1)
            st.rerun()
    with cols[2]:
        if st.button("Next →", type="primary",
                     use_container_width=True,
                     key=f"{safe_key}_next_{view_idx}"):
            _save_and_advance()
            st.rerun()
