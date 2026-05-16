"""
utils/validators.py
===================
Input validation & sentiment gating for the SAD Intervention App.

Decision model: BINARY
    POSITIVE -> accept
    NEGATIVE -> reject
    (No "unclear" / "neutral" / "flagged" / "pending" states.)

Sentiment backbone: SiEBERT (siebert/sentiment-roberta-large-english).
SiEBERT was fine-tuned across 15 different sentiment-classification datasets
and produces only POSITIVE / NEGATIVE labels. That property is critical here:
the previous CardiffNLP model produced a 3-way (POSITIVE/NEUTRAL/NEGATIVE)
distribution, so obvious negatives like "kill" landed at low confidence and
ended up in a review queue. With SiEBERT, the same input is a confident
NEGATIVE and gets rejected immediately.

Pipeline (in order, short-circuiting):
    1. Quality control     (empty / too-long / format / gibberish)
    2. Repetition check    (used-already + over-quota)
    3. Hard negative gate  (explicit blacklist for absolutely-must-reject tokens)
    4. Sentiment           (SiEBERT — POSITIVE accept / NEGATIVE reject)

Linguistic-pattern detection is retained ONLY as part of the stored audit
trail for downstream research analysis. It does NOT influence the decision.

Public API (preserved for backward compatibility):
    validate_ptc_response(response, cue, used_responses, repeats_used) -> dict
    classify_sentiment(text) -> (label, confidence)
    calculate_score(label) -> int
    is_valid_format(response, cue_word) -> bool
    looks_like_gibberish(word) -> bool
    validate_demographics(d) -> (ok, errors)
    validate_oximeter_reading(spo2, bpm) -> (ok, errors)
"""

from __future__ import annotations
import re
from typing import Tuple, Optional

import streamlit as st

import config

# ============================================================================
# CACHED RESOURCES
# ============================================================================
@st.cache_resource(show_spinner="Loading sentiment model (SiEBERT)...")
def _load_sentiment_classifier():
    try:
        from transformers.pipelines import pipeline
        return pipeline("sentiment-analysis", model=config.SENTIMENT_MODEL_ID)
    except Exception:
        return None


@st.cache_resource(show_spinner="Loading gibberish detector...")
def _load_gibberish_classifier():
    try:
        from transformers.pipelines import pipeline
        return pipeline("text-classification", model=config.GIBBERISH_MODEL_ID)
    except Exception:
        return None


@st.cache_resource
def _load_vocabulary() -> set[str]:
    try:
        import nltk
        from nltk.corpus import brown
        return set(w.lower() for w in brown.words())
    except Exception:
        return set()


# ============================================================================
# QUALITY CONTROL
# ============================================================================
def looks_like_gibberish(word: str) -> bool:
    vocab = _load_vocabulary()
    w = word.lower()
    return (
        len(w) < 1
        or not w.isalpha()
        or bool(re.fullmatch(r"(.)\1{4,}", w))
        or bool(re.search(r"[aeiou]{5,}", w))
        or bool(re.search(r"[zxcvbnm]{6,}", w))
        or (len(w) < 3 and w not in vocab)
    )


def is_valid_format(response: str, cue: str) -> bool:
    tokens = response.lower().strip().split()
    if not (1 <= len(tokens) <= 3):
        return False
    cue_lower = cue.lower()
    for token in tokens:
        if token == cue_lower or token in config.PTC_STOPWORDS or looks_like_gibberish(token):
            return False
    return True


def _quality_control(text: str, cue: str) -> dict:
    text_clean = (text or "").strip()
    if not text_clean:
        return {"overall_quality": "FAIL", "reason": "empty"}

    if len(text_clean) > config.PTC_RESPONSE_MAX_CHARS:
        return {"overall_quality": "FAIL", "reason": "too_long"}

    if not is_valid_format(text_clean, cue):
        return {"overall_quality": "FAIL", "reason": "invalid_format"}

    # Gibberish model
    gib_model = _load_gibberish_classifier()
    if gib_model:
        try:
            result = gib_model(text_clean)[0]
            if result["label"].lower() != "clean" and result["score"] >= 0.65:
                return {"overall_quality": "FAIL", "reason": "gibberish"}
        except Exception:
            pass

    return {"overall_quality": "PASS", "reason": "ok"}


# ============================================================================
# SENTIMENT ANALYSIS
# ============================================================================
def classify_sentiment(text: str) -> Tuple[str, float]:
    text = (text or "").strip()
    if not text:
        return ("NEGATIVE", 0.5)

    clf = _load_sentiment_classifier()
    if clf is None:
        return ("NEGATIVE", 0.5)

    try:
        result = clf(text)[0]
        label = "POSITIVE" if "pos" in result.get("label", "").lower() else "NEGATIVE"
        return label, float(result.get("score", 0.5))
    except Exception:
        return ("NEGATIVE", 0.5)


def calculate_score(label: str) -> int:
    """POSITIVE = +2, NEGATIVE = 0 (less punishing for pilot)"""
    return 2 if label == "POSITIVE" else 0


# ============================================================================
# HARD NEGATIVE & REPETITION
# ============================================================================
def _hits_hard_negative(text: str) -> Optional[str]:
    tokens = re.findall(r"[a-z']+", text.lower())
    hit = set(tokens) & config.PTC_HARD_NEGATIVE_WORDS
    return next(iter(hit), None)


