"""
components/assessment_battery.py
=================================
Optimized Assessment Battery Orchestrator.
Inner questionnaires already use @st.fragment for speed.
"""

import streamlit as st

import config
from utils.helpers import next_phase as _next_phase, now_iso
from utils.data_logger import get_logger
from utils.questionnaire_engine import is_questionnaire_complete

from components.questionnaires import lsas, bfne, cbq, cbq_trait, bat, oximeter, dot_probe, wsa


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


def _battery_steps(base_path: str):
    return [
        ("lsas",       lsas.render,       len(config.LSAS_ITEMS),       f"{base_path}/lsas"),
        ("bfne",       bfne.render,       len(config.BFNE_ITEMS),       f"{base_path}/bfne"),
        ("cbq",        cbq.render,        len(config.CBQ_ITEMS),        f"{base_path}/cbq"),
        ("cbq_trait",  cbq_trait.render,  len(config.CBQ_TRAIT_ITEMS),  f"{base_path}/cbq_trait"),
        ("bat",        bat.render,        len(config.BAT_SCENARIOS),    f"{base_path}/bat"),
        ("dot_probe",  dot_probe.render,  None,                         f"{base_path}/dot_probe"),
        ("wsa",        wsa.render,        None,                         f"{base_path}/wsa"),
        ("oximeter",   oximeter.render,   None,                         f"{base_path}/oximeter"),
    ]


def _is_oximeter_complete(code: str, base_path: str) -> bool:
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
    logger = get_logger()
    node = logger.get(code, base_path) or {}
    return isinstance(node, dict) and bool(node.get("completed_timestamp"))


def render(phase_key: str):
    """Main battery renderer - Clean & Efficient"""
    code = st.session_state.get("participant_code")
    group = st.session_state.get("group")
    if not code:
        st.error("No participant code in session.")
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
        "Your progress is saved automatically.</div>",
        unsafe_allow_html=True,
    )

    steps = _battery_steps(base_path)

    # Find and render first incomplete questionnaire
    for key, render_fn, total_items, sub_path in steps:
        if key == "oximeter":
            done = _is_oximeter_complete(code, sub_path)
        elif key in ("dot_probe", "wsa"):
            done = _is_task_complete_by_timestamp(code, sub_path)
        else:
            done = is_questionnaire_complete(code, sub_path, total_items)

        if not done:
            # Inner render functions already use @st.fragment → very fast
            render_fn(code=code, base_path=sub_path, on_complete=lambda: st.rerun())
            return

    # ====================== ALL QUESTIONNAIRES COMPLETED ======================
    if not logger.get(code, f"{base_path}/battery_completed_timestamp"):
        logger.update(code, base_path, {
            "battery_completed_timestamp": now_iso()
        }, sync=False)

        logger.save_progress(code, {
            "current_phase": phase_key,
            "current_session": 0,
            "completed_phases": (
                (logger.get(code, "progress/completed_phases") or []) + [phase_key]
            ),
        })

    st.success(f"🎉 {title} complete!")

    if st.button("Continue ➜", type="primary", key=f"{phase_key}_advance"):
        nxt = _next_phase(phase_key, group) if group else None
        if nxt:
            st.session_state["phase"] = nxt
            logger.save_progress(code, {
                "current_phase": nxt,
                "current_session": 0,
            })
        st.rerun()