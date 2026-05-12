"""
components/real_exposure_phase.py
==================================
Orchestrates the 4-session Real (in-vivo) Exposure phase (all groups).

Per-session sub-flow:
  1. Wait for therapist to enter exposure scenario (free-form text)
  2. Participant: SUDS before exposure
  3. Participant: Reads scenario, performs exposure (offline)
  4. Participant: SUDS after exposure
  5. Optional notes
"""

import streamlit as st

import config
from utils.helpers import next_phase as _next_phase, now_iso
from utils.data_logger import get_logger
from components.questionnaires import suds


def _scenario_set(code: str, session_num: int) -> dict | None:
    logger = get_logger()
    d = logger.get(code, f"real_exposure/session_{session_num}/therapist_scenario")
    if d and isinstance(d, dict) and (d.get("text") or "").strip():
        return d
    return None


def _suds_done(code: str, session_num: int, which: str) -> bool:
    logger = get_logger()
    d = logger.get(code, f"real_exposure/session_{session_num}/{which}_suds") or {}
    return isinstance(d, dict) and d.get("value") is not None


def _session_complete(code: str, session_num: int) -> bool:
    return (
        _scenario_set(code, session_num) is not None
        and _suds_done(code, session_num, "pre")
        and _suds_done(code, session_num, "post")
        and _notes_submitted(code, session_num)
    )


def _notes_submitted(code: str, session_num: int) -> bool:
    logger = get_logger()
    d = logger.get(code, f"real_exposure/session_{session_num}") or {}
    if not isinstance(d, dict):
        return False
    return d.get("session_completed_timestamp") is not None


def render():
    code = st.session_state.get("participant_code")
    group = st.session_state.get("group")
    if not code:
        st.error("No participant code in session.")
        return

    st.header("Real Exposure Phase")
    st.markdown(
        "<div class='form-text'>This phase consists of 4 in-vivo (real-world) exposure sessions. "
        "Your therapist will provide a scenario for each session.</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    # Find current session
    current = 0
    for s in range(1, config.REAL_EXP_NUM_SESSIONS + 1):
        if not _session_complete(code, s):
            current = s
            break
    if current == 0:
        st.success("🎉 All 4 Real Exposure sessions complete!")
        st.balloons()
        if st.button("Continue to Post-Assessment 3 (Final) ➜", type="primary"):
            nxt = _next_phase("real_exposure", group)
            st.session_state["phase"] = nxt or "post3_assessment"
            logger = get_logger()
            logger.save_progress(code, {
                "current_phase": st.session_state["phase"],
                "completed_phases": (
                    (logger.get(code, "progress/completed_phases") or [])
                    + ["real_exposure"]
                ),
            })
            st.rerun()
        return

    # Keep progress.current_session in sync with the active Real Exposure session
    get_logger().save_progress(code, {
        "current_phase": "real_exposure",
        "current_session": int(current),
    })

    st.subheader(f"Real Exposure Session {current} of {config.REAL_EXP_NUM_SESSIONS}")
    base = f"real_exposure/session_{current}"
    scenario = _scenario_set(code, current)

    # Step 1: Wait for therapist to set scenario
    if scenario is None:
        st.warning(
            "⏳ Your therapist has not yet entered the exposure scenario for this session. "
            "Please ask your therapist to set it from their dashboard."
        )
        if st.button("🔄 Refresh", type="primary", key=f"re_refresh_{current}"):
            st.rerun()
        return

    # Display the scenario
    st.markdown("### Scenario for This Session")
    st.info(scenario.get("text", ""))

    # Step 2: Pre-exposure SUDS
    if not _suds_done(code, current, "pre"):
        st.markdown("### Step 1 / 3: Rate Your Distress BEFORE the Exposure")
        suds.render(code=code, base_path=f"{base}/pre_suds",
                    label=f"Pre-Exposure SUDS (Session {current})",
                    on_complete=lambda: st.rerun())
        return

    # Step 3: Confirmation that exposure has been completed
    exposure_confirmed_key = f"re_exposure_confirmed_{current}"
    if not st.session_state.get(exposure_confirmed_key):
        st.markdown("### Step 2 / 3: Complete the Exposure Activity")
        st.markdown(
            "<div class='form-text'>Now go and complete the exposure activity described above. "
            "Once you have finished the activity in real life, click the button below to continue."
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("✓ I have completed the exposure activity",
                     type="primary", key=f"re_done_{current}"):
            st.session_state[exposure_confirmed_key] = True
            st.rerun()
        return

    # Step 4: Post-exposure SUDS
    if not _suds_done(code, current, "post"):
        st.markdown("### Step 3 / 3: Rate Your Distress AFTER the Exposure")
        suds.render(code=code, base_path=f"{base}/post_suds",
                    label=f"Post-Exposure SUDS (Session {current})",
                    on_complete=lambda: st.rerun())
        return

    # Step 5: Optional notes + finalize
    if not _notes_submitted(code, current):
        st.markdown("### Optional: Notes from this Session")
        notes = st.text_area(
            "Any thoughts, reflections, or observations? (optional)",
            key=f"re_notes_{current}", height=100,
        )
        if st.button("Finish Session ➜", type="primary", key=f"re_finish_{current}"):
            logger = get_logger()
            logger.update(code, base, {
                "participant_notes": notes or "",
                "session_completed_timestamp": now_iso(),
            })
            logger.log_event(code, "real_exposure_session_completed", {
                "session": current,
            })
            st.rerun()
        return

    # Complete
    st.success(f"🎉 Real Exposure Session {current} complete!")
    if current < config.REAL_EXP_NUM_SESSIONS:
        if st.button("Continue to Next Session ➜", type="primary"):
            st.rerun()
    else:
        if st.button("Continue to Final Post-Assessment ➜", type="primary"):
            nxt = _next_phase("real_exposure", group)
            st.session_state["phase"] = nxt or "post3_assessment"
            st.rerun()
