import json
from pathlib import Path

from codewrap.models import PresetConfig


class PresetManager:
    """Manages preset configurations in ~/.codewrap/presets or a custom folder."""

    def __init__(self, custom_dir: Path | None = None) -> None:
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

    def load_preset(self, name: str) -> PresetConfig | None:
        preset_path = self._get_preset_path(name)
        if not preset_path.exists():
            return None

        data = json.loads(preset_path.read_text(encoding="utf-8"))
        return PresetConfig.model_validate(data)

    def list_presets(self) -> list[str]:
        return [f.stem for f in self.presets_dir.glob("*.json")]

    @staticmethod
    def load_local_config(folder: Path) -> PresetConfig | None:
        """Loads .codewrap.json if present in the target directory."""
        local_file = folder / ".codewrap.json"
        if not local_file.exists():
            return None
        try:
            data = json.loads(local_file.read_text(encoding="utf-8"))
            return PresetConfig.model_validate(data)
        except Exception:
            return None

    @staticmethod
    def init_local_config(folder: Path, config: PresetConfig) -> Path:
        """Writes a .codewrap.json config file into the specified directory."""
        local_file = folder / ".codewrap.json"
        data = config.model_dump(mode="json")
        local_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return local_file
