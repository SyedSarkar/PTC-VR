"""
config.py
========
Central configuration for the SAD Intervention App.
Contains:
- Firebase credentials loader
- All scale items (LSAS, BFNE, CBQ, SSQ, I-Group Presence, BAT)
- App constants & study metadata
- Therapist credentials
"""

import os
import json
from pathlib import Path

# Try to load .env.local for local development
try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(BASE_DIR / ".env.local")
except ImportError:
    pass

# ============================================================================
# STUDY METADATA
# ============================================================================
STUDY_TITLE = "Comparing Intervention Approaches for Social Anxiety Disorder: A Randomized Controlled Trial"
PRINCIPAL_INVESTIGATOR = "Ather Mujtaba"
RESEARCHER = "Esha Jaffar"
INSTITUTION = "GIFT University"
VERSION_DATE = "5/6/2026"
RESEARCHER_EMAIL = "eshajaffar009@gmail.com"
PI_EMAIL = "ather.mujitaba@gift.edu.pk"

# ============================================================================
# THERAPIST CREDENTIALS
# ============================================================================
THERAPIST_USERNAME = os.getenv("THERAPIST_USERNAME", "Esha")
THERAPIST_PASSWORD = os.getenv("THERAPIST_PASSWORD", "Eshatherapist")

# ============================================================================
# FIREBASE CONFIGURATION
# ============================================================================
def get_firebase_credentials():
    """
    Load Firebase service account credentials.
    Priority:
      1. Streamlit secrets (cloud deployment) -> st.secrets["FIREBASE_CREDENTIALS_JSON"]
      2. Environment variable FIREBASE_CREDENTIALS_JSON (raw JSON string)
      3. File path FIREBASE_CREDENTIALS_PATH
    """
    # Try Streamlit secrets first (for cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "FIREBASE_CREDENTIALS_JSON" in st.secrets:
            creds_str = st.secrets["FIREBASE_CREDENTIALS_JSON"]
            return json.loads(creds_str) if isinstance(creds_str, str) else dict(creds_str)
    except Exception:
        pass

    # Try env var with raw JSON
    raw_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if raw_json:
        return json.loads(raw_json)

    # Try file path
    path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if path and os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)

    raise ValueError(
        "Firebase credentials not found. Set FIREBASE_CREDENTIALS_JSON or "
        "FIREBASE_CREDENTIALS_PATH in your .env.local or Streamlit secrets."
    )


FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "")

# ============================================================================
# GROUP ASSIGNMENT
# ============================================================================
GROUPS = ["PTC", "VR", "CBT"]

# ============================================================================
# PHASES (state-machine keys)
# ============================================================================
PHASE_WELCOME           = "welcome"
PHASE_CONSENT           = "consent"
PHASE_DEMOGRAPHICS      = "demographics"
PHASE_PRE_ASSESSMENT    = "pre_assessment"
PHASE_PTC_TRAINING      = "ptc_training"          # Group A only
PHASE_WAITING           = "waiting_period"        # Groups B, C only
PHASE_POST1_ASSESSMENT  = "post1_assessment"
PHASE_VR_EXPOSURE       = "vr_exposure"
PHASE_POST2_ASSESSMENT  = "post2_assessment"
PHASE_REAL_EXPOSURE     = "real_exposure"
PHASE_POST3_ASSESSMENT  = "post3_assessment"
PHASE_COMPLETE          = "complete"
PHASE_WITHDRAWN         = "withdrawn"
PHASE_THERAPIST         = "therapist_dashboard"

# ============================================================================
# LSAS (Liebowitz Social Anxiety Scale) — 24 items, Fear + Avoidance
# ============================================================================
LSAS_INSTRUCTIONS = (
    "Read each situation carefully and answer two questions about that situation. "
    "The first question asks how anxious or fearful you feel in the situation. "
    "The second question asks how often you avoid the situation. If you come across "
    "a situation that you ordinarily do not experience, imagine \"what if you were "
    "faced with that situation,\" and then rate the degree to which you would fear "
    "this hypothetical situation and how often you would tend to avoid it. "
    "Please base your ratings on the way that the situations have affected you in the last week."
)

