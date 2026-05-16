"""
components/questionnaires/cbq.py
=================================
Core Beliefs Questionnaire - 20 items
"""

import config
from utils.questionnaire_engine import run_single_scale_questionnaire


def render(code: str, base_path: str, on_complete=None):
    run_single_scale_questionnaire(
        code=code,
        base_path=base_path,
        title="Core Beliefs Questionnaire (CBQ)",
        instructions=config.CBQ_INSTRUCTIONS,
        items=config.CBQ_ITEMS,
        scale_labels=config.CBQ_LABELS,
        scale_values=[1, 2, 3, 4, 5, 6],
        on_complete=on_complete,
    )