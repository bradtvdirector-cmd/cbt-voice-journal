from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
from datetime import datetime
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from urllib.parse import quote

app = Flask(__name__)

# Load credentials from file
try:
    with open('cbt-voice-journal-51a2223d4113.json', 'r') as f:
        creds_info = json.load(f)
    credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=['https://www.googleapis.com/auth/documents'])
    docs_service = build('docs', 'v1', credentials=credentials)
except Exception as e:
    print(f"Error loading credentials: {e}")
    docs_service = None

# Store session data
sessions = {}

# 13 custom CBT questions
QUESTIONS = [
    "What situation triggered your thoughts or feelings?",
    "How are you feeling right now, and how strong is that feeling from zero to ten?",
    "What is the first thought that popped into your mind about this situation?",
    "What facts or experiences make that thought seem true?",
    "What facts or experiences might show that this thought is not fully true?",
    "If you step back, what is a more balanced or helpful way to look at this?",
    "After thinking about it this way, how strong is your feeling now from 0 to 10?",
    "When you look closely, what real evidence supports this thought?",
    "When you look closely, what real evidence goes against this thought?",
    "If a good friend were in your shoes, what would you say to them?",
    "Are you treating a feeling as if it were a fact?",
    "Can you think of another possible way to see this situation?",
    "Are you seeing this in all-or-nothing terms, like only good or only bad?"
]

@app.route('/sms', methods=['POST'])
def sms_handler():
    resp = VoiceResponse()
    from_number = request.form.get('From')
    sessions[from_number] = {'awaiting_callback': True, 'timestamp': datetime.now().isoformat()}
    callback_url = request.url_root + 'voice'
    resp.say("Journal entry request received. You will receive a call shortly.")
    print(f"SMS received from {from_number}, callback URL: {callback_url}")
    return str(resp)

@app.route('/voice', methods=['POST'])
def voice_handler():
    resp = VoiceResponse()
    from_number = request.form.get('From') or request.form.get('To')
    digit = request.form.get('Digits', '')
    question_index = int(request.form.get('question', 0))
    if from_number not in sessions:
        sessions[from_number] = {'pin_verified': False, 'answers': {}, 'current_question': 0}
    session = sessions[from_number]
    if not session.get('pin_verified') and not digit:
        resp.pause(length=75)
    if not session.get('pin_verified'):
        if not digit:
            gather = Gather(num_digits=4, action='/voice', method='POST')
            gather.say('Welcome to your C B T voice journal. Please enter your 4-digit PIN.')
            resp.append(gather)
            return str(resp)
        expected_pin = os.environ.get('PIN_CODE', '1234')
        if digit == expected_pin:
            session['pin_verified'] = True
            session['answers'] = {}
            session['current_question'] = 0
        else:
            resp.say('Invalid PIN. Goodbye.')
            resp.hangup()
            return str(resp)
    question_index = session.get('current_question', 0)
    if question_index < len(QUESTIONS):
        question_text = QUESTIONS[question_index]
        resp.say(f"Question {question_index + 1}. {question_text}")
        resp.record(action=f'/recording-complete?question={question_index}', method='POST', finish_on_key='#', max_length=120, transcribe=False)
        return str(resp)
    else:
        save_to_google_doc(from_number, session['answers'])
        resp.say("Thank you. Your journal entry has been saved. Goodbye.")
        resp.hangup()
        if from_number in sessions:
            del sessions[from_number]
        return str(resp)

@app.route('/recording-complete', methods=['POST'])
def recording_complete_handler():
    resp = VoiceResponse()
    from_number = request.form.get('From') or request.form.get('To')
    recording_url = request.form.get('RecordingUrl', '')
    question_index = int(request.args.get('question', '0'))
    if from_number not in sessions:
        resp.say("Session expired. Please call again.")
        resp.hangup()
        return str(resp)
    session = sessions[from_number]
    session['temp_recording'] = recording_url
    session['temp_question'] = question_index
    encoded_url = quote(recording_url, safe='')
    gather = Gather(num_digits=1, action=f'/menu-choice?question={question_index}&RecordingUrl={encoded_url}', method='POST')
    gather.say('Press 1 to save and continue, 2 to re-record, or 3 to review.')
    resp.append(gather)
    resp.say('No input received.')
    resp.redirect(url=f'/recording-complete?question={question_index}', method='POST')
    return str(resp)

@app.route('/menu-choice', methods=['POST'])
def menu_choice_handler():
    resp = VoiceResponse()
    from_number = request.form.get('From') or request.form.get('To')
    digit = request.form.get('Digits', '')
    recording_url = request.args.get('RecordingUrl', '')
    question_index = int(request.args.get('question', '0'))
    if from_number not in sessions:
        resp.say("Session expired. Please call again.")
        resp.hangup()
        return str(resp)
    session = sessions[from_number]
    if digit == '1':
        session['answers'][question_index] = recording_url
        session['current_question'] = question_index + 1
        resp.redirect(url='/voice', method='POST')
    elif digit == '2':
        resp.redirect(url='/voice', method='POST')
    elif digit == '3':
        resp.say('Here is your recording.')
        resp.play(recording_url)
        encoded_url = quote(recording_url, safe='')
        gather = Gather(num_digits=1, action=f'/menu-choice?question={question_index}&RecordingUrl={encoded_url}', method='POST')
        gather.say('Press 1 to save and continue, 2 to re-record, or 3 to review again.')
        resp.append(gather)
    else:
        resp.say('Invalid choice.')
        encoded_url = quote(recording_url, safe='')
        resp.redirect(url=f'/recording-complete?question={question_index}', method='POST')
    return str(resp)

def save_to_google_doc(phone_number, answers):
    if not docs_service:
        print("Google Docs service not available")
        return
    doc_id = os.environ.get('GOOGLE_DOC_ID')
    if not doc_id:
        print("GOOGLE_DOC_ID not set")
        return
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry_text = f"\n\n--- Journal Entry: {timestamp} ---\n"
    entry_text += f"Phone: {phone_number}\n\n"
    for q_index, recording_url in answers.items():
        question_text = QUESTIONS[q_index] if q_index < len(QUESTIONS) else f"Question {q_index + 1}"
        entry_text += f"Q{q_index + 1}: {question_text}\n"
        entry_text += f"Recording: {recording_url}\n\n"
    try:
        requests = [{'insertText': {'location': {'index': 1}, 'text': entry_text}}]
        docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests}).execute()
        print(f"Successfully saved entry to Google Doc for {phone_number}")
    except Exception as e:
        print(f"Error saving to Google Doc: {e}")

@app.route('/wake', methods=['GET', 'POST'])
def wake_handler():
    return "Service is awake!", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