LSAS_FEAR_LABELS = ["None (0)", "Mild (1)", "Moderate (2)", "Severe (3)"]
LSAS_AVOID_LABELS = ["Never (0)", "Occasionally (1)", "Often (2)", "Usually (3)"]

LSAS_ITEMS = [
    "Telephoning in public",
    "Participating in small groups",
    "Eating in public places",
    "Drinking with others in public places",
    "Talking to people in authority",
    "Acting, performing, or giving a talk in front of an audience",
    "Going to a party",
    "Working while being observed",
    "Writing while being observed",
    "Calling someone you don't know very well",
    "Talking with people you don't know very well",
    "Meeting strangers",
    "Urinating in a public bathroom",
    "Entering a room when others are already seated",
    "Being the center of attention",
    "Speaking up at a meeting",
    "Taking a test",
    "Expressing a disagreement/disapproval to people you don't know very well",
    "Looking at people you don't know very well in the eyes",
    "Giving a report to a group",
    "Trying to pick up someone",
    "Returning goods to a store",
    "Giving a party",
    "Resisting a high pressure salesperson",
]

# ============================================================================
# BFNE (Brief Fear of Negative Evaluation) — 12 items, 1-5 scale
# ============================================================================
BFNE_INSTRUCTIONS = (
    "Please read each of the statements below carefully and think about how well "
    "each one describes you. There are no right or wrong answers. Answer as honestly "
    "as you can based on how you typically feel or behave."
)

BFNE_LABELS = [
    "1 — Not at all characteristic",
    "2 — Slightly characteristic",
    "3 — Moderately characteristic",
    "4 — Very characteristic",
    "5 — Extremely characteristic",
]

BFNE_ITEMS = [
    "I worry about what other people will think of me even when I know it doesn't make any difference.",
    "I am unconcerned even if I know people are forming an unfavorable impression of me.",
    "I am frequently afraid of other people noticing my shortcomings.",
    "I rarely worry about what kind of impression I am making on someone.",
    "I am afraid others will not approve of me.",
    "I am afraid that people will find fault with me.",
    "Other people's opinions of me do not bother me.",
    "When I am talking to someone, I worry about what they may be thinking about me.",
    "I am usually worried about what kind of impression I make.",
    "If I know someone is judging me, it has little effect on me.",
    "Sometimes I think I am too concerned with what other people think of me.",
    "I often worry that I will say or do the wrong things.",
]

# Reverse-scored items for BFNE (1-indexed: items 2, 4, 7, 10)
BFNE_REVERSE_SCORED = [2, 4, 7, 10]

# ============================================================================
# CBQ (Cognitive Beliefs Questionnaire) — 20 items, 1-6 scale
# ============================================================================
CBQ_INSTRUCTIONS = (
    "People frequently hold a range of both positive and negative beliefs about how "
    "they are perceived by other people. Below is a list of common negative beliefs "
    "that people may hold in varying degrees. During social situations, to what extent "
    "do you believe that others will think the following about you? Social situations "
    "include those where you have to interact with other people (e.g., social gatherings, "
    "work meetings), or perform in front of other people (e.g., giving a presentation)."
)

CBQ_LABELS = [
    "1 — Strongly disbelieve",
    "2 — Moderately disbelieve",
    "3 — Slightly disbelieve",
    "4 — Slightly believe",
    "5 — Moderately believe",
    "6 — Strongly believe",
]

CBQ_ITEMS = [
    "Others think I am unlikeable",
    "Others think I am foolish",
    "Others think I am inadequate",
    "Others think I am inferior",
    "Others think I am uninteresting",
    "Others think I am boring",
    "Others think I am dumb/stupid",
    "Others think I am a weak person",
    "Others think I am incompetent",
    "Others think I am unacceptable",
    "Others think I am not a worthwhile person",
    "Others think I'm a weird person",
    "Others think I'm odd/peculiar",
    "Others think I'm unimportant",
    "Others think I'm physically unattractive",
    "Others think I am inept",
    "Others think I am undesirable",
    "Others think I am unlovable",
    "Others think I am a failure",
    "Others think I'm defective",
]

