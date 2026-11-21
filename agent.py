#!/usr/bin/env python3
"""Meeting Prep Research Agent.

Give it a company or a person you are about to meet, and it researches them
on the live web with the Tavily API, then writes a one-page markdown
briefing you can read in two minutes before the meeting.

Usage:
    python agent.py "Acme Corp"
    python agent.py "Acme Corp" --relationship "a prospective client" \
        --agenda "a first demo" --when 2026-11-25 --where "online" \
        --why "they asked to see it" --purpose sales \
        --offering "our onboarding service" --goal "a paid pilot"
    python agent.py "Acme Corp" --context "partnership discussion"
    python agent.py "Jane Smith, CEO of Acme" --out jane.md

The questions at the end of the brief are driven by the meeting
context, organised as the 5W — Who (--relationship), What
(--agenda), When (--when), Where (--where), Why (--why) — plus your
side of it: --purpose / --offering / --goal. Free text is also
accepted via --context. A meeting date within a week narrows the
news search to the last week. With no context at all, the brief
asks for it instead of printing generic questions.

Requires a Tavily API key in the TAVILY_API_KEY environment variable
(or in a .env file next to this script). Get one at https://tavily.com

Optional: with NEBIUS_API_KEY or META_MODEL_API_KEY set, an LLM
drafts the executive summary and the questions from the search
results. Drafts are source-checked in code — every URL in a draft
must be one the search returned — and anything that fails a check,
or a run with no key at all, falls back to the deterministic brief.
"""

import argparse
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

TAVILY_URL = "https://api.tavily.com/search"


def load_api_key():
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("TAVILY_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def tavily_search(api_key, query, topic="general", time_range=None,
                  search_depth="basic", max_results=5):
    payload = {
        "query": query,
        "topic": topic,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": "advanced" if search_depth == "advanced" else "basic",
        "include_raw_content": False,
    }
    if time_range:
        payload["time_range"] = time_range
    # Transient truncation is real on some networks: a proxy can
    # hand back the headers and then cut the body (IncompleteRead).
    # Retry a few times; the last attempt also drops the advanced
    # answer, which changes the response and escapes a stuck variant.
    last_exc = None
    for attempt in range(4):
        if attempt == 3 and payload["include_answer"] == "advanced":
            payload = dict(payload, include_answer="basic")
        req = urllib.request.Request(
            TAVILY_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 429 (rate limit) and 5xx are transient: retry with
            # backoff, honouring Retry-After when sent. Other 4xx
            # are real answers (401 bad key, 403, 404): fail fast.
            if exc.code == 429 or 500 <= exc.code < 600:
                last_exc = exc
                wait = 1.5 * (attempt + 1)
                retry_after = None
                if exc.headers is not None:
                    retry_after = exc.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = min(float(retry_after), 30.0)
                    except (TypeError, ValueError):
                        pass
                time.sleep(wait)
                continue
            raise
        except (http.client.IncompleteRead, ConnectionError,
                urllib.error.URLError) as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise last_exc


WHEN_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
)


def parse_meeting_when(text):
    """Parse a meeting date the user typed, or return None.

    Deliberately strict: only the listed formats count. Anything
    else is shown in the brief verbatim but never guessed at, so
    the recency weighting below only ever acts on a date the user
    actually gave in a known shape."""
    from datetime import datetime as _dt

    text = (text or "").strip()
    if not text:
        return None
    for fmt in WHEN_FORMATS:
        try:
            return _dt.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "subject"


# ------------------------------------------------------------------
# Optional LLM layer
#
# When an API key is present in the environment, an LLM drafts the
# executive summary and the questions from the search results.
# Two routes only: Nebius Token Factory (NEBIUS_API_KEY) or the
# Meta Model API (META_MODEL_API_KEY). MEETING_PREP_LLM=off forces
# the layer off, and --no-llm does the same per run.
#
# The layer is optional by construction: no key, a failed call, or
# a draft that fails the source check below all fall back to the
# deterministic brief, unchanged. The guardrail is enforced in
# code, not just in the prompt: every URL in an LLM draft must be
# one of the URLs the search actually returned, or the draft is
# discarded.
# ------------------------------------------------------------------

LLM_PROVIDERS = {
    # provider: (chat completions URL, model env var, default model)
    "nebius": (
        "https://api.tokenfactory.nebius.com/v1/chat/completions",
        "NEBIUS_MODEL",
        "meta-models/muse-spark-open",
    ),
    "meta": (
        "https://api.meta.ai/v1/chat/completions",
        "META_MODEL",
        "muse-spark-1.3",
    ),
}

GUARDRAIL_SYSTEM = """You write parts of a meeting-prep brief from web search results.

Hard rules — follow them exactly:
1. Use ONLY facts that appear in the SOURCES provided by the user. Never use your own knowledge about the subject.
2. Never invent or guess names, numbers, dates, events, or relationships. If the sources do not say it, do not write it.
3. Cite every factual claim with the number of the source it came from, in square brackets, like [2]. Never write out a URL yourself — the numbers are turned into links afterwards.
4. If the sources are thin, write less rather than filling gaps.
5. Plain, direct language. No hype, no advice, no commentary about these rules."""


