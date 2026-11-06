import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.auto_life import AutoLife, try_auto_life
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.profiles import BotProfile, ProfileStore

PROFILE = replace(BotProfile.default(1), auto_life_enabled=True, auto_life_key="F9")
BINDING = (0x10000, 0x20000, 0x30000, 0x40000, (209, 8888, 0))


def response(status=56):
    return {
        "status": status,
        "exception": 0,
        "message": "Esperando recuperación",
        "auto_life": {
            "key": 9,
            "threshold": 50,
            "low_mask": 2,
            "unavailable_mask": 0,
            "members": [
                {"slot": i, "kind": 200 + i, "hp": 100, "mp": 20 if i == 2 else 100, "max_mp": 100}
                for i in range(1, 10)
            ],
        },
    }


@pytest.mark.parametrize("key", [f"F{i}" for i in range(1, 10)])
def test_auto_life_saves_key_threshold_by_profile_and_preserves_speed(tmp_path, key):
    profile = replace(PROFILE, auto_life_key=key, general_speed_enabled=True, general_speed_rate=3)
    store = ProfileStore(tmp_path)
    store.save(profile)
    assert store.load(1) == profile


@pytest.mark.parametrize(
    "values",
    [
        {"auto_life_threshold": 0},
        {"auto_life_threshold": 101},
        {"auto_life_threshold": True},
        {"auto_life_key": "F10"},
        {"auto_life_key": "Q"},
        {"auto_life_enabled": 1},
    ],
)
def test_invalid_auto_life_configuration_cannot_replace_saved_profile(tmp_path, values):
    store = ProfileStore(tmp_path)
    store.save(PROFILE)
    with pytest.raises(DiagnosticError):
        store.save(replace(PROFILE, **values))
    assert store.load(1) == PROFILE


def test_auto_life_uses_bound_character_and_selected_key_once(monkeypatch):
    monkeypatch.setattr("atlantica_bot.auto_life.binding", lambda session: BINDING)
    requests = []

    def request(session, window, candidate, **kwargs):
        requests.append(kwargs)
        assert candidate is None
        return response()

    monkeypatch.setattr("atlantica_bot.auto_life._request", request)
    report, bound = try_auto_life(None, None, PROFILE, "signal")
    assert bound == BINDING and not report["potion_confirmed"]
    assert requests[0]["operation"] == 19 and requests[0]["cancellation"] == "signal"
    assert requests[0]["auto_life"] == {
        "life-player": 0x30000,
        "life-info": 0x40000,
        "life-key": 9,
        "life-threshold": 50,
        "actor-kind": 209,
        "actor-serial": 8888,
        "actor-unique": 0,
    }


@pytest.mark.parametrize("recovered", [True, False])
def test_low_mp_waits_for_recovery_without_repeating_and_times_out_only_auto_life(
    monkeypatch, recovered
):
    controller = AutoLife(PROFILE)
    requests = []
    monkeypatch.setattr("atlantica_bot.auto_life.binding", lambda session: BINDING)
    monkeypatch.setattr(
        "atlantica_bot.auto_life.Reader",
        lambda s: SimpleNamespace(i32=lambda a: 80 if recovered else 20),
    )
    monkeypatch.setattr(
        "atlantica_bot.auto_life.try_auto_life",
        lambda *args: (requests.append(1) or response(), BINDING),
    )
    assert controller.tick(None, None, None, 0)
    if recovered:
        assert not controller.tick(None, None, None, 0.5)
        assert controller.report["recoveries_observed"] == 1
        assert not controller.tick(None, None, None, 1)
    else:
        assert controller.tick(None, None, None, 9.9)
        assert not controller.tick(None, None, None, 10)
        assert controller.disabled and controller.report["paused"]
        assert not controller.tick(None, None, None, 1000)
    assert requests == [1]


def test_disabled_auto_life_does_not_read_memory_or_send_keys(monkeypatch):
    monkeypatch.setattr(
        "atlantica_bot.auto_life.binding", lambda *_: pytest.fail("No read expected")
    )
    assert not AutoLife(BotProfile.default(1)).tick(None, None, None, 0)


def test_schema_nine_loads_with_auto_life_off_and_preserves_existing_general_mode(tmp_path):
    old = replace(BotProfile.default(1), general_speed_enabled=True, general_speed_rate=3)
    payload = old.summary()
    payload["schema_version"] = 9
    for key in ("auto_life_enabled", "auto_life_threshold", "auto_life_key"):
        del payload[key]
    path = tmp_path / "profile-1.json"
    saved = json.dumps(payload).encode()
    path.write_bytes(saved)
    assert ProfileStore(tmp_path).load(1) == old
    assert path.read_bytes() == saved
