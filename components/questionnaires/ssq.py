"""
components/questionnaires/ssq.py
=================================
Simulator Sickness Questionnaire - 16 items, 0-3 scale.
Used pre/post each VR session.
"""

import streamlit as st

import config
from utils.questionnaire_engine import run_single_scale_questionnaire
from utils.data_logger import get_logger
from utils.helpers import now_iso


def render_motion_sickness_check(code: str, base_path: str) -> bool | None:
    """
    Returns True/False (selection made) or None (still pending).
    Saves the result at {base_path}/motion_sick.
    """
    logger = get_logger()
    existing = logger.get(code, f"{base_path}/motion_sick")
    if existing is not None:
        return bool(existing.get("value")) if isinstance(existing, dict) else bool(existing)

    # Use safe key (no slashes) for widget keys
    safe_key = base_path.replace("/", "_")

    st.markdown("### Are you motion sick now?")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("✓ Yes", type="primary", use_container_width=True, key=f"{safe_key}_ms_yes"):
            logger.set(code, f"{base_path}/motion_sick", {"value": True, "timestamp": now_iso()})
            st.rerun()
    with col3:
        if st.button("✗ No", type="secondary", use_container_width=True, key=f"{safe_key}_ms_no"):
            logger.set(code, f"{base_path}/motion_sick", {"value": False, "timestamp": now_iso()})
            st.rerun()
    return None


def render(code: str, base_path: str, on_complete=None, ask_motion_sick: bool = True):
    """
    Args:
        code: participant code
        base_path: e.g. 'vr_exposure/session_1/pre_ssq'
        ask_motion_sick: whether to prompt the Yes/No motion-sickness question first
    """
    if ask_motion_sick:
        ms = render_motion_sickness_check(code, base_path)
        if ms is None:
            return  # still waiting

    run_single_scale_questionnaire(
        code=code,
        base_path=base_path,
        title="Simulator Sickness Questionnaire (SSQ)",
        instructions=config.SSQ_INSTRUCTIONS,
        items=config.SSQ_ITEMS,
        scale_labels=config.SSQ_LABELS,
        scale_values=[0, 1, 2, 3],
        on_complete=on_complete,
    )
