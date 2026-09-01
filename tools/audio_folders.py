import os
from pathlib import Path

def audio_folders(chosen: list[Path] | None) -> list[Path]:
    """Папки с исходными записями: названные флагом или одна из AUDIO_PATH."""
    if chosen:
        return [Path(folder).expanduser() for folder in chosen]

    raw = os.getenv("AUDIO_PATH")
    if not raw:
        raise RuntimeError(
            "Не задан AUDIO_PATH — папка с исходными записями. "
            "Добавьте его в .env, например: AUDIO_PATH=~/Desktop/YAWolfgang, "
            "или назовите папку флагом --audio"
        )

    return [Path(raw).expanduser()]
