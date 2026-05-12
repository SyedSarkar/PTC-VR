"""
components/questionnaires/wsa.py
=================================
Word Sentence Association (WSA) Paradigm.

Same pattern as dot_probe.py — runs client-side in an HTML/JS iframe so
the 300 ms / 500 ms stimulus windows are accurate, and uploads results
directly to Firebase via REST.

Protocol per trial:
    1. Fixation "+"     — WSA_FIXATION_MS
    2. Word flashes     — WSA_WORD_MS
    3. Sentence shown   — until participant presses Space
    4. Question         — "Was the word associated with the sentence?"
                          Y = yes, N = no, up to WSA_DECISION_TIMEOUT_MS

Stored at participants/{code}/{base_path}:
    {
        "completed_timestamp": ...,
        "num_trials": N,
        "accuracy": 0.87,
        "mean_decision_rt_ms": ...,
        "mean_reading_rt_ms": ...,
        "trials": [ {word, sentence, expected, response, correct, rt_*}, ... ]
    }
"""

from __future__ import annotations
import json
import random

import streamlit as st
import streamlit.components.v1 as components

import config
from utils.helpers import load_lines  # noqa: F401  (kept for symmetry)
from utils.data_logger import get_logger


def _is_complete(code: str, base_path: str) -> bool:
    logger = get_logger()
    node = logger.get(code, base_path) or {}
    return isinstance(node, dict) and bool(node.get("completed_timestamp"))


