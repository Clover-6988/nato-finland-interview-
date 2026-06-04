# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running locally

**Manual (recommended for development):**
```bash
pip install -r app/requirements.txt
python app/app.py          # starts dev server on http://127.0.0.1:8000
```

**Mock mode — no API calls, no key required:**
```bash
MOCK_MODE=1 python app/app.py
```

**Start a test interview in the browser:**
```
http://127.0.0.1:8000/<INTERVIEW_ID>/<SESSION_ID>
# e.g. http://127.0.0.1:8000/NATO_FINLAND/test-001
```

**Healthcheck / smoke test:**
```bash
curl http://127.0.0.1:8000/         # returns "Running!"
curl http://127.0.0.1:8000/retrieve # returns all stored sessions as JSON
```

## Configuration — `app/parameters.py`

All interview behaviour lives here. The only active config is `NATO_FINLAND`. Add a new interview type by adding a key to `INTERVIEW_PARAMETERS`; the key becomes the `<INTERVIEW_ID>` in URLs.

Each config has:
- `first_question` — hardcoded welcome message shown on page load (no research question)
- `interview_plan` — list of `{topic, length}` dicts; `length` controls when the topic transitions; set to `number_of_probe_questions + 1`
- `closing_questions` — empty list (`[]`); end-of-interview is handled by `end_of_interview_message`
- Four agent dicts (`summary`, `transition`, `probe`, `moderator`) each with `model`, `max_tokens`, `temperature`, and a `prompt`

The `probe` dict's `prompt` field is an unused placeholder — `probe_within_topic()` in `core/agent.py` builds its prompt inline with the exact last question, last answer, and next required question as concrete values. The `model`, `temperature`, and `max_tokens` fields are still read from the config.

Prompt templates for the other three agents support these placeholders: `{current_topic_history}`, `{summary}`, `{topics}`, `{current_topic}`, `{next_interview_topic}`, `{question}`, `{answer}`.

The API key is read from the `ANTHROPIC_API_KEY` environment variable (set it there, not hardcoded).

## Architecture

### Request flow

```
Browser (direct link: /<interview_id>/<session_id>)
        │  GET  → renders chat.html with first_question
        │  POST /next  {session_id, interview_id, user_message}
        ▼
app/app.py  (Flask)
        │
        ▼
core/logic.py          — orchestrates one turn of the interview
        │
        ├── core/manager.py    — InterviewManager: loads/saves session state,
        │                        tracks topic_idx / question_idx / finish_idx
        │
        ├── core/agent.py      — LLMAgent (real) or MockLLMAgent (MOCK_MODE=1)
        │       │  probe_within_topic()   → sequential Python logic + optional LLM follow-up
        │       │  transition_topic()     → calls 'transition' (+ 'summary') agents concurrently
        │       │  review_answer()        → calls 'moderator' agent
        │       └  review_question()      → single Haiku call to flag harmful output
        │
        └── database/file.py   — saves sessions as JSON files in app/data/
```

### Turn logic in `core/logic.py:next_question()`

Each turn follows this decision tree:
1. Optionally moderate the user's answer (`review_answer`) — flag/terminate if off-topic too often
2. Add the answer to session history
3. Check position in `interview_plan`:
   - **Within topic, not at length limit** → `probe_within_topic()`, increment `question_idx`
   - **At topic length limit, not last topic** → `transition_topic()` (runs summary + transition concurrently), increment `topic_idx`, reset `question_idx`
   - **Last topic, at length limit** → serve next `closing_question` (empty → terminate)
4. Optionally moderate the generated question (`review_question`) — terminate on flag

### Probe agent — semi-structured mode

`probe_within_topic()` in `core/agent.py` uses a two-layer design:

**Python layer** (`_next_required_question`): tracks position in the required question sequence using substring matching against the topic description. Correctly handles transition-agent bridging text and LLM-generated follow-ups.

**LLM layer** (Sections B/C/D only): after each required question, the LLM decides Option A (advance) or Option B (one specific follow-up). After any follow-up is answered, always advances. Section A is always purely sequential — no LLM call.

### Session state

Each message saved to `app/data/<session_id>.json` is a flat dict:
```python
{
  'session_id': str, 'order': int, 'topic_idx': int, 'question_idx': int,
  'finish_idx': int, 'flagged_messages': int, 'terminated': bool,
  'summary': str, 'type': 'question'|'answer', 'content': str
}
```
The full interview is a list of these dicts. `InterviewManager` resumes by reading the last element.

### Interview structure (NATO_FINLAND)

```
Welcome message (first_question) → user types anything
Topic 1 — Section A (A1-A6):   probe asks all 6, then transitions
Topic 2 — Section B (B1-B7):   transition asks B1, probe handles B2-B7
Topic 3 — Section C (C1-C7):   transition asks C1, probe handles C2-C7
Topic 4 — Section D (D1-D4):   transition asks D1, probe handles D2-D4
End → end_of_interview_message
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for real API calls |
| `MOCK_MODE` | unset | Set to `1`/`true`/`yes` to use `MockLLMAgent` |
| `DATA_DIR` | `./app/data` | Directory for local JSON session files |
| `LOG_LEVEL` | `ERROR` | Python logging level |

