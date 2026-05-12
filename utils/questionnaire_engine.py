"""
utils/questionnaire_engine.py
=============================
Generic, resume-capable engine for item-by-item questionnaires.

Used by:
  - LSAS (24 items, two scales each: fear & avoidance)
  - BFNE (12 items, 1-5)
  - CBQ  (20 items, 1-6)
  - SSQ  (16 items, 0-3)
  - I-Group Presence (24 items, 7-point)
  - BAT  (8 scenarios, 0-10)

Each questionnaire stores responses to:
    participants/{code}/{base_path}/items/{i}
Where i is the 0-based index. Resume = read existing items, jump to first unanswered.

Public API:
    run_single_scale_questionnaire(...)   # one rating per item
    run_lsas_questionnaire(...)           # special: two ratings per item
"""

from __future__ import annotations
import streamlit as st

from utils.helpers import safe_progress, now_iso
from utils.data_logger import get_logger


# ============================================================================
# SHARED HELPERS
# ============================================================================
def _load_existing_responses(code: str, base_path: str) -> dict:
    """Return {index_str: response_dict} from Firebase, or empty dict.

    Firebase Realtime Database converts numeric keys into arrays, so we
    normalise lists back into dicts before returning.
    """
    logger = get_logger()
    data = logger.get(code, f"{base_path}/items") or {}
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        # Firebase turned numeric keys into an array
        return {str(i): v for i, v in enumerate(data) if v is not None}
    return {}


def _first_unanswered_index(existing: dict, total: int) -> int:
    """Find lowest 0-based index that's not yet answered."""
    answered = {int(k) for k in existing.keys() if str(k).isdigit()}
    for i in range(total):
        if i not in answered:
            return i
    return total  # all done


def _save_item_response(code: str, base_path: str, index: int, payload: dict) -> bool:
    """
    Write one item response. We deliberately skip the redundant log_event
    write here — the same data is already stored at /items/{index}, so
    duplicating it to /events/ would double the per-click latency for no
    research benefit. Item-level edits remain greppable via the timestamp
    on the item itself.
    """
    logger = get_logger()
    payload = dict(payload)
    payload["timestamp"] = now_iso()
    return logger.set(code, f"{base_path}/items/{index}", payload)


def _save_completion(code: str, base_path: str, total_score=None, totals: dict = None):
    """Mark the questionnaire as completed."""
    logger = get_logger()
    completion = {"completed_timestamp": now_iso()}
    if total_score is not None:
        completion["total_score"] = total_score
    if totals:
        completion.update(totals)
    logger.update(code, base_path, completion)


# ============================================================================
# AUTO-ADVANCE NAVIGATION HELPERS
# ============================================================================
def _view_idx(safe_key: str, default_idx: int, total: int) -> int:
    """Current view index, clamped. Stored in session_state so Previous/Next
    can override the natural 'first unanswered' position."""
    key = f"{safe_key}_view_idx"
    cur = st.session_state.get(key, default_idx)
    cur = max(0, min(int(cur), total))
    st.session_state[key] = cur
    return cur


def _set_view_idx(safe_key: str, value: int):
    st.session_state[f"{safe_key}_view_idx"] = int(value)


def _nav_buttons(safe_key: str, view_idx: int, total: int,
                 can_advance: bool, on_next):
    """Render Previous + Next buttons. Returns True if state changed."""
    cols = st.columns([2, 4, 2])
    with cols[0]:
        if st.button("← Previous", disabled=(view_idx == 0),
                     use_container_width=True,
                     key=f"{safe_key}_prev_{view_idx}"):
            _set_view_idx(safe_key, view_idx - 1)
            st.rerun()
    with cols[2]:
        if st.button("Next →", type="primary",
                     disabled=not can_advance,
                     use_container_width=True,
                     key=f"{safe_key}_next_{view_idx}"):
            on_next()
            st.rerun()


