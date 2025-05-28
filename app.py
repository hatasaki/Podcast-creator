import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, send_file, redirect, flash
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from openai import AzureOpenAI                             # NEW client import :contentReference[oaicite:3]{index=3}
from azure.identity import DefaultAzureCredential
import azure.cognitiveservices.speech as speechsdk

load_dotenv()

app = Flask(__name__)
#app.secret_key = os.getenv("FLASK_SECRET", "change-me")
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Instantiate Azure OpenAI client via the new OpenAI class
client = AzureOpenAI(
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"), 
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),  
    api_version="2024-10-21"
)

deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")

# Speech SDK config
speech_config = speechsdk.SpeechConfig(
    subscription=os.getenv("SPEECH_KEY"),
    region=os.getenv("SPEECH_REGION")
)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET'])
def index():
    return render_template('upload.html')

@app.route('/create', methods=['POST'])
def create_podcast():
    file = request.files.get('file')
    if not file or not allowed_file(file.filename):
        flash('Please upload a valid PDF file.')
        return redirect(request.url)

    # Save and extract PDF text
    filename = secure_filename(file.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(path)
    reader = PdfReader(path)
    full_text = "\n".join(p.extract_text() or "" for p in reader.pages)

    print(full_text)  # Debugging line to check the extracted text

    # Use the new client to get a chat completion
    response = client.chat.completions.create(
        model=deployment_name,
        messages=[
            {"role":"system","content":"You are a podcast scriptwriter."},
            {"role":"user",
             "content":f"Write a 5-minute Japanese conversational podcast between a man and a woman based on the following text. A man part and a woman part should be start with 'Man:' and 'Woman:' respectively without adding new line code.\nText:\n\n{full_text}"}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    conversation = response.choices[0].message.content

    print(conversation)  # Debugging line to check the generated conversation

    # Parse and build SSML as before…
    segments = []
    for line in conversation.splitlines():
        if line.startswith("Man:"):
            segments.append(("male", line[4:].strip()))
        elif line.startswith("Woman:"):
            segments.append(("female", line[6:].strip()))

    ssml = ['<speak version="1.0" xml:lang="ja-JP">']
    for role, text in segments:
        voice = "ja-JP-NaokiNeural" if role=="male" else "ja-JP-AoiNeural"
        ssml.append(f'<voice name="{voice}">{text}</voice>')
    ssml.append("</speak>")
    ssml_text = "".join(ssml)

    # Synthesize
    audio_file = os.path.splitext(filename)[0] + '.mp3'
    out_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_file)
    audio_cfg = speechsdk.audio.AudioOutputConfig(filename=out_path)
    synth = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_cfg)
    synth.speak_ssml_async(ssml_text).get()

    return render_template('result.html', audio_file=audio_file)

@app.route('/download/<audio_file>')
def download(audio_file):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], audio_file), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
