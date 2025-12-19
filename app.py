from flask import Flask, request, session
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
import json
from datetime import datetime
# Force redeploy

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

# In-memory storage (for production, use a database)
pastor_message = {'url': None, 'timestamp': None}
missionary_responses = []

@app.route('/')
def index():
    return 'Missionary IVR System Running!'

@app.route('/voice', methods=['POST'])
def voice():
    response = VoiceResponse()
    response.say("Welcome to the missionary message system.")
    
    gather = Gather(num_digits=3, action='/handle-pin', timeout=10)
    gather.say("Please enter your three digit PIN code.")
    response.append(gather)
    
    response.say("We did not receive your PIN. Goodbye.")
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/handle-pin', methods=['POST'])
def handle_pin():
    digits = request.form.get('Digits', '')
    response = VoiceResponse()
    
    if digits == '888':
        # Pastor flow
        response.say("Welcome Pastor Jason. Please record today's message after the beep. Press pound when finished.")
        response.record(
            max_length=300,
            finish_on_key='#',
            action='/save-pastor-message',
            recording_status_callback='/recording-status'
        )
    elif digits == '777':
        # Missionary flow
        response.say("Welcome missionary. Please state your name after the beep. You have 5 seconds.")
        response.record(
            max_length=5,
            action='/play-pastor-message',
            recording_status_callback='/recording-status'
        )
    else:
        response.say("Invalid PIN. Goodbye.")
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/save-pastor-message', methods=['POST'])
def save_pastor_message():
    global pastor_message
    recording_url = request.form.get('RecordingUrl')
    
    if recording_url:
        pastor_message['url'] = recording_url
        pastor_message['timestamp'] = datetime.now().isoformat()
    
    response = VoiceResponse()
    response.say("Thank you Pastor Jason. Your message has been saved. Goodbye.")
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/play-pastor-message', methods=['POST'])
def play_pastor_message():
    name_recording_url = request.form.get('RecordingUrl')
    session['missionary_name_url'] = name_recording_url
    
    response = VoiceResponse()
    response.say("Thank you. Please listen to Pastor Jason's message.")
    
    if pastor_message['url']:
        response.play(pastor_message['url'])
    else:
        response.say("No message from Pastor Jason is available yet.")
    
    response.say("Please record your response after the beep. You have up to 3 minutes. Press pound when finished.")
    response.record(
        max_length=180,
        finish_on_key='#',
        action='/handle-response-menu'
    )
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/handle-response-menu', methods=['POST'])
def handle_response_menu():
    recording_url = request.form.get('RecordingUrl')
    session['response_url'] = recording_url
    
    response = VoiceResponse()
    
    gather = Gather(num_digits=1, action='/process-menu-choice', timeout=10)
    gather.say("To save your response and disconnect, press 1. To re-record your message, press 2. To hear your playback, press 3.")
    response.append(gather)
    
    # Default: save and hang up
    response.say("No option selected. Saving your response. Goodbye.")
    response.redirect('/save-response')
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/process-menu-choice', methods=['POST'])
def process_menu_choice():
    choice = request.form.get('Digits')
    response = VoiceResponse()
    
    if choice == '1':
        # Save and disconnect
        response.redirect('/save-response')
    elif choice == '2':
        # Re-record
        response.say("Please record your response after the beep. You have up to 3 minutes. Press pound when finished.")
        response.record(
            max_length=180,
            finish_on_key='#',
            action='/handle-response-menu'
        )
    elif choice == '3':
        # Playback
        response.say("Here is your recorded message.")
        if session.get('response_url'):
            response.play(session['response_url'])
        response.redirect('/handle-response-menu')
    else:
        response.say("Invalid option. Goodbye.")
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/save-response', methods=['POST', 'GET'])
def save_response():
    response_url = session.get('response_url')
    name_url = session.get('missionary_name_url')
    
    if response_url:
        missionary_responses.append({
            'name_recording': name_url,
            'response_recording': response_url,
            'timestamp': datetime.now().isoformat(),
            'caller': request.form.get('From', 'Unknown')
        })
    
    response = VoiceResponse()
    response.say("Your response has been saved. Thank you and God bless. Goodbye.")
    return str(response), 200, {'Content-Type': 'text/xml'}

@app.route('/recording-status', methods=['POST'])
def recording_status():
    # Handle recording status callbacks
    return '', 200

@app.route('/responses', methods=['GET'])
def view_responses():
    return json.dumps(missionary_responses, indent=2)

@app.route('/pastor-message', methods=['GET'])
def view_pastor_message():
    return json.dumps(pastor_message, indent=2)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
