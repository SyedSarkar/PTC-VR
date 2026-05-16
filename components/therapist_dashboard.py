"""
components/therapist_dashboard.py
==================================
Therapist Dashboard — comprehensive view of every datum we hold per
participant. Organised into st.subheader sections with dataframes:

    1. Identity / Demographics
    2. Consent
    3. Progress
    4. Pre-Assessment        (LSAS / BFNE / CBQ / BAT / Oximeter — item tables)
    5. PTC Training          (FAT + Sentence Completion responses per session)
    6. Post-1 Assessment
    7. VR Exposure           (per session: SSQ/SUDS/Oximeter/I-Group + mark complete)
    8. Post-2 Assessment
    9. Real Exposure         (per session: scenario/SUDS/notes + mark complete)
   10. Post-3 Assessment
   11. Withdrawal
   12. Events Log
   13. Raw JSON (debug)

Plus admin operations: mark/unmark VR and Real-Exposure session completion,
edit scenarios, and (guarded) delete participant.
"""

from __future__ import annotations
import datetime
import streamlit as st
import pandas as pd

import config
from utils.helpers import now_iso
from utils.data_logger import get_logger
from export import render_single_participant_export
 


# ============================================================================
# LOGIN
# ============================================================================
def render_login():
    st.title("Therapist Login")
    st.markdown(
        "<div class='form-text'>This area is restricted to authorized study staff.</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.form("therapist_login"):
        username = st.text_input("Username", key="ther_user")
        password = st.text_input("Password", type="password", key="ther_pass")
        submitted = st.form_submit_button("Login", type="primary")

    if submitted:
        if username == config.THERAPIST_USERNAME and password == config.THERAPIST_PASSWORD:
            st.session_state["therapist_logged_in"] = True
            st.session_state["user_role"] = "therapist"
            st.success("Logged in successfully.")
            st.rerun()
        else:
            st.error("Invalid credentials.")


# ============================================================================
# SHARED HELPERS
# ============================================================================
def _safe_get(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _normalise_items(items_node) -> list[dict]:
    """
    Firebase RTDB sometimes returns a list (when numeric keys 0..N exist) and
    sometimes a dict. Normalise to an ordered list of dicts indexed by key.
    """
    if items_node is None:
        return []
    if isinstance(items_node, list):
        return [v for v in items_node if isinstance(v, dict)]
    if isinstance(items_node, dict):
        # Sort by integer key when possible, else string key
        def keyfn(kv):
            k, _ = kv
            try:
                return (0, int(k))
            except (TypeError, ValueError):
                return (1, str(k))
        return [v for _, v in sorted(items_node.items(), key=keyfn)
                if isinstance(v, dict)]
    return []


def _scale_df(items: list[dict], scale_name: str, expected_total: int,
              columns: list[tuple[str, str]]) -> pd.DataFrame:
    """
    Build a per-item dataframe for a single scale (LSAS, BFNE, CBQ, etc.).

    columns: list of (display_name, key_in_item_dict).
    Adds an 'Item #' column with the {scale}-{n} prefix the user asked for.
    Missing items are surfaced as blank rows so gaps are visible.
    """
    rows = []
    indexed = {}
    for i, entry in enumerate(items):
        idx = entry.get("item_index", i)
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = i
        indexed[idx] = entry

    for i in range(expected_total):
        entry = indexed.get(i, {})
        row = {"Item #": f"{scale_name}-{i + 1}"}
        for display, key in columns:
            row[display] = entry.get(key, "")
        rows.append(row)
    return pd.DataFrame(rows)


def _completion_summary(node: dict) -> dict:
    """Pull common completion metadata from a questionnaire node."""
    if not isinstance(node, dict):
        return {}
    return {
        "completed_timestamp": node.get("completed_timestamp"),
        "battery_completed_timestamp": node.get("battery_completed_timestamp"),
        "total_score": node.get("total_score"),
        "fear_total": node.get("fear_total"),
        "avoidance_total": node.get("avoidance_total"),
    }


def _kv_dataframe(d: dict, key_label: str = "Field", val_label: str = "Value") -> pd.DataFrame:
    """Render a dict as a two-column dataframe."""
    if not isinstance(d, dict) or not d:
        return pd.DataFrame(columns=[key_label, val_label])
    rows = [{key_label: k, val_label: v} for k, v in d.items()]
    return pd.DataFrame(rows)


# ============================================================================
# PARTICIPANT-LIST SUMMARY ROW
# ============================================================================
def _participant_summary_row(code: str, data: dict) -> dict:
    meta = (data or {}).get("metadata") or {}
    progress = (data or {}).get("progress") or {}
    withdrawal = (data or {}).get("withdrawal") or {}

    vr_done = 0
    vr_data = (data or {}).get("vr_exposure") or {}
    if isinstance(vr_data, dict):
        for sess in vr_data.values():
            if not isinstance(sess, dict):
                continue
            comp = sess.get("vr_completion") or {}
            if isinstance(comp, dict) and comp.get("therapist_confirmed"):
                vr_done += 1

    re_done = 0
    re_data = (data or {}).get("real_exposure") or {}
    if isinstance(re_data, dict):
        for sess in re_data.values():
            if isinstance(sess, dict) and sess.get("session_completed_timestamp"):
                re_done += 1

    ptc_done = 0
    ptc_data = (data or {}).get("ptc_training") or {}
    if isinstance(ptc_data, dict):
        for sess in ptc_data.values():
            if not isinstance(sess, dict):
                continue
            fat = sess.get("fat") or {}
            sc = sess.get("sentence_completion") or {}
            if fat.get("completed_timestamp") and sc.get("completed_timestamp"):
                ptc_done += 1

    return {
        "Code": code,
        "Roll #": meta.get("roll_number", ""),
        "Group": meta.get("group", ""),
        "Phase": progress.get("current_phase", ""),
        "PTC": f"{ptc_done}/{config.PTC_NUM_SESSIONS}",
        "VR":  f"{vr_done}/{config.VR_NUM_SESSIONS}",
        "Real Exp": f"{re_done}/{config.REAL_EXP_NUM_SESSIONS}",
        "Withdrawn": "Yes" if withdrawal.get("withdrawn") else "",
        "Last Activity": progress.get("last_activity_timestamp", ""),
    }


# ============================================================================
# PARTICIPANT LIST
# ============================================================================
def render_participant_list():
    logger = get_logger()
    all_data = logger.list_all_participants()

    st.subheader("All Participants")
    if not all_data:
        st.info("No participants found yet.")
        return

    rows = [_participant_summary_row(code, data)
            for code, data in all_data.items()
            if isinstance(data, dict)]
    df = pd.DataFrame(rows)

    cols = st.columns([2, 2, 2, 2])
    with cols[0]:
        group_filter = st.selectbox("Group", ["All"] + config.GROUPS, key="t_group_filter")
    with cols[1]:
        withdrawn_filter = st.selectbox(
            "Status", ["All", "Active", "Withdrawn"], key="t_status_filter"
        )
    with cols[2]:
        search = st.text_input("Search code/roll #:", key="t_search")
    if group_filter != "All":
        df = df[df["Group"] == group_filter]
    if withdrawn_filter == "Active":
        df = df[df["Withdrawn"] != "Yes"]
    elif withdrawn_filter == "Withdrawn":
        df = df[df["Withdrawn"] == "Yes"]
    if search:
        df = df[
            df["Code"].str.contains(search, case=False, na=False)
            | df["Roll #"].astype(str).str.contains(search, case=False, na=False)
        ]

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Open a Participant Record")
    selected = st.selectbox(
        "Select a participant code:",
        options=[""] + sorted(all_data.keys()),
        key="t_selected_participant",
    )
    if selected:
        st.session_state["therapist_selected_participant"] = selected
        st.rerun()


# ============================================================================
# DETAIL SECTIONS — one function per logical section
# ============================================================================
def _section_identity(meta: dict):
    st.subheader("1. Identity & Demographics")
    keys = [
        "code", "group", "name", "roll_number", "age", "gender", "contact",
        "email", "education", "computer_skills", "anonymized",
        "anonymized_at", "created_timestamp", "last_updated",
    ]
    df = _kv_dataframe({k: meta.get(k, "") for k in keys})
    st.dataframe(df, use_container_width=True, hide_index=True)


def _section_admin_notes(code: str, meta: dict):
    """Allow admin to add custom notes, tips, links for each participant."""
    st.subheader("Admin Notes / Custom Fields")
    logger = get_logger()
    
    # Get existing admin notes
    admin_notes = meta.get("admin_notes") or {}
    if not isinstance(admin_notes, dict):
        admin_notes = {}
    
    # Display existing notes
    if admin_notes:
        st.markdown("**Existing Custom Fields:**")
        df = _kv_dataframe(admin_notes)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Option to delete a field
        with st.expander("🗑 Delete a custom field"):
            field_to_delete = st.selectbox(
                "Select field to delete:",
                options=[""] + list(admin_notes.keys()),
                key=f"del_field_{code}"
            )
            if field_to_delete and st.button(
                "Delete Field", 
                type="secondary",
                key=f"confirm_del_{code}_{field_to_delete}"
            ):
                del admin_notes[field_to_delete]
                logger.set(code, "metadata/admin_notes", admin_notes)
                logger.log_event(code, "admin_note_deleted", {"field": field_to_delete})
                st.success(f"Deleted field: {field_to_delete}")
                st.rerun()
    else:
        st.caption("No custom fields added yet.")
    
    st.divider()
    
    # Add new field
    st.markdown("**Add New Custom Field:**")
    with st.form(key=f"add_note_form_{code}"):
        col1, col2 = st.columns([2, 3])
        with col1:
            field_name = st.text_input(
                "Field Name (e.g., 'Tips', 'Resources', 'Notes')",
                key=f"field_name_{code}"
            )
        with col2:
            field_value = st.text_area(
                "Field Value (e.g., tips, links, notes)",
                key=f"field_value_{code}",
                height=80
            )
        
        submitted = st.form_submit_button("➕ Add Field", type="primary")
        
        if submitted:
            if not field_name.strip():
                st.error("Field name cannot be empty.")
            elif not field_value.strip():
                st.error("Field value cannot be empty.")
            else:
                # Add to admin_notes
                admin_notes[field_name.strip()] = field_value.strip()
                logger.set(code, "metadata/admin_notes", admin_notes)
                logger.log_event(code, "admin_note_added", {
                    "field": field_name.strip()
                })
                st.success(f"Added field: {field_name.strip()}")
                st.rerun()


def _section_consent(consent: dict):
    st.subheader("2. Consent")
    if not consent:
        st.caption("No consent record on file.")
        return
    df = _kv_dataframe({k: consent.get(k, "") for k in ("accepted", "timestamp", "version")})
    st.dataframe(df, use_container_width=True, hide_index=True)


def _section_progress(progress: dict):
    st.subheader("3. Progress")
    if not progress:
        st.caption("No progress record on file.")
        return
    keys = ["current_phase", "current_session", "last_activity_timestamp",
            "completed_phases"]
    flat = {}
    for k in keys:
        v = progress.get(k)
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        flat[k] = v
    st.dataframe(_kv_dataframe(flat), use_container_width=True, hide_index=True)


def _render_lsas_table(lsas_node: dict):
    """LSAS — 24 items, each with fear and avoidance ratings."""
    items = _normalise_items((lsas_node or {}).get("items"))
    df = _scale_df(
        items, "LSAS", len(config.LSAS_ITEMS),
        columns=[
            ("Situation", "situation"),
            ("Fear (0–3)", "fear"),
            ("Fear Label", "fear_label"),
            ("Avoidance (0–3)", "avoidance"),
            ("Avoidance Label", "avoidance_label"),
            ("Timestamp", "timestamp"),
        ],
    )
    st.dataframe(df, use_container_width=True, hide_index=True)
    total_score = sum(int(entry.get("fear", 0)) + int(entry.get("avoidance", 0)) for entry in items if isinstance(entry, dict))
    fear_total = sum(int(entry.get("fear", 0)) for entry in items if isinstance(entry, dict))
    avoidance_total = sum(int(entry.get("avoidance", 0)) for entry in items if isinstance(entry, dict))
    
    st.caption(
        f"Totals — Fear: **{fear_total}**  ·  "
        f"Avoidance: **{avoidance_total}**  ·  "
        f"Combined: **{total_score}**"
    )


def _render_likert_table(node: dict, scale_name: str, total_items: int, item_label: str):
    items = _normalise_items((node or {}).get("items"))
    df = _scale_df(
        items, scale_name, total_items,
        columns=[
            (item_label, "item_text"),
            ("Raw", "raw_value"),
            ("Scored", "scored_value"),
            ("Label", "label"),
            ("Timestamp", "timestamp"),
        ],
    )
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Calculate total score from items since it's not stored at node level
    total_score = sum(int(entry.get("scored_value", 0)) for entry in items if isinstance(entry, dict))
    
    tot = _completion_summary(node)
    completed = tot.get("completed_timestamp") or node.get("completed_timestamp")
    if total_score > 0 or completed:
        st.caption(
            f"Total Score: **{total_score}**  ·  "
            f"Completed: {completed or '—'}"
        )


def _render_bdi_ii_table(node: dict):
    """BDI-II — 21 items with item-specific statements."""
    items = _normalise_items((node or {}).get("items"))
    rows = []
    indexed = {}
    for i, entry in enumerate(items):
        idx = entry.get("item_index", i)
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = i
        indexed[idx] = entry

    # Calculate total score from items
    total_score = sum(int(entry.get("scored_value", 0)) for entry in items if isinstance(entry, dict))

    for i in range(len(config.BDI_II_ITEMS)):
        entry = indexed.get(i, {})
        rows.append({
            "Item #": f"BDI-II-{i + 1}",
            "Title": entry.get("item_title", ""),
            "Selected Statement": entry.get("statement", ""),
            "Score (0–3)": entry.get("scored_value", ""),
            "Timestamp": entry.get("timestamp", ""),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    tot = _completion_summary(node)
    completed = tot.get("completed_timestamp") or node.get("completed_timestamp")
    if total_score > 0 or completed:
        st.caption(
            f"Total Score: **{total_score}**  ·  "
            f"Completed: {completed or '—'}"
        )


def _render_bat_table(node: dict):
    """BAT items historically saved `scenario` / `willingness` instead of
    the generic `item_text` / `raw_value` used by Likert scales. Build the
    rows directly from the BAT keys (with fallbacks for newer aliased data)."""
    # Handle both dict and list structures
    if isinstance(node, list):
        items = _normalise_items(node)
    else:
        items = _normalise_items((node or {}).get("items"))
    rows = []
    indexed = {}
    for i, entry in enumerate(items):
        idx = entry.get("item_index", i)
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = i
        indexed[idx] = entry
    for i in range(len(config.BAT_SCENARIOS)):
        e = indexed.get(i, {})
        scenario = e.get("scenario") or e.get("item_text") or config.BAT_SCENARIOS[i]
        willingness = e.get("willingness")
        if willingness is None:
            willingness = e.get("raw_value")
        rows.append({
            "Item #": f"BAT-{i + 1}",
            "Scenario": scenario,
            "Willingness (0–10)": willingness,
            "Label": e.get("label") or (f"{willingness} / 10" if willingness is not None else ""),
            "Timestamp": e.get("timestamp", ""),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    tot = _completion_summary(node)
    if tot.get("total_score") is not None or tot.get("completed_timestamp"):
        st.caption(
            f"Total Willingness: **{tot.get('total_score', '—')}**  ·  "
            f"Completed: {tot.get('completed_timestamp') or '—'}"
        )


def _render_dot_probe_block(node: dict):
    """Render a dot-probe block (one assessment point)."""
    if not isinstance(node, dict) or not node.get("completed_timestamp"):
        st.caption("Not completed.")
        return
    s_cols = st.columns(4)
    with s_cols[0]:
        st.metric("Trials", node.get("num_trials", "—"))
    with s_cols[1]:
        st.metric("Accuracy", f"{(node.get('accuracy') or 0) * 100:.1f}%")
    with s_cols[2]:
        st.metric("Mean RT (correct)",
                  f"{node.get('mean_rt_correct_ms', '—')} ms")
    with s_cols[3]:
        st.metric("Bias Index",
                  f"{node.get('bias_index_ms', '—')} ms",
                  help="Mean RT(incongruent) − Mean RT(congruent). "
                       "Positive = attentional bias toward threat.")
    st.caption(
        f"Completed: {node.get('completed_timestamp', '—')}  ·  "
        f"Mean RT congruent: {node.get('mean_rt_congruent_ms', '—')} ms  ·  "
        f"Mean RT incongruent: {node.get('mean_rt_incongruent_ms', '—')} ms"
    )
    trials = node.get("trials") or []
    if isinstance(trials, dict):
        trials = _normalise_items(trials)
    if trials:
        df = pd.DataFrame([{
            "Trial #": f"DP-{t.get('trial', i + 1)}",
            "Threat Word": t.get("threat_word"),
            "Neutral Word": t.get("neutral_word"),
            "Threat Pos": t.get("threat_position"),
            "Probe Pos": t.get("probe_position"),
            "Congruent": t.get("is_congruent"),
            "Response": t.get("response"),
            "Correct": t.get("correct"),
            "RT (ms)": t.get("rt_ms"),
            "Timestamp": t.get("timestamp"),
        } for i, t in enumerate(trials)])
        st.dataframe(df, use_container_width=True, hide_index=True)




def _render_oximeter_table(ox_node: dict):
    rows = []
    if isinstance(ox_node, dict):
        for point in config.OXIMETER_READING_POINTS:
            r = ox_node.get(point) or {}
            rows.append({
                "Point": point,
                "SpO₂ (%)": r.get("spo2"),
                "BPM": r.get("bpm"),
                "Notes": r.get("notes"),
                "Timestamp": r.get("timestamp"),
            })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_igroup_table(node: dict):
    items = _normalise_items((node or {}).get("items"))
    df = _scale_df(
        items, "IPQ", len(config.IGROUP_ITEMS),
        columns=[
            ("Question", "question"),
            ("Value (1–7)", "value"),
            ("Timestamp", "timestamp"),
        ],
    )
    st.dataframe(df, use_container_width=True, hide_index=True)
    tot = _completion_summary(node)
    if tot.get("total_score") is not None:
        st.caption(
            f"Total Score: **{tot.get('total_score')}**  ·  "
            f"Completed: {tot.get('completed_timestamp') or '—'}"
        )


def _render_gate_control(code: str, gate_key: str, label_when_pending: str):
    """Approve / revoke control for a single therapist-approval gate.

    Skips entirely if no gate_key was passed (e.g., post3 has no gate).
    """
    if not gate_key:
        return
    logger = get_logger()
    gate = logger.get_gate(code, gate_key)
    approved = bool(gate.get("approved"))
    cols = st.columns([2, 4])
    with cols[0]:
        if approved:
            if st.button(f"↩ Revoke Approval", type="secondary",
                         key=f"gate_revoke_{code}_{gate_key}"):
                logger.revoke_gate(code, gate_key)
                logger.log_event(code, "gate_revoked", {"gate": gate_key})
                st.rerun()
        else:
            if st.button(f"✓ Approve Next Step", type="primary",
                         key=f"gate_approve_{code}_{gate_key}"):
                logger.approve_gate(code, gate_key,
                                    by=config.THERAPIST_USERNAME)
                logger.log_event(code, "gate_approved", {"gate": gate_key})
                st.rerun()
    with cols[1]:
        if approved:
            st.caption(
                f"✅ Approved at {gate.get('timestamp', '')} by "
                f"{gate.get('by', '')}"
            )
        else:
            st.caption(f"⏳ {label_when_pending}")


def _section_assessment(code: str, data: dict, key: str, heading: str,
                        gate_key: str | None):
    st.subheader(heading)
    node = _safe_get(data, "assessments", key) or {}
    if not node:
        st.caption("Not started.")
        return

    battery_done = node.get("battery_completed_timestamp")
    if battery_done:
        st.caption(f"Battery completed: **{battery_done}**")

    # Inline approval control (only when battery is complete AND a gate exists)
    if battery_done and gate_key:
        _render_gate_control(
            code, gate_key,
            label_when_pending=f"Pending therapist approval — "
                               f"{config.APPROVAL_GATE_LABELS.get(gate_key, gate_key)}",
        )

    st.markdown("**LSAS — Liebowitz Social Anxiety Scale (24 items)**")
    _render_lsas_table(node.get("lsas") or {})

    st.markdown("**BDI-II — Beck Depression Inventory II (21 items)**")
    _render_bdi_ii_table(node.get("bdi") or {})

    st.markdown("**BFNE — Brief Fear of Negative Evaluation (12 items)**")
    _render_likert_table(node.get("bfne") or {}, "BFNE", len(config.BFNE_ITEMS), "Item")

    st.markdown("**CBQ — Cognitive Beliefs Questionnaire (20 items)**")
    _render_likert_table(node.get("cbq") or {}, "CBQ", len(config.CBQ_ITEMS), "Item")

    st.markdown("**CBQ-Trait — Cognitive Beliefs Questionnaire - Trait (20 items)**")
    _render_likert_table(node.get("cbq_trait") or {}, "CBQ-Trait", len(config.CBQ_TRAIT_ITEMS), "Item")

    st.markdown("**BAT — Behavioral Avoidance Task (8 scenarios)**")
    _render_bat_table(node.get("bat") or {})

    st.markdown("**Attentional Bias — Dot-Probe Task**")
    _render_dot_probe_block(node.get("dot_probe") or {})

    st.markdown("**Oximeter Readings**")
    _render_oximeter_table(node.get("oximeter") or {})


def _section_ptc_training(code: str, data: dict, group: str):
    if group != "PTC":
        return
    st.subheader("5. PTC Training (Group A only)")
    ptc = data.get("ptc_training") or {}
    if not isinstance(ptc, dict) or not ptc:
        st.caption("Not started.")
        return

    for sess_num in range(1, config.PTC_NUM_SESSIONS + 1):
        sess = ptc.get(f"session_{sess_num}") or {}
        fat = sess.get("fat") or {}
        sc = sess.get("sentence_completion") or {}
        session_done = bool(fat.get("completed_timestamp")) and \
                       bool(sc.get("completed_timestamp"))

        with st.expander(
            f"Session {sess_num}  —  {'✅ Complete' if session_done else '⏳ In progress'}",
            expanded=False,
        ):
            # Session-level approval gate (only after both tasks complete)
            if session_done:
                next_label = (
                    f"Session {sess_num + 1}" if sess_num < config.PTC_NUM_SESSIONS
                    else "Post-Assessment 1"
                )
                _render_gate_control(
                    code, f"ptc_session_{sess_num}",
                    label_when_pending=f"Pending approval to start {next_label}",
                )
                st.divider()

            st.markdown(
                "**Free Association Task (FAT)**  \n"
                "<small>Every attempt is logged — accepted rows have "
                "Accepted = ☑, rejected rows have Accepted = ☐.</small>",
                unsafe_allow_html=True,
            )
            fat_rows = _normalise_items({str(i): r for i, r in
                                         enumerate((fat.get("responses") or []))})
            if fat_rows:
                df = pd.DataFrame([{
                    "Cue #": f"FAT-{r.get('cue_index', i) + 1 if isinstance(r.get('cue_index', i), int) else i + 1}",
                    "Cue": r.get("cue"),
                    "Response": r.get("response"),
                    "Sentiment": r.get("sentiment"),
                    "Confidence": r.get("confidence"),
                    "Score": r.get("score"),
                    "Accepted": r.get("accepted"),
                    "Reason": r.get("reason"),
                    "Is Repeat": r.get("is_repeat"),
                    "RT (s)": r.get("response_time_sec"),
                    "Timestamp": r.get("timestamp"),
                } for i, r in enumerate(fat_rows)])
                st.dataframe(df, use_container_width=True, hide_index=True)
                n_total = len(fat_rows)
                n_accept = sum(1 for r in fat_rows if r.get("accepted"))
                n_reject = n_total - n_accept
                st.caption(
                    f"Attempts: **{n_total}** ({n_accept} accepted · "
                    f"{n_reject} rejected)  ·  "
                    f"FAT Points: **{fat.get('total_points', 0)}**  ·  "
                    f"Repeats Used: {fat.get('repeats_used', 0)}  ·  "
                    f"Completed: {fat.get('completed_timestamp') or '—'}"
                )
            else:
                st.caption("No FAT responses yet.")

            st.markdown(
                "**Sentence Completion**  \n"
                "<small>Every attempt is logged — accepted rows have "
                "Accepted = ☑, rejected rows have Accepted = ☐.</small>",
                unsafe_allow_html=True,
            )
            sc_rows = _normalise_items({str(i): r for i, r in
                                        enumerate((sc.get("responses") or []))})
            if sc_rows:
                df = pd.DataFrame([{
                    "Sentence #": f"SC-{r.get('sentence_index', i) + 1 if isinstance(r.get('sentence_index', i), int) else i + 1}",
                    "Sentence Stem": r.get("sentence"),
                    "Response": r.get("response"),
                    "Sentiment": r.get("sentiment"),
                    "Confidence": r.get("confidence"),
                    "Score": r.get("score"),
                    "Accepted": r.get("accepted"),
                    "Reason": r.get("reason"),
                    "Is Repeat": r.get("is_repeat"),
                    "RT (s)": r.get("response_time_sec"),
                    "Timestamp": r.get("timestamp"),
                } for i, r in enumerate(sc_rows)])
                st.dataframe(df, use_container_width=True, hide_index=True)
                n_total = len(sc_rows)
                n_accept = sum(1 for r in sc_rows if r.get("accepted"))
                n_reject = n_total - n_accept
                st.caption(
                    f"Attempts: **{n_total}** ({n_accept} accepted · "
                    f"{n_reject} rejected)  ·  "
                    f"Sentence-Completion Points: **{sc.get('total_points', 0)}**  ·  "
                    f"Repeats Used: {sc.get('repeats_used', 0)}  ·  "
                    f"Completed: {sc.get('completed_timestamp') or '—'}"
                )
            else:
                st.caption("No sentence-completion responses yet.")


def _section_vr_exposure(code: str, data: dict):
    st.subheader("7. VR Exposure")
    logger = get_logger()
    vr = data.get("vr_exposure") or {}

    for sess_num in range(1, config.VR_NUM_SESSIONS + 1):
        sess = vr.get(f"session_{sess_num}") or {}
        completion = sess.get("vr_completion") or {}
        confirmed = isinstance(completion, dict) and bool(completion.get("therapist_confirmed"))

        with st.expander(
            f"VR Session {sess_num}  —  "
            f"{'✅ Confirmed' if confirmed else '⏳ Pending'}",
            expanded=False,
        ):
            # ---- Mark / Unmark complete ------------------------------------
            cc1, cc2, cc3 = st.columns([2, 2, 4])
            with cc1:
                if not confirmed:
                    if st.button("✓ Mark Completed", type="primary",
                                 key=f"vr_mark_{code}_{sess_num}"):
                        logger.set(code,
                                   f"vr_exposure/session_{sess_num}/vr_completion", {
                                       "therapist_confirmed": True,
                                       "therapist_username": config.THERAPIST_USERNAME,
                                       "timestamp": now_iso(),
                                   })
                        logger.log_event(code, "vr_session_marked_complete",
                                         {"session": sess_num})
                        st.rerun()
                else:
                    if st.button("✗ Unmark", type="secondary",
                                 key=f"vr_unmark_{code}_{sess_num}"):
                        logger.delete_path(code,
                                           f"vr_exposure/session_{sess_num}/vr_completion")
                        logger.log_event(code, "vr_session_unmarked",
                                         {"session": sess_num})
                        st.rerun()
            with cc2:
                if confirmed:
                    ts = completion.get("timestamp", "")
                    by = completion.get("therapist_username", "")
                    st.caption(f"Confirmed at {ts} by {by}")

            # ---- Sub-step data ---------------------------------------------
            st.markdown("**Pre-VR SSQ (16 items)**")
            _render_likert_table(sess.get("pre_ssq") or {}, f"VR{sess_num}-preSSQ",
                                 len(config.SSQ_ITEMS), "Symptom")

            st.markdown("**Pre-VR SUDS**")
            ps = sess.get("pre_suds") or {}
            st.dataframe(_kv_dataframe({
                "Value (0–100)": ps.get("value"),
                "Timestamp": ps.get("timestamp"),
            }), use_container_width=True, hide_index=True)

            st.markdown("**Pre-VR Oximeter**")
            _render_oximeter_table(sess.get("pre_oximeter") or {})

            st.markdown("**Post-VR SUDS**")
            ps = sess.get("post_suds") or {}
            st.dataframe(_kv_dataframe({
                "Value (0–100)": ps.get("value"),
                "Timestamp": ps.get("timestamp"),
            }), use_container_width=True, hide_index=True)

            st.markdown("**Post-VR Oximeter**")
            _render_oximeter_table(sess.get("post_oximeter") or {})

            st.markdown("**I-Group Presence Questionnaire (24 items)**")
            _render_igroup_table(sess.get("igroup_presence") or {})

            st.markdown("**Post-VR SSQ (16 items)**")
            _render_likert_table(sess.get("post_ssq") or {}, f"VR{sess_num}-postSSQ",
                                 len(config.SSQ_ITEMS), "Symptom")


def _section_real_exposure(code: str, data: dict):
    st.subheader("9. Real Exposure")
    logger = get_logger()
    re_data = data.get("real_exposure") or {}

    for sess_num in range(1, config.REAL_EXP_NUM_SESSIONS + 1):
        sess = re_data.get(f"session_{sess_num}") or {}
        scenario = sess.get("therapist_scenario") or {}
        existing_text = scenario.get("text", "") if isinstance(scenario, dict) else ""
        completed_ts = sess.get("session_completed_timestamp")

        with st.expander(
            f"Real Exposure Session {sess_num}  —  "
            f"{'✅ Completed' if completed_ts else ('📝 Scenario set' if existing_text else '⏳ Pending')}",
            expanded=False,
        ):
            # ---- Scenario --------------------------------------------------
            new_text = st.text_area(
                f"Scenario for Session {sess_num}:",
                value=existing_text,
                key=f"re_scenario_{code}_{sess_num}",
                height=100,
                placeholder="e.g., Participant will go to a café and order coffee alone…",
            )
            sc_cols = st.columns([2, 2, 4])
            with sc_cols[0]:
                if st.button("💾 Save Scenario", type="primary",
                             key=f"re_save_{code}_{sess_num}"):
                    if not new_text.strip():
                        st.error("Scenario text cannot be empty.")
                    else:
                        logger.set(code, f"real_exposure/session_{sess_num}/therapist_scenario", {
                            "text": new_text.strip(),
                            "therapist_username": config.THERAPIST_USERNAME,
                            "timestamp_set": now_iso(),
                        })
                        logger.log_event(code, "real_exposure_scenario_set", {
                            "session": sess_num, "text": new_text.strip(),
                        })
                        st.rerun()
            with sc_cols[1]:
                if existing_text and st.button("🗑 Clear Scenario", type="secondary",
                                               key=f"re_clear_{code}_{sess_num}"):
                    logger.delete_path(code,
                                       f"real_exposure/session_{sess_num}/therapist_scenario")
                    st.rerun()

            # ---- SUDS ------------------------------------------------------
            st.markdown("**Pre-Exposure SUDS**")
            ps = sess.get("pre_suds") or {}
            st.dataframe(_kv_dataframe({
                "Value (0–100)": ps.get("value"),
                "Timestamp": ps.get("timestamp"),
            }), use_container_width=True, hide_index=True)

            st.markdown("**Post-Exposure SUDS**")
            ps = sess.get("post_suds") or {}
            st.dataframe(_kv_dataframe({
                "Value (0–100)": ps.get("value"),
                "Timestamp": ps.get("timestamp"),
            }), use_container_width=True, hide_index=True)

            # ---- Notes -----------------------------------------------------
            notes = sess.get("notes") or {}
            note_text = notes.get("text", "") if isinstance(notes, dict) else ""
            if note_text:
                st.markdown("**Participant Notes**")
                st.text(note_text)

            # ---- Mark / Unmark Completed -----------------------------------
            mc_cols = st.columns([2, 4])
            with mc_cols[0]:
                if not completed_ts:
                    if st.button("✓ Mark Session Completed", type="primary",
                                 key=f"re_mark_{code}_{sess_num}"):
                        logger.update(code,
                                      f"real_exposure/session_{sess_num}", {
                                          "session_completed_timestamp": now_iso(),
                                          "marked_by_therapist": True,
                                      })
                        logger.log_event(code, "real_exposure_session_marked_complete",
                                         {"session": sess_num})
                        st.rerun()
                else:
                    if st.button("✗ Unmark", type="secondary",
                                 key=f"re_unmark_{code}_{sess_num}"):
                        # Remove only the completion timestamp / flag
                        logger.delete_path(code,
                                           f"real_exposure/session_{sess_num}/session_completed_timestamp")
                        logger.delete_path(code,
                                           f"real_exposure/session_{sess_num}/marked_by_therapist")
                        logger.log_event(code, "real_exposure_session_unmarked",
                                         {"session": sess_num})
                        st.rerun()
            with mc_cols[1]:
                if completed_ts:
                    st.caption(f"Completed at {completed_ts}")


def _section_withdrawal(withdrawal: dict, meta: dict):
    if not withdrawal:
        return
    st.subheader("11. Withdrawal")
    st.dataframe(_kv_dataframe({
        "Withdrawn": withdrawal.get("withdrawn"),
        "Timestamp": withdrawal.get("timestamp"),
        "Reason": withdrawal.get("reason"),
        "Anonymized": meta.get("anonymized"),
        "Anonymized At": meta.get("anonymized_at"),
    }), use_container_width=True, hide_index=True)


def _section_events(data: dict):
    st.subheader("12. Events Log")
    events = data.get("events") or {}
    if not events:
        st.caption("No events logged.")
        return

    rows = []
    iterable = events.items() if isinstance(events, dict) else enumerate(events)
    for k, v in iterable:
        if not isinstance(v, dict):
            continue
        rows.append({
            "Key": k,
            "Type": v.get("type"),
            "Timestamp": v.get("timestamp"),
            "Payload": str(v.get("payload", "")),
        })
    rows.sort(key=lambda r: r.get("Timestamp") or "")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _section_admin(code: str):
    st.subheader("13. Admin")
    confirm_key = f"confirm_delete_{code}"
    confirmed = st.session_state.get(confirm_key, False)
    cols = st.columns([2, 4])
    with cols[0]:
        if not confirmed:
            if st.button("🗑 Delete Participant", type="secondary",
                         key=f"del_init_{code}"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            if st.button(f"⚠️ CONFIRM delete {code}", type="secondary",
                         key=f"del_confirm_{code}"):
                logger = get_logger()
                ok = logger.delete_participant(code)
                if ok:
                    st.session_state[confirm_key] = False
                    st.session_state["therapist_selected_participant"] = None
                    st.success(f"Deleted {code}.")
                    st.rerun()
                else:
                    st.error("Delete failed.")
    with cols[1]:
        if confirmed:
            st.warning(
                f"Press the red button again to permanently delete **{code}** "
                "and all of its data. This cannot be undone."
            )


# ============================================================================
# PARTICIPANT DETAIL VIEW
# ============================================================================
def render_participant_detail(code: str):
    logger = get_logger()
    data = logger.load_participant(code) or {}
    meta = data.get("metadata") or {}
    progress = data.get("progress") or {}
    consent = data.get("consent") or {}
    withdrawal = data.get("withdrawal") or {}
    group = meta.get("group", "")

    # Top bar
    top = st.columns([1, 4, 1])
    with top[0]:
        if st.button("⬅ Back", key="t_back"):
            st.session_state["therapist_selected_participant"] = None
            st.rerun()
    with top[1]:
        st.title(f"Participant {code}")
    with top[2]:
        if st.button("🔄 Refresh", key="t_refresh"):
            st.rerun()

    # Summary metrics
    m = st.columns(4)
    with m[0]:
        st.metric("Group", group or "—")
    with m[1]:
        st.metric("Current Phase", progress.get("current_phase", "—"))
    with m[2]:
        st.metric("Roll #", meta.get("roll_number", "—"))
    with m[3]:
        st.metric("Withdrawn", "Yes" if withdrawal.get("withdrawn") else "No")
    st.divider()

    # Sections
    _section_identity(meta)
    st.divider()
    _section_admin_notes(code, meta)
    st.divider()
    _section_consent(consent)
    st.divider()
    _section_progress(progress)
    st.divider()
    _section_assessment(code, data, "pre", "4. Pre-Assessment", "pre_assessment")
    st.divider()
    _section_ptc_training(code, data, group)
    if group == "PTC":
        st.divider()
    _section_assessment(code, data, "post1", "6. Post-Assessment 1", "post1_assessment")
    st.divider()
    _section_vr_exposure(code, data)
    st.divider()
    _section_assessment(code, data, "post2", "8. Post-Assessment 2", "post2_assessment")
    st.divider()
    _section_real_exposure(code, data)
    st.divider()
    _section_assessment(code, data, "post3", "10. Post-Assessment 3 (Final)", None)
    if withdrawal:
        st.divider()
        _section_withdrawal(withdrawal, meta)
    st.divider()
    _section_events(data)
    st.divider()
    _section_admin(code)

    # Raw JSON dump for debugging
    with st.expander("🔧 Raw JSON (full participant document)"):
        st.json(data)


# ============================================================================
# EXPORT SECTION
# ============================================================================
def render_export():
    st.subheader("📥 Export All Data")
    st.markdown(
        "<div class='form-text'>Generate a multi-sheet Excel workbook with "
        "every datum we hold: identity, scale items, PTC responses, VR sessions, "
        "real-exposure sessions, oximeter readings, and the events log.</div>",
        unsafe_allow_html=True,
    )

    if st.button("Generate Excel Export", type="primary", key="export_btn"):
        from export import build_workbook_bytes
        with st.spinner("Building export…"):
            xlsx, summary = build_workbook_bytes()
            if xlsx is None:
                st.warning("No participant data to export.")
                return
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                "📥 Download Excel",
                data=xlsx,
                file_name=f"sad_intervention_full_export_{ts}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )
            st.success(
                f"Export ready — {summary.get('participants', 0)} participants, "
                f"{summary.get('sheets', 0)} sheets."
            )
            st.json(summary)


# ============================================================================
# PENDING APPROVALS — global queue across all participants
# ============================================================================
def _pending_gates_for_participant(data: dict) -> list[tuple[str, str]]:
    """
    Return a list of (gate_key, status_label) tuples for milestones this
    participant has completed but which still need therapist approval.
    """
    pending: list[tuple[str, str]] = []
    if not isinstance(data, dict):
        return pending
    meta = data.get("metadata") or {}
    group = meta.get("group")
    gates = data.get("gates") or {}

    def _approved(key: str) -> bool:
        node = gates.get(key) if isinstance(gates, dict) else None
        return isinstance(node, dict) and bool(node.get("approved"))

    # Pre-assessment
    pre = _safe_get(data, "assessments", "pre") or {}
    if pre.get("battery_completed_timestamp") and not _approved("pre_assessment"):
        pending.append(("pre_assessment",
                        config.APPROVAL_GATE_LABELS["pre_assessment"]))

    # PTC sessions 1..4 (Group A only)
    if group == "PTC":
        ptc = data.get("ptc_training") or {}
        if isinstance(ptc, dict):
            for n in range(1, config.PTC_NUM_SESSIONS + 1):
                sess = ptc.get(f"session_{n}") or {}
                fat = sess.get("fat") or {}
                sc = sess.get("sentence_completion") or {}
                if fat.get("completed_timestamp") and sc.get("completed_timestamp") \
                        and not _approved(f"ptc_session_{n}"):
                    pending.append((f"ptc_session_{n}",
                                    config.APPROVAL_GATE_LABELS[f"ptc_session_{n}"]))

    # Post-1
    post1 = _safe_get(data, "assessments", "post1") or {}
    if post1.get("battery_completed_timestamp") and not _approved("post1_assessment"):
        pending.append(("post1_assessment",
                        config.APPROVAL_GATE_LABELS["post1_assessment"]))

    # Post-2
    post2 = _safe_get(data, "assessments", "post2") or {}
    if post2.get("battery_completed_timestamp") and not _approved("post2_assessment"):
        pending.append(("post2_assessment",
                        config.APPROVAL_GATE_LABELS["post2_assessment"]))

    return pending


def render_pending_approvals():
    st.subheader("📋 Pending Approvals")
    st.markdown(
        "<div class='form-text'>Participants who have completed a milestone "
        "and are waiting for you to approve the next step.</div>",
        unsafe_allow_html=True,
    )

    logger = get_logger()
    all_data = logger.list_all_participants() or {}
    all_data = {k: v for k, v in all_data.items() if isinstance(v, dict)}

    rows = []
    for code, data in all_data.items():
        meta = data.get("metadata") or {}
        if (data.get("withdrawal") or {}).get("withdrawn"):
            continue
        for gate_key, label in _pending_gates_for_participant(data):
            rows.append({
                "code": code,
                "roll_number": meta.get("roll_number", ""),
                "group": meta.get("group", ""),
                "gate_key": gate_key,
                "label": label,
            })

    if not rows:
        st.success("✅ No pending approvals. Everyone is caught up.")
        return

    st.caption(f"{len(rows)} pending approval(s).")
    
    # Accept All button
    if st.button("✓ Accept All Approvals", type="primary", key="accept_all_approvals"):
        for row in rows:
            logger.approve_gate(row["code"], row["gate_key"], by=config.THERAPIST_USERNAME)
            logger.log_event(row["code"], "gate_approved", {"gate": row["gate_key"]})
        st.success(f"✅ Approved {len(rows)} pending approval(s).")
        st.rerun()
    
    st.divider()
    
    for row in rows:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 5, 2])
            with c1:
                st.markdown(
                    f"**{row['code']}**"
                    + (f"  ·  Roll #{row['roll_number']}" if row['roll_number'] else "")
                    + (f"  ·  Group {row['group']}" if row['group'] else "")
                )
            with c2:
                st.markdown(row["label"])
            with c3:
                if st.button("✓ Approve", type="primary",
                             key=f"pa_approve_{row['code']}_{row['gate_key']}"):
                    logger.approve_gate(row["code"], row["gate_key"],
                                        by=config.THERAPIST_USERNAME)
                    logger.log_event(row["code"], "gate_approved",
                                     {"gate": row["gate_key"]})
                    st.rerun()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def render():
    if not st.session_state.get("therapist_logged_in"):
        render_login()
        return

    st.title("Therapist Dashboard")

    cols = st.columns([4, 1])
    with cols[1]:
        if st.button("🚪 Logout", type="secondary", key="t_logout"):
            st.session_state["therapist_logged_in"] = False
            st.session_state["user_role"] = None
            st.session_state["therapist_selected_participant"] = None
            st.session_state["phase"] = "welcome"
            st.rerun()

    tab1, tab2, tab3 = st.tabs([
        "👥 Participants",
        "📋 Pending Approvals",
        "📥 Export",
    ])

    with tab1:
        selected = st.session_state.get("therapist_selected_participant")
        if selected:
            render_participant_detail(selected)
        else:
            render_participant_list()

    with tab2:
        render_pending_approvals()

    with tab3:
        render_export()
        render_single_participant_export()
