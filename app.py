import streamlit as st
import os
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

# --- CUSTOM STYLING (CSS) ---
def local_css():
    st.markdown("""
        <style>
        /* 1. The 'Flashcard' Container (Forces White Background) */
        .flashcard {
            background-color: #ffffff;
            padding: 30px;
            border-radius: 20px;
            border: 2px solid #e0e0e0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            text-align: center;
        }
        
        /* 2. The Target Text (Always Dark on White) */
        .big-font {
            font-size: 32px !important;
            font-weight: 700;
            color: #1a1a1a !important; /* Force Black */
            line-height: 1.4;
            margin: 0;
        }
        
        /* 3. The 'Play' Button (High Contrast Blue) */
        div.stButton > button {
            width: 100%;
            height: 70px;
            font-size: 28px !important;
            font-weight: bold;
            color: #ffffff !important;
            background-color: #007bff !important; /* Bright Blue */
            border: none;
            border-radius: 15px;
            transition: transform 0.1s;
        }
        div.stButton > button:active {
            transform: scale(0.98); /* Click effect */
            background-color: #0056b3 !important;
        }
        
        /* 4. Zoomed Recording Widget */
        div[data-testid="stAudioInput"] {
            transform: scale(1.3);
            transform-origin: center left;
            margin-top: 10px;
            margin-bottom: 30px;
        }
        
        /* 5. Result Badges */
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
def get_native_audio(text, language_code, voice_name):
    cache_key = f"audio_{language_code}_{text}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_synthesis_voice_name = voice_name
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synthesizer.speak_text_async(text).get()
    
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        st.session_state[cache_key] = result.audio_data
        return result.audio_data
    return None

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

# --- 1. THE FLASHCARD (Visuals) ---
st.markdown(f"""
<div class="flashcard">
    <p class="big-font">{clean_text}</p>
</div>
""", unsafe_allow_html=True)

# --- 2. AUDIO CONTROLS (Logic) ---
# Ensure audio is generated/cached
audio_data = get_native_audio(clean_text, lang_code, voice_name)

# A. The Big "Play" Button (Triggers Autoplay)
if st.button("🔊 PLAY AUDIO"):
    # This forces a rerun with autoplay=True
    st.session_state['auto_play_trigger'] = True

# B. The Persistent Player (Always visible for replaying)
if audio_data:
    # Check if we should autoplay (triggered by button)
    should_autoplay = st.session_state.get('auto_play_trigger', False)
    
    # Render the player
    st.audio(audio_data, format="audio/wav", autoplay=should_autoplay)
    
    # Reset trigger so it doesn't autoplay on EVERY interaction (like recording)
    if should_autoplay:
        st.session_state['auto_play_trigger'] = False

st.write("---")

# --- 3. RECORDING ---
st.markdown("### 👇 TAP TO RECORD")
audio_input = st.audio_input("Record", key=f"rec_{lang_code}_{clean_text[:5]}")

if audio_input is not None:
    st.spinner("Thinking...")
    
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
        
        # High Contrast Feedback Boxes
        if score >= 80:
            st.markdown(f'<div class="result-box" style="background-color:#d4edda; color:#155724;">🎉 PERFECT! Score: {score}</div>', unsafe_allow_html=True)
            st.balloons()
        elif score >= 60:
            st.markdown(f'<div class="result-box" style="background-color:#fff3cd; color:#856404;">⚠️ GOOD! Score: {score}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="result-box" style="background-color:#f8d7da; color:#721c24;">❌ TRY AGAIN. Score: {score}</div>', unsafe_allow_html=True)
        
        # Word Breakdown
        st.write("") # Spacer
        html_string = "<div style='font-size:24px; line-height:2.2; text-align:center;'>"
        for w in pa.words:
            color = "#28a745" if w.accuracy_score >= THRESHOLD else "#dc3545" # High contrast Green/Red
            if w.error_type == "Omission": color = "#6c757d" # Grey
            
            html_string += f"<span style='border: 2px solid {color}; padding: 5px 12px; border-radius: 12px; margin: 0 4px; color:{color}; font-weight:bold;'>{w.word}</span>"
        html_string += "</div>"
        
        st.markdown(html_string, unsafe_allow_html=True)

    elif result.reason == speechsdk.ResultReason.NoMatch: