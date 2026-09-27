import json
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AppSettings(BaseModel):
    """Global application settings stored in ~/.codewrap/settings.json."""

    tokenizer: str = "o200k_base"
    exclude_binary: bool = True
    max_file_size: str = "512kb"
    auto_rename_outputs: bool = False
    copy_to_clipboard: bool = False
    save_in_current_dir: bool = False


class SettingsManager:
    def __init__(self) -> None:
        self.config_dir = Path.home() / ".codewrap"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.config_dir / "settings.json"

    def load(self) -> AppSettings:
        if not self.settings_file.exists():
            return AppSettings()
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return AppSettings.model_validate(data)
        except Exception as e:
            logger.warning("Failed to load %s (%s) — using default settings.", self.settings_file, e)
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        data = settings.model_dump(mode="json")
        self.settings_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def reset(self) -> AppSettings:
        if self.settings_file.exists():
            self.settings_file.unlink()
        return AppSettings()
