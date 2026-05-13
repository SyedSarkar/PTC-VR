"""
Test script for Dot-Probe component.
Run this to test the dot probe task in isolation.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# Page config
st.set_page_config(
    page_title="Dot-Probe Test",
    page_icon="🎯",
    layout="wide"
)

# Import the component
from components.questionnaires.dot_probe import render

# Mock test data
test_code = "TEST-DOT-PROBE"
test_base_path = "test/dot_probe"

st.title("Dot-Probe Component Test")
st.markdown("Testing the dot probe task in isolation")
st.divider()

# Call the component
render(
    code=test_code,
    base_path=test_base_path,
    on_complete=lambda: st.success("Dot-Probe task completed!")
)
