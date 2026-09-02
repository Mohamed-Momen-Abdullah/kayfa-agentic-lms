import os
import re
import pickle
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SENTIMENT_MODEL_PATH = os.getenv("SENTIMENT_MODEL_PATH", os.path.join(BASE_DIR, "sentiment_model_glove.keras"))
TOKENIZER_PATH = os.getenv("TOKENIZER_PATH", os.path.join(BASE_DIR, "tokenizer.pkl"))

class SentimentAnalyzer:
    def __init__(self):
        try:
            self.model = load_model(SENTIMENT_MODEL_PATH, compile=False)
            with open(TOKENIZER_PATH, "rb") as f:
                self.tokenizer = pickle.load(f)
            self.max_len = 50
            self.labels = ["Negative", "Positive"]
            self.available = True
        except Exception as e:
            print(f"⚠️ Sentiment analyzer could not be loaded: {e}")
            self.available = False

    def predict(self, text: str) -> dict:
        if not self.available:
            return None
        seq = self.tokenizer.texts_to_sequences([text])
        pad = pad_sequences(seq, maxlen=self.max_len, padding="post")
        pred = self.model.predict(pad, verbose=0)
        label = int(np.argmax(pred))
        confidence = float(pred[0][label])
        return {"label": self.labels[label], "confidence": confidence}

sentiment_engine = SentimentAnalyzer()

def arabic_tokenizer(text: str):
    return re.findall(r"[\u0600-\u06FF]+|\w+", text.lower())

def clean_markdown_formatting(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'(?m)^#{1,6}\s*', '', text) 
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text) 
    text = text.replace('##', '').replace('###', '') 
    return text.strip()