def _repetition_layer(phrase: str, used_responses: set[str], repeats_used: int) -> dict:
    is_repeat = phrase in used_responses
    over_quota = is_repeat and repeats_used >= config.PTC_MAX_REPEATS_ALLOWED
    return {
        "is_repeated": is_repeat,
        "repeats_used_so_far": repeats_used,
        "over_quota": over_quota,
    }


# ============================================================================
# MAIN VALIDATOR - Optimized for Fine-tuning
# ============================================================================

def validate_ptc_response(
    response: str,
    cue: str,
    word_counts: dict[str, int],
) -> dict:
    raw_response = (response or "").strip()
    phrase = raw_response.lower()

    if not phrase:
        return _build_reject("empty", "Please type a response.", raw_response, phrase)

    quality = _quality_control(phrase, cue)
    if quality["overall_quality"] == "FAIL":
        msg = {
            "empty": "Please type a response.",
            "too_long": "Response is too long.",
            "invalid_format": "Please use 1–3 alphabetic words only.",
            "gibberish": "That doesn't look like a real word.",
        }.get(quality["reason"], "Invalid response.")
        return _build_reject(quality["reason"], msg, raw_response, phrase)

    # Hard negative
    hard_neg = _hits_hard_negative(phrase)
    if hard_neg:
        return _build_reject("negative", f"Word '{hard_neg}' is not allowed.", raw_response, phrase)

    # === PER-WORD REPETITION LOGIC ===
    current_count = word_counts.get(phrase, 0)
    is_repeat = current_count > 0
    over_quota = current_count >= config.PTC_MAX_REPEATS_ALLOWED

    if over_quota:
        return _build_reject(
            "used",
            f"Already used {current_count} time(s). Please use a different word.",
            raw_response, phrase, is_repeat=True
        )

    # Sentiment
    sentiment_label, confidence = classify_sentiment(phrase)

    accepted = sentiment_label == "POSITIVE"
    score = 2 if accepted else 0

    return {
        "accepted": accepted,
        "reason": "positive" if accepted else "negative",
        "sentiment": sentiment_label,
        "confidence": round(confidence, 4),
        "score": score,
        "is_repeat": is_repeat,
        "feedback": "Accepted!" if accepted else "Try a more positive word!",
        "raw_response": raw_response,
        "normalized_response": phrase,
        "validation_layers": {
            "repetition": {"is_repeated": is_repeat, "repeats_used_so_far": current_count}
        }
    }

def _build_reject(reason: str, feedback: str, raw: str, normalized: str, is_repeat: bool = False):
    return {
        "accepted": False,
        "reason": reason,
        "sentiment": "NEGATIVE",
        "confidence": 0.8,
        "score": 0,
        "is_repeat": is_repeat,
        "feedback": feedback,
        "raw_response": raw,
        "normalized_response": normalized,
        "validation_layers": {}
    }

# ============================================================================
# DEMOGRAPHIC FIELD VALIDATORS (unchanged)
# ============================================================================
EMAIL_RE = re.compile(r"^[\w\.\+\-]+@[\w\-]+(\.[\w\-]+)+$")


def validate_demographics(d: dict) -> Tuple[bool, list[str]]:
    errors = []
    name = (d.get("name") or "").strip()
    if len(name) < 2:
        errors.append("Name must be at least 2 characters.")
    roll = (d.get("roll_number") or "").strip()
    if len(roll) < 1:
        errors.append("Roll number / University ID is required.")
    age = d.get("age")
    if age is None or not (10 <= int(age) <= 100):
        errors.append("Age must be between 10 and 100.")
    if not (d.get("gender") or "").strip():
        errors.append("Gender is required.")
    contact = (d.get("contact") or "").strip()
    if len(contact) < 5:
        errors.append("Contact details are required.")
    email = (d.get("email") or "").strip()
    if not EMAIL_RE.match(email):
        errors.append("A valid email address is required.")
    if not (d.get("education") or "").strip():
        errors.append("Education level is required.")
    skills = d.get("computer_skills")
    if skills is None or not (1 <= int(skills) <= 5):
        errors.append("Computer skills rating is required (1–5).")
    return (len(errors) == 0, errors)


# ============================================================================
# OXIMETER VALIDATION (unchanged)
# ============================================================================
def validate_oximeter_reading(spo2, bpm) -> Tuple[bool, list[str]]:
    errors = []
    try:
        spo2_f = float(spo2)
        if not (config.OXIMETER_VALIDATION["spo2_min"] <= spo2_f <= config.OXIMETER_VALIDATION["spo2_max"]):
            errors.append(
                f"SpO₂ must be between "
                f"{config.OXIMETER_VALIDATION['spo2_min']} and "
                f"{config.OXIMETER_VALIDATION['spo2_max']}%."
            )
    except (TypeError, ValueError):
        errors.append("SpO₂ must be a number.")
    try:
        bpm_i = int(bpm)
        if not (config.OXIMETER_VALIDATION["bpm_min"] <= bpm_i <= config.OXIMETER_VALIDATION["bpm_max"]):
            errors.append(
                f"BPM must be between "
                f"{config.OXIMETER_VALIDATION['bpm_min']} and "
                f"{config.OXIMETER_VALIDATION['bpm_max']}."
            )
    except (TypeError, ValueError):
        errors.append("BPM must be a whole number.")
    return (len(errors) == 0, errors)
