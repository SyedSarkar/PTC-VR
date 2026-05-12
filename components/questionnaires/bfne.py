"""
components/questionnaires/bfne.py
==================================
Brief Fear of Negative Evaluation - 12 items, 1-5 Likert scale.
Items 2, 4, 7, 10 are reverse-scored.
"""

import config
from utils.questionnaire_engine import run_single_scale_questionnaire


def render(code: str, base_path: str, on_complete=None):
    run_single_scale_questionnaire(
        code=code,
        base_path=base_path,
        title="Brief Fear of Negative Evaluation (BFNE)",
        instructions=config.BFNE_INSTRUCTIONS,
        items=config.BFNE_ITEMS,
        scale_labels=config.BFNE_LABELS,
        scale_values=[1, 2, 3, 4, 5],
        reverse_scored_items=config.BFNE_REVERSE_SCORED,
        on_complete=on_complete,
    )
