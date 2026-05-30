from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.tools.evidence import tools as evtools
from decepticon.tools.evidence.tools import export_session_asciicast, list_session_recordings


def test_workspace_default_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DECEPTICON_ENGAGEMENT_WORKSPACE", raising=False)
    assert evtools._workspace() == Path("/workspace")


def test_workspace_returns_path_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    assert evtools._workspace() == tmp_path


def test_evidence_dir_is_workspace_subpath(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    assert evtools._evidence_dir() == tmp_path / "evidence" / "recordings"


def test_json_helper_round_trips_dict() -> None:
    result = evtools._json({"k": 1})
    assert json.loads(result) == {"k": 1}


def test_export_session_asciicast_explicit_log_path_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    log_file = tmp_path / "cmd.log"
    log_file.write_text(
        "first\nDECEPTICON_PROMPT_END_xx\nsecond\nDECEPTICON_PROMPT_END_xx\n",
        encoding="utf-8",
    )
    result = json.loads(
        export_session_asciicast.invoke(
            {
                "session_name": "sess",
                "pipe_pane_log_path": str(log_file),
                "title": "My Title",
            }
        )
    )
    assert result["status"] == "exported"
    assert result["session_name"] == "sess"
    assert result["segments"] == 2
    cast_path = Path(result["asciicast_path"])
    assert cast_path == tmp_path / "evidence" / "recordings" / "sess.cast"
    assert cast_path.exists()
    sidecar = cast_path.with_suffix(cast_path.suffix + ".manifest.json")
    assert sidecar.exists()


def test_export_session_asciicast_fallback_tmux_log_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    tmux_logs_dir = tmp_path / ".tmux-logs"
    tmux_logs_dir.mkdir()
    log_file = tmux_logs_dir / "fb.log"
    log_file.write_text(
        "output\nDECEPTICON_PROMPT_END_xx\nmore\nDECEPTICON_PROMPT_END_xx\n",
        encoding="utf-8",
    )
    result = json.loads(export_session_asciicast.invoke({"session_name": "fb"}))
    assert result["status"] == "exported"
    assert (
        result["source_log"].endswith(".tmux-logs/fb.log")
        or result["source_log"] == str(log_file).replace("\\", "/")
        or Path(result["source_log"]) == log_file
    )


def test_export_session_asciicast_error_when_log_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    result = json.loads(export_session_asciicast.invoke({"session_name": "missing"}))
    assert "error" in result
    assert "status" not in result
    assert "pipe-pane log not found" in result["error"]


def test_list_session_recordings_empty_when_evidence_dir_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    result = json.loads(list_session_recordings.invoke({}))
    assert result == {"count": 0, "recordings": []}


def test_list_session_recordings_returns_manifests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DECEPTICON_ENGAGEMENT_WORKSPACE", str(tmp_path))
    recordings_dir = tmp_path / "evidence" / "recordings"
    recordings_dir.mkdir(parents=True)
    (recordings_dir / "a.cast.manifest.json").write_text(
        json.dumps({"session_name": "a"}), encoding="utf-8"
    )
    (recordings_dir / "b.cast.manifest.json").write_text(
        json.dumps({"session_name": "b"}), encoding="utf-8"
    )
    result = json.loads(list_session_recordings.invoke({}))
    assert result["count"] == 2
    assert sorted(r["session_name"] for r in result["recordings"]) == ["a", "b"]
