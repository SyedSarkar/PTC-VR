"""
components/assessment_battery.py
=================================
Orchestrates the full pre/post assessment battery in order:
  1. LSAS  (24 items)
  2. BFNE  (12 items)
  3. CBQ   (20 items)
  4. BAT   (8 scenarios)
  5. Oximeter (4 reading points)

Each step is resume-safe. The orchestrator finds the first incomplete
sub-questionnaire and renders only that one.
"""

import streamlit as st

import config
from utils.helpers import next_phase as _next_phase
from utils.data_logger import get_logger
from utils.questionnaire_engine import is_questionnaire_complete

from components.questionnaires import lsas, bfne, cbq, bat, oximeter, dot_probe, wsa


# Map: phase -> firebase root for that battery
ASSESSMENT_PATHS = {
    "pre_assessment":   "assessments/pre",
    "post1_assessment": "assessments/post1",
    "post2_assessment": "assessments/post2",
    "post3_assessment": "assessments/post3",
}

ASSESSMENT_TITLES = {
    "pre_assessment":   "Pre-Assessment",
    "post1_assessment": "Post-Assessment 1",
    "post2_assessment": "Post-Assessment 2",
    "post3_assessment": "Post-Assessment 3 (Final)",
}


# Each step: (key, render_callable, total_items_or_None, sub_path)
# Dot Probe + WSA slot in between BAT and Oximeter per the protocol.
# total_items=None means the step uses a custom completion check below.
def _battery_steps(base_path: str):
    return [
        ("lsas",      lsas.render,       len(config.LSAS_ITEMS),    f"{base_path}/lsas"),
        ("bfne",      bfne.render,       len(config.BFNE_ITEMS),    f"{base_path}/bfne"),
        ("cbq",       cbq.render,        len(config.CBQ_ITEMS),     f"{base_path}/cbq"),
        ("bat",       bat.render,        len(config.BAT_SCENARIOS), f"{base_path}/bat"),
        ("dot_probe", dot_probe.render,  None,                      f"{base_path}/dot_probe"),
        ("wsa",       wsa.render,        None,                      f"{base_path}/wsa"),
        ("oximeter",  oximeter.render,   None,                      f"{base_path}/oximeter"),
    ]


def _is_oximeter_complete(code: str, base_path: str) -> bool:
    """Oximeter completion = all four reading points have spo2 set."""
    logger = get_logger()
    data = logger.get(code, base_path) or {}
    if not isinstance(data, dict):
        return False
    for point in config.OXIMETER_READING_POINTS:
        reading = data.get(point) or {}
        if not isinstance(reading, dict) or reading.get("spo2") is None:
            return False
    return True


def _is_task_complete_by_timestamp(code: str, base_path: str) -> bool:
    """Dot Probe / WSA completion = a completed_timestamp exists at the node."""
    logger = get_logger()
    node = logger.get(code, base_path) or {}
    return isinstance(node, dict) and bool(node.get("completed_timestamp"))


# Map phase_key -> gate_key for approval gating. post3 has no gate
# (it is the final assessment of the study).
_PHASE_GATE_KEYS = {
    "pre_assessment":   "pre_assessment",
    "post1_assessment": "post1_assessment",
    "post2_assessment": "post2_assessment",
    "post3_assessment": None,
}


def _render_waiting_screen(phase_key: str):
    title = ASSESSMENT_TITLES[phase_key]
    next_label = {
        "pre_assessment":   "the next phase of the study",
        "post1_assessment": "VR Exposure",
        "post2_assessment": "Real Exposure",
    }.get(phase_key, "the next phase")
    st.success(f"🎉 {title} complete!")
    st.markdown(
        f"<div class='form-text'>"
        f"Thank you for completing this assessment. Your therapist will let "
        f"you know when to return for <b>{next_label}</b>.<br><br>"
        f"Please <b>sign out now</b> using the button in the sidebar."
        f"</div>",
        unsafe_allow_html=True,
    )
    st.info(
        "⏳ This screen will remain here until your therapist approves the "
        "next step. You can safely sign out and return later."
    )


def render(phase_key: str):
    """Render the appropriate assessment battery based on phase_key."""
    code = st.session_state.get("participant_code")
    group = st.session_state.get("group")
    if not code:
        st.error("No participant code in session. Please log in again.")
        return

    if phase_key not in ASSESSMENT_PATHS:
        st.error(f"Unknown assessment phase: {phase_key}")
        return

    base_path = ASSESSMENT_PATHS[phase_key]
    title = ASSESSMENT_TITLES[phase_key]
    logger = get_logger()

    st.header(title)
    st.markdown(
        "<div class='form-text'>Please complete each questionnaire below. "
        "You can take breaks; your progress is saved automatically.</div>",
        unsafe_allow_html=True,
    )

    steps = _battery_steps(base_path)

    # Find first incomplete step
    for key, render_fn, total_items, sub_path in steps:
        if key == "oximeter":
            done = _is_oximeter_complete(code, sub_path)
        elif key in ("dot_probe", "wsa"):
            done = _is_task_complete_by_timestamp(code, sub_path)
        else:
            done = is_questionnaire_complete(code, sub_path, total_items)

        if not done:
            render_fn(code=code, base_path=sub_path,
                      on_complete=lambda: st.rerun())
            return

    # All steps done -> mark battery complete (once)
    if not logger.get(code, f"{base_path}/battery_completed_timestamp"):
        logger.update(code, base_path, {
            "battery_completed_timestamp":
                __import__("datetime").datetime.utcnow().isoformat() + "Z"
        })
        logger.save_progress(code, {
            "current_phase": phase_key,
            "current_session": 0,
            "completed_phases": (
                (logger.get(code, "progress/completed_phases") or [])
                + [phase_key]
            ),
        })

    # Therapist-approval gate. post3 has no gate — auto-advance to "complete".
    gate_key = _PHASE_GATE_KEYS.get(phase_key)
    if gate_key and not logger.is_gate_approved(code, gate_key):
        _render_waiting_screen(phase_key)
        return

    # Approved (or no gate required) — advance to next phase.
    st.success(f"🎉 {title} complete!")
    st.markdown(
        "<div class='form-text'>Your therapist has approved the next phase. "
        "Click below to continue.</div>"
        if gate_key else
        "<div class='form-text'>Thank you for completing this final "
        "assessment. Click below to finish the study.</div>",
        unsafe_allow_html=True,
    )

    if st.button("Continue ➜", type="primary", key=f"{phase_key}_advance"):
        nxt = _next_phase(phase_key, group) if group else None
        if nxt:
            st.session_state["phase"] = nxt
            logger.save_progress(code, {
                "current_phase": nxt,
                "current_session": 0,
            })
        st.rerun()
