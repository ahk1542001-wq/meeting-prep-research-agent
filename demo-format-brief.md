# Winning Hackathon Demo Video — Format Brief

Researched 2026-11-20 from Devpost's official demo-video guidance, Devpost's
"6 Tips" (from repeat winners), judge interviews (JetBrains x Codex judging
table; Devpost's 5-judge panel: Square, Databricks, Google, NEAR, Atlassian),
and published winning-video structures (Sui Overflow, AWS AI Agent, ASI Agents
playbooks). Applied at the end to the Meeting Prep Research Agent.

Key sources:
- https://help.devpost.com/article/84-video-making-best-practices
- https://info.devpost.com/blog/6-tips-for-making-a-hackathon-demo-video
- https://info.devpost.com/blog/hackathon-judging-tips
- http://blog.jetbrains.com/ai/2026/06/how-to-win-a-hackathon-notes-from-the-judging-table/

---

## 1. Length and structure

**Target 2:00–2:30. Hard ceiling: the event's cap (most Devpost events: under
3 minutes).** Judges watch 30–100 videos; async judging means the video may be
the *only* thing a judge ever sees. Shorter and complete beats longer and
thorough. Never speed up audio to fit — cut content instead.

Canonical structure (2:30 cut):

| Time | Beat | Job |
|---|---|---|
| 0:00–0:10 | **Hook** | One line: the painful situation + what this product does about it. Product name on screen. |
| 0:10–0:30 | **Problem** | Make the judge *feel* the problem. Concrete scenario, not abstractions. |
| 0:30–0:40 | **Solution reveal** | Product appears, already open. One sentence: what it is. |
| 0:40–1:50 | **Live demo** | The product running end-to-end, one clean flow. This is ~50% of the video and its centerpiece. |
| 1:50–2:15 | **How it works / differentiator** | One simple diagram or one distinctive mechanism, 3 sentences max. No architecture lecture. |
| 2:15–2:30 | **Impact + close** | Who it's for, what changes for them, memorable final line + repo/product name card. |

Variants seen in winning playbooks: 60–90s cuts (hook 10s / problem 10s /
demo 40s / impact 30s) for README embeds; 5-min cuts only when the event
explicitly allows them. When in doubt, ship the ~2:30 version.

## 2. The first 10 seconds

- **Elevator pitch immediately.** Devpost: "treat the opening seconds like a
  movie trailer" — what the app does, in the first few seconds, before any
  detail.
- **Lead with the problem's frustration or the end result** — never with the
  team name, the tech stack, a logo animation, or "Hi, we're Team X."
- Judges form an opinion in the first ~30 seconds and spend the rest of the
  slot looking for evidence to confirm it. The hook decides the score's
  direction.
- **Something functional must be on screen within ~90 seconds** (judge
  consensus). Slides-first openings die here.
- Formula that works: *"[Painful situation]. [Product] fixes that — watch."*
  Then prove it.

## 3. Screen footage vs slides/talking

- **~70% real product screen footage, ~30% title/problem/diagram cards,
  0% talking head needed** for async judging.
- Devpost is explicit: make a screencast of the actual app running (localhost
  is fine). "Snazzy marketing videos don't help judges evaluate your app."
  And: "Make sure it's a demo! Show your project in action."
- Slides earn their place only at three moments: the hook line, the problem
  framing, and the one how-it-works diagram. Everything else is the product.
- One experienced winner's split is ~60% explaining / 40% demoing for
  pitch-style events — but for screen-first async events (Devpost/HackCulture
  style), demo-heavy wins. Err toward more product, less narration over slides.
- Production floor: 1080p, cursor visible and moving deliberately, text
  readable at player size, no music louder than the voice.

## 4. Voiceover that wins

- **Script it word-for-word and rehearse it aloud.** Every winning playbook
  says this. Budget the script by seconds per section before recording.
  Judges also warn: generic AI-written scripts read as generic — write it in
  your own words about your own product.
- **Pace: conversational, ~130–150 wpm.** A 2:30 video ≈ 330–370 words
  total. Short sentences (8–12 words). If a line doesn't fit the footage,
  shorten the line — never accelerate the delivery.
- **Narrate significance, not cursor movements.** Say what the result *means*
  ("every claim links to its source, so nothing is invented"), not "now I
  click the button" — the screen already shows that.
- **Sync and breathing room:** the voice lands *with* the action; pause
  briefly after a result appears so the judge can actually read it before
  the next beat. Dead air during waits/loads gets edited out, not narrated over.
- **Tone: genuine enthusiasm.** Judges explicitly read creativity and
  enthusiasm as proxies for effort invested. Flat, monotone, or obviously
  reluctant narration costs points. AI voice is acceptable if it sounds
  natural and paced — record a rough timing read first either way.
- While the product runs, the VO pattern is: *what I'm doing → what just
  happened → why it matters*, in one short sentence each.

## 5. Captions and text overlays

