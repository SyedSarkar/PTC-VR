"""
utils/helpers.py
================
Shared utility functions used across the app.
"""

import random
import re
import string
import datetime
from pathlib import Path
from typing import Iterable

import streamlit as st


# ============================================================================
# TIMESTAMPS (UTC ISO format)
# ============================================================================
def now_iso() -> str:
    """UTC timestamp in ISO 8601 format."""
    return datetime.datetime.utcnow().isoformat() + "Z"


def now_local_str() -> str:
    """Local timestamp for display purposes only."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================================
# PARTICIPANT CODE
# ============================================================================
def generate_participant_code(prefix: str = "SAD") -> str:
    """
    Generate a unique participant code: e.g. SAD-A3F92K
    Format: {prefix}-{6-char alphanumeric upper}
    """
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"{prefix}-{suffix}"


def safe_id(s: str) -> str:
    """Make a string safe for use in keys/filenames."""
    return re.sub(r"[^\w\-]", "_", s.strip())


# ============================================================================
# GROUP ASSIGNMENT
# ============================================================================
def assign_group(groups: Iterable[str]) -> str:
    """Randomly assign a participant to one of the groups (uniform probability)."""
    return random.choice(list(groups))


# ============================================================================
# PROGRESS HELPERS
# ============================================================================
def safe_progress(current: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return min(max(current / total, 0.0), 1.0)


# ============================================================================
# CSS INJECTION
# ============================================================================
def inject_global_css():
    """Inject Times New Roman 12pt + theme styling globally."""
    css = """
    <style>
    html, body, [class*="css"], .stMarkdown, .stTextInput, .stTextArea, .stRadio,
    .stSelectbox, .stButton, .stCheckbox, .stSlider, label, p, span, div, h1, h2, h3, h4, h5, h6 {
        font-family: 'Times New Roman', Times, serif;
    }
    /* Preserve Material Icons for Streamlit UI elements */
    .material-icons, [class*="material-icons"], [style*="font-family: Material"] {
        font-family: 'Material Icons' !important;
    }
    .stApp {
        background-color: #f6f9fc;
    }
    .form-text { text-align: left; font-size: 16px; }
    .scale-text { text-align: center; font-size: 16px; }
    .item-title { font-size: 20px; font-weight: bold; margin: 20px 0 10px 0; text-align: center; }
    .progress-text { font-size: 14px; color: #555; }
    .feedback-success { color: #27ae60; font-weight: bold; text-align: center; padding: 10px; }
    .feedback-error   { color: #c0392b; font-weight: bold; text-align: center; padding: 10px; }
    .feedback-warn    { color: #e67e22; font-weight: bold; text-align: center; padding: 10px; }
    .cue-word { text-align: center; font-size: 36px; font-weight: bold; color: #010d1a; padding: 20px; }
    .points-banner { font-size: 16px; font-weight: bold; padding: 8px; border-radius: 4px;
                     background: #eafaf1; color: #1e8449; display: inline-block; }
    /* Primary buttons green, secondary red overridden by streamlit type=primary/secondary */
    .stButton > button[kind="primary"] {
        background-color: #2ecc71 !important;
        color: white !important;
        border: none !important;
    }
    .stButton > button[kind="secondary"] {
        background-color: #e74c3c !important;
        color: white !important;
        border: none !important;
    }
    .scale-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; color: #555; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ============================================================================
# DATA FILE LOADERS
# ============================================================================
def load_lines(path: Path) -> list[str]:
    """Load non-empty lines from a text file."""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


# ============================================================================
# SCALE LABEL FORMATTING
# ============================================================================
def render_scale_anchor_row(anchors: list[str]):
    """Render evenly-spaced scale anchor labels (for visual reference)."""
    if not anchors:
        return
    n = len(anchors)
    cols = st.columns(n)
    for c, lbl in zip(cols, anchors):
        c.markdown(f"<div style='text-align:center; font-size:12px; color:#555;'>{lbl}</div>",
                   unsafe_allow_html=True)


# ============================================================================
# SESSION STATE INIT (shared keys)
# ============================================================================
def init_session_state():
    """Initialize default session_state keys if absent."""
    defaults = {
        "phase": "welcome",          # current top-level phase
        "user_role": None,           # 'participant' or 'therapist'
        "participant_code": None,
        "group": None,
        "withdrawn": False,
        "metadata": {},
        # questionnaire-level
        "current_questionnaire": None,
        "current_item_index": 0,
        "current_responses": {},
        # PTC training
        "ptc_session_num": 0,
        "ptc_block_num": 0,
        "ptc_step": 0,
        "ptc_used_responses": set(),
        "ptc_repeats_used": 0,
        "ptc_score": 0,
        "ptc_responses": [],
        "ptc_task_type": None,        # 'fat' or 'sentence'
        # VR & real exposure
        "vr_session_num": 0,
        "vr_subphase": None,
        "real_exp_session_num": 0,
        # Assessment battery
        "assessment_phase": None,     # 'pre' | 'post1' | 'post2' | 'post3'
        "assessment_step_index": 0,
        # Therapist
        "therapist_logged_in": False,
        "therapist_selected_participant": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================================
# PHASE FLOW BY GROUP
# ============================================================================
def get_phase_sequence(group: str) -> list[str]:
    """Return the ordered list of top-level phases for a given group."""
    if group == "PTC":
        return [
            "consent", "demographics",
            "pre_assessment", "ptc_training", "post1_assessment",
            "vr_exposure", "post2_assessment",
            "real_exposure", "post3_assessment",
            "complete",
        ]
    elif group in ("VR", "CBT"):
        return [
            "consent", "demographics",
            "pre_assessment", "waiting_period", "post1_assessment",
            "vr_exposure", "post2_assessment",
            "real_exposure", "post3_assessment",
            "complete",
        ]
    return []


def next_phase(current: str, group: str) -> str | None:
    """Get the next phase after `current` in the group's sequence."""
    seq = get_phase_sequence(group)
    if current not in seq:
        return None
    idx = seq.index(current)
    return seq[idx + 1] if idx + 1 < len(seq) else None
