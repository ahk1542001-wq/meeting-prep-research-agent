#!/usr/bin/env python3
"""A one-page web UI for the Meeting Prep Research Agent.

    python ui.py            # then open http://127.0.0.1:8090

Standard library only. The page uses a small inline script for the
guided step flow; with scripts off, every step is shown stacked and
the form still works. Binds to localhost only.

Design — "Archival Ink" (a field-dossier theme):
The product's world is an analyst's dossier, so the page behaves
like being walked through a briefing, not filling in a spreadsheet.
The context is collected as a guided sequence — one W at a time,
each step a single question with an example — because the 5W
structure is the product's idea and the interface should teach it.
Your side of the meeting is the final step, with a live summary of
what was given. The brief reads as a document: a dossier strip of
the context used, a lead snapshot, then sections, with the
questions set as numbered items and Watch out alone in signal red.
Colour carries information only; teal is structure and action.
"""

import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402  (the CLI pipeline: searches + brief builder)

PORT = int(os.environ.get("MEETING_PREP_UI_PORT", "8090"))

CSS = """
* { box-sizing: border-box; }
body {
  margin: 0; background: #F7F8F6; color: #1C2B33;
  font-family: "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 15px; line-height: 1.45;
}
header.top { max-width: 880px; margin: 0 auto; padding: 34px 24px 4px; }
header.top h1 { font-size: 27px; margin: 0 0 4px; font-weight: 650; }
header.top p { margin: 0; color: #5A6B70; max-width: 60ch; }
main { max-width: 880px; margin: 0 auto; padding: 10px 24px 48px; }

/* --- guided form --- */
.subject-block { margin-top: 18px; }
.q { display: block; font-size: 17px; font-weight: 650; margin: 0 0 8px; }
.subject-input {
  width: 100%; font-size: 19px; font-weight: 600; padding: 13px 14px;
  border: 1px solid #B9C2BB; border-radius: 5px; background: #FFFFFF;
  color: #1C2B33;
}
.alt { display: block; margin-top: 14px; font-size: 13.5px; color: #5A6B70; }
.alt input {
  width: 100%; margin-top: 5px; padding: 9px 11px; font: inherit;
  font-size: 14px; border: 1px solid #B9C2BB; border-radius: 5px;
  background: #FFFFFF; color: #1C2B33;
}
input:focus, textarea:focus {
  outline: 2px solid #205E63; outline-offset: 0; border-color: #205E63;
}
.progress {
  display: flex; gap: 6px; margin: 30px 0 4px; padding: 0; list-style: none;
}
.progress li {
  flex: 1; text-align: center; font-size: 12.5px; color: #8A979B;
  padding-top: 9px; border-top: 3px solid #D9DDD8;
}
.progress li.done { color: #205E63; border-top-color: #205E63; }
.progress li.now { color: #1C2B33; font-weight: 700; border-top-color: #1C2B33; }
.step {
  background: #FFFFFF; border: 1px solid #D9DDD8; border-radius: 6px;
  padding: 26px 30px 24px; margin-top: 16px;
}
.w-display {
  font-family: Georgia, "Times New Roman", serif; font-style: italic;
  font-size: 34px; color: #205E63; line-height: 1.1; margin: 0 0 6px;
}
.step .q { font-size: 16.5px; }
.step input[type="text"], .step textarea {
  width: 100%; padding: 10px 12px; font: inherit; font-size: 15px;
  border: 1px solid #B9C2BB; border-radius: 5px; background: #FFFFFF;
  color: #1C2B33;
}
.step label.f { display: block; font-size: 13.5px; font-weight: 600;
  margin: 14px 0 5px; }
.step label.f:first-of-type { margin-top: 4px; }
.example { font-size: 13px; color: #5A6B70; margin: 8px 0 0; }
.step-nav { margin-top: 22px; display: flex; gap: 10px; align-items: center; }
button.next, button.run {
  font: inherit; font-size: 15px; font-weight: 650; color: #FFFFFF;
  background: #205E63; border: none; border-radius: 5px; cursor: pointer;
  height: 44px; padding: 0 22px; line-height: 1.2;
}
button.next:hover, button.run:hover { background: #18494D; }
button.back, button.skip {
  font: inherit; font-size: 14px; color: #40525A; background: none;
  border: none; cursor: pointer; padding: 8px 6px;
}
button.run { width: 100%; margin-top: 20px; }
.summary { margin-top: 18px; display: none; }
html.js .summary { display: block; }
.summary .pill {
  display: inline-block; background: #EDF3F1; color: #205E63;
  border-radius: 20px; padding: 4px 12px; font-size: 13px;
  margin: 0 6px 6px 0;
}
.summary .pill b { font-weight: 700; }
.summary .none { font-size: 13.5px; color: #5A6B70; }
.error {
  margin-top: 16px; padding: 10px 12px; border-left: 3px solid #B3352B;
  background: #FDF1F0; font-size: 14px;
}
.js-only { display: none; }
html.js .js-only { display: block; }
html.js .step { display: none; }
html.js .step.active { display: block; }
html.js .no-js-only { display: none; }

/* --- chat intake --- */
.modes { display: flex; gap: 8px; margin-top: 18px; }
.modes button {
  font: inherit; font-size: 14px; font-weight: 650; cursor: pointer;
  padding: 8px 16px; border-radius: 999px; border: 1px solid #205E63;
  background: #FFFFFF; color: #205E63;
}
.modes button.on { background: #205E63; color: #FFFFFF; }
.chat-panel {
  margin-top: 14px; background: #FFFFFF; border: 1px solid #D9DDD8;
  border-radius: 6px; padding: 18px 20px;
}
.chat-log { display: flex; flex-direction: column; gap: 10px; }
.bubble {
  max-width: 85%; padding: 10px 14px; border-radius: 12px;
  font-size: 14.5px; line-height: 1.5; white-space: pre-wrap;
}
.bubble.agent {
  background: #EDF3F1; color: #1C2B33; align-self: flex-start;
  border-bottom-left-radius: 4px;
}
.bubble.user {
  background: #205E63; color: #FFFFFF; align-self: flex-end;
  border-bottom-right-radius: 4px;
}
.bubble.sys {
  background: #FDF1F0; color: #7A241E; align-self: stretch;
  max-width: 100%;
}
.chat-row { display: flex; gap: 8px; margin-top: 14px; }
.chat-row input {
  flex: 1; padding: 11px 12px; font: inherit; font-size: 14.5px;
  border: 1px solid #B9C2BB; border-radius: 5px; background: #FFFFFF;
  color: #1C2B33;
}
.chat-row button {
  font: inherit; font-weight: 650; cursor: pointer; padding: 11px 20px;
  border: none; border-radius: 5px; background: #205E63;
  color: #FFFFFF;
}
.chat-row button:disabled { opacity: .55; cursor: default; }
#chat-summary { margin-top: 16px; }
button.chat-run {
  width: 100%; margin-top: 14px; background: #205E63; color: #FFFFFF;
  border: none; border-radius: 5px; padding: 13px; font: inherit;
  font-weight: 650; font-size: 16px; cursor: pointer;
}
button.chat-run:hover { background: #18494D; }

/* --- brief document --- */
.dossier {
  display: flex; flex-wrap: wrap; gap: 10px 26px; margin: 20px 0 4px;
  padding: 16px 20px; background: #FFFFFF; border: 1px solid #D9DDD8;
  border-radius: 6px;
}
.dossier .fact .k { display: block; font-size: 12px; color: #205E63;
  font-weight: 700; }
.dossier .fact .v { font-family: Georgia, "Times New Roman", serif;
  font-size: 15px; }
.sheet {
  background: #FFFFFF; border: 1px solid #D9DDD8; border-radius: 6px;
  padding: 30px 38px 36px; margin-top: 16px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 15.5px; line-height: 1.6; color: #1C2B33;
}
.sheet h1 { font-size: 24px; line-height: 1.25; margin: 0 0 4px; }
.sheet .researched { color: #5A6B70; font-size: 13.5px; margin: 0 0 6px;
  font-family: "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif; }
.sheet section { margin-top: 24px; padding-top: 18px;
  border-top: 1px solid #D9DDD8; }
.sheet h2 {
  font-size: 15.5px; margin: 0 0 8px;
  font-family: "Avenir Next", "Segoe UI", Helvetica, Arial, sans-serif;
  font-weight: 700; color: #205E63;
}
.sheet section.watchout h2 { color: #B3352B; }
.sheet section.watchout {
  border-top: 2px solid #B3352B; background: #FDF6F5;
  margin-left: -14px; margin-right: -14px; padding-left: 14px;
  padding-right: 14px; border-radius: 0 0 4px 4px;
}
.sheet p { margin: 8px 0; max-width: 72ch; }
.sheet p.lead { font-size: 17.5px; line-height: 1.55; }
.sheet h3 { font-size: 15px; margin: 16px 0 6px; }
.sheet ul { margin: 8px 0; padding-left: 20px; }
.sheet li { margin: 4px 0; max-width: 70ch; }
.sheet a { color: #205E63; }
.sheet section.sources { font-size: 13.5px; color: #40525A; }
.sheet ol.questions { list-style: none; padding: 0; margin: 6px 0;
  counter-reset: q; }
.sheet ol.questions li {
  counter-increment: q; position: relative; padding: 12px 0 12px 52px;
  border-top: 1px solid #EDF0EC; max-width: 70ch; margin: 0;
}
.sheet ol.questions li:first-child { border-top: none; }
.sheet ol.questions li::before {
  content: counter(q); position: absolute; left: 2px; top: 8px;
  font-size: 26px; color: #205E63; font-style: italic; line-height: 1;
}
.saved { margin-top: 16px; font-size: 13.5px; color: #5A6B70; }
a.again {
  display: inline-block; margin-top: 10px; font-weight: 650;
  color: #205E63;
}
"""

