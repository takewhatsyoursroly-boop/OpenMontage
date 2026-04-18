"""Tests for tools.publishers.r2_storage."""
import os
from unittest.mock import MagicMock, patch

import pytest

from tools.publishers.r2_storage import R2Storage


@pytest.fixture
def r2_env(monkeypatch):
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sk")
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://test.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_PUBLIC_URL", "https://pub.example.com")


def test_upload_returns_public_url(r2_env, tmp_path):
    local_file = tmp_path / "clip.mp4"
    local_file.write_bytes(b"fake-mp4")

    fake_client = MagicMock()
    with patch("tools.publishers.r2_storage.boto3.client", return_value=fake_client):
        tool = R2Storage()
        result = tool.execute({
            "action": "upload",
            "local_path": str(local_file),
            "key": "openmontage/run-x/clip.mp4",
        })

    assert result.success
    assert result.data["public_url"] == "https://pub.example.com/openmontage/run-x/clip.mp4"
    fake_client.upload_file.assert_called_once_with(
        str(local_file), "test-bucket", "openmontage/run-x/clip.mp4"
    )


def test_upload_missing_file_returns_error(r2_env, tmp_path):
    fake_client = MagicMock()
    with patch("tools.publishers.r2_storage.boto3.client", return_value=fake_client):
        tool = R2Storage()
        result = tool.execute({
            "action": "upload",
            "local_path": str(tmp_path / "nope.mp4"),
            "key": "x/y.mp4",
        })
    assert not result.success
    assert "not found" in result.error.lower()


def test_upload_trims_trailing_slash_in_public_url(monkeypatch, tmp_path):
    monkeypatch.setenv("R2_BUCKET", "b")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sk")
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://test.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_PUBLIC_URL", "https://pub.example.com/")

    local_file = tmp_path / "a.mp4"
    local_file.write_bytes(b"x")

    fake_client = MagicMock()
    with patch("tools.publishers.r2_storage.boto3.client", return_value=fake_client):
        tool = R2Storage()
        result = tool.execute({
            "action": "upload",
            "local_path": str(local_file),
            "key": "k/v.mp4",
        })
    assert result.success
    assert result.data["public_url"] == "https://pub.example.com/k/v.mp4"


def test_status_unavailable_when_env_incomplete(monkeypatch):
    for k in ("R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
              "R2_ENDPOINT_URL", "R2_PUBLIC_URL"):
        monkeypatch.delenv(k, raising=False)
    tool = R2Storage()
    assert tool.get_status().value == "unavailable"


def test_status_available_when_env_complete(r2_env):
    tool = R2Storage()
    assert tool.get_status().value == "available"


def test_invalid_action_returns_error(r2_env):
    tool = R2Storage()
    result = tool.execute({"action": "bogus"})
    assert not result.success
    assert "action" in result.error.lower()