- **Burn in captions.** Judges may watch muted, on a phone, or in a noisy
  review queue. The video must fully work on mute — do a final muted
  playback check.
- **Captions add meaning, they don't transcribe clicks.** One idea per
  caption, short enough to read before the scene changes, broken at natural
  phrases. "The rule applies to every new workspace" beats "Now I'm clicking
  Save."
- **Caption every key claim** (numbers, differentiators, the closing line) —
  these are the lines judges remember and quote in scoring.
- Keep captions clear of the UI elements being shown (menus, buttons, the
  cursor's destination). Large, high-contrast, consistent style.
- Text overlays on cards: one line per card, big type. If a card needs two
  commas and a semicolon, it needs to be two cards.

## 6. Common mistakes that lose

1. **No clear problem statement** — the single most-cited judge complaint.
   Tech-first openings ("we used LangChain and…") before anyone knows why.
2. **Slides/architecture before anything works.** Nothing functional in the
   first 90 seconds = judge checks out.
3. **Feature tour.** Five half-shown features lose to one flow shown
   end-to-end. Scope the demo to the single best path.
4. **Unedited dead time** — loading spinners, typing, waiting for APIs,
   scrolling hunts. Edit it out; pre-fill what can be pre-filled; rehearse
   the exact clicks.
5. **Sped-up or rushed narration** to cram content under the cap.
6. **Going over the time limit** — can make the submission ineligible, and
   judges stop watching anyway.
7. **Slick video, thin product.** Judges open the repo/README and check the
   claims match. Overclaiming in the video backfires in technical review.
8. **Unreadable screen text** — recording at low res, tiny fonts, zoomed-out
   full-desktop captures of a dense UI.
9. **Access failures** — private/unlisted-wrong YouTube video, "for kids"
   flag blocking access, upload started at the deadline (processing can take
   hours). Upload early, check privacy settings, mark "Not for Kids."
10. **Music over voice, bad mic, echo.** Audio quality is a scored impression;
    use the best available mic and keep music well under the narration.

---

## 7. Shot list — Meeting Prep Research Agent (target 2:20–2:30)

Pre-record ONE successful live run and edit it; do not record a risky live
take. Pre-fill the 5W answers in rehearsal so clicks are deliberate. Use a
meeting date within the week so the brief shows "Recent developments (last
week)" and the timing question — it demos the recency weighting for free.

| # | Time | Visual | Voiceover / caption job |
|---|---|---|---|
| 1 | 0:00–0:08 | Title card: product name + one line | HOOK: "Your meeting is in one hour — and you know nothing about them." Caption the line. |
| 2 | 0:08–0:25 | Problem montage: a dozen browser tabs, a blank notes doc, a calendar invite | PROBLEM: manual pre-meeting research takes an hour of scattered Googling and still misses things. |
| 3 | 0:25–0:35 | UI home page; type the subject (a real company, e.g. Tavily) | REVEAL: "Meeting Prep turns that into one page. Tell it who you're meeting." |
| 4 | 0:35–1:00 | The 5 guided steps: click through Who → What → When → Where → Why cards, answering each (light speed-up OK) | KEY IDEA: "It doesn't guess. It asks five questions — who they are to you, what this meeting is for, when, where, and why now — because good questions depend on the context." |
| 5 | 1:00–1:08 | Click "Prepare the brief"; brief generates (trim the wait to ~2s of visible progress) | "One click. It runs five live searches." |
| 6 | 1:08–1:35 | The brief, part 1: dossier strip at top, then Executive summary — zoom so the source links are visible | PROOF: "A one-page brief. Every claim in the summary links to its source — nothing is invented." |
| 7 | 1:35–1:55 | The brief, part 2: scroll through Recent developments → Competitors → **Watch out** (red panel) → Key people | "Recent developments, competitors, the things you'd rather know before the meeting than during it, and the key people." |
| 8 | 1:55–2:08 | Questions to ask section, zoomed; highlight 1–2 questions with their source links | DIFFERENTIATOR: "And questions written for *this* meeting — grounded in the sources, each with its link. With no API key, it still works: the brief is built deterministically." |
| 9 | 2:08–2:20 | One diagram card: 5W context → 5 Tavily searches → optional LLM (source-checked) → brief | HOW IT WORKS: "Plain Python, standard library only. The optional LLM drafts are checked in code — any citation that isn't a real search result is thrown away." |
| 10 | 2:20–2:30 | Closing card: product name + repo URL | CLOSE: "Walk into every meeting prepared." |

Optional 10-second bonus beat if the cut runs short (insert at #4): show the
clarify-first behaviour — submit with no context and the brief *asks for the
context instead of inventing questions*. It is the product's most unusual
design decision and judges reward departures from the template.

Production checklist: 1080p screen capture, browser zoomed so brief text is
readable, cursor visible, captions burned in, VO recorded from the final
script at conversational pace, muted playback check, upload early with
privacy set to public/unlisted-per-rules and "Not for Kids."
