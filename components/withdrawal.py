"""
components/withdrawal.py
========================
Handles partial withdrawal: marks participant as withdrawn and
anonymizes PII (name, email, contact). Anonymized data is retained.
"""

import streamlit as st

from utils.data_logger import get_logger


def render_withdraw_button(location: str = "sidebar"):
    """Render a 'Withdraw' button. Call from anywhere."""
    container = st.sidebar if location == "sidebar" else st
    if not st.session_state.get("participant_code"):
        return
    container.markdown("---")
    if container.button("Withdraw from Study", type="secondary", key=f"withdraw_btn_{location}"):
        st.session_state["phase"] = "withdrawn"
        st.rerun()


def render():
    """Withdrawal confirmation page."""
    code = st.session_state.get("participant_code")

    st.title("Withdraw from Study")
    st.markdown(
        "<div class='form-text'>"
        "We're sorry to see you go. Before you confirm, please note:"
        "<ul>"
        "<li>Your participation is entirely voluntary.</li>"
        "<li>Once withdrawn, your personal identifiers (name, email, contact) "
        "will be <b>permanently anonymized</b>.</li>"
        "<li>Anonymized response data may be retained for analysis.</li>"
        "<li>This action cannot be undone.</li>"
        "</ul>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    reason = st.text_area(
        "Reason for withdrawal (optional):", key="withdraw_reason",
        placeholder="You may leave this blank.", height=100,
    )

    st.warning("Are you sure you want to withdraw? This action cannot be undone.")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("Yes, Withdraw", type="secondary",
                     use_container_width=True, key="withdraw_confirm"):
            if not code:
                st.error("No participant code found. Cannot withdraw.")
                return
            logger = get_logger()
            logger.withdraw(code, reason=reason or "")
            st.session_state["withdrawn"] = True
            st.session_state["phase"] = "withdrawn_confirmed"
            st.rerun()
    with col3:
        if st.button("Cancel — Return", type="primary",
                     use_container_width=True, key="withdraw_cancel"):
            # Return to pre_assessment as a safe default
            st.session_state["phase"] = st.session_state.get("phase_before_withdraw",
                                                             "pre_assessment")
            st.rerun()


def render_confirmed():
    st.title("You have withdrawn from the study")
    st.markdown(
        "<div class='form-text'>"
        "Your personal information has been anonymized. Thank you for the time you spent "
        "with us. If you have any questions or concerns, please contact the research team."
        "</div>",
        unsafe_allow_html=True,
    )
