"""
components/consent.py
=====================
Renders the consent form. Participant must explicitly agree
before proceeding to demographics.
"""

import streamlit as st

import config
from utils.helpers import init_session_state


def render():
    init_session_state()

    st.title("Welcome aboard")
    st.markdown(
        "<div class='form-text'>We are pleased to see you here. "
        "Thank you for being part of this research project and seeking help for yourself."
        "</div>", unsafe_allow_html=True,
    )
    st.divider()

    st.subheader("Informed Consent")

    st.markdown(
        f"""
        <div class='form-text'>
        <p><b>Study Title:</b> <i>{config.STUDY_TITLE}</i></p>
        <ul>
          <li><b>Principal Investigator:</b> {config.PRINCIPAL_INVESTIGATOR}</li>
          <li><b>Institution / Department:</b> {config.INSTITUTION}</li>
          <li><b>Version Date:</b> {config.VERSION_DATE}</li>
        </ul>

        <p>You are invited to participate in a research study on <b>Social Anxiety Disorder (SAD)</b>.</p>

        <p>The purpose of this study is to compare different psychological intervention
        approaches for individuals experiencing fear or discomfort in social situations.</p>

        <p>If you agree to participate, you will:</p>
        <ul>
          <li>Complete questionnaires and assessments at <b>four time points</b>.</li>
          <li>Attend <b>12 structured sessions</b> over a specified period.</li>
        </ul>

        <p>This study includes <b>three intervention groups</b>. Participants will be assigned
        through a <b>randomized process</b>, meaning assignment is based on chance and not
        on researcher judgment or symptom severity. You will have an approximately
        <b>equal chance</b> of being placed in any group.</p>

        <p>To reduce bias and maintain scientific accuracy, you will not be informed of your
        assigned group during the study. After completion, the researcher will explain your
        group assignment and the overall purpose of the interventions.</p>

        <p>All information collected will remain <b>confidential</b>. Your responses will be
        identified using a code number rather than your name, and data will be securely stored
        by the research team only.</p>

        <p>Participation is entirely <b>voluntary</b>. You may withdraw from the study at any
        time without penalty or effect on your academic standing, care, or services.</p>

        <p><b>For study-related questions:</b><br>
        {config.RESEARCHER} — <a href="mailto:{config.RESEARCHER_EMAIL}">{config.RESEARCHER_EMAIL}</a></p>

        <p><b>For concerns about participant rights or ethics:</b><br>
        {config.PRINCIPAL_INVESTIGATOR} — <a href="mailto:{config.PI_EMAIL}">{config.PI_EMAIL}</a></p>

        <p>If you agree to take part after reading this, please confirm your consent below.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        agree = st.button("✓ I Agree", type="primary", use_container_width=True, key="consent_agree")
    with col3:
        disagree = st.button("✗ I Disagree", type="secondary", use_container_width=True, key="consent_disagree")

    if agree:
        st.session_state["consent_accepted"] = True
        st.session_state["phase"] = "demographics"
        # Save consent to Firebase if we already have a participant code
        code = st.session_state.get("participant_code")
        if code:
            from utils.data_logger import get_logger
            from utils.helpers import now_iso
            logger = get_logger()
            logger.save_consent(code, accepted=True, version=config.VERSION_DATE)
            logger.log_event(code, "consent_accepted", {"timestamp": now_iso()})
        st.success("Thank you for your trust. Moving to next page...")
        st.rerun()

    if disagree:
        st.session_state["consent_accepted"] = False
        st.warning(
            "Thank you for coming. You are willingly disqualified from the study. "
            "Have a good day. 👋"
        )
        st.stop()