def load_llm_config():
    """Resolve the LLM route from the environment, or None."""
    if (os.environ.get("MEETING_PREP_LLM") or "").strip().lower() \
            == "off":
        return None
    for provider, key_var in (
            ("nebius", "NEBIUS_API_KEY"),
            ("meta", "META_MODEL_API_KEY")):
        key = (os.environ.get(key_var) or "").strip()
        if key:
            url, model_var, default_model = LLM_PROVIDERS[provider]
            return {
                "provider": provider,
                "url": url,
                "key": key,
                "model": (os.environ.get(model_var)
                          or default_model).strip(),
            }
    return None


def llm_chat(cfg, system, user, max_tokens=1100):
    """One chat completion; returns the reply text or raises."""
    payload = {
        "model": cfg["model"],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        cfg["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['key']}",
        },
        method="POST",
    )
    last_exc = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as exc:
            # 429/5xx are transient and worth the second attempt;
            # other 4xx are real answers — fail fast.
            if exc.code == 429 or 500 <= exc.code < 600:
                last_exc = exc
                time.sleep(1.5)
                continue
            raise
        except (http.client.IncompleteRead, ConnectionError,
                urllib.error.URLError) as exc:
            last_exc = exc
            time.sleep(1.5)
    raise last_exc


def _norm_url(url):
    return (url or "").strip().rstrip("/").lower()


def collect_sources(*searches):
    """Deduped search results plus the set of URLs they came from."""
    sources = []
    allowed = set()
    for search in searches:
        if not search:
            continue
        for r in search.get("results", []):
            url = (r.get("url") or "").strip()
            if not url or _norm_url(url) in allowed:
                continue
            allowed.add(_norm_url(url))
            sources.append({
                "title": (r.get("title") or "").strip(),
                "url": url,
                "content": (r.get("content") or "").strip(),
            })
    return sources, allowed


def _sources_block(sources, limit=12):
    lines = []
    for i, s in enumerate(sources[:limit], 1):
        content = s["content"][:400].replace("\n", " ")
        lines.append(f"[{i}] {s['title']}\nURL: {s['url']}\n{content}")
    return "\n\n".join(lines)


_URL_RE = re.compile(r"https?://[^\s)\]]+")


def _draft_urls_ok(text, allowed):
    """Every URL in a draft must be a URL the search returned."""
    found = _URL_RE.findall(text or "")
    return all(_norm_url(u) in allowed for u in found), found


def _fix_citation_labels(text):
    """Normalise [2](url) style citations to [source](url)."""
    return re.sub(r"\[\d+\]\((https?://[^)]+)\)", r"[source](\1)",
                  text or "")


def _repair_number_citations(text, sources):
    """Map bare [n] citations to the n-th source's link.

    Models often cite the numbered sources block as just "[2]"
    instead of "[source](url)". The number refers to a source we
    provided, so the repair is deterministic: replace it with
    that source's real link. Numbers outside the block's range
    are left untouched (and will fail the URL check).
    """
    def repl(match):
        n = int(match.group(1))
        if 1 <= n <= len(sources):
            return f"[source]({sources[n - 1]['url']})"
        return match.group(0)

    return re.sub(r"\[(\d+)\](?!\()", repl, text or "")


