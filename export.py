"""
export.py
=========
Multi-sheet Excel export — every datum stored against every participant.

Public API:
    build_workbook_bytes()         -> (bytes, summary_dict)
    build_export_dataframe()       -> pd.DataFrame   (legacy flat-row export)
    dataframe_to_xlsx_bytes(df)    -> bytes          (legacy single-sheet writer)
    export_single_participant(code)-> pd.DataFrame   (legacy single-row export)

Workbook layout (one sheet each, where data exists):
    Summary
    Participants                — one row per participant (the legacy flat view)
    Demographics                — all metadata columns
    Consent
    Progress
    Withdrawals
    Assessments_<scale>_<phase> — BDI-II / LSAS / BFNE / CBQ / BAT / Oximeter
                                  for pre / post1 / post2 / post3
    PTC_FAT                     — every FAT response, all sessions
    PTC_SentenceCompletion      — every Sentence-Completion response
    VR_SessionMeta              — completion + SUDS per session
    VR_SSQ_pre / VR_SSQ_post    — item-level SSQ
    VR_IGroupPresence           — item-level IPQ
    VR_Oximeter                 — pre + post readings flattened
    RealExposure_Sessions
    EventsLog
"""

from __future__ import annotations
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st

import config
from utils.data_logger import get_logger


# ============================================================================
# LOW-LEVEL HELPERS
# ============================================================================
def _safe_get(d: dict, *path: str) -> Any:
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _normalise_items(items_node) -> list[dict]:
    """Firebase may return list or dict; normalise to ordered list."""
    if items_node is None:
        return []
    if isinstance(items_node, list):
        return [v for v in items_node if isinstance(v, dict)]
    if isinstance(items_node, dict):
        def keyfn(kv):
            k, _ = kv
            try:
                return (0, int(k))
            except (TypeError, ValueError):
                return (1, str(k))
        return [v for _, v in sorted(items_node.items(), key=keyfn)
                if isinstance(v, dict)]
    return []


# ============================================================================
# LEGACY FLAT-ROW EXTRACTORS (kept for backward compatibility)
# ============================================================================
def _extract_lsas_scores(data: dict, assessment_key: str) -> dict:
    lsas = _safe_get(data, "assessments", assessment_key, "lsas") or {}
    return {
        f"{assessment_key}_lsas_fear": lsas.get("fear_total"),
        f"{assessment_key}_lsas_avoidance": lsas.get("avoidance_total"),
        f"{assessment_key}_lsas_total": lsas.get("total_score"),
    }


def _extract_scale_total(data: dict, assessment_key: str, scale: str) -> dict:
    scale_data = _safe_get(data, "assessments", assessment_key, scale) or {}
    # Calculate total from individual scored_value items (includes reverse scoring)
    items = _normalise_items(scale_data.get("items"))
    total = sum(int(item.get("scored_value", 0)) for item in items if isinstance(item, dict))
    return {f"{assessment_key}_{scale}_total": total}


def _extract_oximeter(data: dict, assessment_key: str) -> dict:
    ox = _safe_get(data, "assessments", assessment_key, "oximeter") or {}
    result = {}
    for point in config.OXIMETER_READING_POINTS:
        reading = ox.get(point) or {}
        result[f"{assessment_key}_oximeter_{point}_spo2"] = reading.get("spo2")
        result[f"{assessment_key}_oximeter_{point}_bpm"] = reading.get("bpm")
    return result


def _extract_bat_scores(data: dict, assessment_key: str) -> dict:
    bat = _safe_get(data, "assessments", assessment_key, "bat") or {}
    return {f"{assessment_key}_bat_total": bat.get("total_score")}


def _extract_ptc_training(data: dict) -> dict:
    ptc = data.get("ptc_training") or {}
    if not isinstance(ptc, dict):
        return {"ptc_sessions_completed": 0, "ptc_total_score": 0}
    sessions_completed = 0
    total_score = 0
    for _, sess_data in ptc.items():
        if not isinstance(sess_data, dict):
            continue
        fat = sess_data.get("fat") or {}
        sc = sess_data.get("sentence_completion") or {}
        if fat.get("completed_timestamp") and sc.get("completed_timestamp"):
            sessions_completed += 1
        total_score += int(fat.get("total_points", 0) or 0)
        total_score += int(sc.get("total_points", 0) or 0)
    return {
        "ptc_sessions_completed": sessions_completed,
        "ptc_total_score": total_score,
    }


