"""
utils/questionnaire_engine.py
=============================
Final Optimized Version:
- Auto-advance on selection
- Batch saving (in-memory until Next or End)
- Very fast UI
"""

from __future__ import annotations
import streamlit as st

from utils.helpers import safe_progress, now_iso
from utils.data_logger import get_logger


# ============================================================================
# HELPERS
# ============================================================================
def _load_existing_responses(code: str, base_path: str) -> dict:
    logger = get_logger()
    data = logger.get(code, f"{base_path}/items") or {}
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {str(i): v for i, v in enumerate(data) if v is not None}
    return {}


def _first_unanswered_index(existing: dict, total: int) -> int:
    answered = {int(k) for k in existing.keys() if str(k).isdigit()}
    for i in range(total):
        if i not in answered:
            return i
    return total


def _save_item_response(code: str, base_path: str, index: int, payload: dict):
    logger = get_logger()
    payload = dict(payload)
    payload["timestamp"] = now_iso()
    logger.set(code, f"{base_path}/items/{index}", payload, sync=False)


def _save_completion(code: str, base_path: str, total_score: int,
                     totals: dict | None = None):
    """Write a one-shot completion marker for a questionnaire.

    Mirrors the pattern used elsewhere (assessment_battery.py, fat.py):
    a `completed_timestamp` field on the questionnaire's base path plus
    its summary score(s). Guarded so a rerun after completion does not
    rewrite the timestamp.
    """
    logger = get_logger()
    node = logger.get(code, base_path) or {}
    if isinstance(node, dict) and node.get("completed_timestamp"):
        return
    payload = {
        "completed_timestamp": now_iso(),
        "total_score": int(total_score),
    }
    if totals:
        payload.update({k: int(v) for k, v in totals.items()})
    logger.update(code, base_path, payload, sync=False)


def _safe_index(labels: list, value):
    """Return labels.index(value) or None if value is missing/malformed."""
    if value is None:
        return None
    try:
        return labels.index(value)
    except (ValueError, TypeError):
        return None


def _flush_pending(code: str, base_path: str, pending: dict, items: list, 
                   scale_labels: list, scale_values: list, reverse_scored=None):
    """Save all pending answers at once."""
    if not pending:
        return
    for idx, label in list(pending.items()):
        choice_idx = scale_labels.index(label)
        value = scale_values[choice_idx]
        scored = value
        if reverse_scored and (idx + 1) in reverse_scored:
            scored = (max(scale_values) + min(scale_values)) - value

        _save_item_response(code, base_path, idx, {
            "item_index": idx,
            "item_text": str(items[idx]),
            "raw_value": value,
            "scored_value": scored,
            "label": label,
        })
    pending.clear()


# ============================================================================
# NAVIGATION
# ============================================================================
def _view_idx(safe_key: str, default_idx: int, total: int) -> int:
    key = f"{safe_key}_view_idx"
    cur = st.session_state.get(key, default_idx)
    cur = max(0, min(int(cur), total))
    st.session_state[key] = cur
    return cur


def _set_view_idx(safe_key: str, value: int):
    st.session_state[f"{safe_key}_view_idx"] = int(value)


def _nav_buttons(safe_key: str, view_idx: int, total: int, can_advance: bool, on_next):
    cols = st.columns([2, 4, 2])
    with cols[0]:
        if st.button("← Previous", disabled=(view_idx == 0),
                     use_container_width=True, key=f"{safe_key}_prev"):
            _set_view_idx(safe_key, view_idx - 1)
            st.rerun()
    with cols[2]:
        if st.button("Next →", type="primary", disabled=not can_advance,
                     use_container_width=True, key=f"{safe_key}_next"):
            on_next()
            st.rerun()


