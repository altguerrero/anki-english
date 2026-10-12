"""Optional local Kokoro adapter; imports/models are loaded only on use."""

from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Protocol

from .config import TTSConfig


class AudioError(RuntimeError):
    pass


class TTSProvider(Protocol):
    def synthesize(self, text: str) -> Path: ...


class KokoroTTS:
    def __init__(self, config: TTSConfig):
        self.config = config
        self._pipeline = None

    def synthesize(self, text: str) -> Path:
        try:
            package_version = version("kokoro")
        except PackageNotFoundError as error:
            raise AudioError("Install audio dependencies: pip install -e '.[audio]'; "
                             "or explicitly use --no-audio.") from error
        identity = ["kokoro-82m-v1.0", package_version, self.config.voice,
                    self.config.lang_code, self.config.speed, "mp3-128k-v1", text]
        digest = sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        directory = Path(self.config.cache_dir).expanduser()
        destination = directory / f"eng_{digest}.mp3"
        if destination.is_file() and destination.stat().st_size > 0:
            return destination
        if not shutil.which("ffmpeg"):
            raise AudioError("ffmpeg is required for MP3. On macOS: brew install ffmpeg")
        directory.mkdir(parents=True, exist_ok=True)
        try:
            import numpy as np
            import soundfile as sf
            from kokoro import KPipeline

            if self._pipeline is None:
                self._pipeline = KPipeline(lang_code=self.config.lang_code, repo_id="hexgrad/Kokoro-82M")
            chunks = [audio for _, _, audio in self._pipeline(
                text, voice=self.config.voice, speed=self.config.speed
            ) if audio is not None and len(audio)]
            if not chunks:
                raise AudioError("Kokoro generated no audio")
            # Temp dir on the same filesystem permits atomic cache replacement.
            with tempfile.TemporaryDirectory(dir=directory) as temporary:
                wav = Path(temporary) / "speech.wav"
                mp3 = Path(temporary) / "speech.mp3"
                sf.write(wav, np.concatenate(chunks), 24000)
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(wav),
                                "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3)],
                               check=True, capture_output=True, timeout=120)
                if not mp3.is_file() or mp3.stat().st_size == 0:
                    raise AudioError("MP3 encoder produced an empty file")
                mp3.replace(destination)
        except AudioError:
            raise
        except Exception as error:
            raise AudioError("Audio generation failed. Check Kokoro dependencies/model download, "
                             "voice and ffmpeg. No note was added for this card.") from error
        return destination
