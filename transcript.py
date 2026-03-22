from flask import Flask, jsonify
from vapi import Vapi
import logging
from dotenv import load_dotenv
import os
import re
load_dotenv()

app = Flask(__name__)

def parse_transcription(text):
    # Regex to find "Speaker: Message"
    pattern = r"(AI|User):\s*(.*)"
    matches = re.findall(pattern, text)
    
    conversation = []
    
    for i, (speaker, message) in enumerate(matches):
        # Basic dictionary structure
        entry = {
            "id": i + 1,
            "sender": speaker.lower(),
            "text": message.strip()
        }
        
        # Logic to detect a correction: 
        # If the same speaker repeats a message that is 80%+ similar, 
        # you could flag it. Here, we'll just add them all.
        conversation.append(entry)
        
    return conversation


@app.route('/latest_transcript', methods=['GET'])
def latest_transcript():
    print("here")
    # Initialize the Vapi client
    VAPI_API_KEY = os.environ.get('VAPI_API_KEY')
    client = Vapi(token=VAPI_API_KEY)
    """Get the transcript from the latest Vapi call"""
    try:
        calls_list = client.calls.list(limit=1)
        
        if not calls_list:
            return jsonify({
                'status': 'FAILURE',
                'message': 'No calls found in this account.'
            }), 404
        
        # Get the ID from the first item in the list
        latest_call = calls_list[0]
        call_id_fetched = latest_call.id
        
        print(f"Fetching transcript for Call ID: {call_id_fetched}")
        
        # Fetch the transcript
        call_data = client.calls.get(id=call_id_fetched)
        chat_list = parse_transcription(call_data.transcript)
        
        return jsonify({
            'status': 'SUCCESS',
            'call_id': call_id_fetched,
            'transcript': chat_list
        })
    
    except Exception as e:
        print(f"Error fetching Vapi transcript: {str(e)}")
        return jsonify({
            'status': 'FAILURE',
            'message': f'Error fetching transcript: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)