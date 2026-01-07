import argparse
import os
import re
import string
import time
from difflib import SequenceMatcher
from dotenv import load_dotenv
import azure.cognitiveservices.speech as speechsdk

REFERENCE_TEXT = "I would like a cup of coffee."

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

def run(threshold: float, lang: str, min_completeness: float, min_similarity: float, min_accuracy: float, min_words_for_off_script: int) -> int:
    load_dotenv()

    key = os.getenv("AZURE_SPEECH_KEY")
    region = os.getenv("AZURE_SPEECH_REGION")
    if not key or not region:
        print("Missing AZURE_SPEECH_KEY / AZURE_SPEECH_REGION in .env")
        return 2

    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_recognition_language = lang
    # Helpful for richer results (optional)
    speech_config.output_format = speechsdk.OutputFormat.Detailed
    # Set silence timeouts to prevent indefinite waiting
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

    print(f"Reference: {REFERENCE_TEXT}")
    print("Speak now (one short utterance).")

    t0 = time.perf_counter()
    result = recognizer.recognize_once()
    dt = time.perf_counter() - t0

    if result.reason == speechsdk.ResultReason.NoMatch:
        print("NoMatch: speech could not be recognized. Try a louder/cleaner mic input.")
        print(f"Latency: {dt:.2f}s")
        return 1

    if result.reason == speechsdk.ResultReason.Canceled:
        details = speechsdk.CancellationDetails(result)
        print(f"Canceled: {details.reason}")
        print(f"Error details: {details.error_details}")
        print(f"Latency: {dt:.2f}s")
        return 1

    if result.reason != speechsdk.ResultReason.RecognizedSpeech:
        print(f"Unexpected result reason: {result.reason}")
        print(f"Latency: {dt:.2f}s")
        return 1

    pa = speechsdk.PronunciationAssessmentResult(result)

    # Compute similarity between recognized and reference text
    similarity = compute_similarity(result.text, REFERENCE_TEXT)
    normalized_recognized = normalize_text(result.text)
    recognized_words = len(normalized_recognized.split()) if normalized_recognized else 0

    # 1. First, did they say something totally different?
    if recognized_words < min_words_for_off_script:
        outcome = "TOO_SHORT"
    elif similarity < min_similarity:
        outcome = "OFF_SCRIPT"  # Check this BEFORE completeness!

    # 2. Second, did they miss half the sentence?
    elif pa.completeness_score < min_completeness:
        outcome = "INCOMPLETE"  # Renamed from TOO_SHORT for clarity

    # 3. Third, did they pronounce it well?
    elif pa.accuracy_score >= min_accuracy:
        outcome = "PASS"
    
    # 4. If none of the above, they said the right words but badly
    else:
        outcome = "BAD_ACCENT" # Use this instead of "TRY_AGAIN" to be specific

    print(f"Latency: {dt:.2f}s")
    print(f"Similarity: {similarity:.2f}")
    print(f"Outcome: {outcome}")
    print("\n--- Summary ---")
    print(f"Recognized: {result.text}")
    print(f"Accuracy:       {pa.accuracy_score:.1f}")
    print(f"Fluency:        {pa.fluency_score:.1f}")
    print(f"Completeness:   {pa.completeness_score:.1f}")
    print(f"Pronunciation:  {pa.pronunciation_score:.1f}")

    problems = []
    for w in (pa.words or []):
        word = getattr(w, "word", "")
        error_type = getattr(w, "error_type", "None")
        acc = getattr(w, "accuracy_score", None)

        # accuracy_score is not meaningful for "Omission" per SDK docs; treat as problem anyway
        is_problem = (error_type is not None and str(error_type) != "None")
        if acc is not None and str(error_type) != "Omission" and acc < threshold:
            is_problem = True

        if is_problem:
            acc_str = "—" if (acc is None or str(error_type) == "Omission") else f"{acc:.1f}"
            problems.append((word, str(error_type), acc_str))

    print("\n--- Problem words ---")
    if not problems:
        print(f"None (threshold={threshold})")
    else:
        for word, err, acc in problems:
            print(f"- {word} | error_type={err} | accuracy={acc}")

    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=80.0, help="Word accuracy threshold (0-100).")
    ap.add_argument("--lang", type=str, default="en-US", help="Locale, e.g., en-US, en-GB.")
    ap.add_argument("--min_completeness", type=float, default=85.0, help="Minimum completeness score for outcome (0-100).")
    ap.add_argument("--min_similarity", type=float, default=0.70, help="Minimum text similarity for outcome (0-1).")
    ap.add_argument("--min_accuracy", type=float, default=75.0, help="Minimum accuracy score for PASS outcome (0-100).")
    ap.add_argument("--min_words_for_off_script", type=int, default=4, help="Minimum word count to consider OFF_SCRIPT (otherwise TOO_SHORT).")
    args = ap.parse_args()
    raise SystemExit(run(args.threshold, args.lang, args.min_completeness, args.min_similarity, args.min_accuracy, args.min_words_for_off_script))
