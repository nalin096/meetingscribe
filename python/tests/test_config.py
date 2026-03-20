from meetingscribe.config import load_config, MeetingScribeConfig


def test_load_config_returns_typed_config(sample_config):
    config = load_config(sample_config)
    assert isinstance(config, MeetingScribeConfig)
    assert config.audio.sample_rate == 16000
    assert config.retry.max_retries == 3


def test_load_config_validates_vault_path(tmp_home):
    config_path = tmp_home / ".meetingscribe" / "config.toml"
    config_path.write_text('[vault]\npath = "/nonexistent/path"\ntimezone = "UTC"')
    import pytest
    with pytest.raises(ValueError, match="vault path"):
        load_config(config_path)


def test_load_config_missing_file():
    from pathlib import Path
    import pytest
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/config.toml"))
