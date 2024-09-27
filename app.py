# # ElevenLabs configuration
# elevenlabs_api_key = '5c924f93c3f3a228a6da75ab00f73bc2'
# god_voice_id = 'IKne3meq5aSn9XLyUdCD'
# devil_voice_id = 'pFZP5JQG7iQjIQuC4Bku'
from flask import Flask, render_template, request, jsonify, Response
import requests
import json
import logging
import asyncio
import base64
import websockets
import os
from dotenv import load_dotenv

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Ollama configuration
ollama_base_url = 'http://localhost:11434'
god_model = 'GOD:latest'
devil_model = 'DEVIL:latest'

# ElevenLabs configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
god_voice_id = 'IKne3meq5aSn9XLyUdCD'
devil_voice_id = 'pFZP5JQG7iQjIQuC4Bku'
model_id = 'eleven_turbo_v2'

conversation_history = []


def generate_response(model, prompt):
    payload = {
        "model": model,
        "prompt": prompt,
        "temperature": 0.7,
        "max_tokens": 150,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "top_p": 0.9,
        "stop": None,
        "stream": False,
        "repeat_penalty": 1.1,
        "top_k": 40,
        "mirostat": 0,
        "mirostat_tau": 5.0,
        "mirostat_eta": 0.1,
        "seed": -1,
        "num_ctx": 131072,
        "num_thread": 8,
        "rope_freq_base": 500000,
        "rope_freq_scale": 1.0
    }

    try:
        response = requests.post(f"{ollama_base_url}/api/generate", json=payload, timeout=30)

        if response.status_code == 200:
            return response.json()['response'].strip()
        else:
            logger.error(f"Ollama API Error: {response.status_code} {response.text}")
            return "I'm sorry, I couldn't generate a response."
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return "I'm sorry, I couldn't generate a response."

async def text_to_speech_ws_streaming(text, voice_id):
    uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id={model_id}"
    
    async with websockets.connect(uri, extra_headers={"xi-api-key": ELEVENLABS_API_KEY}) as websocket:
        await websocket.send(json.dumps({
            "text": text,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            },
            "xi-api-key": ELEVENLABS_API_KEY
        }))

        await websocket.send(json.dumps({"text": ""}))

        audio_data = b""
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)
                if data.get("audio"):
                    audio_data += base64.b64decode(data["audio"])
                elif data.get("isFinal"):
                    break
            except asyncio.TimeoutError:
                break
            except websockets.exceptions.ConnectionClosedError:
                break

    return audio_data


@app.route('/stream_audio', methods=['POST'])
def stream_audio():
    data = request.json
    text = data['text']
    voice_id = data['voice_id']
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_data = loop.run_until_complete(text_to_speech_ws_streaming(text, voice_id))
        
        return Response(audio_data, mimetype="audio/mpeg")
    except Exception as e:
        logger.error(f"Error in stream_audio: {str(e)}")
        return jsonify({"error": "An error occurred while streaming audio"}), 500
    finally:
        loop.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data['message']
    bot = data['bot']

    if bot == 'god':
        model = god_model
        voice_id = god_voice_id
    else:
        model = devil_model
        voice_id = devil_voice_id

    conversation_history.append(f"User: {message}")
    prompt = "\n".join(conversation_history[-10:]) + f"\n{bot.capitalize()}: "
    
    response = generate_response(model, prompt)
    conversation_history.append(f"{bot.capitalize()}: {response}")

    return jsonify({
        'response': response,
        'bot': bot,
        'voice_id': voice_id
    })


@app.route('/chat_between_bots', methods=['POST'])
def chat_between_bots():
    god_prompt = "\n".join(conversation_history[-10:]) + "\nGod: "
    devil_prompt = "\n".join(conversation_history[-10:]) + "\nDevil: "

    god_response = generate_response(god_model, god_prompt)
    conversation_history.append(f"God: {god_response}")

    devil_response = generate_response(devil_model, devil_prompt)
    conversation_history.append(f"Devil: {devil_response}")

    return jsonify({
        'god_response': god_response,
        'devil_response': devil_response,
        'god_voice_id': god_voice_id,
        'devil_voice_id': devil_voice_id
    })

if __name__ == '__main__':
    app.run(debug=True)