SCRIPT = """
document.documentElement.classList.add('js');
(function () {
  var steps = Array.prototype.slice.call(
    document.querySelectorAll('.step'));
  var dots = Array.prototype.slice.call(
    document.querySelectorAll('.progress li'));
  var current = 0;
  function show(n) {
    current = Math.max(0, Math.min(n, steps.length - 1));
    steps.forEach(function (s, i) {
      s.classList.toggle('active', i === current);
    });
    dots.forEach(function (d, i) {
      d.classList.toggle('now', i === current);
      d.classList.toggle('done', i < current);
    });
    var field = steps[current].querySelector('input, textarea');
    if (field) { field.focus(); }
    refreshSummary();
  }
  function refreshSummary() {
    var box = document.getElementById('summary');
    if (!box) { return; }
    var names = ['subject', 'relationship', 'agenda', 'when', 'where',
                 'why', 'purpose', 'offering', 'goal', 'fallback',
                 'prior'];
    var labels = {subject: 'Subject', relationship: 'Who',
      agenda: 'What', when: 'When', where: 'Where', why: 'Why',
      purpose: 'Type', offering: 'Presenting', goal: 'Outcome',
      prior: 'Prior contact'};
    var pills = [];
    names.forEach(function (n) {
      var el = document.querySelector('[name="' + n + '"]');
      if (el && el.value.trim()) {
        var v = el.value.trim();
        if (v.length > 42) { v = v.slice(0, 42) + '…'; }
        pills.push('<span class="pill"><b>' + labels[n] + ':</b> ' +
          v.replace(/</g, '&lt;') + '</span>');
      }
    });
    box.innerHTML = pills.length ? pills.join('') :
      '<span class="none">Nothing yet — every field is optional, ' +
      'and the brief is sharper with each one you add.</span>';
  }
  document.querySelectorAll('[data-go]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      show(current + parseInt(btn.getAttribute('data-go'), 10));
    });
  });
  document.querySelectorAll('input, textarea').forEach(function (el) {
    el.addEventListener('input', refreshSummary);
  });
  show(0);
})();

/* --- chat intake: the agent asks, the visitor just answers --- */
(function () {
  var panel = document.getElementById('chat-panel');
  if (!panel) { return; }
  var form = document.getElementById('intake-form');
  var log = document.getElementById('chat-log');
  var input = document.getElementById('chat-input');
  var send = document.getElementById('chat-send');
  var runBtn = document.getElementById('chat-run');
  var summary = document.getElementById('chat-summary');
  var modeChat = document.getElementById('mode-chat');
  var modeForm = document.getElementById('mode-form');
  var state = { fields: {}, skipped: [] };
  var labels = {subject: 'Subject', relationship: 'Who',
    agenda: 'What', when: 'When', where: 'Where', why: 'Why',
    purpose: 'Type', offering: 'Presenting', goal: 'Outcome',
    fallback: 'Fallback', prior: 'Prior contact'};
  var order = ['subject', 'relationship', 'agenda', 'when', 'where',
               'why', 'purpose', 'offering', 'goal', 'fallback',
               'prior'];
  function bubble(who, text) {
    var d = document.createElement('div');
    d.className = 'bubble ' + who;
    d.textContent = text;
    log.appendChild(d);
  }
  function renderSummary() {
    var pills = [];
    order.forEach(function (n) {
      var v = (state.fields[n] || '').trim();
      if (v) {
        if (v.length > 42) { v = v.slice(0, 42) + '…'; }
        pills.push('<span class="pill"><b>' + labels[n] + ':</b> ' +
          v.replace(/</g, '&lt;') + '</span>');
      }
    });
    summary.innerHTML = pills.length ? pills.join('') :
      '<span class="none">Nothing collected yet.</span>';
    runBtn.style.display =
      (state.fields.subject || '').trim() ? 'block' : 'none';
  }
  function setMode(chat) {
    panel.style.display = chat ? 'block' : 'none';
    form.style.display = chat ? 'none' : 'block';
    modeChat.classList.toggle('on', chat);
    modeForm.classList.toggle('on', !chat);
    if (!chat) {
      order.forEach(function (n) {
        var el = form.querySelector('[name="' + n + '"]');
        if (el && state.fields[n]) {
          el.value = state.fields[n];
          el.dispatchEvent(new Event('input'));
        }
      });
    }
  }
  modeChat.addEventListener('click', function () { setMode(true); });
  modeForm.addEventListener('click', function () { setMode(false); });
  function sendChat() {
    var text = input.value.trim();
    if (!text) { return; }
    bubble('user', text);
    input.value = '';
    send.disabled = true;
    fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({fields: state.fields,
                            skipped: state.skipped, message: text})
    }).then(function (r) {
      return r.json().then(function (data) {
        return {ok: r.ok, data: data};
      });
    }).then(function (res) {
      send.disabled = false;
      if (!res.ok || res.data.error) {
        bubble('sys', (res.data && res.data.error) ||
          'The chat is unavailable right now — the form still works.');
        return;
      }
      state.fields = res.data.fields || {};
      state.skipped = res.data.skipped || [];
      if (res.data.reply) { bubble('agent', res.data.reply); }
      renderSummary();
      input.focus();
    }).catch(function () {
      send.disabled = false;
      bubble('sys',
        'The chat could not be reached — the form still works.');
    });
  }
  send.addEventListener('click', sendChat);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); sendChat(); }
  });
  runBtn.addEventListener('click', function () {
    var f = document.createElement('form');
    f.method = 'post';
    f.action = '/run';
    order.concat(['context']).forEach(function (n) {
      var i = document.createElement('input');
      i.type = 'hidden';
      i.name = n;
      i.value = state.fields[n] || '';
      f.appendChild(i);
    });
    document.body.appendChild(f);
    f.submit();
  });
  renderSummary();
  setMode(true);
})();
"""