def _context_lines(subject, context, structured):
    lines = []
    if context:
        lines.append(f"Free-text context: {context}")
    for key, label in (
            ("relationship", "Their role to the user"),
            ("agenda", "This meeting is for"),
            ("when", "When"),
            ("where", "Where"),
            ("why", "Why it is happening"),
            ("purpose", "Meeting type"),
            ("offering", "The user is presenting"),
            ("goal", "The outcome the user wants"),
            ("prior", "Previous contact, in the user's words")):
        value = (structured.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return lines


def llm_synthesize(cfg, subject, context, structured, sources,
                   allowed):
    """Draft the executive summary; None if it fails any check."""
    ctx = "\n".join(_context_lines(subject, context, structured)) \
        or "none given"
    user = (
        f"SUBJECT: {subject}\n"
        f"MEETING CONTEXT: {ctx}\n\n"
        f"SOURCES:\n{_sources_block(sources)}\n\n"
        "Write an executive summary of the subject for someone "
        "about to meet them:\n"
        "- 3 to 5 sentences of summary prose first.\n"
        "- Then up to 4 key points, one per line, each starting "
        "with \"- \".\n"
        "Cite with source numbers from the SOURCES, like [2] — "
        "one citation per sentence, at the sentence's end. "
        "Output only the summary — no heading, no introduction."
    )
    try:
        text = llm_chat(cfg, GUARDRAIL_SYSTEM, user)
    except Exception:
        return None
    text = _repair_number_citations(text, sources)
    ok, found = _draft_urls_ok(text, allowed)
    if not ok or not found or not (80 <= len(text) <= 3000):
        return None
    return _fix_citation_labels(text)


def llm_questions(cfg, subject, context, structured, sources,
                  allowed):
    """Draft the questions; None if the draft fails any check."""
    ctx = "\n".join(_context_lines(subject, context, structured)) \
        or "none given"
    user = (
        f"SUBJECT: {subject}\n"
        f"MEETING CONTEXT:\n{ctx}\n\n"
        f"SOURCES:\n{_sources_block(sources)}\n\n"
        "Write exactly 5 questions the user can ask in this "
        "meeting. Rules:\n"
        "- Each question must be grounded in a specific fact "
        "from the SOURCES and end with that fact's source "
        "number in square brackets, like [2].\n"
        "- Use the meeting context: what the meeting is for, why "
        "it is happening, what the user is presenting, and the "
        "outcome they want.\n"
        "- Specific questions worth asking out loud, not generic "
        "ones.\n"
        "Output only a numbered list, 1. to 5., one question "
        "per line."
    )
    try:
        text = llm_chat(cfg, GUARDRAIL_SYSTEM, user, max_tokens=1600)
    except Exception:
        return None
    text = _repair_number_citations(text, sources)
    parsed = []
    for raw in (text or "").splitlines():
        m = re.match(r"^\s*(?:\d+[.)]|[-*])\s+(.*)$", raw)
        if m:
            parsed.append(m.group(1).strip())
    # Keep only questions that carry a source link and cite
    # nothing outside the search results. A question without a
    # link is ungrounded or was cut off mid-draft, so it is
    # dropped; if too few survive, the whole draft is discarded
    # and the deterministic questions are used instead.
    questions = []
    for q in parsed:
        ok, found = _draft_urls_ok(q, allowed)
        if ok and found:
            questions.append(_fix_citation_labels(q))
    if len(questions) < 3:
        return None
    # Repetition cap: the observed failure mode is five paraphrases
    # of one source claim (same question re-dressed). Drop any
    # question whose content words mostly repeat an earlier kept
    # question; if too few distinct questions survive, discard the
    # draft and use the deterministic questions instead.
    def _content_words(q):
        return set(re.findall(r"[a-z0-9]+", q.lower())) - {
            "the", "a", "an", "of", "to", "in", "on", "for", "and",
            "or", "is", "are", "you", "your", "we", "our", "with",
            "that", "this", "it", "as", "at", "by", "from", "how",
            "what", "would", "could", "do", "does",
        }
    kept = []
    for q in questions:
        words = _content_words(q)
        if any(
            words and len(words & _content_words(k))
            / max(1, len(words | _content_words(k))) >= 0.5
            for k in kept
        ):
            continue
        kept.append(q)
    if len(kept) < 3:
        return None
    return kept[:5]


# --- Guided chat intake -------------------------------------------------
# The chat walks the same context fields as the CLI flags and the
# web form, one question at a time, for people who do not know what
# to type into a form. The queue order and the ready rule are
# deterministic (code); the LLM only extracts what the user actually
# said and phrases the next question. It never fills a field the
# user did not state.

CHAT_QUEUE = [
    ("subject",
     "Who or what is the meeting about — a company or a person?",
     "Tavily, Satya Nadella, Acme Corp"),
    ("relationship", "What are they to you?",
     "a prospective client · a partner · an employer"),
    ("agenda", "What is this meeting for?",
     "a first demo · a partnership discussion · a job conversation"),
    ("when", "When is the meeting?",
     "a date like 2026-11-25 — within a week, the brief weights "
     "the freshest news"),
    ("where", "Where does it happen?",
     "online (video call) · their office · a coffee shop in Bangkok"),
    ("why", "Why is it happening — who asked for it, and what "
     "prompted it?",
     "they asked to see it · I requested it after their launch"),
    ("purpose", "What kind of meeting is it?",
     "sales · partnership · interview · client"),
    ("offering", "What will you present or bring?",
     "our onboarding service · a demo of the tool"),
    ("goal", "What outcome do you want from it?",
     "a paid pilot · an API partnership with startup credits"),
    ("fallback", "If that outcome is not reachable, what would "
     "you settle for?",
     "a follow-up meeting booked · an introduction to their team"),
    ("prior", "Any previous contact with them? Whatever you write "
     "is printed in the brief exactly as written — or say skip.",
     "met in October; they said onboarding takes three weeks"),
]

CHAT_FIELDS = [name for name, _q, _e in CHAT_QUEUE]

CHAT_SKIP_WORDS = {"skip", "skip this one", "pass", "don't know",
                   "dont know", "no idea", "none", "n/a", "-"}

CHAT_SYSTEM = """You run the intake chat for a meeting-prep research agent. The user is describing a meeting in their own words; your job is to collect a fixed set of context fields from what they say.

Hard rules — follow them exactly:
1. Extract ONLY facts the user actually stated. Never invent, guess, or fill a field from your own knowledge.
2. Never change a field that is already filled unless the user clearly corrects it.
3. Keep each extracted value short and in the user's own words where you can.
4. Reply with ONLY a JSON object, no other text:
   {"fields": {"field_name": "value", ...}, "reply": "your next message to the user"}
   "fields" holds only the fields this message newly fills or corrects (it may be empty).
5. "reply" is one short friendly message: briefly confirm what you captured, then ask about the NEXT FIELD named in the instructions. Ask about that field only, and include its example if one is given.
6. If the user's message does not answer anything, "fields" is empty and "reply" gently re-asks about the next field."""


def next_chat_field(fields, skipped):
    """The first queue field still unfilled and not skipped.

    The subject is never skippable: without it there is no brief.
    """
    for name, _q, _e in CHAT_QUEUE:
        if name == "subject":
            if not (fields.get("subject") or "").strip():
                return name
            continue
        if name in skipped:
            continue
        if not (fields.get(name) or "").strip():
            return name
    return None


def chat_question(name):
    for n, q, e in CHAT_QUEUE:
        if n == name:
            return f"{q} (For example: {e}.)"
    return ""


def _parse_chat_json(raw):
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def chat_turn(fields, skipped, user_text, cfg=None, chat_fn=None):
    """One intake-chat turn.

    Returns {"fields", "skipped", "reply", "next", "ready"}, or
    None when no LLM route is configured (the caller then points
    the user at the form). chat_fn is injectable for testing.
    """
    cfg = cfg if cfg is not None else load_llm_config()
    if cfg is None:
        return None
    fields = {k: (v or "").strip()
              for k, v in (fields or {}).items() if k in CHAT_FIELDS}
    skipped = [s for s in (skipped or []) if s in CHAT_FIELDS]
    text = (user_text or "").strip()
    target = next_chat_field(fields, skipped)
    if target and text.lower() in CHAT_SKIP_WORDS:
        if target == "subject":
            return {"fields": fields, "skipped": skipped,
                    "reply": "That one I do need — the brief has "
                             "to be about someone. "
                             + chat_question("subject"),
                    "next": "subject", "ready": False}
        skipped.append(target)
        nxt = next_chat_field(fields, skipped)
        if nxt is None:
            reply = "No problem — that's everything I need."
        else:
            reply = "Skipped. " + chat_question(nxt)
        return {"fields": fields, "skipped": skipped, "reply": reply,
                "next": nxt,
                "ready": nxt is None
                and bool((fields.get("subject") or "").strip())}
    known = "\n".join(f"- {k}: {v}" for k, v in fields.items() if v) \
        or "(nothing yet)"
    nxt_name = target or "none — everything is collected"
    q_hint = chat_question(target) if target else ""
    user_prompt = (
        f"Fields collected so far:\n{known}\n\n"
        f"The field we are asking about now: {nxt_name}. {q_hint}\n\n"
        f"User message: {text}\n\n"
        "Extract what this message answers (it may answer later "
        "fields too, or correct an earlier one) and reply with the "
        "JSON object only.")
    raw = (chat_fn or llm_chat)(cfg, CHAT_SYSTEM, user_prompt,
                                max_tokens=500)
    data = _parse_chat_json(raw)
    if data:
        for k, v in (data.get("fields") or {}).items():
            if k in CHAT_FIELDS and isinstance(v, str) \
                    and v.strip():
                fields[k] = v.strip()[:300]
    nxt = next_chat_field(fields, skipped)
    ready = nxt is None \
        and bool((fields.get("subject") or "").strip())
    # The question text is ALWAYS the deterministic queue text for
    # the target field; the model's own "reply" phrasing is never
    # shown. If the model asked about a different field than the
    # code's target, the user would answer THAT question while the
    # code files the answer under the target — a data-integrity
    # bug, not a style nit (Wonder gate, 2026-11-21). The model's
    # job in this chat is extraction only.
    if ready:
        reply = ("That's everything I need. You can prepare "
                 "the brief now — or tell me anything you'd "
                 "like to change.")
    elif nxt:
        reply = chat_question(nxt)
    else:
        reply = ""
    return {"fields": fields, "skipped": skipped, "reply": reply,
            "next": nxt, "ready": ready}


def top_results(search, limit=3):
    out = []
    for r in search.get("results", [])[:limit]:
        out.append({
            "title": r.get("title", "").strip(),
            "url": r.get("url", "").strip(),
            "content": (r.get("content", "") or "").strip(),
        })
    return out


def clean_title(title, limit=110):
    """Make a search-result title safe to quote inside a question."""
    title = title.replace("*", "").replace('"', "'").strip()
    # Long titles often append site/author cruft after a pipe
    # ("Headline | Person posted on the topic | ..."); when the
    # first segment already reads as a full headline, keep only it.
    if " | " in title:
        first = title.split(" | ", 1)[0].strip()
        if len(first) >= 40:
            title = first
    if len(title) > limit:
        title = title[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."
    return title


# How a headline question is framed depends on why the meeting is
# happening. The headline itself always comes from the results.
HEADLINE_FRAMES = {
    "sales": (
        "is that creating any pressure or opportunity on your "
        "side that we should talk about?"
    ),
    "partnership": (
        "how does that affect what a partner could build with "
        "you this year?"
    ),
    "interview": "how is that shaping the team's work right now?",
    "client": "is that changing anything about the work we do together?",
}
HEADLINE_FRAME_DEFAULT = (
    "what is the background to it, and where is it heading?"
)


def headline_questions(news, purpose=""):
    frame = HEADLINE_FRAMES.get(
        (purpose or "").strip().lower(), HEADLINE_FRAME_DEFAULT
    )
    out = []
    for item in top_results(news, 5):
        if len(out) >= 2:
            break
        title = clean_title(item["title"])
        # Very short titles are page labels ("Blog | Tavily"),
        # not headlines — never build a question on one. Topic
        # index pages ("X - Latest News and Updates") are labels
        # too, however long they are.
        if len(title) < 30 or "latest news" in title.lower():
            continue
        out.append(f'A recent story was headlined "{title}" — {frame}')
    return out


def build_questions(subject, context, structured, overview, news, people,
                    landmines=None):
    """Questions to ask in the meeting. They are driven by the
    meeting context first and the research second, because a good
    question depends on what the meeting is for: the same company
    gets different questions for a sales call than for a job
    interview. Everything is still deterministic and grounded —
    context questions quote the user's own purpose / offering /
    goal text, headline questions quote real headlines from the
    results, and the rest point at sections of this brief. When no
    context is supplied at all, this returns no questions and the
    brief asks for the context instead (clarify-first)."""
    relationship = (structured.get("relationship") or "").strip()
    agenda = (structured.get("agenda") or "").strip()
    prior = (structured.get("prior") or "").strip()
    purpose = (structured.get("purpose") or "").strip()
    offering = (structured.get("offering") or "").strip()
    goal = (structured.get("goal") or "").strip()
    kind = purpose.lower()
    has_people = bool((people.get("answer") or "").strip())
    has_overview = bool((overview.get("answer") or "").strip())
    has_news = bool(news.get("answer"))
    # The two lead questions come first in every structured mode:
    # who this person is to you, and what this meeting is for.
    lead = []
    if relationship:
        lead.append(
            f"As {relationship} — what do you most want to get "
            "out of this meeting?"
        )
    if agenda:
        lead.append(
            f"This meeting is for {agenda} — what needs to be "
            "true by the end of it for you to call it time "
            "well spent?"
        )
    fallback = (structured.get("fallback") or "").strip()
    if fallback:
        lead.append(
            f"If the main outcome is not reachable today, the "
            f"fallback is {fallback} — what is the smallest step "
            "toward it we could agree on before we leave?"
        )
    why = (structured.get("why") or "").strip()
    days_until = structured.get("days_until")
    when_text = (structured.get("when") or "").strip()
    if isinstance(days_until, int) and 0 <= days_until <= 3:
        # The meeting is imminent: surface the freshest findings
        # first by asking what is most likely to come up.
        if days_until == 0:
            timing = "The meeting is today"
        elif days_until == 1:
            timing = f"The meeting is tomorrow ({when_text})"
        else:
            timing = f"The meeting is in {days_until} days ({when_text})"
        lead.append(
            f"{timing} — which of the recent developments above "
            "is most likely to come up first?"
        )
    if why:
        lead.append(
            f"The background here is {why} — is that still the "
            "main thing on your mind, or has anything shifted "
            "since?"
        )
    questions = list(lead)
    if kind == "sales":
        if offering:
            questions.append(
                f"I would like to show you {offering} — before I "
                "do, what does your current setup for this look "
                "like, and where does it fall short?"
            )
        if goal:
            questions.append(
                f"If we could get to {goal} — who else on your "
                "side would need to be convinced, and what would "
                "they ask first?"
            )
        questions += headline_questions(news, kind)
        if has_people:
            questions.append(
                "The key people above run this area — who owns "
                "the budget for something like this, and what do "
                "they measure success by?"
            )
    elif kind == "partnership":
        if offering:
            questions.append(
                f"We bring {offering} — where would that fit "
                "best in what you are building, and what would "
                "you want from a partner in return?"
            )
        if goal:
            questions.append(
                f"For {goal} to work, what would each side need "
                "to commit in the first 90 days?"
            )
        questions += headline_questions(news, kind)
        if has_news:
            questions.append(
                "Of the recent developments above, which one "
                "opens the most room for a partner right now?"
            )
    elif kind == "interview":
        if offering:
            questions.append(
                f"My background is {offering} — where would that "
                "experience actually get used in this team?"
            )
        if goal:
            questions.append(
                f"I am hoping this process leads to {goal} — "
                "what are the next steps, and who makes the "
                "final decision?"
            )
        questions += headline_questions(news, kind)
        if has_overview:
            questions.append(
                f"The snapshot above summarises {subject} — "
                "which part of it is this team focused on "
                "this year?"
            )
    elif kind == "client":
        if offering:
            questions.append(
                f"Since we last spoke I have been working on "
                f"{offering} — does that address the problem you "
                "raised, or has the problem moved?"
            )
        if goal:
            questions.append(
                f"Today I would like us to leave with {goal} — "
                "what would you need to see for that to be an "
                "easy yes?"
            )
        questions += headline_questions(news, kind)
        if has_news:
            questions.append(
                "Of the recent developments above, is any of "
                "it about to change what you need from us?"
            )
    elif purpose or offering or goal or relationship or agenda or when_text or why or prior:
        # Structured context without a dedicated purpose template
        # (or with only some fields): frame questions from the
        # user's own words, then the findings.
        if offering:
            questions.append(
                f"I want to present {offering} — what should I "
                "understand about your side before I do?"
            )
        if goal:
            questions.append(
                f"I am hoping for {goal} from this meeting — "
                "what would a successful outcome look like from "
                "your side?"
            )
        questions += headline_questions(news)
        if has_people:
            questions.append(
                "The key people above lead this area — what are "
                "their current priorities?"
            )
    elif context:
        # Free-text --context only.
        questions += headline_questions(news)
        if context:
            questions.append(
                f'This meeting\'s context is "{context}" — what '
                "would a successful outcome look like from your side?"
            )
        if has_people:
            questions.append(
                "The key people above lead this area — what are "
                "their current priorities, and what do they look "
                "for first when someone brings them a proposal?"
            )
        if has_overview:
            questions.append(
                f"The snapshot above summarises what {subject} "
                "does — which part of that is the top priority "
                "right now, and what is the biggest obstacle to it?"
            )
        if has_news:
            questions.append(
                "Of the recent developments above, which one "
                "matters most for the next quarter — and which "
                "is most likely to be misunderstood by outsiders?"
            )
    if not questions and not context and not any(
        [relationship, agenda, prior, purpose, offering, goal,
         why, when_text, fallback]
    ):
        # No context at all: general questions drawn from the
        # research only. build_brief labels them under an
        # Assumptions heading (the clarify-first ask still leads
        # the brief) — the user is never left at a dead end
        # (Wonder gate, 2026-11-21).
        questions += headline_questions(news)
        if has_overview:
            questions.append(
                f"The snapshot above summarises {subject} — "
                "which part of it matters most right now, and "
                "what is the biggest obstacle to it?"
            )
        if has_people:
            questions.append(
                "The key people above lead this area — what "
                "are their current priorities?"
            )
        if has_news:
            questions.append(
                "Of the recent developments above, which one "
                "matters most for the next quarter?"
            )
    # Watch-out caution question: structured modes only, placed
    # right after the lead context questions. The title quoted is
    # a real headline returned by the landmines search pass.
    has_structured = any(
        [relationship, agenda, prior, purpose, offering, goal, why,
         when_text]
    )
    mine_titles = [
        clean_title(r.get("title", ""))
        for r in ((landmines or {}).get("results") or [])
    ]
    mine_titles = [t for t in mine_titles if len(t) >= 30]
    if has_structured and mine_titles:
        topic = agenda or "this meeting"
        caution = (
            f"Recent coverage included \"{mine_titles[0]}\" — "
            f"is there anything about that which affects {topic}?"
        )
        questions.insert(min(len(lead), len(questions)), caution)
    return questions[:5]


def build_brief(subject, context, structured, overview, news, people,
                competitors=None, landmines=None, llm=None):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Optional LLM drafts (executive summary + questions). Each
    # draft is source-checked in the llm_* functions; a draft that
    # fails any check comes back None and the deterministic text
    # below is used instead. Questions are only drafted when some
    # meeting context exists — the clarify-first rule applies to
    # the LLM exactly as it does to the deterministic questions.
    synthesis = None
    llm_qs = None
    if llm:
        sources, allowed = collect_sources(
            overview, news, people, competitors, landmines)
        if sources:
            synthesis = llm_synthesize(
                llm, subject, context, structured, sources, allowed)
            has_context = bool(context) or any(
                (structured.get(k) or "").strip()
                for k in (
                    "relationship", "agenda", "when", "where",
                    "why", "purpose", "offering", "goal", "prior",
                    "fallback",
                )
            )
            if has_context:
                llm_qs = llm_questions(
                    llm, subject, context, structured, sources,
                    allowed)

    lines = []
    lines.append(f"# Meeting Prep Brief: {subject}")
    lines.append("")
    lines.append(f"_Researched on {now} with the Tavily API._")
    if context:
        lines.append(f"_Meeting context: {context}_")
    if (structured.get("relationship") or "").strip():
        lines.append(
            f"_Their role: {structured['relationship'].strip()}_")
    if (structured.get("agenda") or "").strip():
        lines.append(
            f"_This meeting is for: {structured['agenda'].strip()}_")
    if (structured.get("when") or "").strip():
        when_line = f"_When: {structured['when'].strip()}"
        days_until = structured.get("days_until")
        if isinstance(days_until, int) and days_until >= 0:
            if days_until == 0:
                when_line += " (today)"
            elif days_until == 1:
                when_line += " (tomorrow)"
            else:
                when_line += f" (in {days_until} days)"
        lines.append(when_line + "_")
    if (structured.get("where") or "").strip():
        lines.append(f"_Where: {structured['where'].strip()}_")
    if (structured.get("why") or "").strip():
        lines.append(f"_Why: {structured['why'].strip()}_")
    if (structured.get("purpose") or "").strip():
        lines.append(f"_Meeting purpose: {structured['purpose'].strip()}_")
    if (structured.get("offering") or "").strip():
        lines.append(f"_Presenting: {structured['offering'].strip()}_")
    if (structured.get("goal") or "").strip():
        lines.append(f"_Desired outcome: {structured['goal'].strip()}_")
    if (structured.get("fallback") or "").strip():
        lines.append(
            f"_Fallback outcome: {structured['fallback'].strip()}_")
    if synthesis or llm_qs:
        drafted = []
        if synthesis:
            drafted.append("executive summary")
        if llm_qs:
            drafted.append("questions")
        parts = " and ".join(drafted)
        lines.append(
            f"_{parts[0].upper() + parts[1:]} drafted by "
            f"{llm['model']} from the search results in this "
            "brief. Every cited link was checked against the "
            "sources the search returned; the check verifies "
            "the links, not the claims — treat drafted text as "
            "a hypothesis and read its sources._"
        )
    lines.append("")

    lines.append("## Previous contact")
    lines.append("")
    prior_text = (structured.get("prior") or "").strip()
    if prior_text:
        lines.append("_In your words, unedited:_")
        lines.append("")
        lines.append(prior_text)
        lines.append("")
        lines.append("- Open items you owe them: ___")
        lines.append("- Open items they owe you: ___")
    else:
        lines.append(
            "_No prior history supplied — treat this as a first "
            "meeting._"
        )
    lines.append("")

    if synthesis:
        lines.append("## Executive summary")
        lines.append("")
        lines.append(synthesis)
        lines.append("")

    lines.append("## Snapshot")
    lines.append("")
    lines.append(overview.get("answer") or "No summary available.")
    lines.append("")

    window = (structured.get("news_window") or "month").strip()
    lines.append(
        "## Recent developments (last week)"
        if window == "week"
        else "## Recent developments (last month)"
    )
    lines.append("")
    if news.get("answer"):
        lines.append(news["answer"])
        lines.append("")
    for item in top_results(news, 3):
        snippet = item["content"][:220].replace("\n", " ")
        lines.append(f"- **{item['title']}** — {snippet}... ([source]({item['url']}))")
    lines.append("")

    lines.append("## Competitors found in search")
    lines.append("")
    comp_results = (competitors or {}).get("results") or []
    if comp_results:
        for item in comp_results[:4]:
            lines.append(f"- [{item['title']}]({item['url']})")
    else:
        lines.append("_No competitors found in search._")
    lines.append("")

    lines.append("## Watch out")
    lines.append("")
    mine_results = (landmines or {}).get("results") or []
    if mine_results:
        for item in mine_results[:3]:
            lines.append(f"- [{item['title']}]({item['url']})")
    else:
        lines.append("_No landmines found in search._")
    lines.append("")

    lines.append("## Key people")
    lines.append("")
    lines.append(people.get("answer") or "No people information found.")
    lines.append("")

    lines.append("## Source highlights")
    lines.append("")
    seen = set()
    for search in (overview, news, people):
        for item in top_results(search, 3):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            excerpt = item["content"][:300].replace("\n", " ")
            lines.append(f"### {item['title']}")
            lines.append(excerpt)
            lines.append(f"Source: {item['url']}")
            lines.append("")

    lines.append("## All sources")
    lines.append("")
    urls = []
    for search in (overview, news, people):
        for r in search.get("results", []):
            u = r.get("url", "").strip()
            if u and u not in urls:
                urls.append(u)
    for i, u in enumerate(urls, 1):
        lines.append(f"{i}. {u}")
    lines.append("")

    lines.append("## Questions to ask")
    lines.append("")
    questions = llm_qs if llm_qs else build_questions(
        subject, context, structured, overview, news, people,
        landmines=landmines,
    )
    no_context = not context and not any(
        (structured.get(k) or "").strip()
        for k in (
            "relationship", "agenda", "when", "where", "why",
            "purpose", "offering", "goal", "prior", "fallback",
        )
    )
    if questions:
        if no_context:
            # Clarify-first, softened: the ask comes first, but
            # the brief still delivers general questions drawn
            # from the research, labelled as assumptions-based —
            # never a refusal-only dead end (Wonder gate,
            # 2026-11-21).
            lines.append("## Assumptions")
            lines.append("")
            lines.append(
                "_No meeting context was supplied, so the "
                "questions below are general — drawn from the "
                "research only. They sharpen considerably with "
                "context: `--relationship` (who they are to "
                "you), `--agenda` (what this meeting is for), "
                "`--when`, `--where`, `--why` (who called it, "
                "and why now), `--purpose` (sales / partnership "
                "/ interview / client), `--offering` (what you "
                "will present), `--goal` (the outcome you want) "
                "— or a free-text `--context \"...\"`. The "
                "research above stands either way._"
            )
            lines.append("")
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. {q}")
    else:
        lines.append(
            "Not enough was found about this subject to suggest "
            "questions — consider a more specific name."
        )
    lines.append("")
    return "\n".join(lines)


def research_brief(api_key, subject, context, structured,
                   quiet=False, llm_config="auto"):
    """Run the searches and build the brief.

    Shared by the CLI and the web UI so both produce the same
    brief. llm_config: "auto" resolves the optional LLM layer from
    the environment, None forces it off, a dict is used as given.
    Returns (brief_markdown, llm_cfg_or_None).
    """
    def step(msg):
        if not quiet:
            print(msg)

    news_window = (structured.get("news_window") or "month").strip()
    step(f"[agent] Planning research on: {subject}")
    step("[agent] Step 1/5: overview search")
    overview = tavily_search(
        api_key, f"{subject} company overview what they do",
        search_depth="advanced", max_results=5)
    step("[agent] Step 2/5: recent news search")
    news = tavily_search(
        api_key, f"{subject} latest news announcements",
        topic="news", time_range=news_window, max_results=5)
    step("[agent] Step 3/5: key people search")
    people = tavily_search(
        api_key, f"{subject} founder CEO leadership team",
        max_results=5)
    step("[agent] Step 4/5: competitors searches (3 queries)")
    competitors = tavily_search(
        api_key, f"{subject} competitors", max_results=5)
    seen_urls = {
        (r.get("url") or "") for r in competitors.get("results", [])
    }
    for extra_query in (f"{subject} vs", f"{subject} alternative"):
        extra = tavily_search(api_key, extra_query, max_results=5)
        for r in extra.get("results", []):
            if (r.get("url") or "") not in seen_urls:
                seen_urls.add(r.get("url") or "")
                competitors.setdefault("results", []).append(r)
    step("[agent] Step 5/5: watch-out search")
    landmines = tavily_search(
        api_key,
        f"{subject} layoffs OR lawsuit OR outage OR controversy",
        topic="news", time_range=news_window, max_results=5)
    cfg = load_llm_config() if llm_config == "auto" else llm_config
    if cfg:
        step(f"[agent] LLM layer: {cfg['provider']} / {cfg['model']} "
             "(draft links are checked against the returned "
             "sources; anything that fails is replaced by "
             "the standard text)")
    else:
        step("[agent] LLM layer: off — standard brief")
    step("[agent] Writing the brief")
    brief = build_brief(
        subject, context, structured, overview, news, people,
        competitors=competitors, landmines=landmines, llm=cfg)
    return brief, cfg


def main():
    parser = argparse.ArgumentParser(
        description="Research a company or person and write a meeting prep brief.")
    parser.add_argument("subject", help='Who you are meeting, e.g. "Acme Corp"')
    parser.add_argument("--context", default="",
                        help='Why you are meeting them, e.g. "sales call"')
    parser.add_argument("--relationship", default="",
                        help="Who they are to you: a prospective "
                             "client, a partner, an employer")
    parser.add_argument("--agenda", default="",
                        help="What this specific meeting is for")
    parser.add_argument("--when", default="",
                        help="Meeting date, e.g. 2026-11-25 (a date "
                             "within a week weights recent news "
                             "more heavily)")
    parser.add_argument("--where", default="",
                        help="Where: in person or online, and where")
    parser.add_argument("--why", default="",
                        help="Why this meeting is happening: who "
                             "called it, and why now")
    parser.add_argument("--purpose", default="",
                        help="Meeting type: sales, partnership, "
                             "interview, client (drives the questions)")
    parser.add_argument("--offering", default="",
                        help="What you want to present or propose")
    parser.add_argument("--goal", default="",
                        help="The outcome you want from the meeting")
    parser.add_argument("--fallback", default="",
                        help="Fallback outcome: what you would "
                             "settle for if the main outcome is "
                             "not reachable today")
    parser.add_argument("--prior", default="",
                        help="Anything from previous contact with "
                             "them, in your own words (printed "
                             "verbatim in the brief)")
    parser.add_argument("--out", default="",
                        help="Output markdown file (default: brief-<subject>.md)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip the optional LLM layer even when "
                             "an API key is configured")
    args = parser.parse_args()

    # Clarify-first: questions depend on the meeting context, so
    # when an interactive user gives none at all, ask for the
    # structured fields before researching. Non-interactive runs
    # skip this; their brief leads the questions with an
    # Assumptions section (the ask) and still gives general
    # questions drawn from the research.
    if (
        not args.context
        and not args.relationship
        and not args.agenda
        and not args.when
        and not args.where
        and not args.why
        and not args.purpose
        and not args.offering
        and not args.goal
        and not args.fallback
        and not args.prior
        and sys.stdin.isatty()
    ):
        print("No meeting context given — the questions section "
              "is sharper with it (blank answers are fine).")
        args.relationship = input(
            "Who are they to you (a prospective client, a "
            "partner, an employer...)? ").strip()
        args.agenda = input(
            "What is this specific meeting for? ").strip()
        args.when = input(
            "When is the meeting (e.g. 2026-11-25)? ").strip()
        args.where = input(
            "Where (in person or online, and where)? ").strip()
        args.why = input(
            "Why is this meeting happening (who called it, "
            "why now)? ").strip()
        args.purpose = input(
            "Meeting type (sales / partnership / interview / "
            "client / your own words): ").strip()
        args.offering = input(
            "What do you want to present or propose? ").strip()
        args.goal = input(
            "What outcome do you want from the meeting? ").strip()
        args.fallback = input(
            "If that is not reachable, what would you settle "
            "for? ").strip()
        args.prior = input(
            "Anything from previous contact worth noting "
            "(blank if this is a first meeting)? ").strip()
    # Recency weighting: the closer the meeting, the fresher the
    # news window. An unparseable date is kept as text only.
    meeting_date = parse_meeting_when(args.when)
    days_until = (
        (meeting_date - datetime.now(timezone.utc).date()).days
        if meeting_date
        else None
    )
    news_window = (
        "week"
        if days_until is not None and 0 <= days_until <= 7
        else "month"
    )
    structured = {
        "relationship": args.relationship,
        "agenda": args.agenda,
        "when": args.when,
        "where": args.where,
        "why": args.why,
        "days_until": days_until,
        "news_window": news_window,
        "purpose": args.purpose,
        "offering": args.offering,
        "goal": args.goal,
        "fallback": args.fallback,
        "prior": args.prior,
    }

    api_key = load_api_key()
    if not api_key:
        print("ERROR: TAVILY_API_KEY is not set. Copy .env.example to .env "
              "and add your key, or export TAVILY_API_KEY.", file=sys.stderr)
        return 1

    subject = args.subject
    brief, _cfg = research_brief(
        api_key, subject, args.context, structured,
        llm_config=None if args.no_llm else "auto")
    out_path = args.out or f"brief-{slugify(subject)}.md"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(brief)
    print(f"[agent] Done. Brief saved to {out_path}")
    print("")
    print(brief)
    return 0


if __name__ == "__main__":
    sys.exit(main())