# ============================================================================
# GENERIC SINGLE-SCALE QUESTIONNAIRE
# (BFNE, CBQ, SSQ)
# ============================================================================
def run_single_scale_questionnaire(
    code: str,
    base_path: str,
    title: str,
    instructions: str,
    items: list,
    scale_labels: list[str],
    scale_values: list[int] | None = None,
    reverse_scored_items: list[int] | None = None,  # 1-indexed
    on_complete=None,
    item_renderer=None,
):
    """
    Item-by-item questionnaire with auto-advance on selection:
      - User clicks a radio -> answer is saved and view jumps to next item
      - Previous / Next buttons allow free navigation
      - Already-answered items show their saved selection pre-filled
    """
    if scale_values is None:
        scale_values = list(range(len(scale_labels)))

    total = len(items)
    existing = _load_existing_responses(code, base_path)
    default_idx = _first_unanswered_index(existing, total)

    st.markdown(f"## {title}")
    st.markdown(f"<div class='form-text'>{instructions}</div>", unsafe_allow_html=True)
    st.divider()

    safe_key = base_path.replace("/", "_")
    view_idx = _view_idx(safe_key, default_idx, total)

    # All items answered AND view has walked past the end -> completion screen
    if view_idx >= total:
        if not _load_existing_responses(code, base_path) or \
                _first_unanswered_index(_load_existing_responses(code, base_path), total) < total:
            # Defensive: there are still unanswered items, snap back
            _set_view_idx(safe_key, _first_unanswered_index(_load_existing_responses(code, base_path), total))
            st.rerun()
        st.success("✅ This questionnaire is already complete.")
        if on_complete:
            if st.button("Continue ➜", type="primary", key=f"{base_path}_continue"):
                on_complete()
        return

    # Progress
    st.progress(safe_progress(view_idx, total))
    st.markdown(
        f"<div class='progress-text'>Item {view_idx + 1} of {total}</div>",
        unsafe_allow_html=True,
    )

    item = items[view_idx]
    item_text = item_renderer(item) if item_renderer else str(item)
    st.markdown(f"<div class='item-title'>{item_text}</div>", unsafe_allow_html=True)

    # Pre-select saved value if this item has been answered before
    saved_entry = existing.get(str(view_idx)) or existing.get(view_idx) or {}
    saved_label = saved_entry.get("label") if isinstance(saved_entry, dict) else None
    try:
        default_index = scale_labels.index(saved_label) if saved_label else None
    except ValueError:
        default_index = None

    radio_key = f"{safe_key}_item_{view_idx}"
    choice_label = st.radio(
        "Select your answer:",
        scale_labels,
        key=radio_key,
        index=default_index,
        label_visibility="collapsed",
        horizontal=False,
    )

    # Save handler — extracted so both auto-advance and Next button can call it.
    def _save_and_advance():
        if choice_label is None:
            return
        choice_idx = scale_labels.index(choice_label)
        value = scale_values[choice_idx]
        scored_value = value
        if reverse_scored_items and (view_idx + 1) in reverse_scored_items:
            scored_value = (max(scale_values) + min(scale_values)) - value
        _save_item_response(code, base_path, view_idx, {
            "item_index": view_idx,
            "item_text": str(items[view_idx]),
            "raw_value": value,
            "scored_value": scored_value,
            "label": choice_label,
        })
        # Compute completion if we just answered the last unanswered item
        new_existing = _load_existing_responses(code, base_path)
        if _first_unanswered_index(new_existing, total) >= total:
            total_score = sum(int(v.get("scored_value", 0))
                              for v in new_existing.values()
                              if isinstance(v, dict))
            _save_completion(code, base_path, total_score=total_score)
        _set_view_idx(safe_key, view_idx + 1)

    # Auto-advance: detect change vs. last-known selection for this view_idx
    last_key = f"{safe_key}_last_{view_idx}"
    if last_key not in st.session_state:
        st.session_state[last_key] = saved_label
    if choice_label is not None and choice_label != st.session_state[last_key]:
        st.session_state[last_key] = choice_label
        _save_and_advance()
        st.rerun()

    # Manual nav buttons (Previous always available; Next requires a selection)
    _nav_buttons(
        safe_key, view_idx, total,
        can_advance=(choice_label is not None),
        on_next=_save_and_advance,
    )


# ============================================================================
# LSAS QUESTIONNAIRE (Fear + Avoidance)
# ============================================================================
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
    """
    LSAS — two ratings (Fear + Avoidance) per situation.
    Auto-advance fires only after BOTH ratings are selected for an item.
    Previous/Next buttons remain available for free navigation.
    """
    total = len(items)
    existing = _load_existing_responses(code, base_path)
    default_idx = _first_unanswered_index(existing, total)

    st.markdown(f"## {title}")
    st.markdown(f"<div class='form-text'>{instructions}</div>", unsafe_allow_html=True)
    st.divider()

    safe_key = base_path.replace("/", "_")
    view_idx = _view_idx(safe_key, default_idx, total)

    if view_idx >= total:
        st.success("✅ LSAS already complete.")
        if on_complete:
            if st.button("Continue ➜", type="primary", key=f"{base_path}_continue"):
                on_complete()
        return

    st.progress(safe_progress(view_idx, total))
    st.markdown(
        f"<div class='progress-text'>Situation {view_idx + 1} of {total}</div>",
        unsafe_allow_html=True,
    )

    situation = items[view_idx]
    st.markdown(f"<div class='item-title'>{situation}</div>", unsafe_allow_html=True)

    saved_entry = existing.get(str(view_idx)) or existing.get(view_idx) or {}
    saved_fear_label = saved_entry.get("fear_label") if isinstance(saved_entry, dict) else None
    saved_avoid_label = saved_entry.get("avoidance_label") if isinstance(saved_entry, dict) else None
    try:
        fear_default_index = fear_labels.index(saved_fear_label) if saved_fear_label else None
    except ValueError:
        fear_default_index = None
    try:
        avoid_default_index = avoid_labels.index(saved_avoid_label) if saved_avoid_label else None
    except ValueError:
        avoid_default_index = None

    col_f, col_a = st.columns(2)
    with col_f:
        st.markdown("**Fear / Anxiety**",
                    help="How anxious or fearful do you feel in this situation?")
        fear_choice = st.radio(
            "Fear:", fear_labels,
            key=f"{safe_key}_fear_{view_idx}",
            index=fear_default_index,
            label_visibility="collapsed",
        )
    with col_a:
        st.markdown("**Avoidance**",
                    help="How often do you avoid this situation?")
        avoid_choice = st.radio(
            "Avoidance:", avoid_labels,
            key=f"{safe_key}_avoid_{view_idx}",
            index=avoid_default_index,
            label_visibility="collapsed",
        )

    def _save_and_advance():
        if fear_choice is None or avoid_choice is None:
            st.error("Please answer BOTH Fear and Avoidance before continuing.")
            return
        fear_val = fear_labels.index(fear_choice)
        avoid_val = avoid_labels.index(avoid_choice)
        _save_item_response(code, base_path, view_idx, {
            "item_index": view_idx,
            "situation": situation,
            "fear": fear_val,
            "avoidance": avoid_val,
            "fear_label": fear_choice,
            "avoidance_label": avoid_choice,
        })
        refreshed = _load_existing_responses(code, base_path)
        if _first_unanswered_index(refreshed, total) >= total:
            fear_total = sum(int(v.get("fear", 0)) for v in refreshed.values()
                             if isinstance(v, dict))
            avoid_total = sum(int(v.get("avoidance", 0)) for v in refreshed.values()
                              if isinstance(v, dict))
            _save_completion(
                code, base_path,
                total_score=fear_total + avoid_total,
                totals={"fear_total": fear_total, "avoidance_total": avoid_total},
            )
        _set_view_idx(safe_key, view_idx + 1)

    # Auto-advance once BOTH ratings differ from last-known
    last_fear_key = f"{safe_key}_last_fear_{view_idx}"
    last_avoid_key = f"{safe_key}_last_avoid_{view_idx}"
    if last_fear_key not in st.session_state:
        st.session_state[last_fear_key] = saved_fear_label
    if last_avoid_key not in st.session_state:
        st.session_state[last_avoid_key] = saved_avoid_label

    fear_changed = fear_choice is not None and fear_choice != st.session_state[last_fear_key]
    avoid_changed = avoid_choice is not None and avoid_choice != st.session_state[last_avoid_key]
    if fear_choice is not None:
        st.session_state[last_fear_key] = fear_choice
    if avoid_choice is not None:
        st.session_state[last_avoid_key] = avoid_choice

    if (fear_choice is not None and avoid_choice is not None) and (fear_changed or avoid_changed):
        _save_and_advance()
        st.rerun()

    _nav_buttons(
        safe_key, view_idx, total,
        can_advance=(fear_choice is not None and avoid_choice is not None),
        on_next=_save_and_advance,
    )


