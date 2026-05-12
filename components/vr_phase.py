"""
components/vr_phase.py
=======================
Orchestrates the 4-session VR Exposure phase (all groups).

Per-session sub-flow:
  1. pre_ssq        — SSQ (16 items) before VR
  2. pre_suds       — SUDS (0-100) before VR
  3. pre_oximeter   — Oximeter starting reading
  4. vr_completion  — Therapist marks "VR Session Completed"
  5. post_suds      — SUDS (0-100) after VR
  6. post_oximeter  — Oximeter (highest reading during VR)
  7. igroup_presence— I-Group Presence Questionnaire (24 items)
  8. post_ssq       — SSQ (16 items) after VR
"""

import streamlit as st

import config
from utils.helpers import next_phase as _next_phase, now_iso
from utils.data_logger import get_logger
from utils.questionnaire_engine import is_questionnaire_complete

from components.questionnaires import ssq, suds, oximeter, igroup_presence


VR_SUBSTEPS = [
    "pre_ssq",
    "pre_suds",
    "pre_oximeter",
    "vr_completion",
    "post_suds",
    "post_oximeter",
    "igroup_presence",
    "post_ssq",
]


def _is_substep_complete(code: str, session_num: int, sub: str) -> bool:
    logger = get_logger()
    base = f"vr_exposure/session_{session_num}"

    if sub == "pre_ssq" or sub == "post_ssq":
        return is_questionnaire_complete(code, f"{base}/{sub}", len(config.SSQ_ITEMS))
    if sub == "igroup_presence":
        return is_questionnaire_complete(code, f"{base}/igroup_presence", len(config.IGROUP_ITEMS))
    if sub == "pre_suds" or sub == "post_suds":
        d = logger.get(code, f"{base}/{sub}") or {}
        return isinstance(d, dict) and d.get("value") is not None
    if sub == "pre_oximeter" or sub == "post_oximeter":
        d = logger.get(code, f"{base}/{sub}") or {}
        if not isinstance(d, dict):
            return False
        # For VR we only require one reading point
        for v in d.values():
            if isinstance(v, dict) and v.get("spo2") is not None:
                return True
        return False
    if sub == "vr_completion":
        d = logger.get(code, f"{base}/vr_completion") or {}
        return isinstance(d, dict) and bool(d.get("therapist_confirmed"))
    return False


def _session_complete(code: str, session_num: int) -> bool:
    return all(_is_substep_complete(code, session_num, s) for s in VR_SUBSTEPS)


def _render_vr_completion_wait(code: str, session_num: int):
    """Pause screen while waiting for therapist to mark VR session completed."""
    st.markdown(f"## Continue to Your VR Session {session_num}")
    st.markdown(
        "<div class='form-text'>"
        "<b>Please proceed to the VR session with your therapist.</b><br><br>"
        "When the VR session is complete, your therapist will mark it from the "
        "Therapist Dashboard. This page will then advance automatically — please "
        "click <i>Refresh</i> below after the session ends."
        "</div>",
        unsafe_allow_html=True,
    )
    st.info(f"Session: {session_num} of {config.VR_NUM_SESSIONS}")
    if st.button("🔄 Refresh", type="primary", key=f"vr_refresh_{session_num}"):
        st.rerun()


def render():
    code = st.session_state.get("participant_code")
    group = st.session_state.get("group")
    if not code:
        st.error("No participant code in session.")
        return

    st.header("VR Exposure Phase")
    st.markdown(
        "<div class='form-text'>This phase consists of 4 VR exposure sessions. "
        "Each session begins and ends with a brief assessment.</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    # Find current session
    current = 0
    for s in range(1, config.VR_NUM_SESSIONS + 1):
        if not _session_complete(code, s):
            current = s
            break
    if current == 0:
        # All done
        st.success("🎉 All 4 VR Exposure sessions complete!")
        st.balloons()
        if st.button("Continue to Post-Assessment 2 ➜", type="primary"):
            nxt = _next_phase("vr_exposure", group)
            st.session_state["phase"] = nxt or "post2_assessment"
            logger = get_logger()
            logger.save_progress(code, {
                "current_phase": st.session_state["phase"],
                "completed_phases": (
                    (logger.get(code, "progress/completed_phases") or [])
                    + ["vr_exposure"]
                ),
            })
            st.rerun()
        return

    # Keep progress.current_session in sync with the active VR session
    get_logger().save_progress(code, {
        "current_phase": "vr_exposure",
        "current_session": int(current),
    })

    st.subheader(f"VR Session {current} of {config.VR_NUM_SESSIONS}")
    base = f"vr_exposure/session_{current}"

    # Find first incomplete substep
    for sub in VR_SUBSTEPS:
        if _is_substep_complete(code, current, sub):
            continue

        if sub == "pre_ssq":
            st.markdown("### Step 1 / 8: Pre-VR Simulator Sickness Check")
            ssq.render(code=code, base_path=f"{base}/pre_ssq",
                       on_complete=lambda: st.rerun(),
                       ask_motion_sick=True)
        elif sub == "pre_suds":
            st.markdown("### Step 2 / 8: Pre-VR Distress Rating")
            suds.render(code=code, base_path=f"{base}/pre_suds",
                        label=f"Pre-VR Session {current}",
                        on_complete=lambda: st.rerun())
        elif sub == "pre_oximeter":
            st.markdown("### Step 3 / 8: Pre-VR Oximeter Reading")
            oximeter.render(code=code, base_path=f"{base}/pre_oximeter",
                            points=["starting"],
                            on_complete=lambda: st.rerun())
        elif sub == "vr_completion":
            st.markdown("### Step 4 / 8: VR Session (Therapist-led)")
            _render_vr_completion_wait(code, current)
        elif sub == "post_suds":
            st.markdown("### Step 5 / 8: Post-VR Distress Rating")
            suds.render(code=code, base_path=f"{base}/post_suds",
                        label=f"Post-VR Session {current}",
                        on_complete=lambda: st.rerun())
        elif sub == "post_oximeter":
            st.markdown("### Step 6 / 8: Post-VR Oximeter (highest reading during VR)")
            oximeter.render(code=code, base_path=f"{base}/post_oximeter",
                            points=["maximum"],
                            on_complete=lambda: st.rerun())
        elif sub == "igroup_presence":
            st.markdown("### Step 7 / 8: I-Group Presence Questionnaire")
            igroup_presence.render(code=code, base_path=f"{base}/igroup_presence",
                                   on_complete=lambda: st.rerun())
        elif sub == "post_ssq":
            st.markdown("### Step 8 / 8: Post-VR Simulator Sickness Check")
            ssq.render(code=code, base_path=f"{base}/post_ssq",
                       on_complete=lambda: st.rerun(),
                       ask_motion_sick=True)
        return

    # All substeps complete
    if current < config.VR_NUM_SESSIONS:
        st.success(f"🎉 VR Session {current} complete!")
        if st.button("Continue to Next VR Session ➜", type="primary"):
            st.rerun()
    else:
        st.success("🎉 All 4 VR sessions complete!")
        if st.button("Continue to Post-Assessment 2 ➜", type="primary"):
            nxt = _next_phase("vr_exposure", group)
            st.session_state["phase"] = nxt or "post2_assessment"
            st.rerun()
