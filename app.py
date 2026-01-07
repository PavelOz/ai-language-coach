import os
import re
import string
import time
from difflib import SequenceMatcher
from dotenv import load_dotenv
import streamlit as st
import azure.cognitiveservices.speech as speechsdk

REFERENCE_TEXT = "I would like a cup of coffee."

# Default thresholds (matching main.py defaults)
DEFAULT_THRESHOLD = 80.0
DEFAULT_MIN_COMPLETENESS = 85.0
DEFAULT_MIN_SIMILARITY = 0.70
DEFAULT_MIN_ACCURACY = 75.0
DEFAULT_MIN_WORDS_FOR_OFF_SCRIPT = 4

def normalize_text(text: str) -> str:
    """Normalize text: lowercase, remove punctuation, collapse spaces."""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()
    return text

def compute_similarity(text1: str, text2: str) -> float:
    """Compute normalized similarity between two texts."""
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    return SequenceMatcher(None, norm1, norm2).ratio()

def get_word_color(accuracy_score: float, error_type: str) -> str:
    """Get color for word based on accuracy score."""
    if error_type and str(error_type) != "None":
        return "red"  # Error type present
    if accuracy_score is None:
        return "red"  # No score available
    if accuracy_score >= 80:
        return "green"
    elif accuracy_score >= 60:
        return "orange"
    else:
        return "red"

def create_color_coded_html(words_data: list, reference_text: str) -> str:
    """Create HTML string with color-coded words based on recognized words."""
    html_parts = []
    
    # Create a mapping: normalized word -> accuracy and error type
    word_map = {}
    for w in words_data:
        word = getattr(w, "word", "")
        if word:
            # Normalize for matching
            word_normalized = normalize_text(word)
            acc = getattr(w, "accuracy_score", None)
            error_type = getattr(w, "error_type", "None")
            word_map[word_normalized] = {"acc": acc, "error": error_type, "original": word}
    
    # Split reference text into words (preserving punctuation)
    reference_words = re.findall(r'\b\w+\b|[^\w\s]', reference_text)
    
    # Color-code each reference word
    for ref_token in reference_words:
        if ref_token.isalnum():  # It's a word
            ref_normalized = normalize_text(ref_token)
            color = "red"  # Default: not found or error
            
            # Try to find matching word in recognized words
            if ref_normalized in word_map:
                acc = word_map[ref_normalized]["acc"]
                error_type = word_map[ref_normalized]["error"]
                color = get_word_color(acc, error_type)
            else:
                # Word not in recognized list - likely omission
                color = "red"
            
            html_parts.append(f'<span style="color: {color}; font-weight: bold; font-size: 1.2em; margin: 0 2px;">{ref_token}</span>')
        else:  # Punctuation
            html_parts.append(f'<span style="font-size: 1.2em;">{ref_token}</span>')
    
    return " ".join(html_parts)

def assess_pronunciation():
    """Run Azure pronunciation assessment and return results."""
    load_dotenv()
    
    key = os.getenv("AZURE_SPEECH_KEY")
    region = os.getenv("AZURE_SPEECH_REGION")
    
    if not key or not region:
        st.error("❌ Missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION in .env file")
        return None
    
    # Configure Azure Speech (identical to main.py)
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_recognition_language = "en-US"
    speech_config.output_format = speechsdk.OutputFormat.Detailed
    
    # Set silence timeouts
    speech_config.set_property(
        speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "15000"
    )
    speech_config.set_property(
        speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "700"
    )
    
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    
    pron_cfg = speechsdk.PronunciationAssessmentConfig(
        reference_text=REFERENCE_TEXT,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Word,
        enable_miscue=True,
    )
    pron_cfg.apply_to(recognizer)
    
    # Record and assess
    t0 = time.perf_counter()
    result = recognizer.recognize_once()
    dt = time.perf_counter() - t0
    
    # Handle errors
    if result.reason == speechsdk.ResultReason.NoMatch:
        return {
            "error": "NoMatch",
            "message": "I didn't hear anything. Please try speaking louder or check your microphone.",
            "latency": dt
        }
    
    if result.reason == speechsdk.ResultReason.Canceled:
        details = speechsdk.CancellationDetails(result)
        return {
            "error": "Canceled",
            "message": f"Recording was canceled: {details.reason}. {details.error_details}",
            "latency": dt
        }
    
    if result.reason != speechsdk.ResultReason.RecognizedSpeech:
        return {
            "error": "Unexpected",
            "message": f"Unexpected result: {result.reason}",
            "latency": dt
        }
    
    # Process successful recognition
    pa = speechsdk.PronunciationAssessmentResult(result)
    
    # Compute similarity
    similarity = compute_similarity(result.text, REFERENCE_TEXT)
    normalized_recognized = normalize_text(result.text)
    recognized_words = len(normalized_recognized.split()) if normalized_recognized else 0
    
    # Classify outcome (exact logic from main.py)
    if recognized_words < DEFAULT_MIN_WORDS_FOR_OFF_SCRIPT:
        outcome = "TOO_SHORT"
    elif similarity < DEFAULT_MIN_SIMILARITY:
        outcome = "OFF_SCRIPT"
    elif pa.completeness_score < DEFAULT_MIN_COMPLETENESS:
        outcome = "INCOMPLETE"
    elif pa.accuracy_score >= DEFAULT_MIN_ACCURACY:
        outcome = "PASS"
    else:
        outcome = "BAD_ACCENT"
    
    return {
        "success": True,
        "recognized_text": result.text,
        "outcome": outcome,
        "similarity": similarity,
        "latency": dt,
        "accuracy_score": pa.accuracy_score,
        "fluency_score": pa.fluency_score,
        "completeness_score": pa.completeness_score,
        "pronunciation_score": pa.pronunciation_score,
        "words": pa.words or [],
    }

