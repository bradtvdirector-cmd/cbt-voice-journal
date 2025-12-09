import os
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

@app.route('/voice', methods=['POST', 'GET'])
def voice():
    """Handle incoming phone calls"""
    response = VoiceResponse()
    response.say("Welcome to your voice journal. Please record your entry after the beep.")
    response.record(maxLength=300, transcribe=True)
    response.say("Thank you for your entry. Goodbye.")
    return str(response), 200, {'Content-Type': 'text/xml'}

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
