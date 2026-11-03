import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from atlantica_bot.clients import ClientWindow
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import HuntingResult
from atlantica_bot.native_action import (
    stop_movement,
    stop_native_pursuit,
    try_approach,
    try_attack,
    try_native_attack,
)
from atlantica_bot.navigation import ApproachSettings
from atlantica_bot.session import LiveState
from atlantica_bot.world import Candidate, GridPosition, NativePursuit, NavigationState


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
                {
                    "pid": 200,
                    "slot": 6,
                    "status": 1,
                    "thread_id": 1234,
                    "exception": 0,
                    "operation": 1,
                }
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


def test_native_attack_passes_search_area_and_same_instance_without_grid_route(bridge, monkeypatch):
    session, window, candidate = bridge
    pursuit = NativePursuit(0x30010000, 1234, 52, 202, 267, (12.125, -33.5, 0.0), 1)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert "--native-attack" in args and "--approach" not in args
        assert args[args.index("--pid") + 1] == "200"
        assert args[args.index("--created") + 1] == "123456"
        assert args[args.index("--radius") + 1] == "60"
        assert args[args.index("--origin-x") + 1] == "193"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "pid": 200,
                    "slot": 6,
                    "thread_id": 1234,
                    "operation": 4,
                    "status": 22,
                    "pursuit": pursuit.summary(),
                }
            ),
        )

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    result = try_native_attack(
        session,
        window,
        candidate,
        GridPosition(52, 193, 300),
        ApproachSettings(False, 60),
    )
    assert len(calls) == 1 and result["status"] == 22 and not result["battle_confirmed"]
    assert result["action"] == "native_attack"


def test_native_stop_supplies_exact_owned_float_goal_and_never_selects_another_actor(
    bridge, monkeypatch
):
    session, window, _ = bridge
    pursuit = NativePursuit(0x30010000, 1234, 52, 202, 267, (12.125, -33.5, 0.0), 1)

    def run(args, **kwargs):
        assert "--stop-native" in args and "--slot" not in args
        assert args[args.index("--goal-y") + 1] == "-33.5"
        assert args[args.index("--route-player") + 1] == str(pursuit.player_address)
        assert args[args.index("--map") + 1] == "52"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "pid": 200,
                    "slot": 0,
                    "thread_id": 1234,
                    "operation": 5,
                    "status": 23,
                    "pursuit": pursuit.summary(),
                }
            ),
        )

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    assert stop_native_pursuit(session, window, pursuit)["status"] == 23


def test_native_target_outside_search_area_never_launches_bridge(bridge, monkeypatch):
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run", lambda *a, **kw: pytest.fail("outside radius")
    )
    session, window, target = bridge
    with pytest.raises(DiagnosticError, match="radio de búsqueda"):
        try_native_attack(
            session, window, target, GridPosition(52, 193, 300), ApproachSettings(False, 5)
        )


def test_native_response_cannot_be_from_legacy_operation(bridge, monkeypatch):
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"pid": 200, "slot": 6, "thread_id": 1234, "operation": 2, "status": 22}
            ),
        ),
    )
    with pytest.raises(DiagnosticError, match="respuesta no válida"):
        try_native_attack(*bridge, GridPosition(52, 193, 300), ApproachSettings(False, 60))


def test_busy_movement_is_a_valid_attack_rejection_not_a_corrupt_response(bridge, monkeypatch):
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"pid": 200, "slot": 6, "thread_id": 1234, "operation": 1, "status": 20}
            ),
        ),
    )
    assert try_attack(*bridge)["status"] == 20


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


def test_approach_supplies_selected_instance_origin_radius_and_target(bridge, monkeypatch):
    calls = []
    session, window, candidate = bridge
    route = NavigationState(0x123456, 1010, candidate.map_id, candidate.x, candidate.y, True, True)

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "pid": 200,
                    "slot": 6,
                    "status": 15,
                    "thread_id": 1234,
                    "operation": 2,
                    "navigation": route.summary(),
                }
            ),
        )

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    result = try_approach(
        session,
        window,
        candidate,
        GridPosition(52, 193, 300),
        ApproachSettings(True),
        navigation=NavigationState(0x123456, 1001, -1, 0, 0, False, None, 2, 255),
    )
    assert result["status"] == 15 and result["action"] == "approach"
    assert len(calls) == 1
    args = calls[0]
    assert "--approach" in args
    assert args[args.index("--radius") + 1] == "60"
    assert args[args.index("--origin-x") + 1] == "193"
    assert args[args.index("--x") + 1] == "202"
    assert args[args.index("--route-player") + 1] == str(0x123456)
    assert args[args.index("--route-tick") + 1] == "1001"


def test_stop_uses_route_ownership_and_a_fresh_cancellation_channel(bridge, monkeypatch):
    session, window, candidate = bridge
    route = NavigationState(0x123456, 1010, 52, 202, 267, True, True)
    calls, signals = [], []

    def signal(pid):
        value = SimpleNamespace(
            name=f"Local\\AtlanticaPanel.Cancel.{pid}.fresh",
            cancel=lambda: None,
            close=lambda: None,
        )
        signals.append(value)
        return value

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "pid": 200,
                    "slot": 0,
                    "status": 16,
                    "thread_id": 1234,
                    "operation": 3,
                    "navigation": {
                        "active": False,
                        "moving": False,
                        "active_raw": 0,
                        "moving_raw": 0,
                    },
                }
            ),
        )

    monkeypatch.setattr("atlantica_bot.native_action.Cancellation", signal)
    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    assert stop_movement(session, window, route)["status"] == 16
    assert len(calls) == len(signals) == 1
    args = calls[0]
    assert "--stop-move" in args and "--attack" not in args
    assert args[args.index("--route-tick") + 1] == "1010"
    assert args[args.index("--route-player") + 1] == str(0x123456)
    assert args[args.index("--cancel-event") + 1] == signals[0].name


@pytest.mark.parametrize("operation,status", [(2, 1), (1, 15)])
def test_response_to_a_different_operation_is_rejected(bridge, monkeypatch, operation, status):
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"pid": 200, "slot": 6, "thread_id": 1234, "operation": operation, "status": status}
            ),
        ),
    )
    with pytest.raises(DiagnosticError, match="respuesta no válida"):
        try_attack(*bridge)
