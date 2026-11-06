"""Interpret observed BF fields without claiming complete command eligibility."""

from __future__ import annotations

STATE_LABELS = {
    0: "Estado admite movimiento y básico",
    1: "Movimiento bloqueado; estado admite básico",
    2: "Básico bloqueado; estado admite movimiento",
    3: "Movimiento y básico bloqueados",
    4: "En espera",
}


def _group(value) -> int | None:
    return value if type(value) is int and 0 <= value < 8 else None


def _unit_view(row: dict, active_group: int | None) -> dict:
    raw = row.get("raw_21a8_to_21b8", ())
    state = raw[0] if raw and type(raw[0]) is int else None
    groups = row.get("raw_21a0", ())
    group = _group(groups[0]) if groups else None
    values = row.get("member_values_4c_50", ())
    hp, mp = (
        values
        if len(values) == 2 and all(type(v) is int and v >= 0 for v in values)
        else (None, None)
    )
    dead_flag = row.get("raw_2ac8")
    defeated = hp == 0 and dead_flag == 1
    alive = hp is not None and hp > 0 and dead_flag == 0
    return {
        "index": row["index"],
        "member_index": row.get("member_index_219c"),
        "group": group,
        "position": row.get("grid_candidate"),
        "hp": hp,
        "mp": mp,
        "hp_max": row.get("raw_2038"),
        "mp_max": row.get("raw_2040"),
        "life_status": "defeated" if defeated else "alive" if alive else "unknown",
        "state": state,
        "state_label": STATE_LABELS.get(state, "Estado desconocido"),
        "same_turn_group": group == active_group
        if group is not None and active_group is not None
        else None,
        "movement_state_allows": state in (0, 2) if state in STATE_LABELS else None,
        "basic_state_allows": state in (0, 1) if state in STATE_LABELS else None,
        "action_eligibility_fully_validated": False,
    }


def describe_tbs_snapshot(snapshot: dict) -> dict:
    """Also accepts a 0.29 snapshot, whose active turn group is unknown."""
    bf = snapshot.get("bf", {})
    result = {
        "status": "unavailable",
        "main": None,
        "units": [],
        "turn_execution_available": False,
        "green_destinations_verified": False,
        "tbs_mission_automatically_identified": False,
    }
    if (
        snapshot.get("route") != "bf_context_b_candidate"
        or bf.get("status") not in ("captured", "partial")
        or bf.get("tables") != ["04368DB0", "043691DC", "04368C9C"]
    ):
        return {**result, "reason": "bf_route_not_resolved"}
    turn = bf.get("turn", {})
    active = _group(turn.get("active_group")) if turn.get("status") == "captured" else None
    rows = [
        row
        for row in bf.get("units", ())
        if row.get("status") == "captured"
        and row.get("table") == "0436803C"
        and type(row.get("index")) is int
        and row.get("entry_2194") == row["index"]
    ]
    units = [_unit_view(row, active) for row in rows]
    result.update(
        {
            "status": "observed",
            "units": units,
            "active_group": active,
            "turn_counter": turn.get("turn_counter") if active is not None else None,
            "phase": bf.get("controls", {}).get("phase_798"),
            "collection_complete": bf.get("status") == "captured" and not bf.get("truncated"),
        }
    )
    mapping = bf.get("controls", {}).get("member_mapping_114", ())
    mains = [
        row
        for row in rows
        if row.get("matches_local_identity_word") is True
        and row.get("member_index_219c") == 0
        and mapping
        and mapping[0] == row["index"]
    ]
    if len(mains) != 1:
        return {**result, "reason": "main_identity_and_slot_not_unique"}
    main = next(unit for unit in units if unit["index"] == mains[0]["index"])
    result["main"] = main
    for unit in units:
        unit["role"] = (
            "main"
            if unit is main
            else "same_group"
            if (main["group"] is not None and unit["group"] == main["group"])
            else "other_group"
            if main["group"] is not None and unit["group"] is not None
            else "unknown"
        )
    result["defeated_observed"] = sum(unit["life_status"] == "defeated" for unit in units)
    result["other_groups_alive"] = sum(
        unit["role"] == "other_group" and unit["life_status"] == "alive" for unit in units
    )
    result["main_turn_relation"] = (
        "same_group"
        if main["same_turn_group"] is True
        else ("other_group" if main["same_turn_group"] is False else "unknown")
    )
    return result
