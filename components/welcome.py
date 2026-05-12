"""
components/welcome.py
======================
Initial landing page. User chooses:
  - New Participant (-> consent flow)
  - Resume as Participant (enter code or roll number)
  - Therapist Login
"""

import streamlit as st

import config
from utils.helpers import init_session_state
from utils.data_logger import get_logger


def render():
    init_session_state()

    st.title("Welcome aboard")
    st.markdown(
        f"<div class='form-text'>"
        f"<i>{config.STUDY_TITLE}</i>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='form-text'>We are pleased to see you here. "
        "Thank you for being part of this research project.</div>",
        unsafe_allow_html=True,
    )

    st.divider()

    cols = st.columns(3)

    with cols[0]:
        st.markdown("### 🆕 New Participant")
        st.markdown(
            "<div class='form-text'>Click below if you are joining the study for the first time.</div>",
            unsafe_allow_html=True,
        )
        if st.button("Start", type="primary", key="welcome_new", use_container_width=True):
            st.session_state["phase"] = "consent"
            st.session_state["user_role"] = "participant"
            st.rerun()

    with cols[1]:
        st.markdown("### ↩️ Resume Participant")
        st.markdown(
            "<div class='form-text'>Enter your participant code or roll number to continue.</div>",
            unsafe_allow_html=True,
        )
        identifier = st.text_input("Code or Roll #:", key="welcome_resume_input",
                                   label_visibility="collapsed",
                                   placeholder="SAD-XXXXXX  or  Roll Number")
        if st.button("Resume", key="welcome_resume", use_container_width=True):
            if not identifier.strip():
                st.error("Please enter your participant code or roll number.")
            else:
                _resume_participant(identifier.strip())

    with cols[2]:
        st.markdown("### 🩺 Therapist Login")
        st.markdown(
            "<div class='form-text'>Authorized study staff: log in to manage participants.</div>",
            unsafe_allow_html=True,
        )
        if st.button("Therapist Login", key="welcome_therapist", use_container_width=True):
            st.session_state["phase"] = "therapist_dashboard"
            st.session_state["user_role"] = "therapist"
            st.rerun()


def _resume_participant(identifier: str):
    """Try resume by code first; fallback to roll number search."""
    logger = get_logger()
    code = None

    if identifier.startswith(config.PARTICIPANT_CODE_PREFIX):
        if logger.participant_exists(identifier):
            code = identifier
        else:
            st.error(f"No participant found with code: {identifier}")
            return
    else:
        # Search by roll number
        code = logger.find_by_roll_number(identifier)
        if not code:
            st.error(f"No participant found with roll number: {identifier}")
            return

    data = logger.load_participant(code) or {}
    meta = data.get("metadata") or {}
    progress = data.get("progress") or {}
    withdrawal = data.get("withdrawal") or {}

    st.session_state["participant_code"] = code
    st.session_state["group"] = meta.get("group")
    st.session_state["metadata"] = meta
    st.session_state["user_role"] = "participant"

    if withdrawal.get("withdrawn"):
        st.session_state["withdrawn"] = True
        st.session_state["phase"] = "withdrawn_confirmed"
    else:
        st.session_state["phase"] = progress.get("current_phase", "pre_assessment")

    st.success(f"Welcome back, {code}! Resuming your study.")
    st.rerun()