# ============================================================================
# MAIN SINGLE-SCALE FUNCTION (Used by BFNE, CBQ, SSQ, CBQ-Trait)
# ============================================================================
@st.fragment
def run_single_scale_questionnaire(
    code: str,
    base_path: str,
    title: str,
    instructions: str,
    items: list,
    scale_labels: list[str],
    scale_values: list[int] | None = None,
    reverse_scored_items: list[int] | None = None,
    on_complete=None,
):
    if scale_values is None:
        scale_values = list(range(len(scale_labels)))

    total = len(items)
    safe_key = base_path.replace("/", "_")

    # Caching
    cache_key = f"{safe_key}_cache"
    pending_key = f"{safe_key}_pending"

    if cache_key not in st.session_state:
        st.session_state[cache_key] = _load_existing_responses(code, base_path)
    if pending_key not in st.session_state:
        st.session_state[pending_key] = {}

    existing = st.session_state[cache_key]
    pending = st.session_state[pending_key]

    default_idx = _first_unanswered_index(existing, total)

    st.markdown(f"## {title}")
    st.markdown(f"<div class='form-text'>{instructions}</div>", unsafe_allow_html=True)
    st.divider()

    view_idx = _view_idx(safe_key, default_idx, total)

    if view_idx >= total:
        _flush_pending(code, base_path, pending, items, scale_labels, scale_values, reverse_scored_items)
        st.success("✅ Questionnaire complete!")
        if on_complete and st.button("Continue ➜", type="primary"):
            on_complete()
        return

    st.progress(safe_progress(view_idx, total))
    st.markdown(f"**Item {view_idx + 1} of {total}**")

    item_text = str(items[view_idx])
    st.markdown(f"<div class='item-title'>{item_text}</div>", unsafe_allow_html=True)

    # Get current selection
    saved_label = pending.get(view_idx) or existing.get(str(view_idx), {}).get("label")
    try:
        default_index = scale_labels.index(saved_label) if saved_label else None
    except ValueError:
        default_index = None

    choice_label = st.radio(
        "Select your answer:",
        scale_labels,
        key=f"{safe_key}_item_{view_idx}",
        index=default_index,
        label_visibility="collapsed",
        horizontal=False,
    )

    # Save selection to memory instantly
    if choice_label is not None:
        pending[view_idx] = choice_label

    def _save_and_advance():
        _flush_pending(code, base_path, pending, items, scale_labels, scale_values, reverse_scored_items)
        _set_view_idx(safe_key, view_idx + 1)
        st.rerun()

    # Auto-advance on selection
    last_key = f"{safe_key}_last_{view_idx}"
    if last_key not in st.session_state:
        st.session_state[last_key] = saved_label

    if choice_label is not None and choice_label != st.session_state.get(last_key):
        st.session_state[last_key] = choice_label
        _save_and_advance()          # This triggers flush + move to next

    _nav_buttons(
        safe_key, view_idx, total,
        can_advance=(choice_label is not None),
        on_next=_save_and_advance,
    )
    
# ============================================================================
# LSAS QUESTIONNAIRE
# ============================================================================
@st.fragment
def run_lsas_questionnaire(
    code: str,
    base_path: str,
    title: str,
    instructions: str,
    items: list[str],
    fear_labels: list[str],
    avoid_labels: list[str],
    on_complete=None,
):
    total = len(items)
    safe_key = base_path.replace("/", "_")

    # In-memory cache — load once, then keep updates local. Eliminates the
    # per-click Firebase round-trip that made LSAS feel laggy.
    cache_key = f"{safe_key}_cache"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = _load_existing_responses(code, base_path)
    existing = st.session_state[cache_key]

    default_idx = _first_unanswered_index(existing, total)

    st.markdown(f"## {title}")
    st.markdown(f"<div class='form-text'>{instructions}</div>", unsafe_allow_html=True)
    st.divider()

    view_idx = _view_idx(safe_key, default_idx, total)

    if view_idx >= total:
        st.success("✅ LSAS already complete.")
        if on_complete and st.button("Continue ➜", type="primary", key=f"{safe_key}_continue"):
            on_complete()
        return

    st.progress(safe_progress(view_idx, total))
    st.markdown(f"**Situation {view_idx + 1} of {total}**")

    situation = items[view_idx]
    st.markdown(f"<div class='item-title'>{situation}</div>", unsafe_allow_html=True)

    saved_entry = existing.get(str(view_idx)) or existing.get(view_idx) or {}
    saved_fear = saved_entry.get("fear_label") if isinstance(saved_entry, dict) else None
    saved_avoid = saved_entry.get("avoidance_label") if isinstance(saved_entry, dict) else None

    col_f, col_a = st.columns(2)
    with col_f:
        st.markdown("**Fear / Anxiety**")
        fear_choice = st.radio("Fear:", fear_labels, key=f"{safe_key}_fear_{view_idx}",
                               index=_safe_index(fear_labels, saved_fear),
                               label_visibility="collapsed")
    with col_a:
        st.markdown("**Avoidance**")
        avoid_choice = st.radio("Avoidance:", avoid_labels, key=f"{safe_key}_avoid_{view_idx}",
                                index=_safe_index(avoid_labels, saved_avoid),
                                label_visibility="collapsed")

    def _save_and_advance():
        if fear_choice is None or avoid_choice is None:
            return
        fear_val = fear_labels.index(fear_choice)
        avoid_val = avoid_labels.index(avoid_choice)
        item_payload = {
            "item_index": view_idx,
            "situation": situation,
            "fear": fear_val,
            "avoidance": avoid_val,
            "fear_label": fear_choice,
            "avoidance_label": avoid_choice,
        }
        _save_item_response(code, base_path, view_idx, item_payload)
        # Update cache locally so we don't need to re-read from Firebase
        existing[str(view_idx)] = item_payload

        if _first_unanswered_index(existing, total) >= total:
            fear_total = sum(int(v.get("fear", 0)) for v in existing.values() if isinstance(v, dict))
            avoid_total = sum(int(v.get("avoidance", 0)) for v in existing.values() if isinstance(v, dict))
            _save_completion(code, base_path, total_score=fear_total + avoid_total,
                             totals={"fear_total": fear_total, "avoidance_total": avoid_total})

        _set_view_idx(safe_key, view_idx + 1)

    # Auto-advance logic
    last_fear_key = f"{safe_key}_last_fear_{view_idx}"
    last_avoid_key = f"{safe_key}_last_avoid_{view_idx}"

    if last_fear_key not in st.session_state:
        st.session_state[last_fear_key] = saved_fear
    if last_avoid_key not in st.session_state:
        st.session_state[last_avoid_key] = saved_avoid

    if (fear_choice is not None and avoid_choice is not None) and \
       (fear_choice != st.session_state[last_fear_key] or avoid_choice != st.session_state[last_avoid_key]):
        st.session_state[last_fear_key] = fear_choice
        st.session_state[last_avoid_key] = avoid_choice
        _save_and_advance()
        st.rerun()

    _nav_buttons(safe_key, view_idx, total,
                 can_advance=(fear_choice is not None and avoid_choice is not None),
                 on_next=_save_and_advance)