# (step word, question, [(field, label, placeholder)], example)
STEPS = [
    ("Who", "What are they to you?",
     [("relationship", "", "a prospective client")],
     "a prospective client · a partner · an employer · a candidate"),
    ("What", "What is this meeting for?",
     [("agenda", "", "a first demo")],
     "a first demo · a quarterly review · a job conversation"),
    ("When", "When is it?",
     [("when", "", "2026-11-25")],
     "A date within a week makes the brief weight the freshest "
     "news more heavily."),
    ("Where", "Where does it happen?",
     [("where", "", "online (video call)")],
     "online (video call) · their office · a coffee shop in Bangkok"),
    ("Why", "Why is it happening?",
     [("why", "", "they asked to see it")],
     "they asked to see it · I requested it after their launch · "
     "a referral from a former colleague"),
    ("Your side", "What are you bringing, and what do you want?",
     [("purpose", "Meeting type", "sales"),
      ("offering", "What you will present", "our onboarding service"),
      ("goal", "The outcome you want", "a paid pilot"),
      ("fallback", "Fallback outcome", "a follow-up booked"),
      ("prior", "Previous contact (your words)", "")],
     "Previous contact is printed in the brief exactly as written "
     "— leave it blank for a first meeting."),
]


def esc(text):
    return html.escape(text or "", quote=True)


