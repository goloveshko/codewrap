"""Tests for CLI-override handling of local .codewrap.json configs (review #12)."""

import json
from pathlib import Path

from codewrap.handlers import resolve_scan_config
from codewrap.presets import PresetManager
from codewrap.settings import AppSettings


def resolve(
    tmp_path: Path,
    output: Path | None = None,
    target: list[str] | None = None,
    directory_passed: bool = True,
):
    return resolve_scan_config(
        current_folder=tmp_path,
        preset=None,
        target=target,
        files_list=None,
        modified=False,
        since=None,
        output=output,
        preset_mgr=PresetManager(custom_dir=tmp_path / "presets"),
        saved_settings=AppSettings(),
        directory_passed=directory_passed,
    )


class TestLocalConfigOverrides:
    def test_output_and_directory_applied(self, tmp_path: Path):
        (tmp_path / ".codewrap.json").write_text(
            json.dumps({"name": "loc", "root_path": str(tmp_path / "elsewhere")}),
            encoding="utf-8",
        )
        config = resolve(tmp_path, output=Path("custom_out.md"))
        assert config.root_path == str(tmp_path)
        assert config.output_file == "custom_out.md"

    def test_local_config_loaded_without_overrides(self, tmp_path: Path):
        (tmp_path / ".codewrap.json").write_text(json.dumps({"name": "loc"}), encoding="utf-8")
        config = resolve(tmp_path, directory_passed=False)
        assert config.name == "loc"

    def test_explicit_target_bypasses_local_config(self, tmp_path: Path):
        (tmp_path / ".codewrap.json").write_text(json.dumps({"name": "loc"}), encoding="utf-8")
        from codewrap.utils import parse_target_arg

        config = resolve(tmp_path, target=["src:py"])
        assert config.targets == [parse_target_arg("src:py")]
