"""
components/questionnaires/dot_probe.py
=======================================
Dot-Probe Task - Loads from CSV + Randomizes trial order per session
"""

from __future__ import annotations
import json
import random
import pandas as pd

import streamlit as st
import streamlit.components.v1 as components

import config
from utils.data_logger import get_logger


def _load_dot_probe_trials() -> list[dict]:
    """Load from CSV and shuffle order for each session"""
    try:
        df = pd.read_csv(config.DATA_DIR / "dot_probe.csv")
        trials = []
        
        for _, row in df.iterrows():
            top_word = str(row.get("TOP Word", "")).strip()
            bottom_word = str(row.get("BOTTOM Word", "")).strip()
            dot_pos = str(row.get("Dot Position", "top")).strip().lower()
            
            trials.append({
                "trial": int(row.get("Trial")),
                "block": int(row.get("Block", 1)),
                "pair_type": str(row.get("Pair Type", "")),
                "threat_word": top_word if dot_pos == "top" else bottom_word,
                "neutral_word": bottom_word if dot_pos == "top" else top_word,
                "word_top": top_word,
                "word_bottom": bottom_word,
                "threat_position": "top" if dot_pos == "top" else "bottom",
                "probe_position": "top" if dot_pos == "top" else "bottom",
                "is_congruent": (dot_pos == "top"),
            })
        
        # === RANDOMIZE TRIAL ORDER ===
        random.shuffle(trials)
        
        # Re-number trials sequentially after shuffle
        for i, trial in enumerate(trials):
            trial["trial"] = i + 1
            
        return trials
        
    except Exception as e:
        st.error(f"Error loading dot_probe.csv: {e}")
        st.info("Using fallback from config.py")
        return _build_fallback_trials()


def _build_fallback_trials() -> list[dict]:
    """Original fallback"""
    import random
    pairs = list(config.DOT_PROBE_WORD_PAIRS)
    random.shuffle(pairs)
    trials = []
    for i, (threat, neutral) in enumerate(pairs[:config.DOT_PROBE_NUM_TRIALS]):
        threat_pos = random.choice(["top", "bottom"])
        probe_pos = random.choice(["top", "bottom"])
        trials.append({
            "trial": i + 1,
            "threat_word": threat,
            "neutral_word": neutral,
            "word_top": threat if threat_pos == "top" else neutral,
            "word_bottom": neutral if threat_pos == "top" else threat,
            "threat_position": threat_pos,
            "probe_position": probe_pos,
            "is_congruent": threat_pos == probe_pos,
        })
    return trials


def _build_firebase_put_url(code: str, base_path: str) -> str:
    base = config.FIREBASE_DATABASE_URL.rstrip("/")
    if not base:
        try:
            creds = config.get_firebase_credentials()
            project = creds.get("project_id")
            if project:
                base = f"https://{project}-default-rtdb.firebaseio.com"
        except Exception:
            base = ""
    path = f"participants/{code}/{base_path.strip('/')}"
    return f"{base}/{path}.json" if base else ""


def _is_complete(code: str, base_path: str) -> bool:
    logger = get_logger()
    node = logger.get(code, base_path) or {}
    return isinstance(node, dict) and bool(node.get("completed_timestamp"))


