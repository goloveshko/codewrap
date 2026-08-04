import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class AppSettings(BaseModel):
    presets_dir: Optional[str] = None
    use_numbering: bool = False
    copy_to_clipboard: bool = False
    save_in_cwd: bool = False  # Сохранять ли файл в папке терминала
    last_preset: Optional[str] = None


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
        except Exception:
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        data = settings.model_dump(mode="json")
        self.settings_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def reset(self) -> AppSettings:
        if self.settings_file.exists():
            self.settings_file.unlink()
        return AppSettings()
