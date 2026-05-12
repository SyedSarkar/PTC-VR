"""
components/demographics.py
==========================
Demographics form. On submit:
  1. Validates fields
  2. Generates a unique participant code
  3. Randomly assigns to one of {PTC, VR, CBT} (hidden from participant)
  4. Saves metadata + consent to Firebase
  5. Advances to pre_assessment
"""

import streamlit as st

import config
from utils.helpers import (
    generate_participant_code,
    assign_group,
    init_session_state,
)
from utils.validators import validate_demographics
from utils.data_logger import get_logger


GENDERS = ["Male", "Female", "Prefer not to say", "Other"]
EDUCATION_LEVELS = [
    "High school or below",
    "Bachelor's (in progress)",
    "Bachelor's (completed)",
    "Master's (in progress)",
    "Master's (completed)",
    "Doctorate / PhD",
    "Other",
]
COMPUTER_SKILLS_LEVELS = [
    "1 — Beginner",
    "2 — Basic",
    "3 — Intermediate",
    "4 — Advanced",
    "5 — Expert",
]


def _render_form() -> dict | None:
    st.markdown("## Demographics")
    st.markdown(
        "<div class='form-text'>Please fill out the following details. "
        "All information is kept confidential and used only for research purposes.</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Full Name *", key="demo_name")
        age = st.number_input("Age *", min_value=10, max_value=100, value=20, step=1, key="demo_age")
        contact = st.text_input("Contact Number *", key="demo_contact",
                                placeholder="+92-300-1234567")
        education = st.selectbox("Education *", options=[""] + EDUCATION_LEVELS, key="demo_edu")
    with col2:
        roll_number = st.text_input("Roll Number / University ID *", key="demo_roll")
        gender = st.selectbox("Gender *", options=[""] + GENDERS, key="demo_gender")
        email = st.text_input("Email Address *", key="demo_email", placeholder="you@example.com")
        skills_label = st.selectbox(
            "Computer Skills *", options=[""] + COMPUTER_SKILLS_LEVELS, key="demo_skills"
        )

    st.markdown(
        "<div class='form-text' style='color:#666; font-size:13px;'>* Required fields</div>",
        unsafe_allow_html=True,
    )

    submitted = st.button("Submit & Continue ➜", type="primary", use_container_width=True)
    if not submitted:
        return None

    skills_value = None
    if skills_label:
        try:
            skills_value = int(skills_label.split(" ")[0])
        except Exception:
            skills_value = None

    data = {
        "name": name,
        "roll_number": roll_number,
        "age": int(age),
        "gender": gender,
        "contact": contact,
        "email": email,
        "education": education,
        "computer_skills": skills_value,
    }
    return data


def render():
    init_session_state()
    st.markdown(
        "<div class='form-text'>Welcome! Before we begin, please tell us a little about yourself.</div>",
        unsafe_allow_html=True,
    )

    data = _render_form()
    if data is None:
        return

    ok, errors = validate_demographics(data)
    if not ok:
        for e in errors:
            st.error(e)
        return

    logger = get_logger()

    # If a participant with this roll number already exists, resume them instead of creating new.
    existing_code = logger.find_by_roll_number(data["roll_number"])
    if existing_code:
        st.info(
            f"We found existing data linked to your Roll Number. "
            f"Resuming your study under code: **{existing_code}**"
        )
        existing = logger.load_participant(existing_code) or {}
        meta = existing.get("metadata") or {}
        st.session_state["participant_code"] = existing_code
        st.session_state["group"] = meta.get("group")
        st.session_state["metadata"] = meta
        st.session_state["user_role"] = "participant"
        # Resume to the appropriate phase based on stored progress
        progress = (existing.get("progress") or {})
        st.session_state["phase"] = progress.get("current_phase", "pre_assessment")
        st.rerun()
        return

    # Create a new participant
    code = generate_participant_code(prefix=config.PARTICIPANT_CODE_PREFIX)
    # Ensure uniqueness (extremely unlikely collision but safe)
    while logger.participant_exists(code):
        code = generate_participant_code(prefix=config.PARTICIPANT_CODE_PREFIX)

    group = assign_group(config.GROUPS)

    metadata = dict(data)
    metadata["code"] = code
    metadata["group"] = group  # stored, but never displayed to participant

    # Save consent + metadata
    logger.save_consent(code, accepted=True, version=config.VERSION_DATE)
    logger.save_metadata(code, metadata)
    logger.save_progress(code, {
        "current_phase": "pre_assessment",
        "current_session": 0,
        "completed_phases": ["consent", "demographics"],
    })

    st.session_state["participant_code"] = code
    st.session_state["group"] = group
    st.session_state["metadata"] = metadata
    st.session_state["user_role"] = "participant"
    st.session_state["phase"] = "pre_assessment"

    st.success(f"✅ Registration complete. Your participant code is: **{code}**")
    st.info("Please save this code in case you need to resume later.")
    if st.button("Continue to Pre-Assessment ➜", type="primary"):
        st.rerun()
