"""
components/questionnaires/bat.py
=================================
Behavioral Avoidance Task (BAT).
List view of scenarios with Pre/Post SUDS ratings.
Each scenario rated with SUDS (0-100) before and after exposure.
"""

import streamlit as st

import config
from utils.helpers import now_iso
from utils.data_logger import get_logger


def render(code: str, base_path: str, on_complete=None):
    """
    Render BAT with list view and Pre/Post SUDS ratings.
    
    Args:
        code: participant code
        base_path: e.g. 'vr_exposure/session_1/bat'
        on_complete: callback when all scenarios are rated
    """
    logger = get_logger()
    items = config.BAT_SCENARIOS
    total = len(items)
    safe_key = base_path.replace("/", "_")
    
    # Load existing responses
    existing = logger.get(code, base_path) or {}
    
    # Track which scenario is currently being viewed
    if f"{safe_key}_selected_scenario" not in st.session_state:
        st.session_state[f"{safe_key}_selected_scenario"] = None
    
    selected_scenario_idx = st.session_state[f"{safe_key}_selected_scenario"]
    
    st.markdown("## Behavioral Avoidance Task")
    st.markdown(
        f"<div class='form-text'>{config.BAT_INSTRUCTIONS}</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    
    # Check if all scenarios are complete
    completed_count = sum(1 for i in range(total) if existing.get(str(i), {}).get("completed", False))
    
    if completed_count == total:
        st.success(f"✅ All {total} scenarios completed!")
        if on_complete:
            if st.button("Continue ➜", type="primary", key=f"{safe_key}_continue"):
                on_complete()
        return
    
    # Progress indicator
    st.progress(completed_count / total if total > 0 else 0)
    st.markdown(
        f"<div class='progress-text'>Completed: {completed_count} / {total} scenarios</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    
    # If no scenario selected, show list view
    if selected_scenario_idx is None:
        st.markdown("### Select a scenario to rate:")
        for idx, scenario in enumerate(items):
            scenario_data = existing.get(str(idx), {})
            is_complete = scenario_data.get("completed", False)
            
            with st.container():
                col_status, col_text, col_button = st.columns([1, 8, 2])
                
                with col_status:
                    if is_complete:
                        st.success("✅")
                    else:
                        st.info("○")
                
                with col_text:
                    st.markdown(f"<div style='font-size:16px;'>{scenario}</div>", unsafe_allow_html=True)
                
                with col_button:
                    if st.button("Rate", key=f"{safe_key}_select_{idx}", use_container_width=True):
                        st.session_state[f"{safe_key}_selected_scenario"] = idx
                        st.rerun()
                
                st.divider()
    else:
        # Show selected scenario with Pre/Post SUDS ratings
        scenario = items[selected_scenario_idx]
        scenario_data = existing.get(str(selected_scenario_idx), {})
        
        # Back button
        if st.button("← Back to List", key=f"{safe_key}_back"):
            st.session_state[f"{safe_key}_selected_scenario"] = None
            st.rerun()
        
        st.divider()
        
        # Center the scenario
        st.markdown(
            f"<div class='item-title' style='font-size:24px;'>{scenario}</div>",
            unsafe_allow_html=True,
        )
        st.divider()
        
        # Pre and Post SUDS ratings side by side
        col_pre, col_center, col_post = st.columns([1, 1, 1])
        
        with col_pre:
            st.markdown("### Pre-SUDS")
            st.markdown(
                "<div class='form-text' style='font-size:13px;'>Distress BEFORE attempting</div>",
                unsafe_allow_html=True,
            )
            
            # Load existing pre-suds value
            pre_suds_default = scenario_data.get("pre_suds", 50)
            
            pre_suds = st.slider(
                "Pre-SUDS Rating:",
                min_value=0, max_value=100, value=pre_suds_default, step=5,
                key=f"{safe_key}_pre_suds_{selected_scenario_idx}",
            )
            
            # Show anchor description
            nearest_anchor = min(config.SUDS_ANCHORS.keys(), key=lambda x: abs(x - pre_suds))
            desc = config.SUDS_ANCHORS[nearest_anchor]
            if desc and desc != "—":
                st.markdown(
                    f"<div class='scale-text' style='font-size:14px;'>"
                    f"<b>{pre_suds}</b> — <i>{desc}</i></div>",
                    unsafe_allow_html=True,
                )
        
        with col_center:
            st.markdown("###")
            st.markdown(
                "<div style='text-align:center; padding:20px;'>"
                "<b>SCENARIO</b><br><br>↓</div>",
                unsafe_allow_html=True,
            )
        
        with col_post:
            st.markdown("### Post-SUDS")
            st.markdown(
                "<div class='form-text' style='font-size:13px;'>Distress AFTER attempting</div>",
                unsafe_allow_html=True,
            )
            
            # Load existing post-suds value
            post_suds_default = scenario_data.get("post_suds", 50)
            
            post_suds = st.slider(
                "Post-SUDS Rating:",
                min_value=0, max_value=100, value=post_suds_default, step=5,
                key=f"{safe_key}_post_suds_{selected_scenario_idx}",
            )
            
            # Show anchor description
            nearest_anchor = min(config.SUDS_ANCHORS.keys(), key=lambda x: abs(x - post_suds))
            desc = config.SUDS_ANCHORS[nearest_anchor]
            if desc and desc != "—":
                st.markdown(
                    f"<div class='scale-text' style='font-size:14px;'>"
                    f"<b>{post_suds}</b> — <i>{desc}</i></div>",
                    unsafe_allow_html=True,
                )
        
        st.divider()
        
        # Save button
        col_left, col_center, col_right = st.columns([1, 2, 1])
        with col_center:
            if st.button("Save Ratings ✓", type="primary", key=f"{safe_key}_save_{selected_scenario_idx}", use_container_width=True):
                # Save the scenario data with pre/post SUDS
                logger.set(code, f"{base_path}/{selected_scenario_idx}", {
                    "item_index": selected_scenario_idx,
                    "scenario": scenario,
                    "pre_suds": int(pre_suds),
                    "post_suds": int(post_suds),
                    "completed": True,
                    "timestamp": now_iso(),
                })
                
                # Log the event
                logger.log_event(code, "bat_scenario_rated", {
                    "scenario_index": selected_scenario_idx,
                    "scenario_text": scenario,
                    "pre_suds": int(pre_suds),
                    "post_suds": int(post_suds),
                    "path": base_path,
                })
                
                # Return to list view
                st.session_state[f"{safe_key}_selected_scenario"] = None
                st.success(f"✅ Saved ratings for: {scenario}")
                st.rerun()