# ============================================================================
# I-GROUP PRESENCE QUESTIONNAIRE (7-point with left/middle/right labels)
# ============================================================================
def run_igroup_questionnaire(
    code: str,
    base_path: str,
    title: str,
    instructions: str,
    items: list,  # list of (question, left, middle, right)
    on_complete=None,
):
    """I-Group Presence — 7-point horizontal scale, one rating per item.
    Auto-advances on selection; Previous/Next buttons for free navigation."""
    total = len(items)
    existing = _load_existing_responses(code, base_path)
    default_idx = _first_unanswered_index(existing, total)

    st.markdown(f"## {title}")
    st.markdown(f"<div class='form-text'>{instructions}</div>", unsafe_allow_html=True)
    st.divider()

    safe_key = base_path.replace("/", "_")
    view_idx = _view_idx(safe_key, default_idx, total)

    if view_idx >= total:
        st.success("✅ I-Group Presence Questionnaire already complete.")
        if on_complete:
            if st.button("Continue ➜", type="primary", key=f"{safe_key}_continue"):
                on_complete()
        return

    st.progress(safe_progress(view_idx, total))
    st.markdown(
        f"<div class='progress-text'>Item {view_idx + 1} of {total}</div>",
        unsafe_allow_html=True,
    )

    question, left, middle, right = items[view_idx]
    st.markdown(f"<div class='item-title'>{question}</div>", unsafe_allow_html=True)

    anchor_cols = st.columns([2, 3, 2])
    with anchor_cols[0]:
        st.markdown(f"<div style='text-align:left;color:#555;'>{left}</div>", unsafe_allow_html=True)
    with anchor_cols[1]:
        st.markdown(f"<div style='text-align:center;color:#555;'>{middle}</div>", unsafe_allow_html=True)
    with anchor_cols[2]:
        st.markdown(f"<div style='text-align:right;color:#555;'>{right}</div>", unsafe_allow_html=True)

    saved_entry = existing.get(str(view_idx)) or existing.get(view_idx) or {}
    saved_value = saved_entry.get("value") if isinstance(saved_entry, dict) else None
    scale_values = [1, 2, 3, 4, 5, 6, 7]
    default_index = scale_values.index(int(saved_value)) if saved_value in scale_values else None

    choice = st.radio(
        "Rating:",
        options=scale_values,
        key=f"{safe_key}_item_{view_idx}",
        horizontal=True,
        index=default_index,
        label_visibility="collapsed",
    )

    def _save_and_advance():
        if choice is None:
            return
        _save_item_response(code, base_path, view_idx, {
            "item_index": view_idx,
            "question": question,
            "value": int(choice),
        })
        refreshed = _load_existing_responses(code, base_path)
        if _first_unanswered_index(refreshed, total) >= total:
            total_score = sum(int(v.get("value", 0)) for v in refreshed.values()
                              if isinstance(v, dict))
            _save_completion(code, base_path, total_score=total_score)
        _set_view_idx(safe_key, view_idx + 1)

    last_key = f"{safe_key}_last_{view_idx}"
    if last_key not in st.session_state:
        st.session_state[last_key] = saved_value
    if choice is not None and choice != st.session_state[last_key]:
        st.session_state[last_key] = choice
        _save_and_advance()
        st.rerun()

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
