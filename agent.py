#!/usr/bin/env python3
"""Meeting Prep Research Agent.

Give it a company or a person you are about to meet, and it researches them
on the live web with the Tavily API, then writes a one-page markdown
briefing you can read in two minutes before the meeting.

Usage:
    python agent.py "Acme Corp"
    python agent.py "Acme Corp" --context "partnership discussion"
    python agent.py "Jane Smith, CEO of Acme" --out jane.md

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


def build_brief(subject, context, overview, news, people):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append(f"# Meeting Prep Brief: {subject}")
    lines.append("")
    lines.append(f"_Researched on {now} with the Tavily API._")
    if context:
        lines.append(f"_Meeting context: {context}_")
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
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Research a company or person and write a meeting prep brief.")
    parser.add_argument("subject", help='Who you are meeting, e.g. "Acme Corp"')
    parser.add_argument("--context", default="",
                        help='Why you are meeting them, e.g. "sales call"')
    parser.add_argument("--out", default="",
                        help="Output markdown file (default: brief-<subject>.md)")
    args = parser.parse_args()

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
    brief = build_brief(subject, args.context, overview, news, people)
    out_path = args.out or f"brief-{slugify(subject)}.md"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(brief)
    print(f"[agent] Done. Brief saved to {out_path}")
    print("")
    print(brief)
    return 0


if __name__ == "__main__":
    sys.exit(main())
