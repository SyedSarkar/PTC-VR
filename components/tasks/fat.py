"""
components/tasks/fat.py
========================
Optimized Free Association Task (FAT) - Random cue order per session.
"""

import time
import random
import streamlit as st

import config
from utils.helpers import safe_progress, load_lines, load_csv_column_by_session, now_iso
from utils.validators import validate_ptc_response
from utils.data_logger import get_logger


def _format_feedback(msg: str, color: str) -> str:
    return (
        f"<div style='text-align:center; font-size:24px; font-weight:bold; "
        f"color:{color}; padding:12px; margin:10px 0;'>{msg}</div>"
    )


@st.fragment
def render(code: str, session_num: int, on_complete=None):
    """
    Args:
        code: participant code
        session_num: 1..PTC_NUM_SESSIONS
        on_complete: callback when this entire FAT block is finished
    """
    logger = get_logger()
    base_path = f"ptc_training/session_{session_num}/fat"

    # Load cue words from CSV filtered by session (shuffle only once per session)
    cue_words = load_csv_column_by_session(config.FAT_WORDS_CSV, session_num, "Word")
    if not cue_words:
        st.error(f"⚠️ No cue words found for Session {session_num} in `{config.FAT_WORDS_CSV}`.")
        return

    # Shuffle once per session and store in session state
    shuffle_key = f"{base_path}_shuffled_cues"
    if shuffle_key not in st.session_state:
        shuffled = cue_words.copy()
        random.shuffle(shuffled)
        st.session_state[shuffle_key] = shuffled
    cue_words = st.session_state[shuffle_key]

    total = len(cue_words)

    # Load existing progress
    existing = logger.get(code, base_path) or {}
    existing_responses = existing.get("responses") or []
    if isinstance(existing_responses, dict):
        existing_responses = [v for _, v in sorted(existing_responses.items(), key=lambda x: int(x[0]))]

    completed_count = sum(1 for r in existing_responses if r and r.get("accepted"))
    score_so_far = sum(int(r.get("score", 0)) for r in existing_responses if r)
    used = {str(r.get("response", "")).lower() for r in existing_responses if r and r.get("accepted")}
    repeats_used = sum(1 for r in existing_responses if r and r.get("accepted") and r.get("is_repeat"))

    if completed_count >= total:
        st.success(f"✅ FAT for Session {session_num} is already complete.")
        st.markdown(f"<div class='points-banner'>Final Points: {score_so_far}</div>", unsafe_allow_html=True)
        if on_complete:
            if st.button("Continue to Sentence Completion ➜", type="primary", key=f"{base_path}_continue"):
                on_complete()
        return

    st.markdown(f"## Free Association Task — Session {session_num}")
    st.markdown(
        "<div class='form-text'>"
        "<b>Rules:</b> Respond with 1–3 <i>positive or neutral</i> words. "
        "No symbols or numbers. Different word for each cue (one repeat allowed)."
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    # Top banner
    cols = st.columns([1, 2, 1])
    with cols[0]:
        st.markdown(f"<div class='points-banner'>Points: {score_so_far}</div>", unsafe_allow_html=True)
    with cols[2]:
        st.markdown(f"<div class='progress-text' style='text-align:right;'>Cue {completed_count + 1} of {total}</div>", unsafe_allow_html=True)

    st.progress(safe_progress(completed_count, total))

    feedback_placeholder = st.empty()

    cue = cue_words[completed_count]
    st.markdown(
        f"<div class='cue-word' style='text-align:center; font-size:32px; font-weight:bold; "
        f"color:#010d1a; padding:20px; margin:20px 0;'>{cue}</div>",
        unsafe_allow_html=True,
    )

    timer_key = f"{base_path}_start_time_{completed_count}"
    if timer_key not in st.session_state:
        st.session_state[timer_key] = time.time()

    # Form
    response_key = f"{base_path}_input_{completed_count}"
    form_key = f"{base_path}_form_{completed_count}"
    with st.form(form_key, clear_on_submit=True, border=False):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            response = st.text_input(
                "", 
                key=response_key,
                placeholder="e.g., kind, calm, hopeful"
            )
            submit = st.form_submit_button("Submit", type="primary", use_container_width=True)

    if submit:
        rt = round(time.time() - st.session_state[timer_key], 2)
        result = validate_ptc_response(response, cue, used, repeats_used)

        entry = {
            "cue_index": completed_count,
            "cue": cue,
            "response": (response or "").strip().lower(),
            "sentiment": result["sentiment"],
            "confidence": result["confidence"],
            "score": result["score"],
            "accepted": result["accepted"],
            "reason": result["reason"],
            "is_repeat": result["is_repeat"],
            "flagged_for_review": result.get("flagged_for_review", False),
            "flag_reason": result.get("flag_reason"),
            "feedback": result.get("feedback", ""),
            "validation_layers": result.get("validation_layers", {}),
            "response_time_sec": rt,
            "timestamp": now_iso(),
        }

        logger.log_event(code, "fat_attempt", {"session": session_num, "phase": "fat", **entry})

        existing_responses.append(entry)
        new_score = score_so_far + (entry["score"] if result["accepted"] else 0)
        new_repeats = repeats_used + (1 if (result["accepted"] and entry["is_repeat"]) else 0)
        accepted_count_after = completed_count + (1 if result["accepted"] else 0)
        all_done = accepted_count_after >= total

        payload = {
            "responses": existing_responses,
            "total_points": new_score,
            "repeats_used": new_repeats,
            "last_updated": now_iso(),
        }
        if all_done:
            payload["completed_timestamp"] = now_iso()

        logger.set(code, base_path, payload, sync=False)

        if not result["accepted"]:
            color = "#c0392b"
            if result["reason"] == "used":
                color = "#e67e22"
            msg = result.get("feedback") or "Please try a different word."
            feedback_placeholder.markdown(_format_feedback(f"⚠️ {msg}", color), unsafe_allow_html=True)
            return

        # Success
        st.session_state.pop(timer_key, None)
        clinical_msg = result.get("feedback") or "Accepted!"
        feedback_placeholder.markdown(
            _format_feedback(
                f"✅ {clinical_msg} ({result['sentiment']}, {result['confidence']:.2f}) +{entry['score']} pts",
                "#27ae60"
            ),
            unsafe_allow_html=True,
        )
        time.sleep(0.25)
        st.rerun()