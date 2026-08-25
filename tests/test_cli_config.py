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
    """Tests for viewing configuration (bare config and config show)."""

    def test_bare_config_invokes_default_table_show(self):
        """Running `codewrap config` without subcommands should display settings table."""
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "CodeWrap Global Configuration" in result.output
        assert "use_numbering" in result.output
        assert "copy_to_clipboard" in result.output
        assert "encoding" in result.output

    def test_config_show_renders_table(self):
        """Running `codewrap config show` should render the rich settings table."""
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "CodeWrap Global Configuration" in result.output
        assert "o200k_base" in result.output

    def test_config_show_json_flag(self):
        """Running `codewrap config show --json` should output valid parseable JSON."""
        result = runner.invoke(app, ["config", "show", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["encoding"] == "o200k_base"
        assert "use_numbering" in data
        assert "copy_to_clipboard" in data

    def test_config_show_short_json_flag(self):
        """Running `codewrap config show -j` should output valid JSON."""
        result = runner.invoke(app, ["config", "show", "-j"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert data["exclude_binary"] is True


class TestConfigSet:
    """Tests for `codewrap config set` parameter updates."""

    def test_invalid_encoding_rejected(self, fake_tiktoken):
        result = runner.invoke(app, ["config", "set", "--encoding", "bogus-enc"])
        assert result.exit_code == 1
        assert FakeSettingsManager.saved is None
        assert "Unknown tokenizer encoding" in result.output

    def test_valid_encoding_saved(self, fake_tiktoken):
        result = runner.invoke(app, ["config", "set", "--encoding", "cl100k_base"])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.encoding == "cl100k_base"

    def test_set_numbered_flag(self):
        result = runner.invoke(app, ["config", "set", "--numbered"])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.use_numbering is True

    def test_set_copy_flag(self):
        result = runner.invoke(app, ["config", "set", "--copy"])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.copy_to_clipboard is True

    def test_set_cwd_flag(self):
        result = runner.invoke(app, ["config", "set", "--cwd"])
        assert result.exit_code == 0
        assert FakeSettingsManager.saved is not None
        assert FakeSettingsManager.saved.save_in_cwd is True

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
    """Tests for resetting global configuration to defaults."""

    def test_config_reset_command(self):
        result = runner.invoke(app, ["config", "reset"])
        assert result.exit_code == 0
        assert FakeSettingsManager.reset_called is True
        assert "successfully reset to defaults" in result.output
