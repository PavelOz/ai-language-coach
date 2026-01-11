import streamlit as st
import os
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

# --- CONFIGURATION: LANGUAGES & VOICES ---
LANGUAGES = {
    "English (US)": {
        "code": "en-US",
        "voice": "en-US-AndrewMultilingualNeural",
        "flag": "🇺🇸"
    },
    "Chinese (Mandarin, Simplified)": {
        "code": "zh-CN",
        "voice": "zh-CN-YunxiNeural",
        "flag": "🇨🇳"
    },
    "Spanish (Mexico)": {
        "code": "es-MX",
        "voice": "es-MX-JorgeNeural",
        "flag": "🇲🇽"
    },
    "French (France)": {
        "code": "fr-FR",
        "voice": "fr-FR-DeniseNeural",
        "flag": "🇫🇷"
    }
}

# --- CONFIGURATION: THE COURSE CONTENT ---
# We organize levels by language so they don't get mixed up
COURSE_CONTENT = {
    "en-US": {
        "Level 1: Coffee Shop": ["I would like a cup of coffee.", "No sugar, please."],
        "Level 2: Business": ["I have experience in data science.", "Let's schedule a meeting."]
    },
    "zh-CN": {
        "Level 1: Basics": [
            "你好 (Hello)", 
            "谢谢 (Thank you)", 
            "我想喝咖啡 (I want coffee)"
        ],
        "Level 2: Travel": [
            "在这个路口左转 (Turn left at this intersection)",
            "多少钱? (How much is it?)"
        ]
    },
    "es-MX": {
        "Level 1: Basics": ["Hola, ¿cómo estás?", "Una mesa para dos, por favor."],
    },
    "fr-FR": {
        "Level 1: Basics": ["Bonjour, je m'appelle Paul.", "Un croissant, s'il vous plaît."],
    }
}

THRESHOLD = 80.0

# --- SETUP AZURE ---
load_dotenv()
speech_key = os.getenv("AZURE_SPEECH_KEY")
speech_region = os.getenv("AZURE_SPEECH_REGION")

if not speech_key or not speech_region:
    st.error("Missing Azure Keys! Check .env file or Streamlit Secrets.")
    st.stop()

# --- HELPER FUNCTIONS ---
def get_native_audio(text, language_code, voice_name):
    """Generates audio using the specific voice for that language"""
    # Cache key includes voice name so we don't mix languages
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
st.set_page_config(page_title="Polyglot AI Coach", page_icon="🌍")

# SIDEBAR: SETTINGS
with st.sidebar:
    st.header("🌍 Settings")
    
    # 1. Select Language
    selected_lang_label = st.selectbox("Language:", list(LANGUAGES.keys()))
    current_lang_config = LANGUAGES[selected_lang_label]
    lang_code = current_lang_config["code"]
    voice_name = current_lang_config["voice"]
    
    st.divider()
    
    # 2. Select Mode
    st.header("🎮 Mode")
    mode = st.radio("Choose Mode:", ["📚 Course Library", "✍️ Freestyle"])
    
    target_text = ""
    
    if mode == "📚 Course Library":
        # Get content for the selected language (default to empty dict if missing)
        content = COURSE_CONTENT.get(lang_code, {})
        if content:
            selected_level_name = st.selectbox("Scenario:", list(content.keys()))
            sentences = content[selected_level_name]
            target_text = st.selectbox("Select a phrase:", sentences)
        else:
            st.warning("No preset levels for this language. Switch to Freestyle!")
            
    else: # Freestyle Mode
        st.markdown(f"Type any **{selected_lang_label}** sentence.")
        # Default placeholder changes based on language
        default_text = "你好" if "Chinese" in selected_lang_label else "Hello world"
        target_text = st.text_area("Target Text:", value=default_text)

# MAIN APP
st.title(f"{current_lang_config['flag']} AI Language Coach")

if not target_text:
    st.info("Select a sentence or type one to begin.")
    st.stop()

# Clean text for display (remove parenthesis translations if they exist in presets)
display_text = target_text.split("(")[0].strip()

st.divider()

# 1. THE LISTENING PHASE
st.markdown("### 1. Listen")
st.markdown(f"## **{display_text}**")

if st.button("▶️ Play Native Audio"):
    # We pass the voice_name explicitly now
    audio_data = get_native_audio(display_text, lang_code, voice_name)
    if audio_data:
        st.audio(audio_data, format="audio/wav")

st.divider()

# 2. THE SPEAKING PHASE
st.markdown("### 2. Speak")

audio_input = st.audio_input("Record your voice", key=f"rec_{lang_code}_{display_text[:5]}")

if audio_input is not None:
    st.spinner("Analyzing...")
    
    with open("temp_input.wav", "wb") as f:
        f.write(audio_input.read())

    # Configure Azure Analysis with DYNAMIC Language
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = lang_code  # <--- CRITICAL CHANGE
    audio_config = speechsdk.audio.AudioConfig(filename="temp_input.wav")
    
    pron_cfg = speechsdk.PronunciationAssessmentConfig(
        reference_text=display_text,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme, # Phoneme is better for Chinese tones!
        enable_miscue=True
    )
    
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    pron_cfg.apply_to(recognizer)
    
    result = recognizer.recognize_once()
    
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        pa = speechsdk.PronunciationAssessmentResult(result)
        
        color = "green" if pa.accuracy_score >= THRESHOLD else "red"
        outcome_msg = "EXCELLENT!" if pa.accuracy_score >= THRESHOLD else "NEEDS PRACTICE"
        
        st.markdown(f"### Result: :{color}[{outcome_msg}]")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Accuracy", int(pa.accuracy_score))
        c2.metric("Fluency", int(pa.fluency_score))
        c3.metric("Completeness", int(pa.completeness_score))
        c4.metric("Pronunciation", int(pa.pronunciation_score))
        
        # Word Breakdown (Works for Chinese characters too!)
        html_string = ""
        for w in pa.words:
            word_color = "green" if w.accuracy_score >= THRESHOLD else "red"
            if w.error_type == "Omission":
                word_color = "gray"
            # Add margin for English, less for Chinese characters usually, but margin-right:5px is safe
            html_string += f"<span style='color:{word_color}; font-size:24px; font-weight:bold; margin-right:5px;'>{w.word}</span>"
        
        st.markdown(html_string, unsafe_allow_html=True)

    elif result.reason == speechsdk.ResultReason.NoMatch:
        st.warning("Could not hear you clearly. Try again.")