def render(code: str, base_path: str, on_complete=None):
    if not code:
        st.error("No participant code in session.")
        return

    if _is_complete(code, base_path):
        st.success("✅ Dot-Probe task already completed.")
        if on_complete and st.button("Continue ➜", type="primary"):
            on_complete()
        return

    safe_key = base_path.replace("/", "_")
    if f"{safe_key}_instructions_seen" not in st.session_state:
        st.session_state[f"{safe_key}_instructions_seen"] = False

    if not st.session_state[f"{safe_key}_instructions_seen"]:
        st.markdown("## Attentional Bias — Dot-Probe Task")
        st.markdown(
            "<div class='form-text'>"
            "<b>Instructions:</b><br>"
            "• Fixation cross appears briefly.<br>"
            "• Two words flash (one above, one below).<br>"
            "• Dot appears — press ↑ or ↓ quickly.<br>"
            "• Be fast and accurate."
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Start Task ➜", type="primary", key=f"{safe_key}_start"):
            st.session_state[f"{safe_key}_instructions_seen"] = True
            st.rerun()
        return

    st.markdown("### Dot-Probe Task")
    trials = _load_dot_probe_trials()
    put_url = _build_firebase_put_url(code, base_path)

    html = _build_html(trials, put_url)

    with st.container():
        components.html(html, height=560, scrolling=False)

    if st.button("I've finished the task ➜", type="primary", use_container_width=True):
        if _is_complete(code, base_path):
            st.rerun()
        else:
            st.warning("Waiting for results to save... Try again shortly.")


def _build_html(trials, put_url):
    trials_json = json.dumps(trials)
    put_url_str = put_url or ""
    
    return f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ height: 100%; margin: 0; padding: 0; overflow: hidden; }}
  body {{ display: flex; align-items: center; justify-content: center;
         background: #f6f9fc; font-family: 'Times New Roman', serif; color: #010d1a; }}
  .stage {{ width: 100%; height: 500px; position: relative; display: flex; 
           flex-direction: column; align-items: center; justify-content: center;
           border: 2px solid #c9d6e3; border-radius: 8px; background: #ffffff; }}
  .fix {{ font-size: 64px; font-weight: bold; }}
  .word {{ font-size: 36px; font-weight: bold; }}
  .word.top {{ position: absolute; top: 30%; }}
  .word.bottom {{ position: absolute; bottom: 30%; }}
  .probe {{ font-size: 64px; font-weight: bold; color: #c0392b; }}
  .probe.top {{ position: absolute; top: 30%; }}
  .probe.bottom {{ position: absolute; bottom: 30%; }}
  .msg {{ font-size: 22px; text-align: center; padding: 0 30px; }}
  .progress {{ position: absolute; bottom: 10px; right: 14px; font-size: 13px; color: #888; }}
  button.start {{ font-size: 20px; padding: 12px 28px; border-radius: 6px;
                 background: #2ecc71; color: white; border: none; cursor: pointer; }}
</style></head>
<body tabindex="0">
  <div class="stage" id="stage" tabindex="0">
    <div class="msg" id="msg">
      <p>Click the green button to start.<br>
      You'll need your <b>↑ Up</b> and <b>↓ Down</b> arrow keys.</p>
      <button class="start" id="start-btn">▶ Start Task</button>
    </div>
    <div class="progress" id="prog"></div>
  </div>

<script>
(function() {{
  const TRIALS = {trials_json};
  const FIXATION_MS = {config.DOT_PROBE_FIXATION_MS};
  const WORDS_MS = {config.DOT_PROBE_WORDS_MS};
  const PROBE_MS = {config.DOT_PROBE_PROBE_TIMEOUT_MS};
  const ITI_MIN_MS = {config.DOT_PROBE_ITI_MIN_MS};
  const ITI_MAX_MS = {config.DOT_PROBE_ITI_MAX_MS};
  const PUT_URL = "{put_url_str}";

  const stage = document.getElementById('stage');
  const msg = document.getElementById('msg');
  const prog = document.getElementById('prog');
  const startBtn = document.getElementById('start-btn');

  const wait = ms => new Promise(r => setTimeout(r, ms));
  const rand = (a, b) => a + Math.random() * (b - a);
  const now = () => performance.now();

  function clearStage() {{ stage.innerHTML = '<div class="progress" id="prog"></div>'; }}
  function setProgress(i, n) {{
    const p = document.getElementById('prog');
    if (p) p.textContent = `Trial ${{i}} / ${{n}}`;
  }}

  function showFixation() {{
    clearStage();
    const f = document.createElement('div');
    f.className = 'fix';
    f.textContent = '+';
    stage.appendChild(f);
    return wait(FIXATION_MS);
  }}

  function showWords(top, bottom) {{
    clearStage();
    const t = document.createElement('div'); t.className = 'word top'; t.textContent = top;
    const b = document.createElement('div'); b.className = 'word bottom'; b.textContent = bottom;
    stage.appendChild(t); stage.appendChild(b);
    return wait(WORDS_MS);
  }}

  function showProbe(position) {{
    clearStage();
    const p = document.createElement('div');
    p.className = 'probe ' + position;
    p.textContent = '•';
    stage.appendChild(p);
    const start = now();
    return new Promise(resolve => {{
      let resolved = false;
      const onKey = (e) => {{
        if (resolved) return;
        let r = null;
        if (e.key === 'ArrowUp') r = 'up';
        if (e.key === 'ArrowDown') r = 'down';
        if (r === null) return;
        e.preventDefault();
        e.stopPropagation();
        resolved = true;
        window.removeEventListener('keydown', onKey);
        clearTimeout(to);
        resolve({{ response: r, rt_ms: Math.round(now() - start) }});
      }};
      const to = setTimeout(() => {{
        if (resolved) return;
        resolved = true;
        window.removeEventListener('keydown', onKey);
        resolve({{ response: 'timeout', rt_ms: PROBE_MS }});
      }}, PROBE_MS);
      window.addEventListener('keydown', onKey);
    }});
  }}

  function blank() {{
    clearStage();
    return wait(rand(ITI_MIN_MS, ITI_MAX_MS));
  }}

  async function runTrial(t, i, n) {{
    setProgress(i, n);
    await showFixation();
    await showWords(t.word_top, t.word_bottom);
    const r = await showProbe(t.probe_position);
    await blank();
    const correct = (r.response === 'up' && t.probe_position === 'top') ||
                    (r.response === 'down' && t.probe_position === 'bottom');
    return Object.assign({{}}, t, {{
      response: r.response,
      rt_ms: r.rt_ms,
      correct: correct,
      timestamp: new Date().toISOString(),
    }});
  }}

  function summarise(results) {{
    const valid = results.filter(r => r.correct && r.response !== 'timeout');
    const meanRT = valid.length ? valid.reduce((s, r) => s + r.rt_ms, 0) / valid.length : null;
    const acc = results.length ? results.filter(r => r.correct).length / results.length : 0;
    const cong = valid.filter(r => r.is_congruent);
    const incong = valid.filter(r => !r.is_congruent);
    const meanCong = cong.length ? cong.reduce((s,r)=>s+r.rt_ms,0)/cong.length : null;
    const meanIncong = incong.length ? incong.reduce((s,r)=>s+r.rt_ms,0)/incong.length : null;
    const bias = (meanCong !== null && meanIncong !== null) 
      ? Math.round((meanIncong - meanCong) * 100) / 100 : null;

    return {{
      num_trials: results.length,
      accuracy: Math.round(acc * 1000) / 1000,
      mean_rt_correct_ms: meanRT !== null ? Math.round(meanRT) : null,
      mean_rt_congruent_ms: meanCong !== null ? Math.round(meanCong) : null,
      mean_rt_incongruent_ms: meanIncong !== null ? Math.round(meanIncong) : null,
      bias_index_ms: bias,
    }};
  }}

  async function uploadResults(payload) {{
    if (!PUT_URL) return false;
    try {{
      const res = await fetch(PUT_URL, {{
        method: 'PUT',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});
      return res.ok;
    }} catch (e) {{
      return false;
    }}
  }}

  async function run() {{
    startBtn.disabled = true;
    stage.focus();
    
    const preventScroll = (e) => {{
      if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {{
        e.preventDefault(); e.stopPropagation();
      }}
    }};
    window.addEventListener('keydown', preventScroll);
    
    const results = [];
    for (let i = 0; i < TRIALS.length; i++) {{
      const r = await runTrial(TRIALS[i], i + 1, TRIALS.length);
      results.push(r);
    }}
    
    window.removeEventListener('keydown', preventScroll);
    
    const summary = summarise(results);
    const payload = Object.assign({{}}, summary, {{
      trials: results,
      completed_timestamp: new Date().toISOString(),
    }});
    const ok = await uploadResults(payload);
    
    clearStage();
    const done = document.createElement('div');
    done.className = 'msg';
    done.innerHTML = ok
      ? '<h2>✅ Task complete</h2><p>Please click <b>"I\\'ve finished the task"</b> below to continue.</p>'
      : '<h2>⚠️ Could not save results</h2><p>Please notify your therapist.</p>';
    stage.appendChild(done);
  }}

  startBtn.addEventListener('click', () => run().catch(err => {{
    msg.innerHTML = '<h3>Error</h3><pre>' + (err && err.message || err) + '</pre>';
  }}));
  document.body.addEventListener('click', () => stage.focus());
}})();
</script>
</body></html>
"""