# ============================================================================
# I-GROUP PRESENCE QUESTIONNAIRE
# ============================================================================
@st.fragment
def run_igroup_questionnaire(
    code: str,
    base_path: str,
    title: str,
    instructions: str,
    items: list,
    on_complete=None,
):
    total = len(items)
    safe_key = base_path.replace("/", "_")

    # In-memory cache — same pattern as BDI / LSAS. Avoids a synchronous
    # Firebase read after every selection.
    cache_key = f"{safe_key}_cache"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = _load_existing_responses(code, base_path)
    existing = st.session_state[cache_key]

    default_idx = _first_unanswered_index(existing, total)

    st.markdown(f"## {title}")
    st.markdown(f"<div class='form-text'>{instructions}</div>", unsafe_allow_html=True)
    st.divider()

    view_idx = _view_idx(safe_key, default_idx, total)

    if view_idx >= total:
        st.success("✅ I-Group Presence Questionnaire already complete.")
        if on_complete and st.button("Continue ➜", type="primary", key=f"{safe_key}_continue"):
            on_complete()
        return

    st.progress(safe_progress(view_idx, total))
    st.markdown(f"**Item {view_idx + 1} of {total}**")

    question, left, middle, right = items[view_idx]
    st.markdown(f"<div class='item-title'>{question}</div>", unsafe_allow_html=True)

    anchor_cols = st.columns([2, 3, 2])
    with anchor_cols[0]: st.markdown(f"<div style='text-align:left;color:#555;'>{left}</div>", unsafe_allow_html=True)
    with anchor_cols[1]: st.markdown(f"<div style='text-align:center;color:#555;'>{middle}</div>", unsafe_allow_html=True)
    with anchor_cols[2]: st.markdown(f"<div style='text-align:right;color:#555;'>{right}</div>", unsafe_allow_html=True)

    saved_entry = existing.get(str(view_idx)) or existing.get(view_idx) or {}
    saved_value = saved_entry.get("value") if isinstance(saved_entry, dict) else None
    scale_values = [1, 2, 3, 4, 5, 6, 7]
    try:
        default_index = scale_values.index(int(saved_value)) if saved_value is not None else None
    except (ValueError, TypeError):
        default_index = None

    choice = st.radio(
        "Rating:", options=scale_values, key=f"{safe_key}_item_{view_idx}",
        horizontal=True, index=default_index, label_visibility="collapsed"
    )

    def _save_and_advance():
        if choice is None:
            return
        item_payload = {
            "item_index": view_idx,
            "question": question,
            "value": int(choice),
        }
        _save_item_response(code, base_path, view_idx, item_payload)
        # Update local cache; skip the Firebase re-read
        existing[str(view_idx)] = item_payload

        if _first_unanswered_index(existing, total) >= total:
            total_score = sum(int(v.get("value", 0)) for v in existing.values() if isinstance(v, dict))
            _save_completion(code, base_path, total_score=total_score)
        _set_view_idx(safe_key, view_idx + 1)

    last_key = f"{safe_key}_last_{view_idx}"
    if last_key not in st.session_state:
        st.session_state[last_key] = saved_value

    if choice is not None and choice != st.session_state.get(last_key):
        st.session_state[last_key] = choice
        _save_and_advance()
        st.rerun()

    _nav_buttons(safe_key, view_idx, total,
                 can_advance=(choice is not None),
                 on_next=_save_and_advance)