def _extract_vr_session_summary(data: dict) -> dict:
    vr = data.get("vr_exposure") or {}
    if not isinstance(vr, dict):
        vr = {}
    result = {}
    for i in range(1, config.VR_NUM_SESSIONS + 1):
        sess = vr.get(f"session_{i}") or {}
        if not isinstance(sess, dict):
            sess = {}
        completion = sess.get("vr_completion") or {}
        confirmed = bool(completion.get("therapist_confirmed")) \
            if isinstance(completion, dict) else False
        pre_suds = sess.get("pre_suds") or {}
        post_suds = sess.get("post_suds") or {}
        result[f"vr_session_{i}_completed"] = confirmed
        result[f"vr_session_{i}_pre_suds"] = pre_suds.get("value") \
            if isinstance(pre_suds, dict) else None
        result[f"vr_session_{i}_post_suds"] = post_suds.get("value") \
            if isinstance(post_suds, dict) else None
    return result


def _extract_real_exposure_summary(data: dict) -> dict:
    re_node = data.get("real_exposure") or {}
    if not isinstance(re_node, dict):
        re_node = {}
    result = {}
    for i in range(1, config.REAL_EXP_NUM_SESSIONS + 1):
        sess = re_node.get(f"session_{i}") or {}
        if not isinstance(sess, dict):
            sess = {}
        result[f"real_exp_session_{i}_completed"] = \
            bool(sess.get("session_completed_timestamp"))
        result[f"real_exp_session_{i}_has_scenario"] = \
            bool((sess.get("therapist_scenario") or {}).get("text"))
        pre_suds = sess.get("pre_suds") or {}
        post_suds = sess.get("post_suds") or {}
        result[f"real_exp_session_{i}_pre_suds"] = pre_suds.get("value") \
            if isinstance(pre_suds, dict) else None
        result[f"real_exp_session_{i}_post_suds"] = post_suds.get("value") \
            if isinstance(post_suds, dict) else None
    return result


def _participant_to_row(code: str, data: dict) -> dict:
    """Flat one-row-per-participant view (the legacy 'Participants' sheet)."""
    meta = (data or {}).get("metadata") or {}
    progress = (data or {}).get("progress") or {}
    withdrawal = (data or {}).get("withdrawal") or {}

    row = {
        "participant_code": code,
        "roll_number": meta.get("roll_number"),
        "group": meta.get("group"),
        "name": meta.get("name"),
        "email": meta.get("email"),
        "contact": meta.get("contact"),
        "age": meta.get("age"),
        "gender": meta.get("gender"),
        "education": meta.get("education"),
        "computer_skills": meta.get("computer_skills"),
        "created_timestamp": meta.get("created_timestamp"),
        "last_updated": meta.get("last_updated"),
        "current_phase": progress.get("current_phase"),
        "last_activity_timestamp": progress.get("last_activity_timestamp"),
        "withdrawn": bool(withdrawal.get("withdrawn", False)),
        "withdrawal_timestamp": withdrawal.get("timestamp"),
        "withdrawal_reason": withdrawal.get("reason"),
        "anonymized": bool(meta.get("anonymized", False)),
    }
    # Add admin_notes as flattened columns
    admin_notes = meta.get("admin_notes") or {}
    if isinstance(admin_notes, dict):
        for key, value in admin_notes.items():
            row[f"admin_note_{key}"] = value
    for phase in ("pre", "post1", "post2", "post3"):
        row.update(_extract_lsas_scores(data, phase))
        row.update(_extract_scale_total(data, phase, "bdi"))
        row.update(_extract_scale_total(data, phase, "bfne"))
        row.update(_extract_scale_total(data, phase, "cbq"))
        row.update(_extract_scale_total(data, phase, "cbq_trait"))
        row.update(_extract_bat_scores(data, phase))
        row.update(_extract_oximeter(data, phase))
    row.update(_extract_ptc_training(data))
    row.update(_extract_vr_session_summary(data))
    row.update(_extract_real_exposure_summary(data))
    return row


