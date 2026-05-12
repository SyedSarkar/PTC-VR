# SAD Intervention App

A complete, professional Streamlit web application for a Master's thesis studying Social Anxiety Disorder with three intervention arms (PTC, VR, CBT).

## Overview

This application implements a randomized controlled trial for Social Anxiety Disorder (SAD) with:
- **Group A (PTC)**: Proactive Thought Control training with sentiment-validated tasks
- **Group B (VR)**: Virtual Reality exposure therapy
- **Group C (CBT)**: Cognitive Behavioral Therapy (waiting period control)

## Features

### Authentication & Roles
- **Therapist Login**: Full dashboard access (Username: `Esha`, Password: `Eshatherapist`)
- **Participant Login**: Auto-assigned to groups (hidden from participant)

### Assessments
1. **LSAS** (Liebowitz Social Anxiety Scale) - 24 items (Fear + Avoidance)
2. **BFNE** (Brief Fear of Negative Evaluation) - 12 items
3. **CBQ** (Cognitive Beliefs Questionnaire) - 20 items
4. **BAT** (Behavioral Avoidance Task) - Placeholder scenarios
5. **SSQ** (Simulator Sickness Questionnaire) - 16 items
6. **SUDS** (Subjective Units of Distress Scale) - 0-100
7. **I-Group Presence** (VR experience) - 24 items
8. **Oximeter** - Manual SpO2/BPM entry

### PTC Training (Group A Only)
- **Free Association Task (FAT)**: Respond to cue words with 1-3 positive/neutral words
- **Sentence Completion Task**: Complete sentence stems positively
- Sentiment analysis using HuggingFace Transformers (distilbert-base-uncased-finetuned-sst-2-english)
- 4 sessions, 3 blocks per session, continuous flow
- Points tracking with validation

### VR Phase (All Groups)
- Pre: SSQ + SUDS + Oximeter
- Therapist marks completion
- Post: SUDS + Oximeter + I-Group Presence + SSQ

### Real Exposure Phase (All Groups)
- Therapist enters free-form scenarios
- Participant: SUDS before → exposure → SUDS after
- 4 sessions total

### Assessment Schedule
1. **Pre-Assessment** (full battery at baseline)
2. **Post-Assessment 1** (after PTC/waiting period)
3. **Post-Assessment 2** (after VR exposure)
4. **Post-Assessment 3** (final, after real exposure)

### Data Management
- **Firebase Realtime Database**: All responses logged with timestamps
- **Excel Export**: Comprehensive export with all scores and metadata
- **Resume Capability**: Participants can continue from exact item left off
- **Withdrawal**: Partial anonymization (PII removed, data retained)

## Installation

### Prerequisites
- Python 3.9+
- Firebase project with Realtime Database enabled

### Setup

