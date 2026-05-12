"""
utils/data_logger.py
====================
Firebase wrapper for the SAD Intervention App.

Uses the firebase-admin SDK with Firebase Realtime Database.
All participant data is keyed by `participant_code`.

Usage:
    from utils.data_logger import DataLogger
    logger = DataLogger()
    logger.save_metadata(code, metadata_dict)
    logger.save_response(code, "assessments/pre/lsas/items/0", {"fear": 2, "avoidance": 1})
    data = logger.load_participant(code)
"""

from __future__ import annotations
import json
import threading
import concurrent.futures
from typing import Any

import streamlit as st

import config
from utils.helpers import now_iso

# ============================================================================
# FIREBASE INITIALIZATION (cached, thread-safe)
# ============================================================================
_init_lock = threading.Lock()
_firebase_initialized = False

# Shared executor for ALL Firebase writes — avoids spawning a new thread pool
# per call (which was the main source of per-write overhead).
_WRITE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="firebase-writer"
)


def _init_firebase():
    """Initialize firebase-admin once per process."""
    global _firebase_initialized
    if _firebase_initialized:
        return
    with _init_lock:
        if _firebase_initialized:
            return
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred_dict = config.get_firebase_credentials()
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                "databaseURL": config.FIREBASE_DATABASE_URL or
                               f"https://{cred_dict.get('project_id')}-default-rtdb.firebaseio.com/"
            })
        _firebase_initialized = True


