"""
components/waiting_phase.py
============================
Informational waiting period for VR/CBT groups (~15 days).
NOT enforced — participant can proceed at any time.
"""

import datetime
import streamlit as st

import config
from utils.helpers import next_phase as _next_phase
from utils.data_logger import get_logger


def render():
    code = st.session_state.get("participant_code")
    group = st.session_state.get("group")
    if not code:
        st.error("No participant code in session.")
        return

    logger = get_logger()
    progress = logger.get(code, "progress") or {}
    pre_done_data = logger.get(code, "assessments/pre") or {}
    pre_done_at_iso = pre_done_data.get("battery_completed_timestamp") if isinstance(pre_done_data, dict) else None

    st.header("Waiting Period")

    days_recommended = config.WAITING_PERIOD_DAYS
    days_passed = None
    if pre_done_at_iso:
        try:
            pre_dt = datetime.datetime.fromisoformat(pre_done_at_iso.replace("Z", ""))
            days_passed = (datetime.datetime.utcnow() - pre_dt).days
        except Exception:
            days_passed = None

    msg = (
        f"<div class='form-text'>"
        f"Thank you for completing the pre-assessment. As part of the study design, "
        f"we recommend a waiting period of approximately <b>{days_recommended} days</b> "
        f"before continuing with the next phase. "
        f"</div>"
    )
    st.markdown(msg, unsafe_allow_html=True)

    if days_passed is not None:
        if days_passed >= days_recommended:
            st.success(f"✅ Approximately {days_passed} day(s) have passed. You may proceed.")
        else:
            st.info(
                f"⏳ Approximately {days_passed} day(s) since pre-assessment. "
                f"Recommended wait: {days_recommended} days. "
                f"You may still proceed if needed."
            )

    st.divider()
    st.markdown(
        "<div class='form-text'>You can return to this page at any time. "
        "When you're ready, click the button below to proceed.</div>",
        unsafe_allow_html=True,
    )

    if st.button("Continue to Post-Assessment 1 ➜", type="primary"):
        nxt = _next_phase("waiting_period", group)
        st.session_state["phase"] = nxt or "post1_assessment"
        logger.save_progress(code, {
            "current_phase": st.session_state["phase"],
            "completed_phases": (
                (logger.get(code, "progress/completed_phases") or [])
                + ["waiting_period"]
            ),
        })
        st.rerun()
