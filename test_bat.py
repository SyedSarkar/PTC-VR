"""
bat - Behavioral Activation Task component.
Run this to test the bat task in isolation.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# Page config
st.set_page_config(
    page_title="bat",
    page_icon="📝",
    layout="wide"
)

# Import the component
from components.questionnaires.bat import render

# Mock test data
test_code = "TEST-bat"
test_base_path = "test/bat"

st.title("BBAATT")
st.markdown("Testing the bat task in isolation")
st.divider()

# Call the component
render(
    code=test_code,
    base_path=test_base_path,
    on_complete=lambda: st.success("bat task completed!")
)