# ============================================================================
# BDI-II QUESTIONNAIRE (Custom format with item-specific statements)
# ============================================================================
@st.fragment
def run_bdi_ii_questionnaire(
    code: str,
    base_path: str,
    title: str,
    instructions: str,
    items: list,
    on_complete=None,
):
    total = len(items)
    safe_key = base_path.replace("/", "_")

    # Caching
    cache_key = f"{safe_key}_cache"
    pending_key = f"{safe_key}_pending"

    if cache_key not in st.session_state:
        st.session_state[cache_key] = _load_existing_responses(code, base_path)
    if pending_key not in st.session_state:
        st.session_state[pending_key] = {}

    existing = st.session_state[cache_key]
    pending = st.session_state[pending_key]

    default_idx = _first_unanswered_index(existing, total)

    st.markdown(f"## {title}")
    st.markdown(f"<div class='form-text'>{instructions}</div>", unsafe_allow_html=True)
    st.divider()

    view_idx = _view_idx(safe_key, default_idx, total)

    if view_idx >= total:
        # Flush pending responses
        for idx, statement in list(pending.items()):
            # Extract score from statement (first character is the number)
            score = int(statement[0]) if statement and statement[0].isdigit() else 0
            _save_item_response(code, base_path, idx, {
                "item_index": idx,
                "item_title": items[idx]["title"],
                "raw_value": score,
                "scored_value": score,
                "statement": statement,
            })
        pending.clear()
        
        st.success("✅ Questionnaire complete!")
        if on_complete and st.button("Continue ➜", type="primary"):
            on_complete()
        return

    st.progress(safe_progress(view_idx, total))
    
    item = items[view_idx]
    st.markdown(f"<div class='item-title'>{item['title']}</div>", unsafe_allow_html=True)

    # Get current selection
    saved_statement = pending.get(view_idx) or existing.get(str(view_idx), {}).get("statement")
    
    choice = st.radio(
        "Select the statement that best describes you:",
        item["statements"],
        key=f"{safe_key}_item_{view_idx}",
        index=item["statements"].index(saved_statement) if saved_statement in item["statements"] else None,
        label_visibility="collapsed",
    )

    # Save selection to memory instantly
    if choice is not None:
        pending[view_idx] = choice

    def _save_and_advance():
        # Flush pending responses
        for idx, statement in list(pending.items()):
            score = int(statement[0]) if statement and statement[0].isdigit() else 0
            _save_item_response(code, base_path, idx, {
                "item_index": idx,
                "item_title": items[idx]["title"],
                "raw_value": score,
                "scored_value": score,
                "statement": statement,
            })
        pending.clear()
        _set_view_idx(safe_key, view_idx + 1)
        st.rerun()

    # Auto-advance on selection
    last_key = f"{safe_key}_last_{view_idx}"
    if last_key not in st.session_state:
        st.session_state[last_key] = saved_statement

    if choice is not None and choice != st.session_state.get(last_key):
        st.session_state[last_key] = choice
        _save_and_advance()

    _nav_buttons(
        safe_key, view_idx, total,
        can_advance=(choice is not None),
        on_next=_save_and_advance,
    )


# ============================================================================
# COMPLETION CHECK
# ============================================================================
def is_questionnaire_complete(code: str, base_path: str, total_items: int) -> bool:
    existing = _load_existing_responses(code, base_path)
    return _first_unanswered_index(existing, total_items) >= total_items