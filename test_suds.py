"""
Test script for individual components
Run with: streamlit run test_bat.py
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent directory to path to import components
sys.path.insert(0, str(Path(__file__).parent))

import config
from components.questionnaires.bat import render

st.set_page_config(page_title="bat Test", layout="centered")

# Mock participant data
test_code = "TEST-001"
test_base_path = "test_session/pre_bat"
test_label = "Test bat Rating"

st.title("🧪 Component Test: bat")
st.markdown(f"Testing component with:")
st.markdown(f"- Code: `{test_code}`")
st.markdown(f"- Base Path: `{test_base_path}`")
st.markdown(f"- Label: `{test_label}`")
st.divider()

# Call the component
render(
    code=test_code,
    base_path=test_base_path,
    on_complete=lambda: st.success("BAT completed!")
)

st.divider()
st.caption("This is a test script for individual component development")
