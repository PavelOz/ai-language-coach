import streamlit as st
import os
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

# --- CONFIGURATION: THE COURSE CONTENT ---
LEVELS = {
    "Level 1: The Coffee Shop": [
        "I would like a cup of coffee.",
        "Can I pay with a credit card?",
        "No sugar, please."
    ],
    "Level 2: The Taxi Driver": [
        "Take me to the airport, please.",
        "How much is the fare?",
        "Stop here, this is my hotel."
    ],
    "Level 3: The Job Interview": [
        "I have five years of experience in data science.",
        "I work well under pressure.",
        "Do you have any questions for me?"
    ],
    "Level 4: Daily Life": [
        "Where is the nearest supermarket?",
        "I am looking for the subway station.",
        "Could you help me with this?"
    ]
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
def get_native_audio(text):
    """Generates audio from text using Azure TTS"""
    if f"audio_{text}" in st.session_state:
        return st.session_state[f"audio_{text}"]

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_synthesis_voice_name = "en-US-AndrewMultilingualNeural" 
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    
    result = synthesizer.speak_text_async(text).get()
    
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        st.session_state[f"audio_{text}"] = result.audio_data
        return result.audio_data
    return None

# --- UI LAYOUT ---
st.set_page_config(page_title="AI Coach", page_icon="🎧")

# SIDEBAR: MODE SELECTION
with st.sidebar:
    st.header("🎮 Game Mode")
    mode = st.radio("Choose Mode:", ["📚 Course Library", "✍️ Freestyle"])
    
    st.divider()
    
    # Logic for selecting the target sentence
    if mode == "📚 Course Library":
        selected_level_name = st.selectbox("Scenario:", list(LEVELS.keys()))
        # Progress Bar (Visual only)
        st.progress(0.5, text="Level Progress")
        sentences = LEVELS[selected_level_name]
        target_text = st.selectbox("Select a phrase:", sentences)
        
    else: # Freestyle Mode
        st.markdown("Type any sentence you want to practice.")
        target_text = st.text_area("Target Text:", "The quick brown fox jumps over the lazy dog.")

# MAIN APP
st.title("AI Language Coach")

if not target_text:
    st.warning("Please enter some text to start.")
    st.stop()

st.divider()

# 1. THE LISTENING PHASE
st.markdown("### 1. Listen")
st.info(f"Target: **{target_text}**")

# Play Audio
if st.button("▶️ Play Native Audio"):
    audio_data = get_native_audio(target_text)
    if audio_data:
        st.audio(audio_data, format="audio/wav")

st.divider()

# 2. THE SPEAKING PHASE
st.markdown("### 2. Speak")

# Unique key ensures widget resets if text changes
audio_input = st.audio_input("Record your voice", key=f"rec_{target_text[:10]}")

if audio_input is not None:
    st.spinner("Analyzing...")
    
    # Save browser audio
    with open("temp_input.wav", "wb") as f:
        f.write(audio_input.read())

    # Configure Azure Analysis
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = "en-US"
    audio_config = speechsdk.audio.AudioConfig(filename="temp_input.wav")
    
    pron_cfg = speechsdk.PronunciationAssessmentConfig(
        reference_text=target_text,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Word,
        enable_miscue=True
    )
    
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    pron_cfg.apply_to(recognizer)
    
    result = recognizer.recognize_once()
    
    # Display Results
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        pa = speechsdk.PronunciationAssessmentResult(result)
        
        color = "green" if pa.accuracy_score >= THRESHOLD else "red"
        outcome_msg = "EXCELLENT!" if pa.accuracy_score >= THRESHOLD else "NEEDS PRACTICE"
        
        st.markdown(f"### Result: :{color}[{outcome_msg}]")
        
        # Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Accuracy", int(pa.accuracy_score))
        c2.metric("Fluency", int(pa.fluency_score))
        c3.metric("Completeness", int(pa.completeness_score))
        c4.metric("Pronunciation", int(pa.pronunciation_score))
        
        # Word Breakdown
        html_string = ""
        for w in pa.words:
            word_color = "green" if w.accuracy_score >= THRESHOLD else "red"
            if w.error_type == "Omission":
                word_color = "gray"
            html_string += f"<span style='color:{word_color}; font-size:20px; font-weight:bold; margin-right:5px;'>{w.word}</span>"
        
        st.markdown(html_string, unsafe_allow_html=True)

    elif result.reason == speechsdk.ResultReason.NoMatch:
        st.warning("Could not hear you clearly. Try again.")