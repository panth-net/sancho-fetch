"""Tests for `sancho env recommend` — the topic-to-key recommender."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sancho.cli import main
from sancho.constants import WORKSPACE_DIRNAME
from sancho.env_keys import HIDDEN_FILE_HINTS, env_recommend
from sancho.mcp.high_level_tools import build_high_level_tools
from sancho.mcp.models import MCPContext, MCPPolicy


def _init_workspace(tmp_path: Path) -> Path:
    rc = main(["init", "--path", str(tmp_path), "--yes"])
    assert rc == 0
    return tmp_path / WORKSPACE_DIRNAME


def test_env_recommend_flags_missing_required_keys(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("# blank\n", encoding="utf-8")

    payload = env_recommend(workspace, "Census ACS population by state")
    cands = {row["module_id"]: row for row in payload["candidates"]}
    assert "fetch.census.acs_profile" in cands
    census = cands["fetch.census.acs_profile"]
    assert "CENSUS_API_KEY" in census["declared_env_keys"]
    assert "CENSUS_API_KEY" in census["missing_keys"]
    assert census["ready"] is False
    assert "CENSUS_API_KEY" in payload["missing_required_keys"]


def test_env_recommend_marks_provider_ready_when_key_is_populated(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("FRED_API_KEY=any-non-empty-value\n", encoding="utf-8")

    payload = env_recommend(workspace, "Federal Reserve series FRED interest rates")
    fred = next(c for c in payload["candidates"] if c["module_id"] == "fetch.fred.series")
    assert fred["missing_keys"] == []
    assert fred["ready"] is True
    assert "FRED_API_KEY" not in payload["missing_required_keys"]


def test_env_recommend_uses_project_env_fallback(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("SANCHO_DEVELOPER_MODE=false\n", encoding="utf-8")
    (tmp_path / ".env").write_text("FRED_API_KEY=any-non-empty-value\n", encoding="utf-8")

    payload = env_recommend(workspace, "Federal Reserve series FRED interest rates")

    fred = next(c for c in payload["candidates"] if c["module_id"] == "fetch.fred.series")
    assert fred["missing_keys"] == []
    assert fred["ready"] is True
    assert payload["env_path"] == str(tmp_path / ".env")


def test_env_recommend_marks_optional_keys_distinctly(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("# blank\n", encoding="utf-8")

    payload = env_recommend(workspace, "NYC Open Data crimes Socrata")
    nyc = next((c for c in payload["candidates"] if c["module_id"] == "fetch.nyc_open_data"), None)
    if nyc is not None:
        assert nyc["keys_optional"] is True
        assert nyc["ready"] is True
        for name in nyc["missing_keys"]:
            assert name not in payload["missing_required_keys"]


def test_env_recommend_never_contains_env_values(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    secret = "x9q2-leaked-secret-must-not-appear"
    (workspace / ".env").write_text(f"FRED_API_KEY={secret}\n", encoding="utf-8")

    payload = env_recommend(workspace, "Federal Reserve series GDP unemployment")
    serialized = json.dumps(payload, default=str)
    assert secret not in serialized


def test_env_recommend_empty_query_returns_empty_candidates(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    payload = env_recommend(workspace, "")
    assert payload["candidates"] == []
    assert payload["summary"]["total"] == 0
    # Even on empty query, the .env.example reference is surfaced.
    assert "env_example_path" in payload


def test_env_recommend_embeds_full_env_example_contents(tmp_path: Path) -> None:
    """Agent gets the entire .env.example string so it can read URLs / hints itself."""
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("# blank\n", encoding="utf-8")
    payload = env_recommend(workspace, "Census ACS population")
    text = payload["env_example_contents"]
    assert isinstance(text, str) and len(text) > 0
    # The embedded text is the actual .env.example — it must contain
    # at least a couple of well-known KEY= lines.
    assert "CENSUS_API_KEY=" in text
    assert "FRED_API_KEY=" in text
    # And a sign-up URL the user / agent will use.
    assert "huduser.gov" in text or "census.gov" in text


def test_env_recommend_does_not_per_candidate_emit_signup_urls(tmp_path: Path) -> None:
    """We deliberately stopped parsing URLs out of comments — the AI reads the full file instead."""
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("# blank\n", encoding="utf-8")
    payload = env_recommend(workspace, "Census ACS population")
    for row in payload["candidates"]:
        assert "signup_urls" not in row


def test_env_recommend_next_steps_include_hidden_file_hints(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("# blank\n", encoding="utf-8")
    payload = env_recommend(workspace, "Census ACS population")
    steps_blob = "\n".join(payload["next_steps"]).lower()
    # macOS Cmd+Shift+. hint
    assert "cmd+shift+." in steps_blob or "command + shift + period" in steps_blob
    # Windows file explorer hint
    assert "file explorer" in steps_blob or "hidden items" in steps_blob


def test_env_recommend_payload_warns_user_not_to_share_with_ai(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("# blank\n", encoding="utf-8")
    payload = env_recommend(workspace, "Census ACS population by state")
    safety = payload.get("safety", "").lower()
    assert "paste" in safety and ".env" in safety
    assert "never paste a key into the ai chat" in safety
    steps_blob = " ".join(payload["next_steps"]).lower()
    assert "do not share" in steps_blob


def test_env_recommend_hidden_file_hints_constant_is_imported() -> None:
    """The HIDDEN_FILE_HINTS constant exists and references the macOS shortcut."""
    assert "Cmd+Shift+." in HIDDEN_FILE_HINTS


def test_cli_env_recommend_json_payload(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("# blank\n", encoding="utf-8")
    capsys.readouterr()
    rc = main([
        "env", "recommend",
        "housing", "affordability", "rents",
        "--workspace", str(tmp_path),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "housing affordability rents"
    module_ids = {c["module_id"] for c in payload["candidates"]}
    assert "fetch.hud.fmr" in module_ids
    # The full .env.example contents are embedded for the agent.
    assert payload["env_example_contents"]


def test_cli_env_recommend_blank_query_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _init_workspace(tmp_path)
    capsys.readouterr()
    rc = main(["env", "recommend", "", "--workspace", str(tmp_path)])
    assert rc == 1


def test_mcp_tool_sancho_env_recommend_works(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    (workspace / ".env").write_text("# blank\n", encoding="utf-8")
    ctx = MCPContext(workspace_root=workspace, policy=MCPPolicy())
    tools = {t.name: t for t in build_high_level_tools(ctx)}
    assert "sancho_env_recommend" in tools
    result = tools["sancho_env_recommend"].handler({"query": "Census ACS population"})
    assert result["query"] == "Census ACS population"
    assert any(c["module_id"] == "fetch.census.acs_profile" for c in result["candidates"])
    assert "CENSUS_API_KEY" in result["missing_required_keys"]


def test_mcp_tool_hosted_session_omits_env_recommend(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    ctx = MCPContext(workspace_root=workspace, policy=MCPPolicy(stateless=True))
    tools = {t.name: t for t in build_high_level_tools(ctx)}
    assert "sancho_env_recommend" not in tools


def test_env_open_human_output_includes_hidden_file_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _init_workspace(tmp_path)
    # Stub the editor opener.
    monkeypatch.setattr("sancho.cli_env._open_in_editor", lambda path: None)
    capsys.readouterr()
    rc = main(["env", "open", "--workspace", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Cmd+Shift+." in out
    assert "Hidden items" in out
    # Don't-share-with-AI reminder is printed.
    assert "Do not share them with the AI assistant" in out
