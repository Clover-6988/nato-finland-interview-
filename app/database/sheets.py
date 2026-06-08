import json
import logging
import os
from datetime import datetime, timezone

try:
    import gspread
    from google.oauth2.service_account import Credentials
    _GSPREAD_AVAILABLE = True
except ImportError:
    _GSPREAD_AVAILABLE = False
    logging.warning("gspread not installed — Google Sheets integration disabled.")

_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
_client = None  # module-level cached client


def _get_client():
    global _client
    if _client is None:
        raw = os.environ.get('GOOGLE_CREDENTIALS', '')
        if not raw:
            raise RuntimeError("GOOGLE_CREDENTIALS environment variable not set")
        creds = Credentials.from_service_account_info(json.loads(raw), scopes=_SCOPES)
        _client = gspread.authorize(creds)
    return _client


def verify_connection():
    """
    Called once at startup to confirm credentials and Sheet ID are valid.
    Logs the result but never raises — file storage remains the primary store.
    """
    if not _GSPREAD_AVAILABLE:
        logging.warning("Sheets startup check skipped: gspread not installed.")
        return
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID', '')
    if not sheet_id or not os.environ.get('GOOGLE_CREDENTIALS', ''):
        logging.warning("Sheets startup check skipped: env vars not set.")
        return
    try:
        sheet = _get_client().open_by_key(sheet_id).sheet1
        logging.info(f"Sheets startup check OK — sheet title: '{sheet.title}', "
                     f"sheet_id={sheet_id}")
    except Exception as e:
        logging.error(f"Sheets startup check FAILED — sheet_id={sheet_id} error: {e}")


def append_qa_row(session_id: str, question_id: str, question: str, answer: str):
    """
    Append one Q/A row to the Google Sheet identified by GOOGLE_SHEETS_ID.
    No-ops silently when either env var is absent or gspread is unavailable.
    Errors are logged but never propagated — file storage is the primary store.
    """
    logging.info("Sheets: attempting to write row")
    if not _GSPREAD_AVAILABLE:
        logging.error("Sheets error: gspread not installed")
        return
    sheet_id = os.environ.get('GOOGLE_SHEETS_ID', '')
    if not sheet_id or not os.environ.get('GOOGLE_CREDENTIALS', ''):
        logging.error("Sheets error: GOOGLE_SHEETS_ID or GOOGLE_CREDENTIALS not set")
        return
    try:
        sheet = _get_client().open_by_key(sheet_id).sheet1
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        sheet.append_row(
            [session_id, timestamp, question_id, question, answer],
            value_input_option='RAW',
        )
        logging.info("Sheets: success")
    except Exception as e:
        logging.error(f"Sheets error: {e} - Sheet ID: {sheet_id}")
