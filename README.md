# AI-Augmented Qualitative Interview: Finnish Perceptions of US NATO Withdrawal

A semi-structured qualitative interview application for an academic study on how people in Finland perceive the economic and financial impacts of a possible US withdrawal from NATO. The AI interviewer guides respondents through four sections — background, economic perceptions, financial perceptions, and geopolitical perceptions — following a fixed question sequence with intelligent follow-up probing in Sections B, C, and D.

---

## Running locally

**1. Clone the repository**

```bash
git clone <your-repo-url>
cd interviews
```

**2. Create a virtual environment and install dependencies**

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r app/requirements.txt
```

**3. Set your Anthropic API key**

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

Or edit `app/parameters.py` and replace the placeholder value in the `ANTHROPIC_API_KEY` line directly.

**4. Start the server**

```bash
python app/app.py
```

The server starts on `http://127.0.0.1:8000`. You can verify it is running with:

```bash
curl http://127.0.0.1:8000/
# returns: Running!
```

**5. Open an interview session**

Navigate to:

```
http://127.0.0.1:8000/NATO_FINLAND/<session-id>
```

Replace `<session-id>` with any unique string that identifies the respondent (e.g. `participant-001`). Each unique session ID creates a new, independent interview session. To restart an interview, use a different session ID.

**Mock mode (no API key required)**

To test the interview flow without making real API calls:

```bash
MOCK_MODE=1 python app/app.py
```

In mock mode the interview moves through all questions sequentially without LLM inference, which is useful for testing the UI and question flow.

---

## Sharing with respondents using ngrok

[ngrok](https://ngrok.com) exposes your local server to the internet so respondents can access the interview from any device without a dedicated server.

**1. Install ngrok** from [ngrok.com/download](https://ngrok.com/download) and authenticate:

```bash
ngrok config add-authtoken <your-ngrok-token>
```

**2. Start your local server** (in one terminal):

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
python app/app.py
```

**3. Expose it with ngrok** (in a second terminal):

```bash
ngrok http 8000
```

ngrok will display a public URL such as `https://abc123.ngrok-free.app`. Share interview links in the format:

```
https://abc123.ngrok-free.app/NATO_FINLAND/<unique-session-id>
```

Give each respondent a different session ID so their responses are stored separately.

> **Note:** The ngrok URL changes each time you restart ngrok. For a persistent URL, use a paid ngrok plan or deploy to a server.

---

## Interview structure

The interview covers four sections in a fixed order:

| Section | Questions | Description |
|---------|-----------|-------------|
| A | A1–A6 | Background (nationality, age, gender, education, region, border proximity) |
| B | B1–B7 | Economic perceptions (defence spending, personal finances, employment, inflation, FDI, trade, stability) |
| C | C1–C7 | Financial perceptions (market reactions, duration, FDI outlook, macro stability, banking, areas of concern) |
| D | D1–D4 | Geopolitical perceptions (US-NATO relationship, disengagement likelihood, Finland's response, final thoughts) |

Section A is always strictly sequential. In Sections B, C, and D the AI may ask one contextual follow-up question before advancing if an answer is vague or raises an interesting point.

---

## Data storage

Interview responses are saved automatically as JSON files in `app/data/`, one file per session:

```
app/data/<session-id>.json
```

Each file contains the full transcript as a list of message objects with metadata (topic index, question index, timestamp, and the running interview summary). To retrieve all sessions programmatically:

```bash
curl http://127.0.0.1:8000/retrieve
```

---

## Credits

Built on the AI interviewer framework introduced in:

> Chopra, Felix and Haaland, Ingar (2023). *Conducting Qualitative Interviews with AI*. CESifo Working Paper No. 10666. [https://dx.doi.org/10.2139/ssrn.4583756](https://dx.doi.org/10.2139/ssrn.4583756)

The original framework has been adapted for this study: the OpenAI backend has been replaced with the Anthropic Claude API, the interview configuration has been redesigned for the NATO/Finland research context, and the probe agent has been extended with semi-structured follow-up logic.

This code is licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). Uses and distributions should cite the original Chopra & Haaland (2023) paper.
