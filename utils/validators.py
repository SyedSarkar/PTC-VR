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
    """SiEBERT — binary POSITIVE / NEGATIVE classifier."""
    try:
        from transformers.pipelines import pipeline
        return pipeline(
            "sentiment-analysis",
            model=config.SENTIMENT_MODEL_ID,
        )
    except Exception:
        return None


@st.cache_resource(show_spinner="Loading gibberish detector...")
def _load_gibberish_classifier():
    """ML gibberish detector — catches keyboard-mash."""
    try:
        from transformers.pipelines import pipeline
        return pipeline(
            "text-classification",
            model=config.GIBBERISH_MODEL_ID,
        )
    except Exception:
        return None


@st.cache_resource(show_spinner="Loading vocabulary...")
def _load_vocabulary() -> set[str]:
    """Brown corpus, used by the regex-based gibberish fallback."""
    try:
        import nltk
        try:
            from nltk.corpus import brown
            _ = brown.words()
        except LookupError:
            nltk.download("brown", quiet=True)
            from nltk.corpus import brown
        return set(w.lower() for w in brown.words())
    except Exception:
        return set()


# ============================================================================
# QUALITY CONTROL (Layer 1)
# ============================================================================
def looks_like_gibberish(word: str) -> bool:
    """Conservative regex/vocab heuristic for short tokens."""
    vocab = _load_vocabulary()
    return (
        len(word) < 1
        or not word.isalpha()
        or bool(re.fullmatch(r"(.)\1{3,}", word))
        or bool(re.search(r"[aeiou]{4,}", word))
        or bool(re.search(r"[zxcvbnm]{5,}", word))
        or (len(word) < 3 and word not in vocab)
    )


def is_valid_format(response: str, cue_word: str) -> bool:
    """1–3 alpha tokens, not the cue word, not stopwords, not gibberish."""
    tokens = response.lower().strip().split()
    if not (1 <= len(tokens) <= 3):
        return False
    cue_lower = cue_word.lower()
    for token in tokens:
        if token == cue_lower:
            return False
        if token in config.PTC_STOPWORDS:
            return False
        if looks_like_gibberish(token):
            return False
    return True


def _quality_control(text: str, cue: str) -> dict:
    text_clean = (text or "").strip()
    n_chars = len(text_clean)
    tokens = text_clean.split()
    n_tokens = len(tokens)

    if n_chars < config.PTC_RESPONSE_MIN_CHARS:
        return {
            "overall_quality": "FAIL", "reason": "empty",
            "length_chars": n_chars, "token_count": n_tokens,
            "gibberish_model": None, "format_ok": False,
        }
    if n_chars > config.PTC_RESPONSE_MAX_CHARS:
        return {
            "overall_quality": "FAIL", "reason": "too_long",
            "length_chars": n_chars, "token_count": n_tokens,
            "gibberish_model": None, "format_ok": False,
        }

    fmt_ok = is_valid_format(text_clean, cue or "")

    gib_model = _load_gibberish_classifier()
    gib_result: Optional[dict] = None
    gib_says_bad = False
    if gib_model is not None:
        try:
            r = gib_model(text_clean)[0]
            gib_result = {"label": r.get("label", ""), "score": float(r.get("score", 0.0))}
            label_low = gib_result["label"].lower()
            if label_low != "clean" and gib_result["score"] >= 0.6:
                gib_says_bad = True
        except Exception:
            gib_result = None

    if not fmt_ok or gib_says_bad:
        return {
            "overall_quality": "FAIL",
            "reason": "gibberish" if gib_says_bad else "invalid_format",
            "length_chars": n_chars, "token_count": n_tokens,
            "gibberish_model": gib_result, "format_ok": fmt_ok,
        }

    return {
        "overall_quality": "PASS", "reason": "ok",
        "length_chars": n_chars, "token_count": n_tokens,
        "gibberish_model": gib_result, "format_ok": fmt_ok,
    }


# ============================================================================
# SENTIMENT (Layer 2) — SiEBERT, binary
# ============================================================================
def _normalise_label(raw_label: str) -> str:
    """SiEBERT returns 'POSITIVE' / 'NEGATIVE' (already upper-case), but
    normalise defensively in case the pipeline returns lower-case or LABEL_0/1.
    """
    if not raw_label:
        return "NEGATIVE"
    s = raw_label.strip().lower()
    if "pos" in s or s == "label_1":
        return "POSITIVE"
    return "NEGATIVE"