# ============================================================================
# DATA LOGGER CLASS
# ============================================================================
class DataLogger:
    """Wrapper around Firebase Realtime Database for participant data."""

    ROOT = "participants"

    def __init__(self):
        _init_firebase()
        from firebase_admin import db
        self._db = db
        self._root_ref = db.reference(self.ROOT)

    # ------------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------------
    def _ref(self, code: str, path: str = ""):
        full = f"{self.ROOT}/{code}"
        if path:
            full += f"/{path.strip('/')}"
        return self._db.reference(full)

    def get(self, code: str, path: str = "") -> Any:
        """Read raw value at participants/{code}/{path}."""
        try:
            return self._ref(code, path).get()
        except Exception as e:
            st.warning(f"Firebase read error: {e}")
            return None

    def set(self, code: str, path: str, value: Any, sync: bool = True) -> bool:
        """
        Write value at participants/{code}/{path} (overwrites).
        sync=True (default): block up to 5s for the write to land.
        sync=False: fire-and-forget — returns immediately; the write happens
        in the shared executor. Use for hot UI paths where latency matters.
        """
        def _do_set():
            try:
                self._ref(code, path).set(value)
                return True
            except Exception:
                return False
        future = _WRITE_EXECUTOR.submit(_do_set)
        if not sync:
            return True
        try:
            return future.result(timeout=5)
        except concurrent.futures.TimeoutError:
            st.error("Firebase write timed out. Ensure Realtime Database exists and rules allow writes.")
            return False

    def update(self, code: str, path: str, value: dict, sync: bool = True) -> bool:
        """Patch (merge) a dict at participants/{code}/{path}."""
        def _do_update():
            try:
                self._ref(code, path).update(value)
                return True
            except Exception:
                return False
        future = _WRITE_EXECUTOR.submit(_do_update)
        if not sync:
            return True
        try:
            return future.result(timeout=5)
        except concurrent.futures.TimeoutError:
            st.error("Firebase update timed out. Ensure Realtime Database exists and rules allow writes.")
            return False

    def push(self, code: str, path: str, value: Any, sync: bool = True) -> str | None:
        """Append-style write under a generated key. Returns the new key
        when sync=True, or None when fire-and-forget."""
        if not sync:
            _WRITE_EXECUTOR.submit(lambda: self._ref(code, path).push(value))
            return None
        try:
            new_ref = self._ref(code, path).push(value)
            return new_ref.key
        except Exception as e:
            st.warning(f"Firebase push error: {e}")
            return None

    # ------------------------------------------------------------------------
    # Participant-level convenience
    # ------------------------------------------------------------------------
    def participant_exists(self, code: str) -> bool:
        return self.get(code, "metadata/code") is not None

    def find_by_roll_number(self, roll_number: str) -> str | None:
        """Search all participants for a matching roll_number. Returns code or None."""
        try:
            all_data = self._root_ref.order_by_child("metadata/roll_number") \
                .equal_to(roll_number).get()
            if all_data:
                return next(iter(all_data.keys()))
        except Exception:
            # Fallback: full scan (small studies only)
            try:
                all_data = self._root_ref.get() or {}
                for code, data in all_data.items():
                    if isinstance(data, dict):
                        meta = data.get("metadata") or {}
                        if str(meta.get("roll_number", "")).strip() == roll_number.strip():
                            return code
            except Exception as e:
                st.warning(f"Firebase scan error: {e}")
        return None

    def save_metadata(self, code: str, metadata: dict) -> bool:
        metadata = dict(metadata)
        metadata["last_updated"] = now_iso()
        if "created_timestamp" not in metadata:
            metadata["created_timestamp"] = now_iso()
        return self.set(code, "metadata", metadata)

    def update_metadata(self, code: str, patch: dict) -> bool:
        patch = dict(patch)
        patch["last_updated"] = now_iso()
        return self.update(code, "metadata", patch)

    def save_consent(self, code: str, accepted: bool, version: str = "1.0") -> bool:
        return self.set(code, "consent", {
            "accepted": accepted,
            "timestamp": now_iso(),
            "version": version,
        })

    def save_progress(self, code: str, progress: dict) -> bool:
        progress = dict(progress)
        progress["last_activity_timestamp"] = now_iso()
        return self.update(code, "progress", progress)

    def load_participant(self, code: str) -> dict | None:
        return self.get(code)

    def withdraw(self, code: str, reason: str = "") -> bool:
        """
        Mark participant as withdrawn AND anonymize PII (name, email, contact).
        Roll number retained for follow-up tracking.
        """
        meta = self.get(code, "metadata") or {}
        anon_patch = {
            "name": "[ANONYMIZED]",
            "email": "[ANONYMIZED]",
            "contact": "[ANONYMIZED]",
            "anonymized": True,
            "anonymized_at": now_iso(),
        }
        self.update(code, "metadata", anon_patch)
        return self.set(code, "withdrawal", {
            "withdrawn": True,
            "timestamp": now_iso(),
            "reason": reason or "",
        })

    # ------------------------------------------------------------------------
    # Generic event log (for granular per-response logging)
    # ------------------------------------------------------------------------
    def log_event(self, code: str, event_type: str, payload: dict,
                  sync: bool = False) -> str | None:
        """
        Append an event to participants/{code}/events/.
        Fire-and-forget by default — the event log is for *audit*, not the
        primary data path, so blocking the UI on it would be wasteful.
        """
        record = {
            "type": event_type,
            "timestamp": now_iso(),
            "payload": payload,
        }
        return self.push(code, "events", record, sync=sync)

    # ------------------------------------------------------------------------
    # Therapist: list all participants
    # ------------------------------------------------------------------------
    def list_all_participants(self) -> dict:
        """Return {code: {metadata, group, withdrawn, ...}} for all participants."""
        try:
            return self._root_ref.get() or {}
        except Exception as e:
            st.warning(f"Firebase list error: {e}")
            return {}

    # ------------------------------------------------------------------------
    # Therapist approval gates
    # ------------------------------------------------------------------------
    # Stored at participants/{code}/gates/{gate_key}/
    #     approved: bool, by: str, timestamp: ISO, note: str
    GATES_PATH = "gates"

    def is_gate_approved(self, code: str, gate_key: str) -> bool:
        node = self.get(code, f"{self.GATES_PATH}/{gate_key}") or {}
        return isinstance(node, dict) and bool(node.get("approved"))

    def get_gate(self, code: str, gate_key: str) -> dict:
        return self.get(code, f"{self.GATES_PATH}/{gate_key}") or {}

    def approve_gate(self, code: str, gate_key: str, by: str, note: str = "") -> bool:
        return self.set(code, f"{self.GATES_PATH}/{gate_key}", {
            "approved": True,
            "by": by,
            "timestamp": now_iso(),
            "note": note or "",
        })

    def revoke_gate(self, code: str, gate_key: str) -> bool:
        return self.delete_path(code, f"{self.GATES_PATH}/{gate_key}")

    # ------------------------------------------------------------------------
    # Admin: per-participant low-level operations
    # ------------------------------------------------------------------------
    def delete_path(self, code: str, path: str) -> bool:
        """Delete a node at participants/{code}/{path}. Used by mark/unmark toggles."""
        try:
            self._ref(code, path).delete()
            return True
        except Exception as e:
            st.warning(f"Firebase delete error: {e}")
            return False

    def delete_participant(self, code: str) -> bool:
        """Hard-delete a participant. Use with confirmation in the UI."""
        try:
            self._ref(code).delete()
            return True
        except Exception as e:
            st.warning(f"Firebase delete-participant error: {e}")
            return False


# ============================================================================
# CACHED SINGLETON
# ============================================================================
@st.cache_resource
def get_logger() -> DataLogger:
    return DataLogger()