# Streamlit UI
st.set_page_config(page_title="AI Language Coach", layout="wide")

st.title("🎯 AI Language Coach (PoC)")

# Display target sentence
st.markdown("### The Stage")
st.markdown(f'<div style="font-size: 2em; font-weight: bold; padding: 20px; background-color: #f0f2f6; border-radius: 10px; text-align: center;">{REFERENCE_TEXT}</div>', 
            unsafe_allow_html=True)

st.markdown("---")

# Recording button
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🎤 Start Recording", type="primary", use_container_width=True):
        with st.spinner("🎙️ Listening..."):
            result = assess_pronunciation()
        
        # Feedback area
        st.markdown("### 📊 Results")
        
        if result is None:
            st.stop()
        
        if "error" in result:
            st.error(f"❌ {result['message']}")
            if "latency" in result:
                st.caption(f"⏱️ Latency: {result['latency']:.2f}s")
            st.stop()
        
        # Display outcome with appropriate styling
        outcome = result["outcome"]
        if outcome == "PASS":
            st.success(f"✅ **{outcome}** - Great job! Your pronunciation is excellent.")
        elif outcome in ["BAD_ACCENT", "OFF_SCRIPT", "INCOMPLETE", "TOO_SHORT"]:
            outcome_messages = {
                "BAD_ACCENT": "⚠️ **BAD_ACCENT** - You said the right words, but pronunciation needs improvement.",
                "OFF_SCRIPT": "❌ **OFF_SCRIPT** - You said something different from the target sentence.",
                "INCOMPLETE": "⚠️ **INCOMPLETE** - You missed part of the sentence.",
                "TOO_SHORT": "⚠️ **TOO_SHORT** - Please say the complete sentence."
            }
            st.warning(outcome_messages.get(outcome, f"⚠️ **{outcome}**"))
        
        # Color-coded sentence
        st.markdown("### 🎨 Your Pronunciation")
        color_coded_html = create_color_coded_html(result["words"], REFERENCE_TEXT)
        st.markdown(f'<div style="padding: 20px; background-color: #f9f9f9; border-radius: 10px; line-height: 2;">{color_coded_html}</div>', 
                    unsafe_allow_html=True)
        
        st.caption("🟢 Green: Excellent (≥80%) | 🟠 Orange: Good (60-80%) | 🔴 Red: Needs Work (<60% or Error)")
        
        # Recognized text
        st.markdown(f"**Recognized:** *{result['recognized_text']}*")
        st.caption(f"Similarity: {result['similarity']:.2f} | Latency: {result['latency']:.2f}s")
        
        # Metrics in columns
        st.markdown("### 📈 Scores")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Accuracy", f"{result['accuracy_score']:.1f}%")
        with col2:
            st.metric("Fluency", f"{result['fluency_score']:.1f}%")
        with col3:
            st.metric("Completeness", f"{result['completeness_score']:.1f}%")
        with col4:
            st.metric("Pronunciation", f"{result['pronunciation_score']:.1f}%")

