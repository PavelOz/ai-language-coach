import streamlit as st
import os
import hashlib
import base64
import time
import xml.sax.saxutils
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

# --- CUSTOM STYLING (CSS) ---
def local_css():
    st.markdown("""
        <style>
        .flashcard {
            background-color: #ffffff;
            padding: 30px;
            border-radius: 20px;
            border: 2px solid #e0e0e0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            text-align: center;
        }
        .big-font {
            font-size: 32px !important;
            font-weight: 700;
            color: #1a1a1a !important;
            line-height: 1.4;
            margin: 0;
        }
        audio {
            width: 80%; 
            height: 60px;
            transform: scale(1.3);
            transform-origin: center;
            margin: 20px auto;
            display: block;
            border-radius: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        /* Visual feedback for non-standard speeds */
        .custom-speed audio {
            border: 3px solid #6610f2; /* Purple border for Custom Speed */
        }
        div[data-testid="stAudioInput"] {
            transform: scale(1.3);
            transform-origin: center left;
            margin-top: 20px;
            margin-bottom: 40px;
        }
        .result-box {
            font-size: 20px; 
            padding: 15px; 
            border-radius: 10px; 
            margin-top: 10px;
            text-align: center;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)

# --- CONFIGURATION ---
LANGUAGES = {
    "English (US)": {"code": "en-US", "voice": "en-US-AndrewMultilingualNeural", "flag": "🇺🇸"},
    "Chinese (Mandarin)": {"code": "zh-CN", "voice": "zh-CN-YunxiNeural", "flag": "🇨🇳"},
    "Spanish (Mexico)": {"code": "es-MX", "voice": "es-MX-JorgeNeural", "flag": "🇲🇽"},
    "French (France)": {"code": "fr-FR", "voice": "fr-FR-DeniseNeural", "flag": "🇫🇷"}
}

COURSE_CONTENT = {
    "en-US": {
        "Level 1: Coffee Shop": ["I would like a cup of coffee.", "No sugar, please."],
        "Level 2: Business": ["I have experience in data science.", "Let's schedule a meeting."]
    },
    "zh-CN": {
        "Level 1: Basics": ["你好 (Hello)", "谢谢 (Thank you)", "我想喝咖啡 (I want coffee)"],
        "Level 2: Travel": ["在这个路口左转 (Turn left)", "多少钱? (How much?)"]
    },
    "es-MX": {"Level 1: Basics": ["Hola, ¿cómo estás?", "Una mesa para dos, por favor."]},
    "fr-FR": {"Level 1: Basics": ["Bonjour, je m'appelle Paul.", "Un croissant, s'il vous plaît."]}
}

THRESHOLD = 80.0

# --- SETUP AZURE ---
load_dotenv()
speech_key = os.getenv("AZURE_SPEECH_KEY")
speech_region = os.getenv("AZURE_SPEECH_REGION")

if not speech_key or not speech_region:
    st.error("Missing Azure Keys! Check .env file.")
    st.stop()

# --- HELPER FUNCTIONS ---
def speed_to_ssml_rate(speed: float) -> str:
    # speed is multiplier like 0.8..1.2
    speed = round(float(speed), 1)
    pct = int(round((speed - 1.0) * 100))
    if pct == 0:
        return "default"
    sign = "+" if pct > 0 else ""  # Azure examples use + for positive
    return f"{sign}{pct}%"

def get_native_audio_path(text, language_code, voice_name, speed_rate):
    speed_rate = round(float(speed_rate), 1)
    ssml_rate = speed_to_ssml_rate(speed_rate)

    # Include voice_name so cache doesn't mix voices
    filename_hash = hashlib.md5(
        f"{language_code}_{voice_name}_{text}_{speed_rate}".encode("utf-8")
    ).hexdigest()

    folder = "audio_cache"
    readable_name = f"{filename_hash}_x{speed_rate}.wav"
    filepath = os.path.join(folder, readable_name)

    os.makedirs(folder, exist_ok=True)

    if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
        return filepath, readable_name

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    audio_config = speechsdk.audio.AudioOutputConfig(filename=filepath)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

    safe_text = xml.sax.saxutils.escape(text)

    ssml_string = f"""
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{language_code}">
  <voice name="{voice_name}">
    <prosody rate="{ssml_rate}">{safe_text}</prosody>
  </voice>
</speak>
""".strip()

    result = synthesizer.speak_ssml_async(ssml_string).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return filepath, readable_name

    if result.reason == speechsdk.ResultReason.Canceled:
        details = speechsdk.SpeechSynthesisCancellationDetails.from_result(result)
        # This will tell you if SSML was invalid / key/region issues / etc.
        st.error(f"TTS canceled: {details.reason} | {details.error_details}")

    return None, None

def render_player(file_path, speed_rate):
    with open(file_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    
    # Unique ID every time to force browser reload
    unique_id = f"PLAYER_{speed_rate}_{int(time.time())}"
    
    # Purple border if not 1.0 (Visual Feedback)
    border_style = "border: 4px solid #6610f2;" if speed_rate != 1.0 else ""

    md = f"""
        <audio controls id="{unique_id}" style="display:block; {border_style}">
            <source src="data:audio/wav;base64,{b64}" type="audio/wav">
        </audio>
    """
    st.markdown(md, unsafe_allow_html=True)

# --- UI LAYOUT ---
st.set_page_config(page_title="AI Coach", page_icon="🧸") 
local_css()

# SIDEBAR
with st.sidebar:
    st.header("⚙️ Settings")
    selected_lang_label = st.selectbox("Language:", list(LANGUAGES.keys()))
    current_lang_config = LANGUAGES[selected_lang_label]
    lang_code = current_lang_config["code"]
    voice_name = current_lang_config["voice"]
    
    st.divider()
    mode = st.radio("Mode:", ["📚 Course", "✍️ Freestyle"])
    
    target_text = ""
    if mode == "📚 Course":
        content = COURSE_CONTENT.get(lang_code, {})
        if content:
            level = st.selectbox("Level:", list(content.keys()))
            target_text = st.selectbox("Phrase:", content[level])
        else:
            st.warning("No levels.")
    else:
        st.markdown(f"Type **{selected_lang_label}** text:")
        default_text = "你好" if "Chinese" in selected_lang_label else "Hello friend"
        target_text = st.text_area("Text:", value=default_text)

# MAIN APP
st.title(f"{current_lang_config['flag']} AI Language Coach")

if not target_text:
    st.stop()

clean_text = target_text.split("(")[0].strip()

# --- 1. THE FLASHCARD ---
st.markdown(f"""
<div class="flashcard">
    <p class="big-font">{clean_text}</p>
</div>
""", unsafe_allow_html=True)

# --- 2. AUDIO PLAYER ---
st.write("🔊 **Playback Speed:**")
# The Slider!
speed_val = st.slider("Select Speed", min_value=0.5, max_value=1.2, value=1.0, step=0.1, label_visibility="collapsed")
speed_val = round(float(speed_val), 1)

# Logic
audio_filepath, audio_filename = get_native_audio_path(clean_text, lang_code, voice_name, speed_val)

if audio_filepath and os.path.exists(audio_filepath):
    render_player(audio_filepath, speed_val)
    
    # Download Button
    with open(audio_filepath, "rb") as f:
        file_bytes = f.read()
    st.download_button(
        label=f"⬇️ Download ({speed_val}x)",
        data=file_bytes,
        file_name=f"audio_x{speed_val}.wav",
        mime="audio/wav"
    )

st.write("---")

# --- 3. RECORDING ---
st.markdown("### 👇 TAP TO RECORD")
audio_input = st.audio_input("Record", key=f"rec_{lang_code}_{clean_text[:5]}")

if audio_input is not None:
    with st.spinner("Thinking..."):
        with open("temp_input.wav", "wb") as f:
            f.write(audio_input.read())

        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
        speech_config.speech_recognition_language = lang_code
        audio_config = speechsdk.audio.AudioConfig(filename="temp_input.wav")
        
        pron_cfg = speechsdk.PronunciationAssessmentConfig(
            reference_text=clean_text,
            grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
            enable_miscue=True
        )
        
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        pron_cfg.apply_to(recognizer)
        
        result = recognizer.recognize_once()
    
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        pa = speechsdk.PronunciationAssessmentResult(result)
        score = int(pa.accuracy_score)
        
        if score >= 80:
            st.markdown(f'<div class="result-box" style="background-color:#d4edda; color:#155724;">🎉 PERFECT! Score: {score}</div>', unsafe_allow_html=True)
            st.balloons()
        elif score >= 60:
            st.markdown(f'<div class="result-box" style="background-color:#fff3cd; color:#856404;">⚠️ GOOD! Score: {score}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="result-box" style="background-color:#f8d7da; color:#721c24;">❌ TRY AGAIN. Score: {score}</div>', unsafe_allow_html=True)
        
        st.write("") 
        html_string = "<div style='font-size:24px; line-height:2.2; text-align:center;'>"
        for w in pa.words:
            color = "#28a745" if w.accuracy_score >= THRESHOLD else "#dc3545"
            if w.error_type == "Omission": color = "#6c757d"
            html_string += f"<span style='border: 2px solid {color}; padding: 5px 12px; border-radius: 12px; margin: 0 4px; color:{color}; font-weight:bold;'>{w.word}</span>"
        html_string += "</div>"
        
        st.markdown(html_string, unsafe_allow_html=True)

    elif result.reason == speechsdk.ResultReason.NoMatch:
        st.info("🎤 I didn't hear anything. Tap Record again!")