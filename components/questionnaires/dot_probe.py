"""
components/questionnaires/dot_probe.py
=======================================
Attentional Bias — Dot-Probe Task.

The experiment runs entirely client-side in an embedded HTML/JS component
because Streamlit's Python rerun loop cannot deliver the 500/700/1500 ms
stimulus windows reliably. Trial-by-trial results are POSTed directly to
Firebase Realtime Database via REST so participants can advance once done.

Protocol (per trial):
    1. Fixation cross "+"      — DOT_PROBE_FIXATION_MS
    2. Word pair (one above, one below)  — DOT_PROBE_WORDS_MS
    3. Probe dot (·) appears in one of the two locations
       until response or DOT_PROBE_PROBE_TIMEOUT_MS
    4. Blank ITI                — random in [ITI_MIN, ITI_MAX]

Saved structure (at participants/{code}/{base_path}):
    {
        "completed_timestamp": "...",
        "num_trials": 30,
        "mean_rt_correct_ms": 612,
        "accuracy": 0.97,
        "bias_index_ms": -23.5,
        "trials": [ { ... per-trial dict ... }, ... ]
    }
"""

from __future__ import annotations
import json
import random

import streamlit as st
import streamlit.components.v1 as components

import config
from utils.data_logger import get_logger


def _is_complete(code: str, base_path: str) -> bool:
    logger = get_logger()
    node = logger.get(code, base_path) or {}
    if not isinstance(node, dict):
        return False
    return bool(node.get("completed_timestamp"))


def _build_trial_list() -> list[dict]:
    """Sample N pairs (without replacement when possible) and randomise
    threat-position + probe-position per trial."""
    pairs = list(config.DOT_PROBE_WORD_PAIRS)
    random.shuffle(pairs)
    n = min(config.DOT_PROBE_NUM_TRIALS, len(pairs))
    pairs = pairs[:n]

    trials = []
    for i, (threat, neutral) in enumerate(pairs):
        threat_position = random.choice(["top", "bottom"])
        probe_position = random.choice(["top", "bottom"])
        if threat_position == "top":
            word_top, word_bottom = threat, neutral
        else:
            word_top, word_bottom = neutral, threat
        trials.append({
            "trial": i + 1,
            "threat_word": threat,
            "neutral_word": neutral,
            "word_top": word_top,
            "word_bottom": word_bottom,
            "threat_position": threat_position,
            "probe_position": probe_position,
            # Congruent = probe replaces the threat word (attention captured by threat)
            "is_congruent": (threat_position == probe_position),
        })
    return trials


def _build_firebase_put_url(code: str, base_path: str) -> str:
    """Build the REST URL for a PUT against participants/{code}/{base_path}.

    NOTE: this assumes Firebase Realtime Database rules permit unauthenticated
    writes (typical for private research deployments). If your rules require
    auth, this won't work — see the dashboard's audit note.
    """
    base = config.FIREBASE_DATABASE_URL.rstrip("/")
    if not base:
        # Fallback to default project URL if available via env
        try:
            creds = config.get_firebase_credentials()
            project = creds.get("project_id")
            if project:
                base = f"https://{project}-default-rtdb.firebaseio.com"
        except Exception:
            base = ""
    path = f"participants/{code}/{base_path.strip('/')}"
    return f"{base}/{path}.json" if base else ""


def render(code: str, base_path: str, on_complete=None):
    if not code:
        st.error("No participant code in session.")
        return

    # If task is already done, skip
    if _is_complete(code, base_path):
        st.success("✅ Dot-Probe task already completed.")
        if on_complete:
            if st.button("Continue ➜", type="primary",
                         key=f"{base_path.replace('/', '_')}_continue"):
                on_complete()
        return

    st.markdown("## Attentional Bias — Dot-Probe Task")
    st.markdown(
        "<div class='form-text'>"
        "<b>Instructions:</b><br>"
        "• A fixation cross <code>+</code> will appear briefly.<br>"
        "• Two words will flash on the screen (one above, one below).<br>"
        "• A small dot <code>·</code> will then appear where one of the words was.<br>"
        "• Press <b>↑ Up Arrow</b> if the dot is above, <b>↓ Down Arrow</b> if it is below.<br>"
        "• Respond as quickly and accurately as you can.<br>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "💡 Click inside the task area below before pressing keys, so the "
        "browser focuses the experiment."
    )
    st.divider()

    # Build trials and PUT URL once per page render. Trial order is randomised
    # on each render, but if the participant refreshes mid-task they restart
    # from trial 1 (acceptable — task is short and only completes once).
    trials = _build_trial_list()
    put_url = _build_firebase_put_url(code, base_path)
    if not put_url:
        st.error(
            "FIREBASE_DATABASE_URL is not configured — the in-browser task "
            "cannot save its results. Please set FIREBASE_DATABASE_URL in "
            ".env.local."
        )
        return

    html = _build_html(
        trials=trials,
        put_url=put_url,
        fixation_ms=config.DOT_PROBE_FIXATION_MS,
        words_ms=config.DOT_PROBE_WORDS_MS,
        probe_timeout_ms=config.DOT_PROBE_PROBE_TIMEOUT_MS,
        iti_min_ms=config.DOT_PROBE_ITI_MIN_MS,
        iti_max_ms=config.DOT_PROBE_ITI_MAX_MS,
    )

    components.html(html, height=560, scrolling=False)

    st.markdown(
        "<div class='form-text' style='margin-top:18px;'>"
        "When the task screen shows <b>'Task complete'</b>, click the button "
        "below to continue.</div>",
        unsafe_allow_html=True,
    )
    safe = base_path.replace("/", "_")
    if st.button("I've finished the task ➜", type="primary",
                 key=f"{safe}_check"):
        # Re-check Firebase to confirm data landed
        if _is_complete(code, base_path):
            st.rerun()
        else:
            st.warning(
                "Couldn't find your task results yet. Please make sure the "
                "task screen says 'Task complete' before clicking, and try "
                "again in a moment."
            )


