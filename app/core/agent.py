import re
import logging
import itertools
import anthropic
from core.auxiliary import (
    execute_queries,
    fill_prompt_with_interview,
    chat_to_string
)


def _next_required_question(parameters: dict, history: list) -> str:
    """
    Return the next required question to ask, entirely in Python.

    Extracts every quoted string from the current topic description (the required
    questions, in order), then finds the last REQUIRED question that was asked in
    the conversation history — skipping any LLM-generated follow-ups — and returns
    the one that follows it.

    If no required question has been asked yet in this topic (e.g. only the welcome
    message exists), returns the first question in the list.
    """
    first_question = parameters.get('first_question', '')
    current_topic_idx = history[-1].get('topic_idx', 1)
    topic_desc = parameters.get('interview_plan', [{}])[current_topic_idx - 1].get('topic', '')

    questions = re.findall(r'"([^"]+)"', topic_desc)
    if not questions:
        return ''

    # Find the index of the last required question asked in this topic.
    # Uses substring matching so that transition-agent bridging text
    # ("Let's turn to economics. [B1 text]") is still correctly identified
    # as containing B1, even though the full stored string doesn't equal B1 exactly.
    last_required_idx = -1
    for m in history:
        if (m.get('topic_idx') != current_topic_idx
                or m['type'] != 'question'
                or m['content'] == first_question):
            continue
        content = m['content']
        for i, q in enumerate(questions):
            if q in content:           # substring match, not equality
                last_required_idx = i
                break                  # one required question per message

    if last_required_idx == -1:
        return questions[0]

    next_idx = last_required_idx + 1
    return questions[next_idx] if next_idx < len(questions) else questions[-1]


class LLMAgent(object):
    """ Class to manage LLM-based agents. """
    def __init__(self, api_key, timeout:int=30, max_retries:int=3):
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=max_retries)
        logging.info("Anthropic client instantiated. Should happen only once!")

    def load_parameters(self, parameters:dict):
        """ Load interview guidelines for prompt construction. """
        self.parameters = parameters

    def transcribe(self, audio) -> str:
        """ Audio transcription is not supported with the Anthropic backend. """
        raise NotImplementedError(
            "Audio transcription requires the OpenAI Whisper API and is not available "
            "with the Anthropic backend. Disable the /transcribe endpoint or add a "
            "separate transcription service."
        )

    def construct_query(self, tasks:list, history:list, user_message:str=None) -> dict:
        """
        Construct Anthropic API messages query.
        Defaults to claude-haiku-4-5-20251001 model, 300 token limit, and temperature of 0.
        For details see https://docs.anthropic.com/en/api/messages.
        """
        return {
            task: {
                "messages": [{
                    "role": "user",
                    "content": fill_prompt_with_interview(
                        self.parameters[task]['prompt'],
                        self.parameters['interview_plan'],
                        history,
                        user_message=user_message
                    )
                }],
                "model": self.parameters[task].get('model', 'claude-haiku-4-5-20251001'),
                "max_tokens": self.parameters[task].get('max_tokens', 300),
                "temperature": self.parameters[task].get('temperature', 0)
            } for task in tasks
        }

    def review_answer(self, message:str, history:list) -> bool:
        """ Moderate answers: Are they on topic? """
        response = execute_queries(
            self.client.messages.create,
            self.construct_query(['moderator'], history, message)
        )
        return "yes" in response["moderator"].lower()

    def review_question(self, next_question:str) -> bool:
        """ Moderate questions: Flag harmful or inappropriate AI-generated questions. """
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            temperature=0,
            messages=[{
                "role": "user",
                "content": (
                    "You are a content moderator for an academic research interview. "
                    "Is the following interview question harmful, offensive, or inappropriate "
                    "for use in a university research context? Answer only 'yes' or 'no'.\n\n"
                    f"Question: {next_question}"
                )
            }]
        )
        return "yes" in response.content[0].text.lower()

    def probe_within_topic(self, history:list) -> str:
        """
        Semi-structured probe logic.

        Section A (topic 1): always advance to the next required question — no follow-up,
        no LLM call, deterministic.

        Section B / C / D (topics 2-4): the LLM decides after each required question
        whether to ask one smart follow-up or move on. After any follow-up is answered,
        always advance with a brief acknowledgment.

        _next_required_question() handles position tracking in Python and correctly
        skips LLM-generated follow-ups when determining the next required question.
        """
        first_q = self.parameters.get('first_question', '')
        current_topic_idx = history[-1].get('topic_idx', 1)
        next_required = _next_required_question(self.parameters, history)

        # ── Section A: purely sequential, no LLM needed ──────────────────────────
        if current_topic_idx == 1:
            logging.info("Section A probe — advancing directly.")
            return next_required

        # ── Section B / C / D: LLM decides ───────────────────────────────────────
        topic_desc = self.parameters['interview_plan'][current_topic_idx - 1]['topic']
        questions_list = re.findall(r'"([^"]+)"', topic_desc)

        # Determine whether the last interviewer question was a required question
        # or an LLM-generated follow-up. Use substring matching (same as
        # _next_required_question) so transition bridging text is not mistaken
        # for a follow-up.
        topic_qs = [
            m['content'] for m in history
            if m.get('topic_idx') == current_topic_idx
            and m['type'] == 'question'
            and m['content'] != first_q
        ]
        last_question = topic_qs[-1] if topic_qs else ''
        was_follow_up = bool(last_question) and not any(q in last_question for q in questions_list)

        # Find the last answer given in this topic.
        last_answer = next(
            (m['content'] for m in reversed(history)
             if m.get('topic_idx') == current_topic_idx and m['type'] == 'answer'),
            ''
        )

        section = {2: 'B', 3: 'C', 4: 'D'}.get(current_topic_idx, 'B/C/D')
        probe_cfg = self.parameters.get('probe', {})

        if was_follow_up:
            # After a follow-up: always advance to the next required question.
            prompt = (
                "You are conducting a warm, conversational academic research interview "
                "about Finnish perceptions of the economic and financial impacts of a "
                "possible US withdrawal from NATO.\n\n"
                f"You just asked a follow-up: {last_question}\n\n"
                f"The respondent answered: {last_answer}\n\n"
                f"Next required question to ask: {next_required}\n\n"
                "Write one brief sentence acknowledging their answer, then ask the next "
                "required question exactly as written above. Keep it natural. "
                "Plain text only — no bold, no asterisks, no markdown formatting."
            )
        else:
            # After a required question: decide whether to follow up or advance.
            prompt = (
                "You are conducting a warm academic research interview (Section "
                f"{section}) about Finnish perceptions of the economic and financial "
                "impacts of a possible US withdrawal from NATO.\n\n"
                f"Question asked: {last_question}\n\n"
                f"Respondent's answer: {last_answer}\n\n"
                f"Next required question: {next_required}\n\n"
                "DECIDE — choose exactly one:\n\n"
                "Option A — The answer is clear and sufficient:\n"
                "  Write one brief sentence acknowledging their answer, then ask the "
                "next required question exactly as written above.\n\n"
                "Option B — The answer is vague, very brief, contradictory, or raises "
                "a genuinely interesting point worth one more question:\n"
                "  Ask ONE smart follow-up question that is specific to what they said. "
                "Do NOT ask the next required question yet.\n\n"
                "RULES:\n"
                "- Follow-up must relate directly to their specific answer — never "
                "generic (e.g. not 'can you say more?').\n"
                "- Keep your response short and conversational.\n"
                "- No labels or preamble.\n"
                "- Plain text only — no bold, no asterisks, no markdown formatting."
            )

        response = self.client.messages.create(
            model=probe_cfg.get('model', 'claude-sonnet-4-6'),
            max_tokens=probe_cfg.get('max_tokens', 200),
            temperature=probe_cfg.get('temperature', 0.5),
            messages=[{'role': 'user', 'content': prompt}]
        )
        result = response.content[0].text.strip()
        logging.info(f"probe_within_topic() — '{result[:80]}'")
        return result

    def transition_topic(self, history:list) -> tuple[str, str]:
        """
        Determine next interview question transitioning from one topic to the next.
        If summarize is set in parameters, also returns a summary of the interview so far.
        """
        summarize = self.parameters.get('summarize')
        tasks = ['summary', 'transition'] if summarize else ['transition']
        response = execute_queries(
            self.client.messages.create,
            self.construct_query(tasks, history)
        )
        return response['transition'], response.get('summary', '')