CHAT_GREETING = (
    "Tell me about the meeting in your own words — one thing at a "
    "time is fine, and you can say skip for anything. First: "
    + agent.chat_question("subject"))


def form_html(values, error=""):
    parts = []
    if error:
        parts.append(f'<div class="error">{esc(error)}</div>')
    try:
        chat_ok = agent.load_llm_config() is not None
    except Exception:
        chat_ok = False
    if chat_ok:
        parts.append(
            '<div class="modes js-only">'
            '<button type="button" id="mode-chat" class="on">'
            "Chat with the agent</button>"
            '<button type="button" id="mode-form">'
            "Fill the form myself</button></div>")
        parts.append('<div class="chat-panel js-only" id="chat-panel">')
        parts.append('<div class="chat-log" id="chat-log">')
        parts.append(
            f'<div class="bubble agent">{esc(CHAT_GREETING)}</div>')
        parts.append("</div>")
        parts.append('<div class="summary" id="chat-summary"></div>')
        parts.append(
            '<div class="chat-row">'
            '<input type="text" id="chat-input" autocomplete="off" '
            'placeholder="Type your answer… (or: skip)">'
            '<button type="button" id="chat-send">Send</button>'
            "</div>")
        parts.append(
            '<button type="button" class="chat-run" id="chat-run" '
            'style="display:none">Prepare the brief</button>')
        parts.append("</div>")
    parts.append('<form method="post" action="/run" id="intake-form">')
    parts.append('<div class="subject-block">')
    parts.append(
        '<label class="q" for="subject">Who or what are you '
        "preparing for?</label>"
    )
    parts.append(
        f'<input class="subject-input" type="text" id="subject" '
        f'name="subject" value="{esc(values.get("subject", ""))}" '
        f'placeholder="Tavily, Satya Nadella, Acme Corp">'
    )
    parts.append(
        '<label class="alt" for="context">Or describe the meeting '
        "in one line (the guided steps below are sharper)"
        f'<input type="text" id="context" name="context" '
        f'value="{esc(values.get("context", ""))}" '
        f'placeholder="partnership discussion"></label>'
    )
    parts.append("</div>")
    parts.append('<ol class="progress">')
    for word, _q, _f, _e in STEPS:
        parts.append(f"<li>{esc(word)}</li>")
    parts.append("</ol>")
    total = len(STEPS)
    for idx, (word, question, fields, example) in enumerate(STEPS):
        parts.append(f'<section class="step" data-word="{esc(word)}">')
        parts.append(f'<div class="w-display">{esc(word)}</div>')
        parts.append(f'<div class="q">{esc(question)}</div>')
        for name, label, placeholder in fields:
            if label:
                parts.append(
                    f'<label class="f" for="{name}">{esc(label)}</label>')
            if name == "prior":
                parts.append(
                    f'<textarea id="{name}" name="{name}" rows="3" '
                    f'placeholder="Met in October; they said '
                    f'onboarding takes three weeks.">'
                    f'{esc(values.get(name, ""))}</textarea>'
                )
            else:
                parts.append(
                    f'<input type="text" id="{name}" name="{name}" '
                    f'value="{esc(values.get(name, ""))}" '
                    f'placeholder="{esc(placeholder)}">'
                )
        parts.append(f'<p class="example">{esc(example)}</p>')
        parts.append('<div class="step-nav js-only">')
        if idx > 0:
            parts.append(
                '<button type="button" class="back" data-go="-1">'
                "Back</button>"
            )
        if idx < total - 1:
            parts.append(
                '<button type="button" class="next" data-go="1">'
                "Continue</button>"
            )
            parts.append(
                '<button type="button" class="skip" data-go="1">'
                "Skip this one</button>"
            )
        parts.append("</div>")
        if idx == total - 1:
            parts.append('<div class="summary" id="summary"></div>')
            parts.append(
                '<button class="run" type="submit">'
                "Prepare the brief</button>"
            )
        parts.append("</section>")
    parts.append("</form>")
    return "\n".join(parts)


