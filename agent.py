#!/usr/bin/env python3
"""Meeting Prep Research Agent.

Give it a company or a person you are about to meet, and it researches them
on the live web with the Tavily API, then writes a one-page markdown
briefing you can read in two minutes before the meeting.

Usage:
    python agent.py "Acme Corp"
    python agent.py "Acme Corp" --relationship "a prospective client" \
        --agenda "a first demo" --purpose sales \
        --offering "our onboarding service" --goal "a paid pilot"
    python agent.py "Acme Corp" --context "partnership discussion"
    python agent.py "Jane Smith, CEO of Acme" --out jane.md

The questions at the end of the brief are driven by the meeting
context: --relationship / --agenda / --purpose / --offering / --goal
(structured) or --context (free text). With no context at all, the
brief asks for it instead of printing generic questions.

Requires a Tavily API key in the TAVILY_API_KEY environment variable
(or in a .env file next to this script). Get one at https://tavily.com
"""

import argparse
import json
import os
import re
import sys
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
    req = urllib.request.Request(
        TAVILY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "subject"


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


def build_questions(subject, context, structured, overview, news, people):
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
    elif purpose or offering or goal or relationship or agenda:
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
    return questions[:5]


def build_brief(subject, context, structured, overview, news, people):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
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
    if (structured.get("purpose") or "").strip():
        lines.append(f"_Meeting purpose: {structured['purpose'].strip()}_")
    if (structured.get("offering") or "").strip():
        lines.append(f"_Presenting: {structured['offering'].strip()}_")
    if (structured.get("goal") or "").strip():
        lines.append(f"_Desired outcome: {structured['goal'].strip()}_")
    lines.append("")

    lines.append("## Snapshot")
    lines.append("")
    lines.append(overview.get("answer") or "No summary available.")
    lines.append("")

    lines.append("## Recent developments (last month)")
    lines.append("")
    if news.get("answer"):
        lines.append(news["answer"])
        lines.append("")
    for item in top_results(news, 3):
        snippet = item["content"][:220].replace("\n", " ")
        lines.append(f"- **{item['title']}** — {snippet}... ([source]({item['url']}))")
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
    questions = build_questions(
        subject, context, structured, overview, news, people
    )
    if questions:
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. {q}")
    elif not any(
        (structured.get(k) or "").strip()
        for k in ("relationship", "agenda", "purpose", "offering", "goal")
    ) and not context:
        # Clarify-first: with no meeting context, generic questions
        # would be noise. Say what is missing and how to add it
        # instead of inventing a purpose for the user.
        lines.append(
            "_Not generated — good questions depend on what this "
            "meeting is for, and no meeting context was supplied. "
            "Add it and re-run:_"
        )
        lines.append("")
        lines.append(
            "- `--relationship` — who they are to you: a "
            "prospective client, a partner, an employer"
        )
        lines.append(
            "- `--agenda` — what this specific meeting is for"
        )
        lines.append(
            "- `--purpose` — the meeting type: sales, partnership, "
            "interview, client"
        )
        lines.append(
            "- `--offering` — what you want to present or propose"
        )
        lines.append("- `--goal` — the outcome you want")
        lines.append("")
        lines.append(
            '_Or pass a free-text `--context "..."`. The research '
            "above stands either way._"
        )
    else:
        lines.append(
            "Not enough was found about this subject to suggest "
            "questions — consider a more specific name."
        )
    lines.append("")
    return "\n".join(lines)


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
    parser.add_argument("--purpose", default="",
                        help="Meeting type: sales, partnership, "
                             "interview, client (drives the questions)")
    parser.add_argument("--offering", default="",
                        help="What you want to present or propose")
    parser.add_argument("--goal", default="",
                        help="The outcome you want from the meeting")
    parser.add_argument("--out", default="",
                        help="Output markdown file (default: brief-<subject>.md)")
    args = parser.parse_args()

    # Clarify-first: questions depend on the meeting context, so
    # when an interactive user gives none at all, ask for the
    # structured fields before researching. Non-interactive runs
    # skip this; their brief carries a context-needed note in the
    # questions section instead of generic questions.
    if (
        not args.context
        and not args.relationship
        and not args.agenda
        and not args.purpose
        and not args.offering
        and not args.goal
        and sys.stdin.isatty()
    ):
        print("No meeting context given — the questions section "
              "is sharper with it (blank answers are fine).")
        args.relationship = input(
            "Who are they to you (a prospective client, a "
            "partner, an employer...)? ").strip()
        args.agenda = input(
            "What is this specific meeting for? ").strip()
        args.purpose = input(
            "Meeting type (sales / partnership / interview / "
            "client / your own words): ").strip()
        args.offering = input(
            "What do you want to present or propose? ").strip()
        args.goal = input(
            "What outcome do you want from the meeting? ").strip()
    structured = {
        "relationship": args.relationship,
        "agenda": args.agenda,
        "purpose": args.purpose,
        "offering": args.offering,
        "goal": args.goal,
    }

    api_key = load_api_key()
    if not api_key:
        print("ERROR: TAVILY_API_KEY is not set. Copy .env.example to .env "
              "and add your key, or export TAVILY_API_KEY.", file=sys.stderr)
        return 1

    subject = args.subject
    print(f"[agent] Planning research on: {subject}")

    print("[agent] Step 1/3: overview search")
    overview = tavily_search(
        api_key, f"{subject} company overview what they do",
        search_depth="advanced", max_results=5)

    print("[agent] Step 2/3: recent news search")
    news = tavily_search(
        api_key, f"{subject} latest news announcements",
        topic="news", time_range="month", max_results=5)

    print("[agent] Step 3/3: key people search")
    people = tavily_search(
        api_key, f"{subject} founder CEO leadership team", max_results=5)

    print("[agent] Writing the brief")
    brief = build_brief(
        subject, args.context, structured, overview, news, people)
    out_path = args.out or f"brief-{slugify(subject)}.md"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(brief)
    print(f"[agent] Done. Brief saved to {out_path}")
    print("")
    print(brief)
    return 0


if __name__ == "__main__":
    sys.exit(main())