class MockLLMAgent(object):
    """
    Drop-in replacement for LLMAgent that returns canned responses without making
    any API calls. Activate by setting the MOCK_MODE environment variable to 1.
    Useful for testing UI and conversation flow locally.

    probe_within_topic() is always strictly sequential — it uses _next_required_question()
    directly, with no follow-up logic. This makes it easy to step through the full
    question sequence without needing real API credits.
    """

    _TRANSITION_QUESTIONS = [
        "Let's move on to the next section.",
        "Thank you — I'd like to turn to a related set of questions now.",
        "Moving on to the next part of the interview.",
    ]

    def __init__(self, *args, **kwargs):
        self._transition_cycle = itertools.cycle(self._TRANSITION_QUESTIONS)
        logging.warning("MockLLMAgent active — no real API calls will be made.")

    def load_parameters(self, parameters:dict):
        self.parameters = parameters

    def transcribe(self, audio) -> str:
        logging.info("MockLLMAgent.transcribe() — returning canned transcription.")
        return "This is a mock transcription. In a real session this would contain the participant's spoken response."

    def review_answer(self, message:str, history:list) -> bool:
        logging.info("MockLLMAgent.review_answer() — returning True (always on-topic).")
        return True

    def review_question(self, next_question:str) -> bool:
        logging.info("MockLLMAgent.review_question() — returning False (never flagged).")
        return False

    def probe_within_topic(self, history:list) -> str:
        """
        Always advances to the next required question in sequence.
        Sections A, B, C, D all treated identically — no follow-ups, no LLM decision.
        Uses _next_required_question() which correctly handles any LLM follow-ups
        that might have been logged in history from a prior real-API run.
        """
        question = _next_required_question(self.parameters, history)
        logging.info(f"MockLLMAgent.probe_within_topic() — '{question[:80]}'")
        return question

    def transition_topic(self, history:list) -> tuple[str, str]:
        question = next(self._transition_cycle)
        summary = "[Mock summary] The interviewee shared their views on the previous topic."
        logging.info(f"MockLLMAgent.transition_topic() — '{question}'")
        return question, summary
