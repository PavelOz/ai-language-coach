import streamlit as st
import os
import hashlib
import base64
import time
import xml.sax.saxutils
import json
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
def _debug_log(hypothesis_id, location, message, data):
    """Helper function for debug logging"""
    try:
        log_path = r"c:\Users\pavel\azure-speech-pronunciation-poc\.cursor\debug.log"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": hypothesis_id, "location": location, "message": message, "data": data, "timestamp": int(time.time() * 1000)}) + "\n")
    except Exception:
        pass  # Silent fail to not break app

def speed_to_ssml_rate(speed: float) -> str:
    # #region agent log
    _debug_log("B", "app.py:104", "speed_to_ssml_rate entry", {"input_speed": speed})
    # #endregion
    # speed is multiplier like 0.8..1.2
    speed = round(float(speed), 1)
    pct = int(round((speed - 1.0) * 100))
    if pct == 0:
        result = "default"
    else:
        sign = "+" if pct > 0 else ""  # Azure examples use + for positive
        result = f"{sign}{pct}%"
    # #region agent log
    _debug_log("B", "app.py:115", "speed_to_ssml_rate exit", {"rounded_speed": speed, "percentage": pct, "ssml_rate": result})
    # #endregion
    return result

def get_native_audio_path(text, language_code, voice_name, speed_rate):
    # #region agent log
    _debug_log("C", "app.py:121", "get_native_audio_path entry", {"text": text, "language_code": language_code, "voice_name": voice_name, "speed_rate_input": speed_rate, "speed_rate_type": str(type(speed_rate))})
    # #endregion
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

    # #region agent log
    cache_exists = os.path.exists(filepath)
    cache_size = os.path.getsize(filepath) if cache_exists else 0
    _debug_log("A", "app.py:138", "cache check", {"filepath": filepath, "exists": cache_exists, "size": cache_size, "speed_rate": speed_rate, "filename_hash": filename_hash})
    # #endregion

    if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
        # #region agent log
        _debug_log("A", "app.py:141", "returning cached file", {"filepath": filepath, "speed_rate": speed_rate})
        # #endregion
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

    # #region agent log
    _debug_log("B", "app.py:159", "SSML generated", {"ssml_string": ssml_string, "ssml_rate": ssml_rate, "speed_rate": speed_rate})
    # #endregion

    result = synthesizer.speak_ssml_async(ssml_string).get()

    # #region agent log
    _debug_log("E", "app.py:165", "Azure synthesis result", {"reason": str(result.reason), "reason_name": result.reason.name if hasattr(result.reason, 'name') else str(result.reason)})
    # #endregion

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        # #region agent log
        _debug_log("E", "app.py:168", "synthesis completed", {"filepath": filepath, "speed_rate": speed_rate})
        # #endregion
        return filepath, readable_name

    if result.reason == speechsdk.ResultReason.Canceled:
        details = speechsdk.SpeechSynthesisCancellationDetails.from_result(result)
        # This will tell you if SSML was invalid / key/region issues / etc.
        # #region agent log
        _debug_log("E", "app.py:174", "synthesis canceled", {"reason": str(details.reason), "error_details": details.error_details})
        # #endregion
        st.error(f"TTS canceled: {details.reason} | {details.error_details}")

    return None, None

def render_player(file_path, speed_rate):
    # #region agent log
    _debug_log("D", "app.py:197", "render_player called", {"file_path": file_path, "speed_rate": speed_rate, "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0})
    # #endregion
    with open(file_path, "rb") as f:
        audio_bytes = f.read()
    
    # Use Streamlit's native audio player with cache-busting key
    # The key includes speed_rate to force re-render when speed changes
    audio_key = f"audio_{speed_rate}_{file_path}_{int(time.time())}"
    
    # #region agent log
    _debug_log("D", "app.py:205", "audio player rendered", {"audio_key": audio_key, "speed_rate": speed_rate, "data_length": len(audio_bytes)})
    # #endregion
    
    # Use Streamlit's native audio component - it handles caching properly
    st.audio(audio_bytes, format="audio/wav", autoplay=False)

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

# #region agent log
_debug_log("C", "app.py:272", "slider value captured", {"speed_val": speed_val, "speed_val_type": str(type(speed_val)), "clean_text": clean_text, "lang_code": lang_code, "voice_name": voice_name})
# #endregion

# Logic
audio_filepath, audio_filename = get_native_audio_path(clean_text, lang_code, voice_name, speed_val)

# #region agent log
_debug_log("D", "app.py:279", "audio path returned", {"audio_filepath": audio_filepath, "audio_filename": audio_filename, "speed_val": speed_val, "file_exists": os.path.exists(audio_filepath) if audio_filepath else False})
# #endregion

# Debug panel (can be collapsed)
with st.expander("🔍 Debug Info", expanded=False):
    st.write("**Speed Slider Value:**", speed_val)
    st.write("**SSML Rate:**", speed_to_ssml_rate(speed_val))
    st.write("**Language Code:**", lang_code)
    st.write("**Voice Name:**", voice_name)
    st.write("**Clean Text:**", clean_text)
    
    if audio_filepath:
        st.write("**Audio File Path:**", audio_filepath)
        st.write("**File Exists:**", os.path.exists(audio_filepath))
        if os.path.exists(audio_filepath):
            st.write("**File Size:**", os.path.getsize(audio_filepath), "bytes")
        
        # Show the SSML that would be generated
        ssml_rate = speed_to_ssml_rate(speed_val)
        safe_text = xml.sax.saxutils.escape(clean_text)
        ssml_string = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang_code}">
  <voice name="{voice_name}">
    <prosody rate="{ssml_rate}">{safe_text}</prosody>
  </voice>
</speak>"""
        st.code(ssml_string, language="xml")
        
        # Show cache info
        filename_hash = hashlib.md5(
            f"{lang_code}_{voice_name}_{clean_text}_{speed_val}".encode("utf-8")
        ).hexdigest()
        st.write("**Cache Hash:**", filename_hash)
        st.write("**Expected Cache File:**", f"{filename_hash}_x{speed_val}.wav")
    else:
        st.warning("No audio file path returned")

if audio_filepath and os.path.exists(audio_filepath):
    # Visual feedback for non-standard speeds
    if speed_val != 1.0:
        st.markdown('<div style="border: 3px solid #6610f2; border-radius: 10px; padding: 10px; margin: 10px 0;">', unsafe_allow_html=True)
    
    render_player(audio_filepath, speed_val)
    
    if speed_val != 1.0:
        st.markdown('</div>', unsafe_allow_html=True)
    
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