# ============================================================================
# CBQ-Trait (Cognitive Beliefs Questionnaire - Trait) — 20 items, 1-6 scale
# ============================================================================
CBQ_TRAIT_INSTRUCTIONS = (
    "People frequently hold a range of both positive and negative beliefs about themselves. "
    "Below is a list of common negative beliefs that people may hold in varying degrees. "
    "Please rate the extent to which you personally believe each statement accurately describes "
    "how you generally feel about yourself. Please try to be as honest as you can when responding "
    "to these items. Remember that your answers will remain completely confidential."
)

CBQ_TRAIT_LABELS = [
    "1 — Strongly disbelieve",
    "2 — Moderately disbelieve",
    "3 — Slightly disbelieve",
    "4 — Slightly believe",
    "5 — Moderately believe",
    "6 — Strongly believe",
]

CBQ_TRAIT_ITEMS = [
    "I am unlikeable",
    "I am foolish",
    "I am inadequate",
    "I am inferior",
    "I am uninteresting",
    "I am boring",
    "I am dumb/stupid",
    "I am a weak person",
    "I am incompetent",
    "I am unacceptable",
    "I am not a worthwhile person",
    "I am a weird person",
    "I am odd/peculiar",
    "I am unimportant",
    "I am physically unattractive",
    "I am inept",
    "I am undesirable",
    "I am unlovable",
    "I am a failure",
    "I am defective",
]

# ============================================================================
# SSQ (Simulator Sickness Questionnaire) — 16 items, 0-3 scale
# ============================================================================
SSQ_INSTRUCTIONS = (
    "Circle how much each symptom below is affecting you now. "
    "0 = Not at all, 1 = Mild, 2 = Moderate, 3 = Severe."
)

SSQ_LABELS = ["0 — Not at all", "1 — Mild", "2 — Moderate", "3 — Severe"]

SSQ_ITEMS = [
    "General discomfort",
    "Fatigue",
    "Headache",
    "Eyestrain",
    "Difficulty focusing",
    "Increased salivation",
    "Sweating",
    "Nausea",
    "Difficulty concentrating",
    "Fullness of head",
    "Blurred vision",
    "Dizziness (eyes open)",
    "Dizziness (eyes closed)",
    "Vertigo (loss of orientation with respect to vertical upright)",
    "Stomach awareness (discomfort just short of nausea)",
    "Burping",
]

# ============================================================================
# SUDS (Subjective Units of Distress Scale) — 0-100
# ============================================================================
SUDS_INSTRUCTIONS = (
    "Try to get used to rating your distress, fear, anxiety or discomfort on a "
    "scale of 0–100. Imagine you have a 'distress thermometer' to measure your feelings."
)

SUDS_ANCHORS = {
    100: "Highest distress / fear / anxiety / discomfort that you have ever felt",
    90:  "Extremely anxious / distressed",
    80:  "Very anxious / distressed, can't concentrate",
    70:  "Quite anxious / distressed, interfering with performance",
    60:  "—",
    50:  "Moderate anxiety / distress, uncomfortable but can continue to perform",
    40:  "—",
    30:  "Mild anxiety / distress, no interference with performance",
    20:  "Minimal anxiety / distress",
    10:  "Alert and awake, concentrating well",
    0:   "Totally relaxed",
}

# ============================================================================
# I-GROUP PRESENCE QUESTIONNAIRE — 24 items, 7-point scale
# ============================================================================
IGROUP_INSTRUCTIONS = (
    "Characterize your experience in the environment by selecting the appropriate point "
    "on the 7-point scale, in accordance with the question content and descriptive labels. "
    "Please consider the entire scale when making your responses, as the intermediate "
    "levels may apply. Answer the questions independently in the order that they appear. "
    "Do not skip questions or return to a previous question to change your answer."
)