def _load_stimuli() -> list[dict]:
    """Load WSA items from the JSON data file. Returns [] if the file is
    missing — the wrapper will display an error in that case."""
    try:
        with open(config.WSA_STIMULI_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = (item.get("word") or "").strip()
        sentence = (item.get("sentence") or "").strip()
        associated = item.get("associated")
        if not word or not sentence or not isinstance(associated, bool):
            continue
        out.append({
            "word": word,
            "sentence": sentence,
            "associated": associated,
            "category": item.get("category") or "",
        })
    return out


def _build_trial_list() -> list[dict]:
    pool = _load_stimuli()
    if not pool:
        return []
    random.shuffle(pool)
    return pool[:max(0, config.WSA_NUM_TRIALS)]


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


def render(code: str, base_path: str, on_complete=None):
    if not code:
        st.error("No participant code in session.")
        return

    if _is_complete(code, base_path):
        st.success("✅ Word-Sentence Association task already completed.")
        if on_complete:
            if st.button("Continue ➜", type="primary",
                         key=f"{base_path.replace('/', '_')}_continue"):
                on_complete()
        return

    st.markdown("## Word Sentence Association Task")
    st.markdown(
        "<div class='form-text'>"
        "<b>Instructions:</b><br>"
        "• A fixation cross <code>+</code> will appear briefly.<br>"
        "• A word will flash for a short moment — read it carefully.<br>"
        "• A sentence will then appear. Read it at your own pace, then "
        "press <b>Space</b> to continue.<br>"
        "• A question will ask if the word was associated with the sentence.<br>"
        "&nbsp;&nbsp;Press <b>Y</b> for Yes, <b>N</b> for No.<br>"
        "• Respond as quickly and accurately as you can.<br>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "💡 Click inside the task area below before pressing keys, so the "
        "browser focuses the experiment."
    )
    st.divider()

    trials = _build_trial_list()
    if not trials:
        st.error(
            f"No WSA stimuli found at `{config.WSA_STIMULI_PATH}`. "
            "Add valid items before running this task."
        )
        return

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
        fixation_ms=config.WSA_FIXATION_MS,
        word_ms=config.WSA_WORD_MS,
        sentence_timeout_ms=config.WSA_SENTENCE_TIMEOUT_MS,
        decision_timeout_ms=config.WSA_DECISION_TIMEOUT_MS,
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
def _build_html(trials, put_url, fixation_ms, word_ms,
                sentence_timeout_ms, decision_timeout_ms) -> str:
    trials_json = json.dumps(trials)
    return f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html, body {{ height: 100%; margin: 0; padding: 0; }}
  body {{
      display: flex; align-items: center; justify-content: center;
      background: #f6f9fc; font-family: 'Times New Roman', Times, serif;
      color: #010d1a;
  }}
  .stage {{
      width: 100%; height: 500px; position: relative;
      display: flex; align-items: center; justify-content: center;
      border: 2px solid #c9d6e3; border-radius: 8px; background: #ffffff;
      padding: 20px; box-sizing: border-box;
  }}
  .fix      {{ font-size: 56px; font-weight: bold; }}
  .word     {{ font-size: 40px; font-weight: bold; }}
  .sentence {{ font-size: 26px; line-height: 1.4; max-width: 80%;
              text-align: center; }}
  .hint     {{ position: absolute; bottom: 16px; left: 0; right: 0;
              text-align: center; font-size: 14px; color: #888; }}
  .question {{ font-size: 24px; text-align: center; }}
  .question b {{ color: #2c3e50; }}
  .msg      {{ font-size: 22px; text-align: center; padding: 0 30px; }}
  .progress {{ position: absolute; bottom: 10px; right: 14px;
              font-size: 13px; color: #888; }}
  button.start {{
      font-size: 20px; padding: 12px 28px; border-radius: 6px;
      background: #2ecc71; color: white; border: none; cursor: pointer;
  }}
</style></head>
<body tabindex="0">
  <div class="stage" id="stage" tabindex="0">
    <div class="msg" id="msg">
      <p>Click the green button to start.<br>
      You'll need your <b>Space</b>, <b>Y</b> and <b>N</b> keys.</p>
      <button class="start" id="start-btn">▶ Start Task</button>
    </div>
    <div class="progress" id="prog"></div>
  </div>
<script>
(function() {{
  const TRIALS  = {trials_json};
  const FIXATION_MS    = {fixation_ms};
  const WORD_MS        = {word_ms};
  const SENT_TIMEOUT   = {sentence_timeout_ms};
  const DECIDE_TIMEOUT = {decision_timeout_ms};
  const PUT_URL        = {json.dumps(put_url)};

  const stage = document.getElementById('stage');
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const now = () => performance.now();
  const startBtn = document.getElementById('start-btn');

  function clearStage() {{
    stage.innerHTML = '<div class="progress" id="prog"></div>';
  }}
  function setProgress(i, n) {{
    const p = document.getElementById('prog');
    if (p) p.textContent = `Trial ${{i}} / ${{n}}`;
  }}

  function showFixation() {{
    clearStage();
    const f = document.createElement('div'); f.className = 'fix'; f.textContent = '+';
    stage.appendChild(f);
    return wait(FIXATION_MS);
  }}

  function showWord(w) {{
    clearStage();
    const el = document.createElement('div'); el.className = 'word'; el.textContent = w;
    stage.appendChild(el);
    return wait(WORD_MS);
  }}

  function showSentenceAndWaitSpace(sentence) {{
    clearStage();
    const el = document.createElement('div'); el.className = 'sentence'; el.textContent = sentence;
    stage.appendChild(el);
    const hint = document.createElement('div'); hint.className = 'hint';
    hint.textContent = 'Press SPACE when you have finished reading.';
    stage.appendChild(hint);
    const start = now();
    return new Promise(resolve => {{
      let resolved = false;
      const onKey = (e) => {{
        if (resolved || e.code !== 'Space') return;
        resolved = true;
        e.preventDefault();
        window.removeEventListener('keydown', onKey);
        clearTimeout(to);
        resolve({{ rt_ms: Math.round(now() - start), timed_out: false }});
      }};
      const to = setTimeout(() => {{
        if (resolved) return;
        resolved = true;
        window.removeEventListener('keydown', onKey);
        resolve({{ rt_ms: SENT_TIMEOUT, timed_out: true }});
      }}, SENT_TIMEOUT);
      window.addEventListener('keydown', onKey);
    }});
  }}

  function askQuestion() {{
    clearStage();
    const q = document.createElement('div');
    q.className = 'question';
    q.innerHTML =
      '<p>Was the word associated with the sentence?</p>' +
      '<p><b>Y</b> = Yes &nbsp;&nbsp; <b>N</b> = No</p>';
    stage.appendChild(q);
    const start = now();
    return new Promise(resolve => {{
      let resolved = false;
      const onKey = (e) => {{
        if (resolved) return;
        let r = null;
        if (e.key === 'y' || e.key === 'Y') r = 'yes';
        if (e.key === 'n' || e.key === 'N') r = 'no';
        if (r === null) return;
        resolved = true;
        window.removeEventListener('keydown', onKey);
        clearTimeout(to);
        resolve({{ response: r, rt_ms: Math.round(now() - start), timed_out: false }});
      }};
      const to = setTimeout(() => {{
        if (resolved) return;
        resolved = true;
        window.removeEventListener('keydown', onKey);
        resolve({{ response: 'timeout', rt_ms: DECIDE_TIMEOUT, timed_out: true }});
      }}, DECIDE_TIMEOUT);
      window.addEventListener('keydown', onKey);
    }});
  }}

  async function runTrial(t, i, n) {{
    setProgress(i, n);
    await showFixation();
    await showWord(t.word);
    const reading = await showSentenceAndWaitSpace(t.sentence);
    const decision = await askQuestion();
    const expected = t.associated ? 'yes' : 'no';
    const correct = decision.response === expected;
    return {{
      trial: i,
      word: t.word,
      sentence: t.sentence,
      category: t.category || '',
      expected: expected,
      response: decision.response,
      correct: correct,
      reading_rt_ms: reading.rt_ms,
      reading_timed_out: reading.timed_out,
      decision_rt_ms: decision.rt_ms,
      decision_timed_out: decision.timed_out,
      timestamp: new Date().toISOString(),
    }};
  }}

  function summarise(results) {{
    const valid = results.filter(r => r.response !== 'timeout');
    const acc = results.length
      ? results.filter(r => r.correct).length / results.length
      : 0;
    const meanDec = valid.length
      ? Math.round(valid.reduce((s, r) => s + r.decision_rt_ms, 0) / valid.length)
      : null;
    const meanRead = valid.length
      ? Math.round(valid.reduce((s, r) => s + r.reading_rt_ms, 0) / valid.length)
      : null;
    return {{
      num_trials: results.length,
      accuracy: Math.round(acc * 1000) / 1000,
      mean_decision_rt_ms: meanDec,
      mean_reading_rt_ms: meanRead,
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
    stage.innerHTML = '<div class="msg"><h3>Error</h3><pre>' +
      (err && err.message || err) + '</pre></div>';
  }}));
  document.body.addEventListener('click', () => stage.focus());
}})();
</script>
</body></html>
"""
