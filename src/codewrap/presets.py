import json
from pathlib import Path
from typing import List, Optional
from codewrap.models import PresetConfig


class PresetManager:
    """Управление пресетами (по умолчанию ~/.codewrap/presets или кастомный путь)."""

    def __init__(self, custom_dir: Optional[Path] = None) -> None:
        if custom_dir is not None:
            self.presets_dir = custom_dir.resolve()
        else:
            self.presets_dir = Path.home() / ".codewrap" / "presets"
            
        self.presets_dir.mkdir(parents=True, exist_ok=True)

    def _get_preset_path(self, name: str) -> Path:
        clean_name = name.removesuffix(".json")
        return self.presets_dir / f"{clean_name}.json"

    def save_preset(self, config: PresetConfig, name: str) -> Path:
        config.name = name
        preset_path = self._get_preset_path(name)
        data = config.model_dump(mode="json")
        preset_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return preset_path

    def load_preset(self, name: str) -> Optional[PresetConfig]:
        preset_path = self._get_preset_path(name)
        if not preset_path.exists():
            return None
        
        data = json.loads(preset_path.read_text(encoding="utf-8"))
        return PresetConfig.model_validate(data)

    def list_presets(self) -> List[str]:
        return [f.stem for f in self.presets_dir.glob("*.json")]