# Each item: (question_text, left_label, middle_label, right_label)
IGROUP_ITEMS = [
    ("How much were you able to control events?", "Not at all", "Somewhat", "Completely"),
    ("How responsive was the environment to actions that you initiated (or performed)?", "Not responsive", "Moderately responsive", "Completely responsive"),
    ("How natural did your interactions with the environment seem?", "Extremely artificial", "Borderline", "Completely natural"),
    ("How much did the visual aspects of the environment involve you?", "Not at all", "Somewhat", "Completely"),
    ("How natural was the mechanism which controlled movement through the environment?", "Extremely artificial", "Borderline", "Completely natural"),
    ("How compelling was your sense of objects moving through space?", "Not at all", "Moderately compelling", "Very compelling"),
    ("How much did your experiences in the virtual environment seem consistent with your real world experiences?", "Not consistent", "Moderately consistent", "Very consistent"),
    ("Were you able to anticipate what would happen next in response to the actions that you performed?", "Not at all", "Somewhat", "Completely"),
    ("How completely were you able to actively survey or search the environment using vision?", "Not at all", "Somewhat", "Completely"),
    ("How compelling was your sense of moving around inside the virtual environment?", "Not compelling", "Moderately compelling", "Very compelling"),
    ("How closely were you able to examine objects?", "Not at all", "Pretty closely", "Very closely"),
    ("How well could you examine objects from multiple viewpoints?", "Not at all", "Somewhat", "Extensively"),
    ("How involved were you in the virtual environment experience?", "Not involved", "Mildly involved", "Completely engrossed"),
    ("How much delay did you experience between your actions and expected outcomes?", "No delays", "Moderate delays", "Long delays"),
    ("How quickly did you adjust to the virtual environment experience?", "Not at all", "Slowly", "Less than one minute"),
    ("How proficient in moving and interacting with the virtual environment did you feel at the end of the experience?", "Not proficient", "Reasonably proficient", "Very proficient"),
    ("How much did the visual display quality interfere or distract you from performing assigned tasks or required activities?", "Not at all", "Interfered somewhat", "Prevented task performance"),
    ("How much did the control devices interfere with the performance of assigned tasks or with other activities?", "Not at all", "Interfered somewhat", "Interfered greatly"),
    ("How well could you concentrate on the assigned tasks or required activities rather than on the mechanisms used to perform those tasks or activities?", "Not at all", "Somewhat", "Completely"),
    ("How much did the auditory aspects of the environment involve you?", "Not at all", "Somewhat", "Completely"),
    ("How well could you identify sounds?", "Not at all", "Somewhat", "Completely"),
    ("How well could you localize sounds?", "Not at all", "Somewhat", "Completely"),
    ("How well could you actively survey or search the virtual environment using touch?", "Not at all", "Somewhat", "Completely"),
    ("How well could you move or manipulate objects in the virtual environment?", "Not at all", "Somewhat", "Extensively"),
]

# ============================================================================
# BAT (Behavioral Avoidance Task) — Placeholder scenarios
# ============================================================================
BAT_INSTRUCTIONS = (
    "Below are common social situations. For each one, rate your willingness to "
    "attempt the situation right now on a scale of 0 (Not willing at all) to 10 "
    "(Completely willing)."
)

BAT_SCENARIOS = [
    "Make a phone call to someone you don't know well",
    "Give a short speech to a small group",
    "Ask a stranger for directions",
    "Order food in a crowded restaurant",
    "Attend a social gathering where you don't know many people",
    "Make eye contact with a stranger for 5 seconds",
    "Return an item to a store",
    "Sit alone in a busy café for 30 minutes",
]

# ============================================================================
# OXIMETER
# ============================================================================
OXIMETER_VALIDATION = {
    "spo2_min": 70.0,
    "spo2_max": 100.0,
    "bpm_min": 30,
    "bpm_max": 220,
}

# Reading points to capture per assessment battery
OXIMETER_READING_POINTS = ["starting", "ending", "minimum", "maximum"]

# ============================================================================
# PTC TRAINING
# ============================================================================
PTC_NUM_SESSIONS = 4
# Maximum number of *repeat events* allowed per task (FAT and Sentence
# Completion are tracked independently). With this set to 2:
#   - first time a word is used  -> not a repeat
#   - second time (1st repeat)   -> allowed (counter=1)
#   - third time  (2nd repeat)   -> allowed (counter=2)
#   - fourth time (3rd repeat)   -> BLOCKED  (counter would be 3, exceeds 2)
PTC_MAX_REPEATS_ALLOWED = 2

# Stopwords from old app
PTC_STOPWORDS = {"hassan", "asim", "ather"}

# ============================================================================
# SENTIMENT VALIDATION — Model identifiers
# ============================================================================
# SiEBERT — RoBERTa-large fine-tuned on 15 sentiment domains; binary output
# (POSITIVE / NEGATIVE only, NO neutral class). This is the right tool for
# a positive-vs-negative gate: unambiguous tokens like "kill" / "hate" /
# "ugly" come back as NEGATIVE with high confidence rather than collapsing
# into a "neutral / unclear" bucket the way CardiffNLP did.
SENTIMENT_MODEL_ID = "siebert/sentiment-roberta-large-english"

