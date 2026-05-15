"""
components/questionnaires/BDI.py
=======================================
BDI Version II
"""

import config
from utils.questionnaire_engine import run_bdi_ii_questionnaire


def render(code: str, base_path: str, on_complete=None):
    run_bdi_ii_questionnaire(
        code=code,
        base_path=base_path,
        title="BDI-II",
        instructions=config.BDI_II_INSTRUCTIONS,
        items=config.BDI_II_ITEMS,
        on_complete=on_complete,
    )