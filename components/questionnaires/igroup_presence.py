"""
components/questionnaires/igroup_presence.py
=============================================
I-Group Presence Questionnaire (Witmer & Singer, revised by UQO Cyberpsychology Lab).
24 items, 7-point scale with left/middle/right anchor labels.
"""

import config
from utils.questionnaire_engine import run_igroup_questionnaire


def render(code: str, base_path: str, on_complete=None):
    run_igroup_questionnaire(
        code=code,
        base_path=base_path,
        title="Presence Questionnaire",
        instructions=config.IGROUP_INSTRUCTIONS,
        items=config.IGROUP_ITEMS,
        on_complete=on_complete,
    )
