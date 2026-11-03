import json
import sys
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.battle import BattleFrame, BattleTrial, BattleUnit
from atlantica_bot.battle_context import NormalBattleContext
from atlantica_bot.clients import ClientWindow
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import HuntingResult
from atlantica_bot.native_action import (
    stop_movement,
    stop_native_pursuit,
    try_approach,
    try_attack,
    try_battle_action,
    try_battle_basic,
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


@pytest.fixture
def battle_trial(bridge):
    context = NormalBattleContext(
        200,
        123456,
        0x500000,
        (209, 8888, 0),
        0x600000,
        0,
        0x700000,
        0x042D8AA4,
        0x10215B8,
        (),
        client_object=0x900000,
    )
    source = BattleUnit(1, 0xA01000, 1, context.actor_identity, 3, 2318, 100, 0, 1, 0x8000)
    target = BattleUnit(2, 0xA02000, 6, (5633, 9999, 0), 5, 5000, 40, 1, 1, 0x8000)
    frame = BattleFrame(context, 3, 0, 0, 12, 123450, (source, target))
    return BattleTrial(frame, source, target)


def battle_reply(trial, status=None):
    if status is None:
        status = {6: 26, 7: 31, 8: 32}[trial.operation]
    return {
        "pid": 200,
        "slot": trial.target.world_slot if trial.target else 0,
        "thread_id": 1234,
        "operation": trial.operation,
        "status": status,
        "battle": {
            "manager": trial.frame.context.manager,
            "context": trial.frame.context.context,
            "client": trial.frame.context.client_object,
            "turn_number": trial.frame.turn_number,
            "turn_tick": trial.frame.turn_tick,
            "mercenary_slot": trial.source.member_slot,
            "target_member_slot": trial.target.member_slot if trial.target else 0,
            "source_unit": trial.source.address,
            "target_unit": trial.target.address if trial.target else 0,
            "native_error": [0, 0, 0, 0],
            "magic_key": trial.arguments().get("magic-key", 0),
            "magic_action": trial.arguments().get("magic-action", 0),
            "magic_count": len(trial.frame.magic_actions),
            "magic_actions": list(trial.frame.magic_actions)
            + [0] * (5 - len(trial.frame.magic_actions)),
        },
    }


def test_battle_basic_sends_one_bound_request_with_distinct_member_and_enemy_slots(
    bridge, battle_trial, monkeypatch
):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        for key, value in {
            "pid": 200,
            "created": 123456,
            "thread": 1234,
            "mercenary": 3,
            "enemy-member": 5,
            "slot": 6,
            "kind": 5633,
            "actor-kind": 209,
            "actor-serial": 8888,
            "turn-number": 12,
            "turn-tick": 123450,
        }.items():
            assert args[args.index(f"--{key}") + 1] == str(value)
        assert "--battle-basic" in args and "--native-attack" not in args
        assert kwargs["timeout"] == 8
        return SimpleNamespace(returncode=0, stdout=json.dumps(battle_reply(battle_trial)))

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    session, window, _ = bridge
    report = try_battle_basic(session, window, battle_trial)
    assert len(calls) == 1 and report["status"] == 26 and report["action"] == "battle_basic"
    assert not report["attack_confirmed"] and not report["battle_confirmed"]


@pytest.mark.parametrize(
    "key,value",
    [("turn_number", 99), ("turn_tick", 123451), ("mercenary_slot", 4), ("target_unit", 0xB00000)],
)
def test_battle_reply_from_a_different_turn_or_member_is_rejected(
    bridge, battle_trial, monkeypatch, key, value
):
    reply = battle_reply(battle_trial)
    reply["battle"][key] = value
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(reply)),
    )
    with pytest.raises(DiagnosticError, match="respuesta no válida"):
        try_battle_basic(bridge[0], bridge[1], battle_trial)


def test_foreign_battle_instance_is_rejected_before_opening_the_helper(
    bridge, battle_trial, monkeypatch
):
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *a, **kw: pytest.fail("foreign process"),
    )
    trial = replace(
        battle_trial,
        frame=replace(
            battle_trial.frame, context=replace(battle_trial.frame.context, creation_time=99999)
        ),
    )
    with pytest.raises(DiagnosticError, match="otra instancia"):
        try_battle_basic(bridge[0], bridge[1], trial)


def test_native_battle_rejection_returns_without_retry_or_claiming_a_hit(
    bridge, battle_trial, monkeypatch
):
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps(battle_reply(battle_trial, 30)))

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    report = try_battle_basic(bridge[0], bridge[1], battle_trial)
    assert len(calls) == 1 and report["status"] == 30 and not report["attack_confirmed"]


def test_world_attack_queue_result_cannot_be_accepted_as_a_battle_action(
    bridge, battle_trial, monkeypatch
):
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout=json.dumps(battle_reply(battle_trial, 1))
        ),
    )
    with pytest.raises(DiagnosticError, match="respuesta no válida"):
        try_battle_basic(bridge[0], bridge[1], battle_trial)


@pytest.fixture
def magic_trial(battle_trial):
    return replace(
        battle_trial,
        action="W",
        frame=replace(
            battle_trial.frame, selected_unit=battle_trial.source.address, magic_actions=(101, 102)
        ),
    )


def test_selection_uses_only_own_member_and_never_sends_an_enemy_target(
    bridge, battle_trial, monkeypatch
):
    trial = replace(battle_trial, action="select", target=None)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert "--battle-select" in args and "--slot" not in args
        assert "--enemy-member" not in args and "--target-unit" not in args
        assert args[args.index("--mercenary") + 1] == "3"
        return SimpleNamespace(returncode=0, stdout=json.dumps(battle_reply(trial)))

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    report = try_battle_action(bridge[0], bridge[1], trial)
    assert len(calls) == 1 and report["status"] == 31 and report["action"] == "battle_select"


def test_magic_can_request_own_target_with_the_exact_bar_shortcut(bridge, magic_trial, monkeypatch):
    trial = replace(magic_trial, target=magic_trial.source)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert "--battle-magic" in args
        for key, value in {
            "slot": 1,
            "kind": 209,
            "enemy-member": 3,
            "magic-key": 2,
            "magic-action": 102,
        }.items():
            assert args[args.index(f"--{key}") + 1] == str(value)
        return SimpleNamespace(returncode=0, stdout=json.dumps(battle_reply(trial)))

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    report = try_battle_action(bridge[0], bridge[1], trial)
    assert len(calls) == 1 and report["status"] == 32 and report["requested_action"] == "W"
    assert not report["attack_confirmed"]


@pytest.mark.parametrize("status", [33, 34, 35])
def test_magic_rejection_never_falls_back_or_retries(bridge, magic_trial, monkeypatch, status):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps(battle_reply(magic_trial, status)))

    monkeypatch.setattr("atlantica_bot.native_action.subprocess.run", run)
    report = try_battle_action(bridge[0], bridge[1], magic_trial)
    assert len(calls) == 1 and "--battle-magic" in calls[0] and report["status"] == status


@pytest.mark.parametrize("field,value", [("magic_key", 1), ("magic_action", 999)])
def test_response_for_other_magic_is_rejected(bridge, magic_trial, monkeypatch, field, value):
    reply = battle_reply(magic_trial)
    reply["battle"][field] = value
    monkeypatch.setattr(
        "atlantica_bot.native_action.subprocess.run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(reply)),
    )
    with pytest.raises(DiagnosticError, match="respuesta no válida"):
        try_battle_action(bridge[0], bridge[1], magic_trial)
