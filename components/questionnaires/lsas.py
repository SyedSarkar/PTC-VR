"""
components/questionnaires/lsas.py
==================================
Liebowitz Social Anxiety Scale - 24 items, Fear (0-3) + Avoidance (0-3) per item.
"""

import config
from utils.questionnaire_engine import run_lsas_questionnaire


def render(code: str, base_path: str, on_complete=None):
    """
    Args:
        code: participant code
        base_path: e.g. 'assessments/pre/lsas' or 'assessments/post1/lsas'
        on_complete: callback when this scale is finished
    """
    run_lsas_questionnaire(
        code=code,
        base_path=base_path,
        title="Liebowitz Social Anxiety Scale (LSAS)",
        instructions=config.LSAS_INSTRUCTIONS,
        items=config.LSAS_ITEMS,
        fear_labels=config.LSAS_FEAR_LABELS,
        avoid_labels=config.LSAS_AVOID_LABELS,
        on_complete=on_complete,
    )
