"""
components/tasks/sentence_completion.py
========================================
Improved Sentence Completion with Fixed Repeat Logic + Rich Logging
"""

import time
import random
import streamlit as st

import config
from utils.helpers import safe_progress, load_csv_column_by_session, now_iso
from utils.validators import validate_ptc_response
from utils.data_logger import get_logger


def _format_feedback(msg: str, color: str, size: str = "28px") -> str:
    return (
        f"<div style='text-align:center; font-size:{size}; font-weight:bold; "
        f"color:{color}; padding:18px; margin:16px 0; border-radius:12px; "
        f"background:rgba(255,255,255,0.95); border:3px solid {color}30;'>"
        f"{msg}</div>"
    )


@st.fragment
def render(code: str, session_num: int, on_complete=None):
    logger = get_logger()
    base_path = f"ptc_training/session_{session_num}/sentence_completion"

    sentences = load_csv_column_by_session(config.PTC_SENTENCE_CSV, session_num, "Word")
    if not sentences:
        st.error(f"⚠️ No sentences found for Session {session_num}.")
        return

    shuffle_key = f"{base_path}_shuffled_sentences"
    if shuffle_key not in st.session_state:
        shuffled = sentences.copy()
        random.shuffle(shuffled)
        st.session_state[shuffle_key] = shuffled
    sentences = st.session_state[shuffle_key]
    total = len(sentences)

    # Load existing responses
    existing = logger.get(code, base_path) or {}
    existing_responses = existing.get("responses") or []
    if isinstance(existing_responses, dict):
        existing_responses = [v for _, v in sorted(existing_responses.items(), key=lambda x: int(x[0]))]

    # === CORRECT CALCULATIONS ===
    completed_count = sum(1 for r in existing_responses if r and r.get("accepted"))
    score_so_far = sum(int(r.get("score", 0)) for r in existing_responses if r)
    
    used = {str(r.get("response", "")).lower() 
            for r in existing_responses if r and r.get("accepted")}
    
    repeats_used = sum(1 for r in existing_responses 
                      if r and r.get("accepted") and r.get("is_repeat"))

    if completed_count >= total:
        st.success(f"✅ Sentence Completion Session {session_num} complete!")
        st.markdown(f"<div class='points-banner'>Final Points: {score_so_far}</div>", unsafe_allow_html=True)
        if on_complete and st.button("Continue ➜", type="primary"):
            on_complete()
        return

    st.markdown(f"## Sentence Completion Task — Session {session_num}")
    st.markdown(
        "<div class='form-text'><b>Rules:</b> Complete each sentence using 1–3 positive or neutral words. "
        f"(Max {config.PTC_MAX_REPEATS_ALLOWED} repeats allowed)</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    cols = st.columns([1, 2, 1])
    with cols[0]:
        st.markdown(f"<div class='points-banner'>Points: {score_so_far}</div>", unsafe_allow_html=True)
    with cols[2]:
        st.markdown(f"<div class='progress-text' style='text-align:right;'>Sentence {completed_count + 1} of {total}</div>", unsafe_allow_html=True)

    st.progress(safe_progress(completed_count, total))

    sentence = sentences[completed_count]
    st.markdown(
        f"<div style='text-align:center; font-size:26px; padding:24px; background:#f8fafd; "
        f"border-radius:12px; border:2px solid #e8f0f7;'><i>{sentence}</i></div>",
        unsafe_allow_html=True,
    )

    feedback_placeholder = st.empty()

    timer_key = f"{base_path}_start_time_{completed_count}"
    if timer_key not in st.session_state:
        st.session_state[timer_key] = time.time()

    with st.form(f"{base_path}_form_{completed_count}", clear_on_submit=True, border=False):
        response = st.text_input("Your completion:", 
                               placeholder="e.g., happy, calm and focused", 
                               key=f"{base_path}_input_{completed_count}")
        submit = st.form_submit_button("Submit", type="primary", use_container_width=True)

    if submit:
        rt = round(time.time() - st.session_state[timer_key], 2)
        
        # Pass freshly calculated repeats_used to validator
        result = validate_ptc_response(response, sentence, used, repeats_used)

        entry = {
            "sentence_index": completed_count,
            "sentence": sentence,
            "raw_response": (response or "").strip(),
            "normalized_response": (response or "").strip().lower(),
            "sentiment": result["sentiment"],
            "confidence": result["confidence"],
            "score": result["score"],
            "accepted": result["accepted"],
            "reason": result["reason"],
            "is_repeat": result.get("is_repeat", False),
            "response_time_sec": rt,
            "timestamp": now_iso(),
        }

        logger.log_event(code, "sentence_attempt", {"session": session_num, **entry})
        existing_responses.append(entry)

        new_score = score_so_far + (entry["score"] if result["accepted"] else 0)
        new_repeats = repeats_used + (1 if (result["accepted"] and entry["is_repeat"]) else 0)
        accepted_count_after = completed_count + (1 if result["accepted"] else 0)

        payload = {
            "responses": existing_responses,
            "total_points": new_score,
            "repeats_used": new_repeats,
            "last_updated": now_iso(),
        }
        if accepted_count_after >= total:
            payload["completed_timestamp"] = now_iso()

        logger.set(code, base_path, payload, sync=False)

        # ====================== IMPROVED FEEDBACK ======================
        if not result["accepted"]:
            if result["reason"] == "used":
                msg = f"Already used {repeats_used} time(s). Please use a different word."
                feedback_placeholder.markdown(_format_feedback(f"⚠️ {msg}", "#e67e22"), unsafe_allow_html=True)
            else:
                feedback_placeholder.markdown(
                    _format_feedback("❌ Incorrect — Try a more positive response!", "#c0392b"),
                    unsafe_allow_html=True
                )
            return

        # SUCCESS
        st.session_state.pop(timer_key, None)
        feedback_placeholder.markdown(
            _format_feedback(f"✅ Correct! +{entry['score']}", "#27ae60", "34px"),
            unsafe_allow_html=True,
        )

        # Positive Reinforcement
        if accepted_count_after % 10 == 0 or new_score % 20 == 0:
            st.balloons()
            st.success("🎉 Great progress! You're building strong positive patterns!")

        time.sleep(0.7)
        st.rerun()