def page(body, title="Meeting Prep — Research Agent"):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <h1>Meeting Prep</h1>
  <p>Research a person or company before a meeting. The brief is
  built from what the search finds and the context you give it —
  nothing is invented.</p>
</header>
<main>
{body}
</main>
<script>{SCRIPT}</script>
</body>
</html>"""


def inline_md(text):
    """Render the inline subset our briefs use: links, bold, italic."""
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w/])_([^_]+)_(?![\w])", r"<em>\1</em>", text)
    return text


def render_lines(lines, section_slug):
    """Render one section's body lines to HTML."""
    out = []
    list_tag = None
    first_para = True

    def close_list():
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("### "):
            close_list()
            out.append(f"<h3>{inline_md(line[4:].strip())}</h3>")
        elif line.startswith("# ") or line.startswith("## "):
            close_list()
            out.append(
                f"<h3>{inline_md(line.lstrip('# ').strip())}</h3>")
        elif re.match(r"^- ", line):
            if list_tag != "ul":
                close_list()
                out.append("<ul>")
                list_tag = "ul"
            out.append(f"<li>{inline_md(line[2:].strip())}</li>")
        elif re.match(r"^\d+\. ", line):
            if list_tag != "ol":
                close_list()
                cls = ' class="questions"' if section_slug == \
                    "questions" else ""
                out.append(f"<ol{cls}>")
                list_tag = "ol"
            item = re.sub(r"^\d+\. ", "", line).strip()
            out.append(f"<li>{inline_md(item)}</li>")
        elif not line.strip():
            close_list()
        else:
            close_list()
            cls = ""
            if section_slug in ("snapshot", "execsummary") \
                    and first_para:
                cls = ' class="lead"'
                first_para = False
            out.append(f"<p{cls}>{inline_md(line.strip())}</p>")
    close_list()
    return "\n".join(out)