1. **Clone the repository**:
```bash
git clone <repository-url>
cd ptc-intervention-app
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure Firebase credentials** (choose one method):

   **Option A**: Environment variable with raw JSON
   ```bash
   # Windows PowerShell
   $env:FIREBASE_CREDENTIALS_JSON = '{"type": "service_account", ...}'
   
   # Or create .env.local file
   FIREBASE_CREDENTIALS_JSON={"type": "service_account", ...}
   ```

   **Option B**: Environment variable with file path
   ```bash
   FIREBASE_CREDENTIALS_PATH=/path/to/serviceAccountKey.json
   ```

   **Option C**: Streamlit secrets (for deployment)
   Create `.streamlit/secrets.toml`:
   ```toml
   FIREBASE_CREDENTIALS_JSON = """{"type": "service_account", ...}"""
   ```

4. **Add PTC training data**:
   Edit `data/cue_words.txt` - one cue word per line
   Edit `data/sentences.txt` - one sentence stem per line

5. **Run the application**:
```bash
streamlit run app.py
```

## Folder Structure

```
ptc-intervention-app/
├── app.py                    # Main entry point
├── config.py                 # Firebase config + all scale items
├── export.py                 # Excel export functionality
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── data/
│   ├── cue_words.txt         # FAT cue words (user provides)
│   └── sentences.txt       # Sentence stems (user provides)
├── utils/
│   ├── __init__.py
│   ├── data_logger.py        # Firebase operations
│   ├── helpers.py            # Shared utilities
│   ├── questionnaire_engine.py   # Generic questionnaire logic
│   └── validators.py         # Input validation + sentiment analysis
└── components/
    ├── __init__.py
    ├── consent.py              # Informed consent
    ├── demographics.py         # Demographics form
    ├── welcome.py              # Welcome/login screen
    ├── withdrawal.py           # Withdrawal handling
    ├── assessment_battery.py   # Pre/post assessment orchestrator
    ├── ptc_phase.py            # PTC training phase
    ├── vr_phase.py             # VR exposure phase
    ├── real_exposure_phase.py  # Real exposure phase
    ├── waiting_phase.py        # Waiting period (VR/CBT groups)
    ├── therapist_dashboard.py  # Therapist admin panel
    └── questionnaires/
        ├── lsas.py             # Liebowitz Social Anxiety Scale
        ├── bfne.py             # Brief Fear of Negative Evaluation
        ├── cbq.py              # Cognitive Beliefs Questionnaire
        ├── bat.py              # Behavioral Avoidance Task
        ├── ssq.py              # Simulator Sickness Questionnaire
        ├── suds.py             # Subjective Units of Distress
        ├── oximeter.py         # Oximeter readings
        └── igroup_presence.py  # I-Group Presence Questionnaire
    └── tasks/
        ├── fat.py              # Free Association Task
        └── sentence_completion.py  # Sentence Completion Task
```

## Study Configuration

All study parameters are in `config.py`:

- `STUDY_TITLE`, `RESEARCHER`, `INSTITUTION` - Study metadata
- `THERAPIST_USERNAME`, `THERAPIST_PASSWORD` - Admin credentials
- `GROUPS` - Study arms (PTC, VR, CBT)
- `PTC_NUM_SESSIONS` - Number of PTC training sessions (default: 4)
- `VR_NUM_SESSIONS` - Number of VR sessions (default: 4)
- `REAL_EXP_NUM_SESSIONS` - Number of real exposure sessions (default: 4)
- `LSAS_ITEMS`, `BFNE_ITEMS`, etc. - All questionnaire items

## Data Export

Therapists can export all participant data to Excel via the dashboard:
- **All Participants sheet**: Complete data for each participant
- **Summary sheet**: Study statistics and completion rates

## Key Features

### Resume Capability
Participants can close the browser and return later - their exact position is saved.

### Sentiment Analysis
PTC tasks use HuggingFace Transformers to validate positive/neutral responses in real-time.

### Firebase Integration
All data persisted to Firebase Realtime Database with structured paths:
```
participants/{code}/
  ├── metadata/
  ├── consent/
  ├── progress/
  ├── assessments/
  │   ├── pre/
  │   ├── post1/
  │   ├── post2/
  │   └── post3/
  ├── ptc_training/
  ├── vr_exposure/
  ├── real_exposure/
  ├── withdrawal/
  └── events/
```

### Security
- Group assignment is hidden from participants
- Withdrawal anonymizes PII while retaining research data
- Therapist credentials required for admin functions

## License

This application is created for academic research purposes.

## Contact

**Researcher**: Esha Jaffar - eshajaffar009@gmail.com  
**Principal Investigator**: Ather Mujtaba - ather.mujitaba@gift.edu.pk  
**Institution**: GIFT University

## Troubleshooting

### NLTK Data Download
If you encounter NLTK errors on first run, the app will auto-download the brown corpus. If manual download is needed:

```python
import nltk
nltk.download('brown')
```

### Sentiment Model
The sentiment classifier downloads automatically on first use (~250MB). Ensure stable internet connection for initial setup.

### Firebase Connection
If Firebase connection fails:
1. Verify credentials JSON is valid
2. Check `FIREBASE_DATABASE_URL` is set correctly
3. Ensure Realtime Database rules allow authenticated writes
