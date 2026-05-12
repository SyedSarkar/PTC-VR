"""
components/ptc_phase.py
========================
Orchestrates the 4-session PTC Training phase (Group A only).
Each session: FAT -> Sentence Completion -> THERAPIST APPROVAL GATE.

After each session the participant is shown a "session complete — please
sign out" screen. They cannot start the next session until the therapist
explicitly approves it in the dashboard. This enforces the inter-session
spacing the study protocol requires (typically 7+ days).
"""

import streamlit as st

import config
from utils.helpers import next_phase as _next_phase
from utils.data_logger import get_logger

from components.tasks import fat, sentence_completion


def _session_complete(code: str, session_num: int) -> bool:
    """A session is complete when both FAT and SentenceCompletion are done."""
    logger = get_logger()
    fat_data = logger.get(code, f"ptc_training/session_{session_num}/fat") or {}
    sc_data = logger.get(code, f"ptc_training/session_{session_num}/sentence_completion") or {}
    return bool(fat_data.get("completed_timestamp")) and bool(sc_data.get("completed_timestamp"))


def _fat_complete(code: str, session_num: int) -> bool:
    logger = get_logger()
    data = logger.get(code, f"ptc_training/session_{session_num}/fat") or {}
    return bool(data.get("completed_timestamp"))


def _save_current_session(code: str, session_num: int):
    """Keep progress.current_session in sync with the active PTC session."""
    logger = get_logger()
    logger.save_progress(code, {
        "current_phase": "ptc_training",
        "current_session": int(session_num),
    })


def _render_waiting_screen(session_num: int, group: str):
    """Shown when participant has completed session_num but therapist has
    not yet approved continuation. Always offers Sign Out."""
    is_final = session_num >= config.PTC_NUM_SESSIONS
    next_label = "Post-Assessment 1" if is_final else f"Session {session_num + 1}"

    st.success(f"🎉 Session {session_num} complete!")
    st.markdown(
        f"<div class='form-text'>"
        f"Thank you for completing this session. Your therapist will let you "
        f"know when to return for <b>{next_label}</b> (typically after about "
        f"7 days).<br><br>"
        f"Please <b>sign out now</b> using the button in the sidebar."
        f"</div>",
        unsafe_allow_html=True,
    )
    st.info(
        "⏳ This screen will remain here until your therapist approves the "
        "next step. You can safely sign out and return later."
    )


def render():
    code = st.session_state.get("participant_code")
    group = st.session_state.get("group")
    if not code or group != "PTC":
        st.error("PTC training is only available to participants in the PTC group.")
        return

    logger = get_logger()

    st.header("PTC Training (Proactive Thought Control)")
    st.markdown(
        "<div class='form-text'>This phase consists of 4 training sessions. "
        "Each session has two tasks: a <b>Free Association Task</b> and a "
        "<b>Sentence Completion Task</b>. Sessions are completed in order, "
        "with therapist-approved breaks between them.</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    # ------------------------------------------------------------------
    # Determine which session this participant is currently on.
    # Rule: walk forward; for each session N:
    #   - if not _session_complete(N) -> we are working on N
    #   - if _session_complete(N) and gate ptc_session_N not approved
    #     -> we are waiting on N's gate
    #   - if _session_complete(N) and gate approved -> move on
    # If all 4 are complete + approved -> advance to post1_assessment
    # ------------------------------------------------------------------
    for current in range(1, config.PTC_NUM_SESSIONS + 1):
        if not _session_complete(code, current):
            _save_current_session(code, current)
            break

        gate_key = f"ptc_session_{current}"
        if not logger.is_gate_approved(code, gate_key):
            _save_current_session(code, current)
            _render_waiting_screen(current, group)
            return
    else:
        # All sessions complete AND approved -> advance to post1
        st.success("🎉 You've completed all 4 PTC training sessions!")
        st.balloons()
        if st.button("Continue to Post-Assessment 1 ➜", type="primary"):
            nxt = _next_phase("ptc_training", group)
            st.session_state["phase"] = nxt or "post1_assessment"
            logger.save_progress(code, {
                "current_phase": st.session_state["phase"],
                "current_session": 0,
                "completed_phases": (
                    (logger.get(code, "progress/completed_phases") or [])
                    + ["ptc_training"]
                ),
            })
            st.rerun()
        return

    # ------------------------------------------------------------------
    # Pre-session welcome screen (shown until user clicks "Start")
    # ------------------------------------------------------------------
    welcome_seen_key = f"ptc_session_{current}_welcomed"
    if not st.session_state.get(welcome_seen_key):
        st.subheader(f"Session {current} of {config.PTC_NUM_SESSIONS}")
        if current == 1:
            st.markdown(
                "<div class='form-text'>Welcome! In this first session, we'll begin with the "
                "Free Association Task and follow with the Sentence Completion Task. "
                "Respond with positive or neutral words only — no nouns describing people.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div class='form-text'>Welcome back! Your therapist has approved "
                f"session <b>{current}</b>. Same two tasks as before.</div>",
                unsafe_allow_html=True,
            )
        if st.button("▶ Start Session", type="primary", key=f"start_session_{current}"):
            st.session_state[welcome_seen_key] = True
            st.rerun()
        return

    # ------------------------------------------------------------------
    # Render FAT first; once complete, render Sentence Completion
    # ------------------------------------------------------------------
    if not _fat_complete(code, current):
        fat.render(code=code, session_num=current,
                   on_complete=lambda: st.rerun())
        return

    sentence_completion.render(code=code, session_num=current,
                               on_complete=lambda: st.rerun())

    # If both tasks now done, show waiting-for-therapist screen on next rerun
    if _session_complete(code, current):
        st.divider()
        _render_waiting_screen(current, group)