# ---------------------------------------------------------------------------
# HTML / JS template
# ---------------------------------------------------------------------------
def _build_html(trials, put_url, fixation_ms, words_ms,
                probe_timeout_ms, iti_min_ms, iti_max_ms) -> str:
    trials_json = json.dumps(trials)
    return f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html, body {{ height: 100%; margin: 0; padding: 0; }}
  body {{
      display: flex; align-items: center; justify-content: center;
      background: #f6f9fc; font-family: 'Times New Roman', Times, serif;
      color: #010d1a;
      outline: none;
  }}
  .stage {{
      width: 100%; height: 500px; position: relative;
      display: flex; flex-direction: column; align-items: center;
      justify-content: center;
      border: 2px solid #c9d6e3; border-radius: 8px; background: #ffffff;
  }}
  .fix     {{ font-size: 64px; font-weight: bold; }}
  .word    {{ font-size: 36px; font-weight: bold; }}
  .word.top    {{ position: absolute; top: 30%; }}
  .word.bottom {{ position: absolute; bottom: 30%; }}
  .probe   {{ font-size: 64px; font-weight: bold; color: #c0392b; }}
  .probe.top    {{ position: absolute; top: 30%; }}
  .probe.bottom {{ position: absolute; bottom: 30%; }}
  .msg     {{ font-size: 22px; text-align: center; padding: 0 30px; }}
  .progress {{
      position: absolute; bottom: 10px; right: 14px;
      font-size: 13px; color: #888;
  }}
  button.start {{
      font-size: 20px; padding: 12px 28px; border-radius: 6px;
      background: #2ecc71; color: white; border: none; cursor: pointer;
  }}
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
  const TRIALS  = {trials_json};
  const FIXATION_MS  = {fixation_ms};
  const WORDS_MS     = {words_ms};
  const PROBE_MS     = {probe_timeout_ms};
  const ITI_MIN_MS   = {iti_min_ms};
  const ITI_MAX_MS   = {iti_max_ms};
  const PUT_URL      = {json.dumps(put_url)};

  const stage = document.getElementById('stage');
  const msg   = document.getElementById('msg');
  const prog  = document.getElementById('prog');
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
        if (e.key === 'ArrowUp')   r = 'up';
        if (e.key === 'ArrowDown') r = 'down';
        if (r === null) return;
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
    const meanRT = valid.length
      ? valid.reduce((s, r) => s + r.rt_ms, 0) / valid.length
      : null;
    const acc = results.length
      ? results.filter(r => r.correct).length / results.length
      : 0;
    // Attentional bias index: mean RT(incongruent) - mean RT(congruent)
    // Positive = vigilance toward threat
    const cong   = valid.filter(r =>  r.is_congruent);
    const incong = valid.filter(r => !r.is_congruent);
    const meanCong   = cong.length   ? cong.reduce((s,r)=>s+r.rt_ms,0)/cong.length   : null;
    const meanIncong = incong.length ? incong.reduce((s,r)=>s+r.rt_ms,0)/incong.length : null;
    const bias = (meanCong !== null && meanIncong !== null)
      ? Math.round((meanIncong - meanCong) * 100) / 100
      : null;
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
    const results = [];
    for (let i = 0; i < TRIALS.length; i++) {{
      const r = await runTrial(TRIALS[i], i + 1, TRIALS.length);
      results.push(r);
    }}
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
      : '<h2>⚠️ Could not save results</h2><p>Please notify your therapist — the task ran but the upload failed.</p>';
    stage.appendChild(done);
  }}

  startBtn.addEventListener('click', () => run().catch(err => {{
    msg.innerHTML = '<h3>Error</h3><pre>' + (err && err.message || err) + '</pre>';
  }}));
  // Keep keystrokes focused on the stage so arrow keys work
  document.body.addEventListener('click', () => stage.focus());
}})();
</script>
</body></html>
"""
