"""
components/questionnaires/cbq_trait.py
=======================================
Cognitive Beliefs Questionnaire - Trait Version - 20 items, 1-6 scale.
"""

import config
from utils.questionnaire_engine import run_single_scale_questionnaire


def render(code: str, base_path: str, on_complete=None):
    run_single_scale_questionnaire(
        code=code,
        base_path=base_path,
        title="Cognitive Beliefs Questionnaire - Trait (CBQ-Trait)",
        instructions=config.CBQ_TRAIT_INSTRUCTIONS,
        items=config.CBQ_TRAIT_ITEMS,
        scale_labels=config.CBQ_TRAIT_LABELS,
        scale_values=[1, 2, 3, 4, 5, 6],
        on_complete=on_complete,
    )
