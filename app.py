from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# Configuration
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
YOUR_PHONE_NUMBER = os.environ.get('YOUR_PHONE_NUMBER')
PIN_CODE = os.environ.get('PIN_CODE', '1234')
GOOGLE_DOC_ID = '1ioyYb07hberX0QS9jvWsDed8V6_15xuc-_AFJM62HuQ'

# Initialize Twilio client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None

# Google Docs setup
SCOPES = ['https://www.googleapis.com/auth/documents']
SERVICE_ACCOUNT_FILE = 'cbt-voice-journal-51a2223d4113.json'

def append_to_google_doc(text):
    """Append transcription to Google Doc"""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('docs', 'v1', credentials=credentials)
        
        timestamp = datetime.now().strftime('%Y-%m-%d %I:%M %p')
        requests = [{
            'insertText': {
                'location': {'index': 1},
                'text': f'\n\n---\n{timestamp}\n{text}\n'
            }
        }]
        
        service.documents().batchUpdate(
            documentId=GOOGLE_DOC_ID, body={'requests': requests}).execute()
        return True
    except Exception as e:
        print(f"Error appending to Google Doc: {e}")
        return False

@app.route('/wake', methods=['GET', 'POST'])
def wake():
    """Wake-up endpoint to prevent cold starts"""
    return 'OK', 200

@app.route('/sms', methods=['POST'])
def sms_handler():
    """Handle incoming SMS and trigger callback with delay"""
    try:
        from_number = request.form.get('From')
        body = request.form.get('Body', '').lower()
        
        print(f"SMS received from {from_number}: {body}")
        
        # Wake up the service
        import requests as http_requests
        try:
            http_requests.get(f"{request.url_root}wake", timeout=1)
        except:
            pass
        
        # Schedule callback after 75 seconds
        if client and YOUR_PHONE_NUMBER:
            call = client.calls.create(
                twiml=f'<Response><Pause length="75"/><Say>Connecting you now.</Say></Response>',
                to=YOUR_PHONE_NUMBER,
                from_=TWILIO_PHONE_NUMBER,
                url=f"{request.url_root}voice",
                method='POST'
            )
            print(f"Scheduled callback: {call.sid}")
        
        return '<Response><Message>Request received. You will receive a call shortly.</Message></Response>', 200
    except Exception as e:
        print(f"Error in SMS handler: {e}")
        return '<Response><Message>Error processing request.</Message></Response>', 500

@app.route('/voice', methods=['POST'])
def voice():
    """Handle incoming calls with PIN authentication"""
    response = VoiceResponse()
    
    if 'Digits' in request.form:
        digits = request.form.get('Digits')
        if digits == PIN_CODE:
            response.say("PIN accepted. Please record your journal entry after the beep.")
            response.record(
                transcribe=True,
                transcribe_callback=f"{request.url_root}transcription",
                max_length=300,
                finish_on_key='#'
            )
            response.say("Thank you for your entry. Goodbye.")
        else:
            response.say("Incorrect PIN. Goodbye.")
    else:
        gather = Gather(num_digits=4, action='/voice', method='POST')
        gather.say("Welcome to your voice journal. Please enter your 4 digit PIN.")
        response.append(gather)
        response.say("We didn't receive your PIN. Please try again.")
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/transcription', methods=['POST'])
def transcription():
    """Handle transcription callback from Twilio"""
    transcription_text = request.form.get('TranscriptionText', '')
    
    if transcription_text:
        print(f"Transcription received: {transcription_text}")
        append_to_google_doc(transcription_text)
    
    return '', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
