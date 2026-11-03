import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from atlantica_bot.clients import ClientWindow
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import HuntingResult
from atlantica_bot.native_action import try_attack
from atlantica_bot.session import LiveState
from atlantica_bot.world import Candidate


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    helper = tmp_path / "AtlanticaBridge.exe"
    helper.write_bytes(b"test helper")
    helper.with_name("AtlanticaHook.dll").write_bytes(b"test library")
    monkeypatch.setattr("atlantica_bot.native_action.bridge_path", lambda: helper)
    monkeypatch.setattr("atlantica_bot.native_action.control_hunting", lambda *args: None)
    monkeypatch.setattr("atlantica_bot.native_action.BotLease", lambda pid: nullcontext())
    monkeypatch.setattr(
        "atlantica_bot.native_action.Cancellation",
        lambda pid: SimpleNamespace(
            name=f"Local\\AtlanticaPanel.Cancel.{pid}.test", cancel=lambda: None, close=lambda: None
        ),
    )
    state = LiveState(False, 0, False, HuntingResult(False, False, False))
    session = SimpleNamespace(
        process=SimpleNamespace(pid=200),
        directory=tmp_path,
        creation_time=123456,
        snapshot=lambda: state,
    )
    window = ClientWindow(200, 0x12345, "Atlantica", 1234)
    candidate = Candidate(6, 12053, 52, 202, 267, 82, (12053, 77, 88))
    return session, window, candidate


def test_one_request_targets_only_selected_pid_window_creation_and_identity(bridge, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["check"] is False and kwargs["timeout"] == 8
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"pid": 200, "slot": 6, "status": 1, "thread_id": 1234, "exception": 0}
            ),
        )

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    result = try_attack(*bridge)
    assert len(calls) == 1
    args = calls[0]
    assert args[args.index("--pid") + 1] == "200"
    assert args[args.index("--window") + 1] == str(0x12345)
    assert args[args.index("--thread") + 1] == "1234"
    assert args[args.index("--created") + 1] == "123456"
    assert args[args.index("--serial") + 1] == "77"
    assert "--attack" in args
    assert result["battle_confirmed"] is False


def test_mismatched_window_is_rejected_before_launching_helper(bridge, monkeypatch):
    session, _, candidate = bridge
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *args, **kw: pytest.fail("wrong client"),
    )
    with pytest.raises(DiagnosticError, match="instancia conectada"):
        try_attack(session, ClientWindow(300, 0x99999, "Atlantica"), candidate)


@pytest.mark.parametrize(
    "auto,hunting,marker", [(True, False, False), (False, True, False), (False, False, True)]
)
def test_native_hunting_conditions_block_experimental_request(bridge, auto, hunting, marker):
    session, _, _ = bridge
    session.snapshot = lambda: LiveState(auto, 50, hunting, HuntingResult(marker, False, False))
    with pytest.raises(DiagnosticError, match="desactivados"):
        try_attack(*bridge)


def test_wrong_instance_response_is_rejected(bridge, monkeypatch):
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *args, **kw: SimpleNamespace(
            returncode=0, stdout=json.dumps({"pid": 300, "slot": 6, "status": 1, "thread_id": 1234})
        ),
    )
    with pytest.raises(DiagnosticError, match="respuesta no válida"):
        try_attack(*bridge)


def test_bridge_failure_has_no_automatic_retry(bridge, monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=24, stdout="")

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", fail)
    with pytest.raises(DiagnosticError, match="no se reintenta"):
        try_attack(*bridge)
    assert len(calls) == 1


def test_response_from_different_thread_is_not_accepted(bridge, monkeypatch):
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *args, **kw: SimpleNamespace(
            returncode=0, stdout=json.dumps({"pid": 200, "slot": 6, "status": 1, "thread_id": 9999})
        ),
    )
    with pytest.raises(DiagnosticError, match="respuesta no válida"):
        try_attack(*bridge)
