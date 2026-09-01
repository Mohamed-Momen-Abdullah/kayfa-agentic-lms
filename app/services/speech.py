import io
import os
from typing import Optional

import librosa
import soundfile as sf
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

MODEL_NAME = os.getenv("ASR_MODEL_NAME", "jonatasgrosman/wav2vec2-large-xlsr-53-arabic")

processor: Optional[Wav2Vec2Processor] = None
model: Optional[Wav2Vec2ForCTC] = None
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

try:
    processor = Wav2Vec2Processor.from_pretrained(MODEL_NAME)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL_NAME).to(device)
    model.eval()
except Exception as exc:
    print(f"⚠️ Speech-to-text model could not be loaded: {exc}")
    processor = None
    model = None


def transcribe_audio_bytes(audio_bytes: bytes, sample_rate: int = 16000) -> str:
    if processor is None or model is None:
        raise RuntimeError("Speech-to-text model is not available.")

    # FIX: Use soundfile directly to decode in-memory bytes
    buffer = io.BytesIO(audio_bytes)
    audio_array, native_sr = sf.read(buffer)

    # Convert stereo to mono if necessary
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    # Resample if the input sample rate doesn't match the required 16kHz
    if native_sr != sample_rate:
        audio_array = librosa.resample(audio_array, orig_sr=native_sr, target_sr=sample_rate)

    inputs = processor(
        audio_array,
        sampling_rate=sample_rate,
        return_tensors="pt",
        padding=True,
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}

    with torch.no_grad():
        logits = model(**inputs).logits

    predicted_ids = torch.argmax(logits, dim=-1)
    text = processor.batch_decode(predicted_ids)[0].strip()
    return text


def transcribe_audio_file(file_path: str, sample_rate: int = 16000) -> str:
    # FIX: Pass file path directly to librosa when loading from a local file
    if processor is None or model is None:
        raise RuntimeError("Speech-to-text model is not available.")

    audio_array, _ = librosa.load(file_path, sr=sample_rate, mono=True)

    inputs = processor(
        audio_array,
        sampling_rate=sample_rate,
        return_tensors="pt",
        padding=True,
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}

    with torch.no_grad():
        logits = model(**inputs).logits

    predicted_ids = torch.argmax(logits, dim=-1)
    text = processor.batch_decode(predicted_ids)[0].strip()
    return text


def main():
    audio_file_path = r"D:\kayfa-agentic-lms\audio.wav"
    try:
        transcript = transcribe_audio_file(audio_file_path)
        print(f"Transcribed text: {transcript}")
    except Exception as e:
        print(f"Error during transcription: {e}")

if __name__ == "__main__":
    main()