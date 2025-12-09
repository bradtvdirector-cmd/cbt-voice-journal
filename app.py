from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
from datetime import datetime
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# Load credentials from environment variable
creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
if creds_json:
    creds_info = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=['https://www.googleapis.com/auth/documents']
    )
    docs_service = build('docs', 'v1', credentials=credentials)
else:
    docs_service = None

# Store session data (in production, use Redis or database)
sessions = {}

# CBT questions
QUESTIONS = [
    "What situation triggered your thoughts or feelings?",
    "What automatic thoughts came to mind?",
    "What emotions did you feel, and how intense were they?",
    "What evidence supports your thoughts?",
    "What evidence contradicts your thoughts?",
    "Is there another way to look at this situation?",
    "What would you tell a friend in this situation?",
    "What action can you take based on this balanced perspective?"
]

@app.route('/sms', methods=['POST'])
def sms_handler():
    """Handle incoming SMS and initiate callback with delay"""
    resp = VoiceResponse()
    
    # Get the caller's phone number
    from_number = request.form.get('From')
    
    # Store session
    sessions[from_number] = {
        'awaiting_callback': True,
        'timestamp': datetime.now().isoformat()
    }
    
    # Make the outbound call with TwiML that includes wake-up delay
    callback_url = request.url_root + 'voice'
    
    # Return empty response - actual call will be made via webhook
    resp.say("Journal entry request received. You will receive a call shortly.")
    
    # Trigger callback (in production, use Twilio API to make call)
    print(f"SMS received from {from_number}, callback URL: {callback_url}")
    
    return str(resp)

@app.route('/voice', methods=['POST'])
def voice_handler():
    """Handle voice calls"""
    resp = VoiceResponse()
    
    # Get session data
    from_number = request.form.get('From') or request.form.get('To')
    digit = request.form.get('Digits', '')
    recording_url = request.form.get('RecordingUrl', '')
    question_index = int(request.form.get('question', 0))
    
    # Initialize session if needed
    if from_number not in sessions:
        sessions[from_number] = {
            'pin_verified': False,
            'answers': {},
            'current_question': 0
        }
    
    session = sessions[from_number]
    
    # Add 75-second pause at start for cold start mitigation
    if not session.get('pin_verified') and not digit:
        resp.pause(length=75)
    
    # PIN verification
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
    
    # Handle menu choice after recording
    if digit and recording_url:
        if digit == '1':  # Save and continue
            session['answers'][question_index] = recording_url
            question_index += 1
        elif digit == '2':  # Re-record
            # Stay on same question, will re-record
            pass
        elif digit == '3':  # Review
            # Play back the recording
            resp.play(recording_url)
            # Show menu again after playback
            gather = Gather(num_digits=1, action=f'/voice?question={question_index}&RecordingUrl={recording_url}', method='POST', timeout=10)
            gather.say('Press 1 to save and continue, 2 to re-record, or 3 to review again.')
            resp.append(gather)
            return str(resp)
    
    # Check if we have more questions
    if question_index < len(QUESTIONS):
        session['current_question'] = question_index
        
        # Ask the question
        resp.say(f"Question {question_index + 1}. {QUESTIONS[question_index]}")
        resp.say("Record your answer after the beep. Press the pound key when finished.")
        
        # Record with finish on key
        resp.record(
            action=f'/voice?question={question_index}',
            method='POST',
            finish_on_key='#',
            max_length=120,
            transcribe=False
        )
        
        # After recording, show menu
        gather = Gather(num_digits=1, action=f'/voice?question={question_index}', method='POST', timeout=10)
        gather.say('Press 1 to save and continue, 2 to re-record, or 3 to review.')
        resp.append(gather)
        
        return str(resp)
    
    # All questions answered - save to Google Doc
    if docs_service and session['answers']:
        try:
            doc_id = os.environ.get('GOOGLE_DOC_ID')
            
            # Format the entry
            entry_text = f"\n\n--- Journal Entry: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            for idx, (q_idx, rec_url) in enumerate(session['answers'].items()):
                entry_text += f"\nQ{q_idx + 1}: {QUESTIONS[q_idx]}\n"
                entry_text += f"Recording: {rec_url}\n"
            
            # Append to document
            requests_list = [
                {
                    'insertText': {
                        'location': {
                            'index': 1,
                        },
                        'text': entry_text
                    }
                }
            ]
            
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests_list}
            ).execute()
            
            resp.say('Your journal entry has been saved. Thank you for using C B T voice journal.')
        except Exception as e:
            print(f"Error saving to Google Doc: {e}")
            resp.say('Your responses were recorded but there was an error saving to the document.')
    else:
        resp.say('Thank you for your responses.')
    
    # Clear session
    if from_number in sessions:
        del sessions[from_number]
    
    resp.hangup()
    return str(resp)

@app.route('/')
def home():
    return 'CBT Voice Journal is running!'

@app.route('/wake', methods=['GET', 'POST'])
def wake():
    """Endpoint to wake up the service before actual call"""
    return 'Awake!', 200

if __name__ == '__main__':
    app.run(debug=True)
