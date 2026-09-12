from app.core.config import settings


def transcribe_audio(file_bytes: bytes, filename: str = "audio.webm", language: str = "ar") -> str:
    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    transcription = client.audio.transcriptions.create(
        file=(filename, file_bytes),
        model="whisper-large-v3-turbo",
        language=language,
        response_format="json",
        temperature=0.0,
    )
    return transcription.text