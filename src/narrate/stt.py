"""Speech-to-text for subtitles on recorded audio (faster-whisper on the CPU).

Scenes narrated by `(audio: file)` have no text to caption. When subtitles
are on and a scene has no block quotes, narrate transcribes its recordings
and times the cues to the words. Transcripts are cached by file content and
model, so rebuilds don't transcribe again.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

from .tts import cache_dir, tools_dir

DEFAULT_MODEL = "small"
_models: dict[str, object] = {}
_lock = threading.Lock()


def model_name() -> str:
    return os.environ.get("NARRATE_STT_MODEL") or DEFAULT_MODEL


def _model():
    name = model_name()
    with _lock:
        if name not in _models:
            from faster_whisper import WhisperModel

            _models[name] = WhisperModel(name, device="cpu", compute_type="int8",
                                         download_root=str(model_dir()))
        return _models[name]


def model_dir() -> Path:
    return tools_dir() / "stt"


def ensure_model() -> Path:
    """Download the speech-to-text model ahead of time."""
    _model()
    return model_dir()


Words = list[tuple[float, float, str]]  # (start, end, word) in seconds


def transcribe(path: Path, language: str | None = None) -> list[Words]:
    """The words spoken in an audio file, grouped by phrase, with their times."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    cached = cache_dir() / "stt" / f"{digest}-{model_name()}-{language or 'auto'}.json"
    if cached.exists():
        return [[tuple(w) for w in phrase] for phrase in json.loads(cached.read_text())]
    from .media import decode_audio

    # Decode with narrate's own ffmpeg: faster-whisper's PyAV path breaks across PyAV releases
    samples = decode_audio(path, 16000)
    segments, _ = _model().transcribe(samples, language=language, vad_filter=True, word_timestamps=True)
    phrases = [[(round(float(w.start), 3), round(float(w.end), 3), w.word.strip()) for w in s.words if w.word.strip()]
               for s in segments]
    phrases = [p for p in phrases if p]
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(phrases, ensure_ascii=False))
    return phrases


def captions(phrases: list[Words], limit: int) -> list[tuple[float, float, str]]:
    """Cues of at most `limit` characters, timed to their words, never spanning two phrases."""
    cues = []
    for words in phrases:
        current: Words = []
        for word in words:
            text = " ".join(w for _, _, w in [*current, word])
            if current and len(text) > limit:
                cues.append((current[0][0], current[-1][1], " ".join(w for _, _, w in current)))
                current = []
            current.append(word)
        if current:
            cues.append((current[0][0], current[-1][1], " ".join(w for _, _, w in current)))
    return cues
