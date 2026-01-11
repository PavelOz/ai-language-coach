import streamlit as st
import os
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

# --- CUSTOM STYLING (CSS) ---
# This makes the buttons huge and high-contrast
def local_css():
    st.markdown("""
        <style>
        /* 1. Style the 'Play Native Audio' Button */
        div.stButton > button {
            width: 100%;             /* Full width */
            height: 80px;            /* Very tall */
            font-size: 35px !important; /* Huge text */
            font-weight: bold;
            border-radius: 20px;     /* Rounded corners (friendly) */
            background-color: #f0f2f6; 
            border: 2px solid #d1d1d1;
            transition: all 0.3s;
        }
        div.stButton > button:hover {
            border-color: #4CAF50;
            color: #4CAF50;
            transform: scale(1.02);
        }

        /* 2. Scale up the Recording Widget */
        /* We zoom the entire widget by 1.3x */
        div[data-testid="stAudioInput"] {
            transform: scale(1.3);
            transform-origin: center left;
            margin-top: 20px;
            margin-bottom: 40px;
        }
        
        /* 3. Make the Target Text Huge */
        .big-font {
            font-size: 40px !important;
            font-weight: 700;
            color: #2c3e50;
            line-height: 1.4;
        }
        </style>
    """, unsafe_allow_html=True)

# --- CONFIGURATION: LANGUAGES & VOICES ---
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
st.set_page_config(page_title="AI Coach", page_icon="🧸") # Teddy bear icon for friendliness
local_css() # <--- INJECT THE CSS HERE

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
            st.warning("No levels yet.")
    else:
        st.markdown(f"Type **{selected_lang_label}** text:")
        default_text = "你好" if "Chinese" in selected_lang_label else "Hello friend"
        target_text = st.text_area("Text:", value=default_text)

# MAIN APP
st.title(f"{current_lang_config['flag']} Language Coach")

if not target_text:
    st.stop()

clean_text = target_text.split("(")[0].strip()

# 1. BIG TARGET TEXT
st.markdown(f'<p class="big-font">{clean_text}</p>', unsafe_allow_html=True)

# 2. HUGE "LISTEN" BUTTON
# We use a button to trigger audio playback because we can style buttons easily
if st.button("🔊 LISTEN NOW"):
    audio_data = get_native_audio(clean_text, lang_code, voice_name)
    if audio_data:
        # We play it immediately using st.audio but hidden, or just visible below
        st.audio(audio_data, format="audio/wav", autoplay=True)

st.write("---")

# 3. SCALED UP RECORDING WIDGET
st.markdown("### 👇 TAP TO RECORD")
# The CSS above will zoom this widget by 1.3x
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
        
        # Simple "Traffic Light" Feedback
        if pa.accuracy_score >= 80:
            st.balloons() # Fun reward!
            st.success(f"PERFECT! Score: {int(pa.accuracy_score)}")
        elif pa.accuracy_score >= 60:
            st.warning(f"GOOD! Score: {int(pa.accuracy_score)}")
        else:
            st.error(f"TRY AGAIN. Score: {int(pa.accuracy_score)}")
        
        # Large Word Breakdown
        html_string = "<div style='font-size:24px; line-height:2.0;'>"
        for w in pa.words:
            color = "green" if w.accuracy_score >= THRESHOLD else "red"
            if w.error_type == "Omission": color = "gray"
            html_string += f"<span style='background-color:{'#e8f5e9' if color=='green' else '#ffebee'}; padding: 5px 10px; border-radius: 10px; margin-right:5px; color:{color};'><b>{w.word}</b></span>"
        html_string += "</div>"
        
        st.markdown(html_string, unsafe_allow_html=True)

    elif result.reason == speechsdk.ResultReason.NoMatch:
        st.info("🎤 I didn't hear anything. Tap Record again!")