# Gibberish detector (catches keyboard-mashing / non-words)
GIBBERISH_MODEL_ID = "madhurjindal/autonlp-Gibberish-Detector-492513457"

# Length bounds for PTC responses (kept compatible with the 1-3 word format).
PTC_RESPONSE_MIN_CHARS = 1
PTC_RESPONSE_MAX_CHARS = 500

# Hard-coded negative blacklist for tokens that must be rejected even if a
# model briefly mis-classifies them. Lower-cased, whole-token match.
PTC_HARD_NEGATIVE_WORDS = {
    "kill", "killed", "killing", "die", "died", "dying", "death", "dead",
    "suicide", "murder", "rape", "raped", "hate", "hated", "hating",
    "disgust", "disgusting", "ugly", "stupid", "idiot", "loser", "worthless",
    "useless", "horrible", "terrible", "awful", "evil", "shit", "fuck",
    "fucking", "bitch", "damn", "hell", "bastard", "asshole",
}

# ============================================================================
# SAD-SPECIFIC LINGUISTIC PATTERNS (Layer 3)
# ============================================================================
# Each set is matched as whole-word tokens (case-insensitive). Multi-word
# phrases are matched as substrings. Tuned for short PTC responses but
# also useful for longer therapeutic disclosures.

# Acknowledgment of anxiety — *not* a bad thing in exposure therapy.
SAD_ANXIETY_MARKERS = {
    "anxious", "anxiety", "nervous", "worried", "worry", "scared", "afraid",
    "fearful", "fear", "tense", "uneasy", "panic", "panicked", "stressed",
    "stress", "shy", "embarrassed", "uncomfortable", "jittery", "frightened",
}

# Effort, action, coping behaviour — therapeutic success markers.
SAD_GROWTH_MARKERS = {
    "tried", "trying", "try", "practiced", "practice", "did", "doing",
    "going", "will", "effort", "attempt", "attempted", "push", "pushed",
    "faced", "facing", "confront", "confronted", "anyway", "still", "despite",
    "progress", "growing", "grew", "stronger", "improved", "improving",
    "managed", "succeeded", "overcoming", "overcame",
}

# Rumination / catastrophising — clinically problematic without coping.
SAD_RUMINATION_MARKERS = {
    "always", "never", "everyone", "nobody", "no-one", "noone",
    "terrible", "awful", "worst", "horrible", "hopeless", "ruined",
    "doomed", "failure", "disaster", "catastrophe", "pointless",
    "useless", "worthless", "unbearable", "forever",
}

# Specific coping strategies — strong therapeutic signal.
SAD_COPING_MARKERS = {
    "breathe", "breathing", "breath", "relax", "relaxed", "calm",
    "focused", "focus", "prepared", "preparing", "plan", "planning",
    "strategy", "mindful", "mindfulness", "grounded", "grounding",
    "centred", "centered", "accept", "accepting", "acceptance",
    "self-compassion", "compassion", "patient", "patience",
}

# Social-context markers — useful corroboration for SAD content.
SAD_SOCIAL_MARKERS = {
    "people", "person", "friend", "friends", "group", "conversation",
    "talk", "talking", "meeting", "party", "social", "others", "everyone",
    "stranger", "strangers", "audience", "crowd", "presentation",
    "interview", "date", "team", "classmate", "classmates",
}

# Phrases (substring match) — capture multi-word therapeutic patterns.
SAD_GROWTH_PHRASES = (
    "tried anyway", "did it", "going to", "i will", "i can",
    "stepped out", "stepped up", "showed up", "kept going",
    "moved forward", "got through", "pushed through",
)

SAD_RUMINATION_PHRASES = (
    "everyone will judge", "everyone judges", "everyone hates",
    "i'll always", "i will always", "never going to", "never will",
    "always fail", "always wrong", "no one likes", "nobody likes",
    "what's the point", "whats the point",
)

SAD_COPING_PHRASES = (
    "deep breath", "deep breaths", "stay calm", "step back",
    "one step at a time", "be kind to myself", "let it go",
    "ground myself",
)

# ============================================================================
# VR & REAL EXPOSURE
# ============================================================================
VR_NUM_SESSIONS = 4
REAL_EXP_NUM_SESSIONS = 4

# Waiting period (informational only)
WAITING_PERIOD_DAYS = 15

# ============================================================================
# THERAPIST APPROVAL GATES
# ============================================================================
# After each major milestone the participant must sign out and wait for the
# therapist to approve continuation. Approval is stored as a small node at
# `participants/{code}/gates/{gate_key}`:
#     { approved: True, by: <username>, timestamp: ISO, note: <optional> }
#
# Gate keys produced by helpers.gate_key_for(...) — listed here so the
# dashboard can iterate them and show pending approvals consistently.
APPROVAL_GATE_KEYS = [
    "pre_assessment",
    "ptc_session_1",
    "ptc_session_2",
    "ptc_session_3",
    "ptc_session_4",
    "post1_assessment",
    "post2_assessment",
    # post3 = final, no gate
]

# Human-readable labels for gate keys
APPROVAL_GATE_LABELS = {
    "pre_assessment":   "Pre-Assessment complete — approve to start next phase",
    "ptc_session_1":    "PTC Session 1 complete — approve Session 2",
    "ptc_session_2":    "PTC Session 2 complete — approve Session 3",
    "ptc_session_3":    "PTC Session 3 complete — approve Session 4",
    "ptc_session_4":    "PTC Session 4 complete — approve Post-Assessment 1",
    "post1_assessment": "Post-Assessment 1 complete — approve VR Exposure",
    "post2_assessment": "Post-Assessment 2 complete — approve Real Exposure",
}

# ============================================================================
# PARTICIPANT CODE GENERATION
# ============================================================================
PARTICIPANT_CODE_PREFIX = "SAD"

# ============================================================================
# ATTENTIONAL BIAS — DOT PROBE TASK
# ============================================================================
# Each pair: (threat / negative word, neutral or positive word).
# Position of threat (above/below) and probe location (above/below) are
# randomised per trial inside the HTML/JS engine.
DOT_PROBE_WORD_PAIRS = [
    ("Criticized",   "Praised"),
    ("Embarrassed",  "Confident"),
    ("Inadequate",   "Capable"),
    ("Failure",      "Achiever"),
    ("Stupid",       "Intelligent"),
    ("Pathetic",     "Admirable")
]

# Trial count per assessment point (default = all pairs once).
DOT_PROBE_NUM_TRIALS = len(DOT_PROBE_WORD_PAIRS)

# Timings (ms) — straight from the protocol you provided.
DOT_PROBE_FIXATION_MS    = 500
DOT_PROBE_WORDS_MS       = 700
DOT_PROBE_PROBE_TIMEOUT_MS = 1500
DOT_PROBE_ITI_MIN_MS     = 500
DOT_PROBE_ITI_MAX_MS     = 1000


# ============================================================================
# WORD SENTENCE ASSOCIATION (WSA) TASK
# ============================================================================
# Stimuli are loaded from data/wsa_stimuli.json. Each entry:
#     { "word": "...", "sentence": "...", "associated": true|false }
# `associated` is the ground-truth answer (Y = true, N = false).
WSA_NUM_TRIALS = 30                  # may be less if the data file has fewer

# Timings (ms) — from the protocol.
WSA_FIXATION_MS        = 300
WSA_WORD_MS            = 500
WSA_SENTENCE_TIMEOUT_MS = 15000      # safety cap; participant presses Space to continue
WSA_DECISION_TIMEOUT_MS = 8000       # safety cap on Y/N decision


# ============================================================================
# DATA FILE PATHS
# ============================================================================
DATA_DIR = Path(__file__).resolve().parent / "data"
CUE_WORDS_PATH = DATA_DIR / "cue_words.txt"
SENTENCES_PATH = DATA_DIR / "sentences.txt"
WSA_STIMULI_PATH = DATA_DIR / "wsa_stimuli.json"

# ============================================================================
# UI THEME
# ============================================================================
COLOR_PRIMARY = "#2ecc71"     # Green
COLOR_DANGER  = "#e74c3c"     # Red
COLOR_TEXT    = "#222222"
COLOR_BG      = "#f6f9fc"
