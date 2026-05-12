"""
run_once.py
===========
Pre-cache every NLP asset used by the hybrid sentiment-validation stack
so the *first* participant doesn't have to wait for ~600 MB of model
weights to download mid-session.

Run this once after installing dependencies (or whenever you bump a
model ID in config.py):

    python run_once.py

What it does:
    1. Downloads CardiffNLP twitter-roberta-base-sentiment-latest
       (Layer 2 — sentiment).
    2. Downloads madhurjindal autonlp Gibberish-Detector
       (Layer 1 — gibberish ML).
    3. Downloads the NLTK Brown corpus
       (Layer 1 — regex/vocab fallback).
    4. Warms TextBlob's required corpora
       (Layer 3 — linguistic polarity).
    5. Smoke-tests each component on a sample sentence.

Exits 0 on success, 1 if any component fails. Safe to re-run.
"""

from __future__ import annotations

import sys
import traceback

import config


def _print_step(n: int, label: str) -> None:
    print(f"\n[{n}/5] {label}")
    print("-" * 60)


# ---------------------------------------------------------------------------
# Step 1 — CardiffNLP sentiment model
# ---------------------------------------------------------------------------
def cache_sentiment_model() -> bool:
    _print_step(1, f"Caching sentiment model: {config.SENTIMENT_MODEL_ID}")
    try:
        from transformers.pipelines import pipeline
        clf = pipeline("sentiment-analysis", model=config.SENTIMENT_MODEL_ID)
        smoke = clf("I'm anxious but I'm going to try anyway.")[0]
        print(f"  OK — sample classification: {smoke}")
        return True
    except Exception:
        print("  FAILED:")
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Step 2 — Gibberish-detector model
# ---------------------------------------------------------------------------
def cache_gibberish_model() -> bool:
    _print_step(2, f"Caching gibberish detector: {config.GIBBERISH_MODEL_ID}")
    try:
        from transformers.pipelines import pipeline
        clf = pipeline("text-classification", model=config.GIBBERISH_MODEL_ID)
        smoke_clean = clf("kindness")[0]
        smoke_gib = clf("asdfghjklqwerty")[0]
        print(f"  OK — 'kindness' -> {smoke_clean}")
        print(f"  OK — 'asdfghjklqwerty' -> {smoke_gib}")
        return True
    except Exception:
        print("  FAILED:")
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Step 3 — NLTK Brown corpus
# ---------------------------------------------------------------------------
def cache_nltk_brown() -> bool:
    _print_step(3, "Caching NLTK Brown corpus")
    try:
        import nltk
        try:
            from nltk.corpus import brown
            _ = brown.words()[:5]
        except LookupError:
            nltk.download("brown", quiet=True)
            from nltk.corpus import brown
            _ = brown.words()[:5]
        print(f"  OK — Brown corpus accessible (sample: {brown.words()[:5]})")
        return True
    except Exception:
        print("  FAILED:")
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Step 4 — TextBlob corpora
# ---------------------------------------------------------------------------
def cache_textblob() -> bool:
    _print_step(4, "Warming TextBlob polarity engine")
    try:
        from textblob import TextBlob
        blob = TextBlob("I'm nervous but I tried anyway and it went okay.")
        polarity = blob.sentiment.polarity
        print(f"  OK — sample polarity = {polarity:+.3f}")
        return True
    except Exception:
        print("  FAILED:")
        traceback.print_exc()
        print("\n  TIP: if TextBlob complains about missing corpora, run:")
        print("       python -m textblob.download_corpora")
        return False


# ---------------------------------------------------------------------------
# Step 5 — End-to-end validator smoke test
# ---------------------------------------------------------------------------
def smoke_test_validator() -> bool:
    _print_step(5, "End-to-end validator smoke test")
    try:
        # The validators module imports streamlit; if streamlit's runtime
        # isn't active that's fine — the cache_resource decorators degrade
        # gracefully to plain functions at module load time.
        from utils.validators import validate_ptc_response

        cases = [
            ("kind",          "happy"),    # clean positive
            ("anxious",       "happy"),    # honest anxiety
            ("asdfghjk",      "happy"),    # gibberish
            ("hopeless",      "happy"),    # rumination
            ("tried anyway",  "happy"),    # anxiety + growth phrase
        ]
        for response, cue in cases:
            r = validate_ptc_response(response, cue, set(), 0)
            print(
                f"  '{response:<14}' -> accepted={r['accepted']:<5}  "
                f"reason={r['reason']:<22}  "
                f"flagged={r.get('flagged_for_review', False)}"
            )
        return True
    except Exception:
        print("  FAILED:")
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 60)
    print("SAD Intervention App — pre-cache NLP assets")
    print("=" * 60)

    results = [
        cache_sentiment_model(),
        cache_gibberish_model(),
        cache_nltk_brown(),
        cache_textblob(),
        smoke_test_validator(),
    ]

    print("\n" + "=" * 60)
    if all(results):
        print("All assets cached successfully. Safe to launch Streamlit.")
        return 0
    failed = sum(1 for r in results if not r)
    print(f"{failed} of {len(results)} steps failed. See traceback above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
