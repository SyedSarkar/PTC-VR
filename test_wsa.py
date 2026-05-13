"""
Test script for Word Sentence Association (WSA) component.
Run this to test the WSA task in isolation.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# Page config
st.set_page_config(
    page_title="WSA Test",
    page_icon="📝",
    layout="wide"
)

# Import the component
from components.questionnaires.wsa import render

# Mock test data
test_code = "TEST-WSA"
test_base_path = "test/wsa"

st.title("Word Sentence Association Component Test")
st.markdown("Testing the WSA task in isolation")
st.divider()

# Call the component
render(
    code=test_code,
    base_path=test_base_path,
    on_complete=lambda: st.success("WSA task completed!")
)
