"""
FAT - PTC component.
Run this to test the WSA task in isolation.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# Page config
st.set_page_config(
    page_title="FAT",
    page_icon="📝",
    layout="wide"
)

# Import the component
from components.tasks.fat import render

# Mock test data
test_code = "TEST-fat"
test_base_path = "test/fat"

st.title("FFAATT")
st.markdown("Testing the FAT task in isolation")
st.divider()

# Call the component
render(
    code=test_code,
    session_num=1,
    on_complete=lambda: st.success("FAT task completed!")
)
