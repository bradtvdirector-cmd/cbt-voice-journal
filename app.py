
import os
from datetime import datetime
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# Google Docs configuration
SCOPES = ['https://www.googleapis.com/auth/documents']
SERVICE_ACCOUNT_FILE = 'cbt-voice-journal-51a2223d4113.json'
DOCUMENT_ID = '1ioyYb07hberX0QS9jvWsDed8V6_15xuc-_AFJM62HuQ'

def get_docs_service():
    """Create and return Google Docs API service"""
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('docs', 'v1', credentials=credentials)
    return service

def append_to_doc(timestamp, transcript, recording_url):
    """Append a journal entry to the Google Doc"""
    try:
        service = get_docs_service()
        
        # Format the entry
        entry_text = f"\n---\nEntry: {timestamp}\n\nTranscript:\n{transcript}\n\nRecording: {recording_url}\n\n"
        
        # Append to the end of the document
        requests = [{
            'insertText': {
                'location': {
                    'index': 1,
                },
                'text': entry_text
            }
        }]
        
        service.documents().batchUpdate(
            documentId=DOCUMENT_ID,
            body={'requests': requests}
        ).execute()
        
        print(f"Successfully added entry to Google Doc at {timestamp}")
        return True
    except Exception as e:
        print(f"Error appending to Google Doc: {e}")
        return False

@app.route('/voice', methods=['POST', 'GET'])
def voice():
    """Handle incoming phone calls"""
    response = VoiceResponse()
    response.say("Welcome to your voice journal. Please record your entry after the beep.")
    response.record(
        maxLength=300,
        transcribe=True,
        transcribeCallback='https://cbt-voice-journal.onrender.com/transcription'
    )
    response.say("Thank you for your entry. Goodbye.")
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/transcription', methods=['POST'])
def transcription():
    """Handle transcription callback from Twilio"""
    try:
        # Get transcription data from Twilio
        transcript = request.form.get('TranscriptionText', 'No transcription available')
        recording_url = request.form.get('RecordingUrl', 'No recording URL')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Append to Google Doc
        append_to_doc(timestamp, transcript, recording_url)
        
        return '', 200
    except Exception as e:
        print(f"Error in transcription handler: {e}")
        return '', 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