SECTION_SLUGS = {
    "previous contact": "previous",
    "executive summary": "execsummary",
    "snapshot": "snapshot",
    "recent developments": "news",
    "competitors found in search": "competitors",
    "watch out": "watchout",
    "key people": "people",
    "source highlights": "sources",
    "all sources": "sources",
    "questions to ask": "questions",
}


def render_brief(md, dossier):
    """Render the brief markdown as a designed document."""
    title = ""
    researched = ""
    sections = []
    current = None
    for raw in md.splitlines():
        if raw.startswith("# ") and current is None and not title:
            title = raw[2:].strip()
        elif raw.startswith("## "):
            current = (raw[3:].strip(), [])
            sections.append(current)
        elif current is not None:
            current[1].append(raw)
        elif raw.strip().startswith("_Researched on"):
            researched = raw.strip().strip("_")
    parts = []
    if dossier:
        facts = "".join(
            f'<div class="fact"><span class="k">{esc(k)}</span>'
            f'<span class="v">{esc(v)}</span></div>'
            for k, v in dossier
        )
        parts.append(f'<div class="dossier">{facts}</div>')
    parts.append('<article class="sheet">')
    parts.append(f"<h1>{inline_md(title)}</h1>")
    if researched:
        parts.append(f'<p class="researched">{esc(researched)}</p>')
    for name, body in sections:
        key = name.lower()
        slug = next(
            (v for k, v in SECTION_SLUGS.items() if key.startswith(k)),
            "section",
        )
        cls = slug
        if slug == "watchout":
            cls = "watchout"
        elif slug == "sources":
            cls = "sources"
        parts.append(f'<section class="{cls}">')
        parts.append(f"<h2>{inline_md(name)}</h2>")
        parts.append(render_lines(body, slug))
        parts.append("</section>")
    parts.append("</article>")
    return "\n".join(parts)


