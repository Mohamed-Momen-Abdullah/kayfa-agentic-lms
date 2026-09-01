import io
import os
from typing import Optional

import librosa
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
except Exception as exc:  # pragma: no cover - loaded at runtime
    print(f"⚠️ Speech-to-text model could not be loaded: {exc}")
    processor = None
    model = None


def transcribe_audio_bytes(audio_bytes: bytes, sample_rate: int = 16000) -> str:
    if processor is None or model is None:
        raise RuntimeError("Speech-to-text model is not available.")

    audio_array, _ = librosa.load(io.BytesIO(audio_bytes), sr=sample_rate, mono=True)

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
    with open(file_path, "rb") as f:
        return transcribe_audio_bytes(f.read(), sample_rate=sample_rate)
