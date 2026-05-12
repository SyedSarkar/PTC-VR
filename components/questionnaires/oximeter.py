"""
components/questionnaires/oximeter.py
======================================
Oximeter readings — manual entry by participant.
Captures four reading points: starting, ending, minimum, maximum.
Each reading: SpO2 (%), BPM, optional notes.
"""

import streamlit as st

import config
from utils.helpers import now_iso
from utils.data_logger import get_logger
from utils.validators import validate_oximeter_reading


READING_LABELS = {
    "starting": "Starting Reading",
    "ending":   "Ending Reading",
    "minimum":  "Minimum (lowest) Reading",
    "maximum":  "Maximum (highest) Reading",
}


def _render_single_reading(code: str, base_path: str, point: str) -> bool:
    """
    Render entry form for one reading point. Returns True on successful save.
    """
    logger = get_logger()
    existing = logger.get(code, f"{base_path}/{point}")
    title = READING_LABELS[point]

    if existing and isinstance(existing, dict) and existing.get("spo2") is not None:
        st.success(
            f"✅ {title} saved: SpO₂ {existing['spo2']}%, BPM {existing['bpm']}"
        )
        return True

    # Use safe key (no slashes) for widget keys
    safe_key = base_path.replace("/", "_")

    st.markdown(f"### {title}")
    col1, col2 = st.columns(2)
    with col1:
        spo2 = st.number_input(
            "Oxygen Level (SpO₂) %",
            min_value=70.0, max_value=100.0, value=98.0, step=0.5,
            key=f"{safe_key}_{point}_spo2",
        )
    with col2:
        bpm = st.number_input(
            "Pulse Rate (BPM)",
            min_value=30, max_value=220, value=75, step=1,
            key=f"{safe_key}_{point}_bpm",
        )
    notes = st.text_area(
        "Notes (e.g., shortness of breath)",
        key=f"{safe_key}_{point}_notes",
        height=70, placeholder="Optional",
    )

    if st.button(f"Save {title}", type="primary", key=f"{safe_key}_{point}_save"):
        ok, errs = validate_oximeter_reading(spo2, bpm)
        if not ok:
            for e in errs:
                st.error(e)
            return False
        logger.set(code, f"{base_path}/{point}", {
            "spo2": float(spo2),
            "bpm": int(bpm),
            "notes": notes or "",
            "timestamp": now_iso(),
        })
        logger.log_event(code, "oximeter_reading", {
            "path": base_path, "point": point,
            "spo2": float(spo2), "bpm": int(bpm),
        })
        st.rerun()
    return False


def render(code: str, base_path: str, on_complete=None,
           points: list[str] = None):
    """
    Render the oximeter entry block. Defaults to all four reading points
    (starting, ending, minimum, maximum). Pass a smaller list for VR sessions
    where only one reading is needed (e.g., points=['maximum']).
    """
    points = points or config.OXIMETER_READING_POINTS

    st.markdown("## Oximeter Readings")
    st.markdown(
        "<div class='form-text'>Please enter the readings from your oximeter device.</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    logger = get_logger()
    existing_all = logger.get(code, base_path) or {}

    completed = []
    for point in points:
        existing = existing_all.get(point) if isinstance(existing_all, dict) else None
        if existing and isinstance(existing, dict) and existing.get("spo2") is not None:
            completed.append(point)
            st.success(
                f"✅ {READING_LABELS[point]} — SpO₂ {existing['spo2']}%, BPM {existing['bpm']}"
            )
        else:
            _render_single_reading(code, base_path, point)
            return  # Only render one form at a time

    # All readings complete
    if len(completed) == len(points):
        # Save completion timestamp
        logger.update(code, base_path, {"completed_timestamp": now_iso()})
        st.success("✅ All oximeter readings recorded.")
        # Use safe key (no slashes) for widget keys
        safe_key = base_path.replace("/", "_")
        if on_complete:
            if st.button("Continue ➜", type="primary", key=f"{safe_key}_continue"):
                on_complete()
