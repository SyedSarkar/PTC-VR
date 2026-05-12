"""
app.py
======
Main entry point for the SAD Intervention App.

This is the state-machine that routes the current `phase` (stored in
st.session_state["phase"]) to the appropriate render function.

Run with:
    streamlit run app.py
"""

import streamlit as st

import config
from utils.helpers import init_session_state, inject_global_css

# Phase render functions
from components import (
    welcome,
    consent,
    demographics,
    withdrawal,
    assessment_battery,
    ptc_phase,
    vr_phase,
    real_exposure_phase,
    waiting_phase,
    therapist_dashboard,
)


# ============================================================================
# PAGE CONFIG (must be first Streamlit call)
# ============================================================================
st.set_page_config(
    page_title="SAD Intervention Study",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="auto",
)


# ============================================================================
# GLOBAL STYLING
# ============================================================================
inject_global_css()


# ============================================================================
# SESSION STATE INIT
# ============================================================================
init_session_state()


# ============================================================================
# SIDEBAR — Always-visible status & withdrawal button
# ============================================================================
def _sign_out():
    """Clear all per-user session state; route back to welcome."""
    keys_to_clear = [
        "user_role", "participant_code", "group", "withdrawn",
        "metadata", "current_questionnaire", "current_item_index",
        "current_responses",
        "ptc_session_num", "ptc_block_num", "ptc_step",
        "ptc_used_responses", "ptc_repeats_used", "ptc_score",
        "ptc_responses", "ptc_task_type",
        "vr_session_num", "vr_subphase",
        "real_exp_session_num",
        "assessment_phase", "assessment_step_index",
        "therapist_logged_in", "therapist_selected_participant",
        "phase_before_withdraw",
    ]
    for k in keys_to_clear:
        st.session_state.pop(k, None)
    # Drop any per-session keys that the phases may have stashed
    for k in list(st.session_state.keys()):
        if k.startswith(("ptc_session_", "battery_complete_", "confirm_delete_")):
            st.session_state.pop(k, None)
    st.session_state["phase"] = "welcome"


def render_sidebar():
    with st.sidebar:
        st.markdown(f"### {config.RESEARCHER}")
        st.markdown(f"<div style='font-size:13px; color:#555;'>"
                    f"<i>{config.STUDY_TITLE}</i></div>",
                    unsafe_allow_html=True)
        st.divider()

        role = st.session_state.get("user_role")
        code = st.session_state.get("participant_code")
        phase = st.session_state.get("phase", "welcome")

        if role == "participant" and code:
            st.markdown(f"**Code:** `{code}`")
            st.markdown(f"**Phase:** {phase.replace('_', ' ').title()}")
            # Group is intentionally HIDDEN from participant
            st.divider()

            # Persistent SIGN OUT button — always available for logged-in
            # participants. Progress is saved to Firebase after every item,
            # so signing out is non-destructive.
            if st.button("🚪 Sign Out", type="primary",
                         use_container_width=True, key="sidebar_signout"):
                _sign_out()
                st.rerun()

            # Withdrawal (separate, terminal action)
            if phase not in ("welcome", "withdrawn", "withdrawn_confirmed"):
                if st.button("⚠️ Withdraw from Study",
                             type="secondary",
                             use_container_width=True,
                             key="sidebar_withdraw"):
                    st.session_state["phase_before_withdraw"] = phase
                    st.session_state["phase"] = "withdrawn"
                    st.rerun()

            st.caption(
                "Your progress is saved automatically. You can sign out and "
                "return later using your participant code or roll number."
            )
        elif role == "therapist":
            st.markdown(f"**Logged in as:** {config.THERAPIST_USERNAME}")
            st.markdown("**Role:** Therapist")
            st.divider()
            if st.button("🚪 Sign Out", type="primary",
                         use_container_width=True, key="sidebar_signout_ther"):
                _sign_out()
                st.rerun()
        else:
            st.info("Welcome! Please choose how to proceed on the main page.")

        st.divider()
        st.caption(f"v{config.VERSION_DATE}")


# ============================================================================
# MAIN ROUTER
# ============================================================================
def main():
    render_sidebar()

    phase = st.session_state.get("phase", "welcome")

    # ---- Therapist routes ----
    if phase == "therapist_dashboard" or st.session_state.get("user_role") == "therapist":
        therapist_dashboard.render()
        return

    # ---- Participant routes ----
    if phase == "welcome":
        welcome.render()

    elif phase == "consent":
        consent.render()

    elif phase == "demographics":
        demographics.render()

    elif phase == "pre_assessment":
        assessment_battery.render("pre_assessment")

    elif phase == "ptc_training":
        ptc_phase.render()

    elif phase == "waiting_period":
        waiting_phase.render()

    elif phase == "post1_assessment":
        assessment_battery.render("post1_assessment")

    elif phase == "vr_exposure":
        vr_phase.render()

    elif phase == "post2_assessment":
        assessment_battery.render("post2_assessment")

    elif phase == "real_exposure":
        real_exposure_phase.render()

    elif phase == "post3_assessment":
        assessment_battery.render("post3_assessment")

    elif phase == "complete":
        _render_complete()

    elif phase == "withdrawn":
        withdrawal.render()

    elif phase == "withdrawn_confirmed":
        withdrawal.render_confirmed()

    else:
        st.error(f"Unknown phase: {phase}")
        if st.button("Return to Welcome"):
            st.session_state["phase"] = "welcome"
            st.rerun()


# ============================================================================
# COMPLETION SCREEN
# ============================================================================
def _render_complete():
    st.balloons()
    st.title("🎉 Thank You!")
    st.markdown(
        f"<div class='form-text'>"
        f"You have successfully completed the entire study. "
        f"Your contribution to research on Social Anxiety Disorder is greatly appreciated."
        f"<br><br>"
        f"If you have any questions, please contact the research team:"
        f"<ul>"
        f"<li>{config.RESEARCHER} — <a href='mailto:{config.RESEARCHER_EMAIL}'>{config.RESEARCHER_EMAIL}</a></li>"
        f"<li>{config.PRINCIPAL_INVESTIGATOR} — <a href='mailto:{config.PI_EMAIL}'>{config.PI_EMAIL}</a></li>"
        f"</ul>"
        f"</div>",
        unsafe_allow_html=True,
    )

    code = st.session_state.get("participant_code")
    if code:
        st.success(f"Your participant code: `{code}`")


# ============================================================================
# RUN
# ============================================================================
if __name__ == "__main__":
    main()
else:
    main()