# ============================================================================
# PER-SHEET BUILDERS (long-form: one row per item/response)
# ============================================================================
def _build_demographics(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        meta = data.get("metadata") or {}
        row = {
            "participant_code": code,
            **{k: meta.get(k) for k in (
                "roll_number", "group", "name", "email", "contact", "age",
                "gender", "education", "computer_skills",
                "anonymized", "anonymized_at",
                "created_timestamp", "last_updated",
            )},
        }
        # Add admin_notes as flattened columns
        admin_notes = meta.get("admin_notes") or {}
        if isinstance(admin_notes, dict):
            for key, value in admin_notes.items():
                row[f"admin_note_{key}"] = value
        rows.append(row)
    return pd.DataFrame(rows)


def _build_consent(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        c = (data or {}).get("consent") or {}
        if not c:
            continue
        rows.append({"participant_code": code, **c})
    return pd.DataFrame(rows)


def _build_progress(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        p = (data or {}).get("progress") or {}
        if not p:
            continue
        completed = p.get("completed_phases")
        if isinstance(completed, list):
            completed = ", ".join(str(x) for x in completed)
        rows.append({
            "participant_code": code,
            "current_phase": p.get("current_phase"),
            "current_session": p.get("current_session"),
            "last_activity_timestamp": p.get("last_activity_timestamp"),
            "completed_phases": completed,
        })
    return pd.DataFrame(rows)


def _build_withdrawals(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        w = (data or {}).get("withdrawal") or {}
        if not w:
            continue
        rows.append({"participant_code": code, **w})
    return pd.DataFrame(rows)


def _build_lsas_items(all_data: dict) -> pd.DataFrame:
    """Wide-by-phase: one row per (participant, phase, situation)."""
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        for phase in ("pre", "post1", "post2", "post3"):
            lsas = _safe_get(data, "assessments", phase, "lsas") or {}
            items = _normalise_items(lsas.get("items"))
            if not items:
                continue
            for i, entry in enumerate(items):
                idx = entry.get("item_index", i)
                rows.append({
                    "participant_code": code,
                    "phase": phase,
                    "item_label": f"LSAS-{int(idx) + 1 if isinstance(idx, int) else i + 1}",
                    "situation": entry.get("situation"),
                    "fear": entry.get("fear"),
                    "fear_label": entry.get("fear_label"),
                    "avoidance": entry.get("avoidance"),
                    "avoidance_label": entry.get("avoidance_label"),
                    "timestamp": entry.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_likert_items(all_data: dict, scale: str, expected_total: int) -> pd.DataFrame:
    """One row per (participant, phase, item) for BFNE / CBQ."""
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        for phase in ("pre", "post1", "post2", "post3"):
            node = _safe_get(data, "assessments", phase, scale) or {}
            items = _normalise_items(node.get("items"))
            if not items:
                continue
            for i, entry in enumerate(items):
                idx = entry.get("item_index", i)
                rows.append({
                    "participant_code": code,
                    "phase": phase,
                    "item_label": f"{scale.upper()}-{int(idx) + 1 if isinstance(idx, int) else i + 1}",
                    "item_text": entry.get("item_text"),
                    "raw_value": entry.get("raw_value"),
                    "scored_value": entry.get("scored_value"),
                    "label": entry.get("label"),
                    "timestamp": entry.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_bat_items(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        for phase in ("pre", "post1", "post2", "post3"):
            node = _safe_get(data, "assessments", phase, "bat") or {}
            items = _normalise_items(node.get("items"))
            if not items:
                continue
            for i, entry in enumerate(items):
                idx = entry.get("item_index", i)
                rows.append({
                    "participant_code": code,
                    "phase": phase,
                    "item_label": f"BAT-{int(idx) + 1 if isinstance(idx, int) else i + 1}",
                    "scenario": entry.get("item_text"),
                    "willingness": entry.get("raw_value"),
                    "scored_value": entry.get("scored_value"),
                    "label": entry.get("label"),
                    "timestamp": entry.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_bdi_ii_items(all_data: dict) -> pd.DataFrame:
    """One row per (participant, phase, item) for BDI-II."""
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        for phase in ("pre", "post1", "post2", "post3"):
            node = _safe_get(data, "assessments", phase, "bdi") or {}
            items = _normalise_items(node.get("items"))
            if not items:
                continue
            for i, entry in enumerate(items):
                idx = entry.get("item_index", i)
                rows.append({
                    "participant_code": code,
                    "phase": phase,
                    "item_label": f"BDI-II-{int(idx) + 1 if isinstance(idx, int) else i + 1}",
                    "item_title": entry.get("item_title"),
                    "raw_value": entry.get("raw_value"),
                    "scored_value": entry.get("scored_value"),
                    "statement": entry.get("statement"),
                    "timestamp": entry.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_dot_probe_summary(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        for phase in ("pre", "post1", "post2", "post3"):
            node = _safe_get(data, "assessments", phase, "dot_probe") or {}
            if not node.get("completed_timestamp"):
                continue
            rows.append({
                "participant_code": code,
                "phase": phase,
                "num_trials": node.get("num_trials"),
                "accuracy": node.get("accuracy"),
                "mean_rt_correct_ms": node.get("mean_rt_correct_ms"),
                "mean_rt_congruent_ms": node.get("mean_rt_congruent_ms"),
                "mean_rt_incongruent_ms": node.get("mean_rt_incongruent_ms"),
                "bias_index_ms": node.get("bias_index_ms"),
                "completed_timestamp": node.get("completed_timestamp"),
            })
    return pd.DataFrame(rows)


def _build_dot_probe_trials(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        for phase in ("pre", "post1", "post2", "post3"):
            node = _safe_get(data, "assessments", phase, "dot_probe") or {}
            trials = node.get("trials") or []
            if isinstance(trials, dict):
                trials = _normalise_items(trials)
            for i, t in enumerate(trials):
                if not isinstance(t, dict):
                    continue
                rows.append({
                    "participant_code": code,
                    "phase": phase,
                    "trial": t.get("trial", i + 1),
                    "threat_word": t.get("threat_word"),
                    "neutral_word": t.get("neutral_word"),
                    "word_top": t.get("word_top"),
                    "word_bottom": t.get("word_bottom"),
                    "threat_position": t.get("threat_position"),
                    "probe_position": t.get("probe_position"),
                    "is_congruent": t.get("is_congruent"),
                    "response": t.get("response"),
                    "correct": t.get("correct"),
                    "rt_ms": t.get("rt_ms"),
                    "timestamp": t.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_wsa_summary(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        for phase in ("pre", "post1", "post2", "post3"):
            node = _safe_get(data, "assessments", phase, "wsa") or {}
            if not node.get("completed_timestamp"):
                continue
            rows.append({
                "participant_code": code,
                "phase": phase,
                "num_trials": node.get("num_trials"),
                "accuracy": node.get("accuracy"),
                "mean_decision_rt_ms": node.get("mean_decision_rt_ms"),
                "mean_reading_rt_ms": node.get("mean_reading_rt_ms"),
                "completed_timestamp": node.get("completed_timestamp"),
            })
    return pd.DataFrame(rows)


def _build_wsa_trials(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        for phase in ("pre", "post1", "post2", "post3"):
            node = _safe_get(data, "assessments", phase, "wsa") or {}
            trials = node.get("trials") or []
            if isinstance(trials, dict):
                trials = _normalise_items(trials)
            for i, t in enumerate(trials):
                if not isinstance(t, dict):
                    continue
                rows.append({
                    "participant_code": code,
                    "phase": phase,
                    "trial": t.get("trial", i + 1),
                    "word": t.get("word"),
                    "sentence": t.get("sentence"),
                    "category": t.get("category"),
                    "expected": t.get("expected"),
                    "response": t.get("response"),
                    "correct": t.get("correct"),
                    "reading_rt_ms": t.get("reading_rt_ms"),
                    "reading_timed_out": t.get("reading_timed_out"),
                    "decision_rt_ms": t.get("decision_rt_ms"),
                    "decision_timed_out": t.get("decision_timed_out"),
                    "timestamp": t.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_assessment_oximeter(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        for phase in ("pre", "post1", "post2", "post3"):
            ox = _safe_get(data, "assessments", phase, "oximeter") or {}
            if not isinstance(ox, dict):
                continue
            for point in config.OXIMETER_READING_POINTS:
                r = ox.get(point) or {}
                if not r:
                    continue
                rows.append({
                    "participant_code": code,
                    "phase": phase,
                    "point": point,
                    "spo2": r.get("spo2"),
                    "bpm": r.get("bpm"),
                    "notes": r.get("notes"),
                    "timestamp": r.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_ptc_fat(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        ptc = data.get("ptc_training") or {}
        if not isinstance(ptc, dict):
            continue
        for sess_key, sess in ptc.items():
            if not isinstance(sess, dict):
                continue
            fat = sess.get("fat") or {}
            responses = fat.get("responses") or []
            if isinstance(responses, dict):
                responses = _normalise_items(responses)
            for i, r in enumerate(responses):
                if not isinstance(r, dict):
                    continue
                idx = r.get("cue_index", i)
                rows.append({
                    "participant_code": code,
                    "session": sess_key,
                    "cue_label": f"FAT-{int(idx) + 1 if isinstance(idx, int) else i + 1}",
                    "cue": r.get("cue"),
                    "response": r.get("response"),
                    "sentiment": r.get("sentiment"),
                    "confidence": r.get("confidence"),
                    "score": r.get("score"),
                    "accepted": r.get("accepted"),
                    "reason": r.get("reason"),
                    "is_repeat": r.get("is_repeat"),
                    "response_time_sec": r.get("response_time_sec"),
                    "timestamp": r.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_ptc_sentence(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        ptc = data.get("ptc_training") or {}
        if not isinstance(ptc, dict):
            continue
        for sess_key, sess in ptc.items():
            if not isinstance(sess, dict):
                continue
            sc = sess.get("sentence_completion") or {}
            responses = sc.get("responses") or []
            if isinstance(responses, dict):
                responses = _normalise_items(responses)
            for i, r in enumerate(responses):
                if not isinstance(r, dict):
                    continue
                idx = r.get("sentence_index", i)
                rows.append({
                    "participant_code": code,
                    "session": sess_key,
                    "sentence_label": f"SC-{int(idx) + 1 if isinstance(idx, int) else i + 1}",
                    "sentence": r.get("sentence"),
                    "response": r.get("response"),
                    "sentiment": r.get("sentiment"),
                    "confidence": r.get("confidence"),
                    "score": r.get("score"),
                    "accepted": r.get("accepted"),
                    "reason": r.get("reason"),
                    "is_repeat": r.get("is_repeat"),
                    "response_time_sec": r.get("response_time_sec"),
                    "timestamp": r.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_vr_session_meta(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        vr = data.get("vr_exposure") or {}
        if not isinstance(vr, dict):
            continue
        for sess_key, sess in vr.items():
            if not isinstance(sess, dict):
                continue
            comp = sess.get("vr_completion") or {}
            pre_suds = sess.get("pre_suds") or {}
            post_suds = sess.get("post_suds") or {}
            rows.append({
                "participant_code": code,
                "session": sess_key,
                "therapist_confirmed": bool(comp.get("therapist_confirmed")),
                "confirmed_timestamp": comp.get("timestamp"),
                "confirmed_by": comp.get("therapist_username"),
                "pre_suds_value": pre_suds.get("value"),
                "pre_suds_timestamp": pre_suds.get("timestamp"),
                "post_suds_value": post_suds.get("value"),
                "post_suds_timestamp": post_suds.get("timestamp"),
            })
    return pd.DataFrame(rows)


def _build_vr_ssq(all_data: dict, which: str) -> pd.DataFrame:
    """which in {'pre_ssq', 'post_ssq'}."""
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        vr = data.get("vr_exposure") or {}
        if not isinstance(vr, dict):
            continue
        for sess_key, sess in vr.items():
            if not isinstance(sess, dict):
                continue
            node = sess.get(which) or {}
            items = _normalise_items(node.get("items"))
            for i, entry in enumerate(items):
                idx = entry.get("item_index", i)
                rows.append({
                    "participant_code": code,
                    "session": sess_key,
                    "item_label": f"SSQ-{int(idx) + 1 if isinstance(idx, int) else i + 1}",
                    "symptom": entry.get("item_text"),
                    "raw_value": entry.get("raw_value"),
                    "scored_value": entry.get("scored_value"),
                    "label": entry.get("label"),
                    "timestamp": entry.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_vr_igroup(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        vr = data.get("vr_exposure") or {}
        if not isinstance(vr, dict):
            continue
        for sess_key, sess in vr.items():
            if not isinstance(sess, dict):
                continue
            node = sess.get("igroup_presence") or {}
            items = _normalise_items(node.get("items"))
            for i, entry in enumerate(items):
                idx = entry.get("item_index", i)
                rows.append({
                    "participant_code": code,
                    "session": sess_key,
                    "item_label": f"IPQ-{int(idx) + 1 if isinstance(idx, int) else i + 1}",
                    "question": entry.get("question"),
                    "value": entry.get("value"),
                    "timestamp": entry.get("timestamp"),
                })
    return pd.DataFrame(rows)


def _build_vr_oximeter(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        vr = data.get("vr_exposure") or {}
        if not isinstance(vr, dict):
            continue
        for sess_key, sess in vr.items():
            if not isinstance(sess, dict):
                continue
            for which in ("pre_oximeter", "post_oximeter"):
                ox = sess.get(which) or {}
                if not isinstance(ox, dict):
                    continue
                for point, r in ox.items():
                    if not isinstance(r, dict):
                        continue
                    rows.append({
                        "participant_code": code,
                        "session": sess_key,
                        "which": which,
                        "point": point,
                        "spo2": r.get("spo2"),
                        "bpm": r.get("bpm"),
                        "notes": r.get("notes"),
                        "timestamp": r.get("timestamp"),
                    })
    return pd.DataFrame(rows)


def _build_real_exposure(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        re_node = data.get("real_exposure") or {}
        if not isinstance(re_node, dict):
            continue
        for sess_key, sess in re_node.items():
            if not isinstance(sess, dict):
                continue
            scenario = sess.get("therapist_scenario") or {}
            pre_suds = sess.get("pre_suds") or {}
            post_suds = sess.get("post_suds") or {}
            notes = sess.get("notes") or {}
            rows.append({
                "participant_code": code,
                "session": sess_key,
                "scenario_text": scenario.get("text") if isinstance(scenario, dict) else None,
                "scenario_set_by": scenario.get("therapist_username") if isinstance(scenario, dict) else None,
                "scenario_set_at": scenario.get("timestamp_set") if isinstance(scenario, dict) else None,
                "pre_suds_value": pre_suds.get("value"),
                "pre_suds_timestamp": pre_suds.get("timestamp"),
                "post_suds_value": post_suds.get("value"),
                "post_suds_timestamp": post_suds.get("timestamp"),
                "notes_text": notes.get("text") if isinstance(notes, dict) else None,
                "session_completed_timestamp": sess.get("session_completed_timestamp"),
                "marked_by_therapist": sess.get("marked_by_therapist"),
            })
    return pd.DataFrame(rows)


def _build_events(all_data: dict) -> pd.DataFrame:
    rows = []
    for code, data in all_data.items():
        if not isinstance(data, dict):
            continue
        events = data.get("events") or {}
        iterable = events.items() if isinstance(events, dict) else enumerate(events)
        for k, v in iterable:
            if not isinstance(v, dict):
                continue
            rows.append({
                "participant_code": code,
                "event_key": k,
                "type": v.get("type"),
                "timestamp": v.get("timestamp"),
                "payload": str(v.get("payload", "")),
            })
    df = pd.DataFrame(rows)
    if not df.empty and "timestamp" in df.columns:
        df = df.sort_values(["participant_code", "timestamp"], na_position="last")
    return df


# ============================================================================
# PUBLIC: MULTI-SHEET EXPORT
# ============================================================================
SHEET_NAME_MAX = 31  # Excel hard limit


def _safe_sheet_name(name: str) -> str:
    return name[:SHEET_NAME_MAX]


def build_workbook_bytes() -> tuple[bytes | None, dict]:
    """
    Build a comprehensive multi-sheet workbook of ALL data. Returns
    (bytes, summary_dict). Returns (None, {}) if no participants exist.
    """
    logger = get_logger()
    all_data = logger.list_all_participants() or {}
    all_data = {k: v for k, v in all_data.items() if isinstance(v, dict)}
    if not all_data:
        return (None, {})

    # Build every sheet up-front so we can include a non-trivial summary.
    sheets: dict[str, pd.DataFrame] = {
        "Participants": pd.DataFrame(
            [_participant_to_row(code, data) for code, data in all_data.items()]
        ),
        "Demographics": _build_demographics(all_data),
        "Consent": _build_consent(all_data),
        "Progress": _build_progress(all_data),
        "Withdrawals": _build_withdrawals(all_data),
        "Assessments_LSAS_items": _build_lsas_items(all_data),
        "Assessments_BDI_II_items": _build_bdi_ii_items(all_data),
        "Assessments_BFNE_items": _build_likert_items(all_data, "bfne", len(config.BFNE_ITEMS)),
        "Assessments_CBQ_items": _build_likert_items(all_data, "cbq", len(config.CBQ_ITEMS)),
        "Assessments_CBQ_Trait_items": _build_likert_items(all_data, "cbq_trait", len(config.CBQ_TRAIT_ITEMS)),
        "Assessments_BAT_items": _build_bat_items(all_data),
        "Assessments_DotProbe_summary": _build_dot_probe_summary(all_data),
        "Assessments_DotProbe_trials": _build_dot_probe_trials(all_data),
        "Assessments_WSA_summary": _build_wsa_summary(all_data),
        "Assessments_WSA_trials": _build_wsa_trials(all_data),
        "Assessments_Oximeter": _build_assessment_oximeter(all_data),
        "PTC_FAT": _build_ptc_fat(all_data),
        "PTC_SentenceCompletion": _build_ptc_sentence(all_data),
        "VR_SessionMeta": _build_vr_session_meta(all_data),
        "VR_SSQ_pre": _build_vr_ssq(all_data, "pre_ssq"),
        "VR_SSQ_post": _build_vr_ssq(all_data, "post_ssq"),
        "VR_IGroupPresence": _build_vr_igroup(all_data),
        "VR_Oximeter": _build_vr_oximeter(all_data),
        "RealExposure_Sessions": _build_real_exposure(all_data),
        "EventsLog": _build_events(all_data),
    }

    # Drop empty sheets so the workbook stays clean
    sheets = {k: v for k, v in sheets.items() if isinstance(v, pd.DataFrame) and not v.empty}

    # Build summary sheet (counts of rows per sheet + group counts)
    participants_df = sheets.get("Participants", pd.DataFrame())
    summary_rows = [
        {"Metric": "Total Participants", "Value": len(participants_df)},
    ]
    if "group" in participants_df.columns:
        for grp in config.GROUPS:
            summary_rows.append({
                "Metric": f"Group {grp}",
                "Value": int((participants_df["group"] == grp).sum()),
            })
    if "withdrawn" in participants_df.columns:
        summary_rows.append({"Metric": "Withdrawn",
                             "Value": int(participants_df["withdrawn"].sum())})
        summary_rows.append({"Metric": "Active",
                             "Value": int((~participants_df["withdrawn"]).sum())})
    if "current_phase" in participants_df.columns:
        summary_rows.append({
            "Metric": "Completed All Phases",
            "Value": int((participants_df["current_phase"] == "complete").sum()),
        })
    for sheet_name, df in sheets.items():
        summary_rows.append({"Metric": f"{sheet_name} rows", "Value": len(df)})
    summary_df = pd.DataFrame(summary_rows)

    # Write to xlsx
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=_safe_sheet_name(name), index=False)

    out.seek(0)
    return (
        out.getvalue(),
        {
            "participants": len(participants_df),
            "sheets": len(sheets) + 1,
            "rows_per_sheet": {name: len(df) for name, df in sheets.items()},
        },
    )


# ============================================================================
# LEGACY PUBLIC API (kept so existing callers keep working)
# ============================================================================
@st.cache_data(ttl=60)
def build_export_dataframe() -> pd.DataFrame:
    """Legacy one-row-per-participant DataFrame."""
    logger = get_logger()
    all_data = logger.list_all_participants() or {}
    if not all_data:
        return pd.DataFrame()
    rows = [_participant_to_row(code, data)
            for code, data in all_data.items() if isinstance(data, dict)]
    df = pd.DataFrame(rows)
    if "created_timestamp" in df.columns:
        df = df.sort_values("created_timestamp", ascending=True)
    return df


def dataframe_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Legacy single-sheet writer."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All Participants", index=False)
    output.seek(0)
    return output.getvalue()


def export_single_participant(code: str) -> pd.DataFrame:
    logger = get_logger()
    data = logger.load_participant(code)
    if not data:
        return pd.DataFrame()
    return pd.DataFrame([_participant_to_row(code, data)])


def build_single_participant_workbook(code: str) -> tuple[bytes | None, dict]:
    """
    Build a comprehensive multi-sheet workbook for a SINGLE participant.
    Returns (bytes, summary_dict). Returns (None, {}) if participant not found.
    """
    logger = get_logger()
    data = logger.load_participant(code)
    if not data or not isinstance(data, dict):
        return (None, {})

    # Wrap single participant data in the format expected by sheet builders
    single_data = {code: data}

    # Build every sheet up-front so we can include a non-trivial summary.
    sheets: dict[str, pd.DataFrame] = {
        "Participants": pd.DataFrame([_participant_to_row(code, data)]),
        "Demographics": _build_demographics(single_data),
        "Consent": _build_consent(single_data),
        "Progress": _build_progress(single_data),
        "Withdrawals": _build_withdrawals(single_data),
        "Assessments_LSAS_items": _build_lsas_items(single_data),
        "Assessments_BDI_II_items": _build_bdi_ii_items(single_data),
        "Assessments_BFNE_items": _build_likert_items(single_data, "bfne", len(config.BFNE_ITEMS)),
        "Assessments_CBQ_items": _build_likert_items(single_data, "cbq", len(config.CBQ_ITEMS)),
        "Assessments_CBQ_Trait_items": _build_likert_items(single_data, "cbq_trait", len(config.CBQ_TRAIT_ITEMS)),
        "Assessments_BAT_items": _build_bat_items(single_data),
        "Assessments_DotProbe_summary": _build_dot_probe_summary(single_data),
        "Assessments_DotProbe_trials": _build_dot_probe_trials(single_data),
        "Assessments_WSA_summary": _build_wsa_summary(single_data),
        "Assessments_WSA_trials": _build_wsa_trials(single_data),
        "Assessments_Oximeter": _build_assessment_oximeter(single_data),
        "PTC_FAT": _build_ptc_fat(single_data),
        "PTC_SentenceCompletion": _build_ptc_sentence(single_data),
        "VR_SessionMeta": _build_vr_session_meta(single_data),
        "VR_SSQ_pre": _build_vr_ssq(single_data, "pre_ssq"),
        "VR_SSQ_post": _build_vr_ssq(single_data, "post_ssq"),
        "VR_IGroupPresence": _build_vr_igroup(single_data),
        "VR_Oximeter": _build_vr_oximeter(single_data),
        "RealExposure_Sessions": _build_real_exposure(single_data),
        "EventsLog": _build_events(single_data),
    }

    # Drop empty sheets so the workbook stays clean
    sheets = {k: v for k, v in sheets.items() if isinstance(v, pd.DataFrame) and not v.empty}

    # Build summary sheet for single participant
    meta = data.get("metadata") or {}
    summary_rows = [
        {"Metric": "Participant Code", "Value": code},
        {"Metric": "Name", "Value": meta.get("name", "")},
        {"Metric": "Roll Number", "Value": meta.get("roll_number", "")},
        {"Metric": "Group", "Value": meta.get("group", "")},
        {"Metric": "Current Phase", "Value": (data.get("progress") or {}).get("current_phase", "")},
    ]
    for sheet_name, df in sheets.items():
        summary_rows.append({"Metric": f"{sheet_name} rows", "Value": len(df)})
    summary_df = pd.DataFrame(summary_rows)

    # Write to xlsx
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=_safe_sheet_name(name), index=False)

    out.seek(0)
    return (
        out.getvalue(),
        {
            "participant_code": code,
            "sheets": len(sheets) + 1,
            "rows_per_sheet": {name: len(df) for name, df in sheets.items()},
        },
    )


def render_single_participant_export():
    """
    Streamlit UI component for selecting and exporting a single participant's data.
    Can be called from therapist dashboard or as a standalone export page.
    """
    st.subheader("📥 Single Participant Export")
    st.markdown(
        "<div class='form-text'>Select a participant to download their complete data "
        "as an Excel file with multiple sheets.</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    logger = get_logger()
    all_data = logger.list_all_participants() or {}
    all_data = {k: v for k, v in all_data.items() if isinstance(v, dict)}

    if not all_data:
        st.info("No participants found in the database.")
        return

    # Build participant list with metadata for selection
    participant_options = []
    for code, data in all_data.items():
        meta = data.get("metadata") or {}
        name = meta.get("name", "")
        roll = meta.get("roll_number", "")
        group = meta.get("group", "")
        label = f"{code}"
        if name:
            label += f" — {name}"
        if roll:
            label += f" (Roll: {roll})"
        if group:
            label += f" [{group}]"
        participant_options.append((code, label))

    participant_options.sort(key=lambda x: x[0])  # Sort by code

    selected = st.selectbox(
        "Select Participant:",
        options=[opt[0] for opt in participant_options],
        format_func=lambda x: next(label for code, label in participant_options if code == x),
        key="single_participant_export_select",
    )

    if selected:
        # Show participant summary
        data = all_data.get(selected, {})
        meta = data.get("metadata") or {}
        progress = data.get("progress") or {}

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Participant Code", selected)
        with col2:
            st.metric("Name", meta.get("name", "N/A"))
        with col3:
            st.metric("Group", meta.get("group", "N/A"))

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Current Phase", progress.get("current_phase", "N/A"))
        with col2:
            st.metric("Roll Number", meta.get("roll_number", "N/A"))

        st.divider()

        # Download button
        if st.button("📥 Download Participant Data", type="primary", key="download_single_participant"):
            workbook_bytes, summary = build_single_participant_workbook(selected)
            
            if workbook_bytes:
                filename = f"participant_{selected}_{st.session_state.get('user_role', 'export')}.xlsx"
                st.download_button(
                    label="⬇️ Click to Download Excel File",
                    data=workbook_bytes,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_single_participant_file"
                )
                st.success(f"Ready to download: {filename}")
                st.info(f"Workbook contains {summary.get('sheets', 0)} sheets with participant data.")
            else:
                st.error("Failed to generate workbook. Please try again.")
