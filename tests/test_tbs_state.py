from copy import deepcopy

import pytest

from atlantica_bot.tbs_state import describe_tbs_snapshot


def row(index, *, local=False, group=0, state=0, hp=100, flag=0):
    return {
        "index": index,
        "entry_2194": index,
        "member_index_219c": 0,
        "matches_local_identity_word": local,
        "status": "captured",
        "table": "0436803C",
        "raw_21a0": [group, 0],
        "raw_21a8_to_21b8": [state, 7, 0, 0, 0],
        "grid_candidate": [38, 88],
        "raw_2038": 100,
        "raw_2040": 50,
        "member_values_4c_50": [hp, 45],
        "raw_2ac8": flag,
    }


def snapshot():
    return {
        "route": "bf_context_b_candidate",
        "bf": {
            "status": "captured",
            "truncated": False,
            "tables": ["04368DB0", "043691DC", "04368C9C"],
            "controls": {
                "member_mapping_114": [0, -1, -1, -1, -1, -1, -1, -1, -1],
                "phase_798": 3,
                "selection_14c": -1,
            },
            "units": [row(0, local=True), row(1, group=1)],
        },
    }


def test_observed_main_is_independent_of_selection_and_uses_separate_tbs_position():
    data = snapshot()
    before = deepcopy(data)
    view = describe_tbs_snapshot(data)
    assert data == before
    assert view["main"]["index"] == 0 and view["main"]["position"] == [38, 88]
    assert view["main"]["hp"] == 100 and view["main"]["mp"] == 45
    assert view["main_turn_relation"] == "unknown" and view["phase"] == 3
    assert view["other_groups_alive"] == 1
    assert not view["turn_execution_available"] and not view["green_destinations_verified"]


@pytest.mark.parametrize(
    "state,movement,basic",
    [
        (0, True, True),
        (1, False, True),
        (2, True, False),
        (3, False, False),
        (4, False, False),
        (9, None, None),
    ],
)
def test_state_gates_do_not_claim_complete_action_eligibility(state, movement, basic):
    data = snapshot()
    data["bf"]["units"][0]["raw_21a8_to_21b8"][0] = state
    main = describe_tbs_snapshot(data)["main"]
    assert main["movement_state_allows"] is movement and main["basic_state_allows"] is basic
    assert not main["action_eligibility_fully_validated"]


@pytest.mark.parametrize(
    "group,relation", [(0, "same_group"), (1, "other_group"), (255, "unknown")]
)
def test_phase_three_alone_never_determines_which_group_can_act(group, relation):
    data = snapshot()
    data["bf"]["turn"] = {"status": "captured", "active_group": group, "turn_counter": 8}
    view = describe_tbs_snapshot(data)
    assert view["main_turn_relation"] == relation
    assert view["turn_counter"] == (8 if group != 255 else None)


@pytest.mark.parametrize(
    "hp,flag,status", [(0, 1, "defeated"), (0, 0, "unknown"), (10, 1, "unknown"), (10, 0, "alive")]
)
def test_death_requires_consistent_life_and_native_flag(hp, flag, status):
    data = snapshot()
    data["bf"]["units"][1] = row(1, group=1, hp=hp, flag=flag)
    view = describe_tbs_snapshot(data)
    assert view["units"][1]["life_status"] == status
    assert view["defeated_observed"] == int(status == "defeated")


@pytest.mark.parametrize("change", ["mapping", "identity", "duplicate", "wrong_table", "inactive"])
def test_main_is_not_guessed_from_nearest_unit_or_selection(change):
    data = snapshot()
    if change == "mapping":
        data["bf"]["controls"]["member_mapping_114"][0] = -1
    elif change == "identity":
        data["bf"]["units"][0]["matches_local_identity_word"] = False
    elif change == "duplicate":
        data["bf"]["units"].append(deepcopy(data["bf"]["units"][0]))
    elif change == "wrong_table":
        data["bf"]["units"][0]["table"] = "00001234"
    else:
        data["route"] = "map_candidate"
    assert describe_tbs_snapshot(data)["main"] is None