def run_pipeline(values):
    """Mirror agent.main(): same searches, same brief builder."""
    api_key = agent.load_api_key()
    if not api_key:
        return "", "", ("No Tavily API key found. Add TAVILY_API_KEY "
                        "to a .env file next to ui.py, or export it, "
                        "then run again.")
    subject = values["subject"]
    meeting_date = agent.parse_meeting_when(values.get("when", ""))
    days_until = (
        (meeting_date - datetime.now(timezone.utc).date()).days
        if meeting_date else None
    )
    news_window = (
        "week" if days_until is not None and 0 <= days_until <= 7
        else "month"
    )
    structured = {
        "relationship": values.get("relationship", ""),
        "agenda": values.get("agenda", ""),
        "when": values.get("when", ""),
        "where": values.get("where", ""),
        "why": values.get("why", ""),
        "days_until": days_until,
        "news_window": news_window,
        "purpose": values.get("purpose", ""),
        "offering": values.get("offering", ""),
        "goal": values.get("goal", ""),
        "fallback": values.get("fallback", ""),
        "prior": values.get("prior", ""),
    }
    brief, _cfg = agent.research_brief(
        api_key, subject, values.get("context", ""), structured,
        quiet=True)
    out_name = f"brief-{agent.slugify(subject)}.md"
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), out_name)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(brief)
    when_label = values.get("when", "")
    if days_until is not None and days_until >= 0:
        suffix = {0: "today", 1: "tomorrow"}.get(
            days_until, f"in {days_until} days")
        when_label = f"{when_label} ({suffix})"
    dossier = [
        ("Their role", values.get("relationship", "")),
        ("What", values.get("agenda", "")),
        ("When", when_label),
        ("Where", values.get("where", "")),
        ("Why", values.get("why", "")),
        ("Meeting type", values.get("purpose", "")),
        ("Presenting", values.get("offering", "")),
        ("Outcome wanted", values.get("goal", "")),
        ("Fallback outcome", values.get("fallback", "")),
    ]
    dossier = [(k, v) for k, v in dossier if (v or "").strip()]
    return render_brief(brief, dossier), out_name, ""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        self._send(page(form_html({})))

    def do_POST(self):
        if self.path == "/chat":
            self._chat()
            return
        if self.path != "/run":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace")
        form = parse_qs(body)
        values = {k: (v[0].strip() if v else "")
                  for k, v in form.items()}
        if not values.get("subject"):
            self._send(page(form_html(
                values,
                "Add a person or company name to prepare a brief.")))
            return
        try:
            brief_html, saved, error = run_pipeline(values)
        except Exception as exc:  # keep the page alive, say what broke
            brief_html, saved = "", ""
            error = f"The research run failed: {exc}"
        if error:
            self._send(page(form_html(values, error)))
            return
        result = (
            brief_html
            + f'<div class="saved">Saved as {esc(saved)} — the same '
            "file the command-line agent writes.</div>"
            + '<a class="again" href="/">Prepare another brief</a>'
        )
        self._send(page(result))

    def _chat(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(
                self.rfile.read(length).decode("utf-8", "replace")
                or "{}")
        except ValueError:
            self._send_json(
                400, {"error": "That message could not be read."})
            return
        if agent.load_llm_config() is None:
            self._send_json(503, {
                "error": "Chat needs an LLM key on the server "
                         "(NEBIUS_API_KEY or META_MODEL_API_KEY). "
                         "The form still works."})
            return
        try:
            result = agent.chat_turn(
                payload.get("fields") or {},
                payload.get("skipped") or [],
                payload.get("message") or "")
        except Exception as exc:  # keep the page alive, say what broke
            self._send_json(
                502, {"error": f"The chat model call failed: {exc}"})
            return
        if result is None:
            self._send_json(503, {
                "error": "Chat is unavailable right now — "
                         "the form still works."})
            return
        self._send_json(200, result)

    def _send_json(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type",
                         "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send(self, content):
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Meeting Prep UI: http://127.0.0.1:{PORT} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