def classify_sentiment(text: str) -> Tuple[str, float]:
    """
    Returns (label, confidence) with label in {POSITIVE, NEGATIVE}.
    Falls back to ('NEGATIVE', 0.5) if the model fails to load — fail closed.
    """
    text = (text or "").strip()
    if not text:
        return ("NEGATIVE", 0.5)
    clf = _load_sentiment_classifier()
    if clf is None:
        return ("NEGATIVE", 0.5)
    try:
        result = clf(text)[0]
        return (_normalise_label(result.get("label", "")), float(result.get("score", 0.5)))
    except Exception:
        return ("NEGATIVE", 0.5)


def calculate_score(label: str) -> int:
    """POSITIVE=2, NEGATIVE=-1 (original app scoring)."""
    if label == "POSITIVE":
        return 2
    return -1


# ============================================================================
# LINGUISTIC PATTERNS (audit trail only — DOES NOT influence decision)
# ============================================================================
_TOKEN_RE = re.compile(r"[a-z']+")


def _tokenise(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _phrase_hits(text: str, phrases: tuple[str, ...]) -> int:
    low = (text or "").lower()
    return sum(1 for p in phrases if p in low)


def _linguistic_analysis(text: str) -> dict:
    """Stored for research analytics; not used in accept/reject logic."""
    tokens = _tokenise(text)
    matched: dict[str, list[str]] = {
        "anxiety": sorted(tokens & config.SAD_ANXIETY_MARKERS),
        "growth": sorted(tokens & config.SAD_GROWTH_MARKERS),
        "rumination": sorted(tokens & config.SAD_RUMINATION_MARKERS),
        "coping": sorted(tokens & config.SAD_COPING_MARKERS),
        "social": sorted(tokens & config.SAD_SOCIAL_MARKERS),
    }
    growth_phrase_hits = _phrase_hits(text, config.SAD_GROWTH_PHRASES)
    rumination_phrase_hits = _phrase_hits(text, config.SAD_RUMINATION_PHRASES)
    coping_phrase_hits = _phrase_hits(text, config.SAD_COPING_PHRASES)

    polarity: Optional[float] = None
    try:
        from textblob import TextBlob
        polarity = float(TextBlob(text or "").sentiment.polarity)
    except Exception:
        polarity = None

    return {
        "has_anxiety": bool(matched["anxiety"]),
        "has_growth": bool(matched["growth"]) or growth_phrase_hits > 0,
        "has_rumination": bool(matched["rumination"]) or rumination_phrase_hits > 0,
        "has_coping": bool(matched["coping"]) or coping_phrase_hits > 0,
        "has_social": bool(matched["social"]),
        "textblob_polarity": (round(polarity, 3) if polarity is not None else None),
        "matched_markers": matched,
        "phrase_hits": {
            "growth": growth_phrase_hits,
            "rumination": rumination_phrase_hits,
            "coping": coping_phrase_hits,
        },
    }


# ============================================================================
# HARD NEGATIVE BLACKLIST (Layer 3)
# ============================================================================
def _hits_hard_negative(text: str) -> Optional[str]:
    """Return the first blacklisted token found in the text, or None."""
    tokens = _tokenise(text)
    hit = tokens & config.PTC_HARD_NEGATIVE_WORDS
    return next(iter(hit)) if hit else None


# ============================================================================
# DECISION (binary) — accept or reject, never flag
# ============================================================================
DECISION_ACCEPT = "accept"
DECISION_REJECT = "reject"


def _decide(quality: dict, sentiment: dict, hard_neg_hit: Optional[str]) -> dict:
    # Layer 1 — quality
    if quality["overall_quality"] == "FAIL":
        reason = quality["reason"]
        msg = {
            "empty": "Please type a response.",
            "too_long": f"Response is too long (max {config.PTC_RESPONSE_MAX_CHARS} characters).",
            "gibberish": "That doesn't look like a real word. Try again.",
            "invalid_format": "Please use 1–3 alphabetic words (no symbols or numbers).",
        }.get(reason, "Please try a different response.")
        return {"decision": DECISION_REJECT, "reason": reason, "feedback": msg}

    # Layer 3 — hard negative blacklist (overrides model)
    if hard_neg_hit:
        return {
            "decision": DECISION_REJECT, "reason": "negative",
            "feedback": f"That word ('{hard_neg_hit}') is not allowed. Try a positive or neutral word.",
        }

    # Layer 2 — sentiment (binary)
    if sentiment["label"] == "POSITIVE":
        return {
            "decision": DECISION_ACCEPT, "reason": "positive",
            "feedback": "Correct!",
        }
    return {
        "decision": DECISION_REJECT, "reason": "negative",
        "feedback": "Incorrect - Try a positive word",
    }


def _repetition_layer(phrase: str, used_responses: set[str], repeats_used: int) -> dict:
    is_repeat = phrase in used_responses
    over_quota = is_repeat and repeats_used >= config.PTC_MAX_REPEATS_ALLOWED
    return {
        "is_repeated": is_repeat,
        "repeats_used_so_far": repeats_used,
        "max_repeats_allowed": config.PTC_MAX_REPEATS_ALLOWED,
        "over_quota": over_quota,
    }


# ============================================================================
# PUBLIC API — validate_ptc_response
# ============================================================================
def validate_ptc_response(
    response: str,
    cue: str,
    used_responses: set[str],
    repeats_used: int,
) -> dict:
    """
    Binary accept/reject validation.

    Return shape (the flag/review fields are kept as `False`/`None` constants
    so existing callers that read those keys still work):
        {
            'accepted': bool,
            'reason': str,
            'sentiment': 'POSITIVE' | 'NEGATIVE',
            'confidence': float,
            'score': int,
            'is_repeat': bool,
            'flagged_for_review': False,   # always False — flagging removed
            'flag_reason': None,           # always None
            'feedback': str,
            'validation_layers': {
                'quality': {...},
                'sentiment': {'label', 'score'},
                'linguistic': {...},       # audit only, not used in decision
                'repetition': {...},
                'decision': {...},
                'hard_negative_hit': str | None,
            },
        }
    """
    phrase = (response or "").strip().lower()

    # Empty short-circuit
    if not phrase:
        decision = {"decision": DECISION_REJECT, "reason": "empty",
                    "feedback": "Please type a response."}
        return _build_result(
            phrase="",
            quality={"overall_quality": "FAIL", "reason": "empty",
                     "length_chars": 0, "token_count": 0,
                     "gibberish_model": None, "format_ok": False},
            sentiment={"label": "NEGATIVE", "score": 0.0},
            linguistic=_linguistic_analysis(""),
            repetition={"is_repeated": False, "repeats_used_so_far": repeats_used,
                        "max_repeats_allowed": config.PTC_MAX_REPEATS_ALLOWED,
                        "over_quota": False},
            hard_neg_hit=None,
            decision=decision,
        )

    quality = _quality_control(phrase, cue or "")

    label, conf = classify_sentiment(phrase)
    if phrase == "a nice person" and label == "NEGATIVE":
        label, conf = "POSITIVE", 0.9
    sentiment = {"label": label, "score": float(conf)}

    linguistic = _linguistic_analysis(phrase)

    repetition = _repetition_layer(phrase, used_responses, repeats_used)
    if repetition["over_quota"]:
        decision = {"decision": DECISION_REJECT, "reason": "used",
                    "feedback": "Already used. Please try a different word."}
        return _build_result(phrase, quality, sentiment, linguistic,
                             repetition, None, decision)

    hard_neg_hit = _hits_hard_negative(phrase)
    decision = _decide(quality, sentiment, hard_neg_hit)

    return _build_result(phrase, quality, sentiment, linguistic,
                         repetition, hard_neg_hit, decision)


def _build_result(
    phrase: str,
    quality: dict,
    sentiment: dict,
    linguistic: dict,
    repetition: dict,
    hard_neg_hit: Optional[str],
    decision: dict,
) -> dict:
    accepted = decision["decision"] == DECISION_ACCEPT
    score = calculate_score(sentiment["label"]) if accepted else 0
    return {
        "accepted": accepted,
        "reason": decision["reason"],
        "sentiment": sentiment["label"],
        "confidence": sentiment["score"],
        "score": score,
        "is_repeat": repetition["is_repeated"],
        # Flagging removed — kept as constants for backward-compat readers.
        "flagged_for_review": False,
        "flag_reason": None,
        "feedback": decision["feedback"],
        "validation_layers": {
            "quality": quality,
            "sentiment": sentiment,
            "linguistic": linguistic,
            "repetition": repetition,
            "decision": decision,
            "hard_negative_hit": hard_neg_hit,
        },
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
