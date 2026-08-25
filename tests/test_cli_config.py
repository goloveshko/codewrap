"""Tests for CodeWrap config CLI commands and settings management."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codewrap import cli
from codewrap.main import app
from codewrap.settings import AppSettings

runner = CliRunner()


class FakeSettingsManager:
    current_settings: AppSettings = AppSettings()
    saved: AppSettings | None = None
    reset_called: bool = False

    def load(self) -> AppSettings:
        return self.current_settings

    def save(self, settings: AppSettings) -> None:
        FakeSettingsManager.saved = settings
        FakeSettingsManager.current_settings = settings

    def reset(self) -> AppSettings:
        FakeSettingsManager.reset_called = True
        FakeSettingsManager.current_settings = AppSettings()
        return FakeSettingsManager.current_settings


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch: pytest.MonkeyPatch):
    FakeSettingsManager.current_settings = AppSettings()
    FakeSettingsManager.saved = None
    FakeSettingsManager.reset_called = False
    monkeypatch.setattr(cli, "SettingsManager", FakeSettingsManager)


@pytest.fixture
def fake_tiktoken(monkeypatch: pytest.MonkeyPatch):
    import tiktoken

    registry = {"o200k_base", "cl100k_base"}

    def get_encoding(name: str):
        if name not in registry:
            raise ValueError(f"Unknown encoding {name}")
        return object()

    monkeypatch.setattr(tiktoken, "get_encoding", get_encoding)
    return registry


class TestConfigShow:
    def test_bare_config_invokes_default_table_show(self):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "CodeWrap Global Configuration" in result.output
        assert "auto_rename_outputs" in result.output
        assert "copy_to_clipboard" in result.output
        assert "tokenizer" in result.output

    def test_config_show_renders_table(self):
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "CodeWrap Global Configuration" in result.output
        assert "o200k_base" in result.output

    def test_config_show_json_flag(self):
        result = runner.invoke(app, ["config", "show", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["tokenizer"] == "o200k_base"
        assert "auto_rename_outputs" in data
        assert "copy_to_clipboard" in data

    def test_config_tokenizers_guide(self):
        result = runner.invoke(app, ["config", "tokenizers"])
        assert result.exit_code == 0
        assert "Supported LLM Tokenizers" in result.output
        assert "o200k_base" in result.output
        assert "cl100k_base" in result.output


class TestConfigSet:
    def test_invalid_tokenizer_rejected(self, fake_tiktoken):
        result = runner.invoke(app, ["config", "set", "--tokenizer", "bogus-enc"])
        assert result.exit_code == 1
        assert FakeSettingsManager.saved is None
        assert "Unknown tokenizer" in result.output

    def test_valid_tokenizer_saved(self, fake_tiktoken):
        result = runner.invoke(app, ["config", "set", "--tokenizer", "cl100k_base"])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.tokenizer == "cl100k_base"

    def test_set_rename_flag(self):
        result = runner.invoke(app, ["config", "set", "--rename"])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.auto_rename_outputs is True

    def test_set_copy_flag(self):
        result = runner.invoke(app, ["config", "set", "--copy"])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.copy_to_clipboard is True

    def test_set_cwd_flag(self):
        result = runner.invoke(app, ["config", "set", "--cwd"])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.save_in_current_dir is True

    def test_set_exclude_binary_flag(self):
        result = runner.invoke(app, ["config", "set", "--no-exclude-binary"])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.exclude_binary is False

    def test_set_presets_dir(self, tmp_path: Path):
        custom_dir = tmp_path / "custom_presets"
        result = runner.invoke(app, ["config", "set", "--presets-dir", str(custom_dir)])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.presets_dir == str(custom_dir.resolve())


class TestConfigReset:
    def test_config_reset_command(self):
        result = runner.invoke(app, ["config", "reset"])
        assert result.exit_code == 0
        assert FakeSettingsManager.reset_called is True
        assert "successfully reset to defaults" in result.output
