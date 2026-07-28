from __future__ import annotations

import json
from pathlib import Path

import pytest
from packaging.version import Version

from sancho import __version__ as SANCHO_VERSION
from sancho.cli import main
from sancho.self_update import (
    PYPI_JSON_URL,
    UPGRADE_COMMAND,
    UPSTREAM_PYPROJECT_URL,
    _parse_version,
    package_status,
    read_checkout_version,
    update_hint,
)


def _make_checkout(tmp_path: Path, version: str) -> Path:
    repo = tmp_path / "sancho-fetch"
    workspace = repo / "sancho-workspace"
    workspace.mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "sancho-fetch"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    return workspace


def _make_bare_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace with no checkout anywhere: the PyPI-install layout."""
    workspace = tmp_path / "sancho-workspace"
    workspace.mkdir(parents=True)
    # The real machine may have a registered library pointing at a checkout;
    # a PyPI-only user has none.
    monkeypatch.setattr("sancho.library.read_library_record", lambda: None)
    return workspace


def _write_stamp(workspace: Path, *, source: str, upstream_version: str) -> None:
    stamp = workspace / "logs" / "update-nudge.json"
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(
        json.dumps({
            "last_check": "2000-01-01T00:00:00+00:00",
            "upstream_version": upstream_version,
            "source": source,
        }),
        encoding="utf-8",
    )


class _FakeResponse:
    def __init__(self, *, text: str = "", payload: dict | None = None) -> None:
        self.text = text
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_parse_version() -> None:
    assert _parse_version("0.2.0") == Version("0.2.0")
    assert _parse_version("1.10") > _parse_version("1.9")
    # Pre-releases parse (and sort before the final release) instead of
    # silently disabling the nudge.
    assert _parse_version("0.3.0rc1") < _parse_version("0.3.0")
    assert _parse_version("not-a-version") is None


def test_read_checkout_version(tmp_path: Path) -> None:
    workspace = _make_checkout(tmp_path, "3.4.5")
    assert read_checkout_version(workspace.parent) == "3.4.5"
    assert read_checkout_version(tmp_path / "nope") is None


# ── checkout mode: the developer flow, unchanged ─────────────────────────


def test_package_status_mismatch_requests_reinstall(tmp_path: Path) -> None:
    workspace = _make_checkout(tmp_path, "9.9.9")
    status = package_status(workspace)
    assert status["installed_version"] == SANCHO_VERSION
    assert status["install_source"] == "checkout"
    assert status["checkout_version"] == "9.9.9"
    assert status["reinstall_needed"] is True
    assert "uv tool install --force" in status["reinstall_command"]
    assert str(workspace.parent) in status["reinstall_command"]


def test_package_status_match_is_quiet(tmp_path: Path) -> None:
    workspace = _make_checkout(tmp_path, SANCHO_VERSION)
    status = package_status(workspace)
    assert status["install_source"] == "checkout"
    assert status["reinstall_needed"] is False
    assert status["reinstall_command"] is None


# ── package mode: the PyPI-install flow ──────────────────────────────────


def test_package_status_no_checkout_is_quiet_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _make_bare_workspace(tmp_path, monkeypatch)
    status = package_status(workspace)
    assert status["install_source"] == "package"
    assert status["checkout_path"] is None
    assert status["upstream_version"] is None
    assert status["reinstall_needed"] is False
    assert status["reinstall_command"] is None


def test_package_status_uses_stamped_pypi_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _make_bare_workspace(tmp_path, monkeypatch)
    _write_stamp(workspace, source="package", upstream_version="99.0.0")
    status = package_status(workspace)
    assert status["install_source"] == "package"
    assert status["upstream_version"] == "99.0.0"
    assert status["reinstall_needed"] is True
    assert status["reinstall_command"] == UPGRADE_COMMAND


def test_package_status_ignores_checkout_mode_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _make_bare_workspace(tmp_path, monkeypatch)
    _write_stamp(workspace, source="checkout", upstream_version="99.0.0")
    status = package_status(workspace)
    assert status["upstream_version"] is None
    assert status["reinstall_needed"] is False


def test_package_status_probe_fetches_pypi_and_stamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _make_bare_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr("sancho.self_update._network_allowed", lambda: True)
    calls: list[str] = []

    def fake_get(url: str, timeout: float = 0) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(payload={"info": {"version": "99.0.0"}})

    monkeypatch.setattr("requests.get", fake_get)
    status = package_status(workspace, probe=True)
    assert calls == [PYPI_JSON_URL]
    assert status["upstream_version"] == "99.0.0"
    assert status["reinstall_needed"] is True
    assert status["reinstall_command"] == UPGRADE_COMMAND
    stamp = json.loads((workspace / "logs" / "update-nudge.json").read_text(encoding="utf-8"))
    assert stamp["source"] == "package"
    assert stamp["upstream_version"] == "99.0.0"


def test_package_status_probe_failure_is_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _make_bare_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr("sancho.self_update._network_allowed", lambda: True)

    def fake_get(url: str, timeout: float = 0) -> _FakeResponse:
        raise ConnectionError("offline")

    monkeypatch.setattr("requests.get", fake_get)
    status = package_status(workspace, probe=True)
    assert status["upstream_version"] is None
    assert status["reinstall_needed"] is False


@pytest.mark.parametrize(
    "upstream, expected_reinstall",
    [
        ("99.0.0", True),      # a genuinely newer release
        (SANCHO_VERSION, False),  # exactly what we publish -- must stay quiet
        ("0.0.1", False),      # older than installed -- never nag to downgrade
    ],
)
def test_package_status_only_nudges_for_a_newer_pypi_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    upstream: str,
    expected_reinstall: bool,
) -> None:
    """Pins the installed-vs-PyPI comparison against a stubbed PyPI response.

    This is the logic that runs for every user the moment a release exists, so
    a regression here means either a permanent false 'update available' nudge
    or a silently missed upgrade.
    """
    workspace = _make_bare_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr("sancho.self_update._network_allowed", lambda: True)

    def fake_get(url: str, timeout: float = 0) -> _FakeResponse:
        assert url == PYPI_JSON_URL
        return _FakeResponse(payload={"info": {"version": upstream}})

    monkeypatch.setattr("requests.get", fake_get)
    status = package_status(workspace, probe=True)

    assert status["installed_version"] == SANCHO_VERSION
    assert status["upstream_version"] == upstream
    assert status["reinstall_needed"] is expected_reinstall
    if expected_reinstall:
        assert status["reinstall_command"] == UPGRADE_COMMAND


def test_update_hint_probes_pypi_when_no_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _make_bare_workspace(tmp_path, monkeypatch)
    monkeypatch.delenv("SANCHO_UPDATE_NUDGE", raising=False)
    monkeypatch.setattr("sancho.self_update._network_allowed", lambda: True)
    calls: list[str] = []

    def fake_get(url: str, timeout: float = 0) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(payload={"info": {"version": "99.0.0"}})

    monkeypatch.setattr("requests.get", fake_get)
    hint = update_hint(workspace)
    assert calls == [PYPI_JSON_URL]
    assert hint is not None
    assert "99.0.0" in hint
    assert SANCHO_VERSION in hint


def test_update_hint_probes_github_when_checkout_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _make_checkout(tmp_path, SANCHO_VERSION)
    monkeypatch.delenv("SANCHO_UPDATE_NUDGE", raising=False)
    monkeypatch.setattr("sancho.self_update._network_allowed", lambda: True)
    calls: list[str] = []

    def fake_get(url: str, timeout: float = 0) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(text='version = "99.0.0"\n')

    monkeypatch.setattr("requests.get", fake_get)
    hint = update_hint(workspace)
    assert calls == [UPSTREAM_PYPROJECT_URL]
    assert hint is not None and "99.0.0" in hint


def test_update_hint_is_silent_under_pytest(tmp_path: Path) -> None:
    workspace = _make_checkout(tmp_path, SANCHO_VERSION)
    # The nudge must never probe the network from a test run.
    assert update_hint(workspace) is None


# ── the reminder actually reaches the user ───────────────────────────────


def test_paths_payload_carries_update_hint_and_respects_throttle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`sancho paths` runs at the start of every skill session: a newer PyPI
    release must show up there, once, and the 14-day stamp must prevent a
    second probe."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("SANCHO_UPDATE_NUDGE", raising=False)
    monkeypatch.setattr("sancho.self_update._network_allowed", lambda: True)

    project = tmp_path / "project"
    project.mkdir()
    rc = main(["init", "--path", str(project), "--yes"])
    assert rc == 0
    monkeypatch.chdir(project)

    calls: list[str] = []

    def fake_get(url: str, timeout: float = 0) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(payload={"info": {"version": "99.0.0"}})

    monkeypatch.setattr("requests.get", fake_get)
    capsys.readouterr()

    rc = main(["paths", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "update_hint" in payload
    assert "99.0.0" in payload["update_hint"]
    assert calls == [PYPI_JSON_URL]

    # Second session inside the throttle window: no new probe, no crash.
    rc = main(["paths", "--json"])
    assert rc == 0
    json.loads(capsys.readouterr().out)
    assert calls == [PYPI_JSON_URL]
