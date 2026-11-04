import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from atlantica_bot.bonus import (
    BONUS_CODE_BLOCKS,
    BonusComparison,
    capture_bonus_snapshot,
    read_bonus_code,
)
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import DiagnosticError, SceneChanged
from atlantica_bot.world import GridPosition, LocalState, Observation


def snapshot(*, scene="battle", pid=100, created=777, turn=0, tick=12345):
    result = {
        "pid": pid,
        "creation_time": created,
        "classification": scene,
        "observation": {"scene_code": 2, "player": {"map_id": 127, "x": 47, "y": 75}},
    }
    if scene == "battle":
        result.update(
            {
                "binding": [pid, created, 0x700000],
                "frame": {"phase": 3, "turn_number": turn, "turn_tick": tick, "units": []},
                "memory": {"published_units": [], "bonus_type_detected": False},
            }
        )
    return result


@pytest.mark.parametrize("category", ["exp", "equipment", "exp_books", "control"])
def test_comparison_keeps_category_as_user_report_and_exports_bounded_code(category, tmp_path):
    capture = BonusComparison(100, 777)
    before = snapshot()
    name, address, size = BONUS_CODE_BLOCKS[0]
    data = b"\x90" * size
    capture.set_before(category, before, [(name, address, data)])
    before["frame"]["phase"] = 999
    after = snapshot(scene="map")
    capture.set_after(after, user_result=False)
    output = tmp_path / "bonus.zip"
    capture.export(output)
    with ZipFile(output) as archive:
        assert archive.testzip() is None and len(archive.namelist()) == 2
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["category"] == category and manifest["category_source"] == "user_reported"
        assert not manifest["bonus_type_detected"] and not manifest["collection_confirmed"]
        assert manifest["collection_user_reported"] is False and manifest["comparison_complete"]
        assert manifest["before_x"]["frame"]["phase"] == 3
        assert manifest["after_x"]["classification"] == "map"
        block = manifest["blocks"][0]
        assert archive.read(block["file"]) == data
        assert block["sha256"] == hashlib.sha256(data).hexdigest()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bonus.zip"]


def test_before_only_can_be_saved_when_bonus_disappears_without_claiming_complete_comparison(
    tmp_path,
):
    capture = BonusComparison(100, 777)
    capture.set_before("equipment", snapshot())
    capture.export(tmp_path / "partial.zip")
    with ZipFile(tmp_path / "partial.zip") as archive:
        report = json.loads(archive.read("manifest.json"))
    assert not report["comparison_complete"] and report["after_x"] is None


@pytest.mark.parametrize("stage", ["before", "after"])
@pytest.mark.parametrize("changed", [{"pid": 101}, {"created": 888}])
def test_foreign_instance_cannot_be_mixed_into_comparison(stage, changed):
    capture = BonusComparison(100, 777)
    capture.set_before("exp_books", snapshot())
    foreign = snapshot(**changed)
    with pytest.raises(DiagnosticError, match="otra instancia"):
        (capture.set_before("exp", foreign) if stage == "before" else capture.set_after(foreign))
    assert capture.category == "exp_books" and capture.after is None


@pytest.mark.parametrize("change", ["binding", "turn_regression", "new_turn_zero", "unknown_scene"])
def test_another_encounter_or_unstable_scene_is_rejected(change):
    capture = BonusComparison(100, 777)
    capture.set_before("equipment", snapshot(turn=1))
    after = snapshot(turn=1)
    if change == "binding":
        after["binding"][2] += 0x1000
    elif change == "turn_regression":
        after["frame"]["turn_number"] = 0
    elif change == "new_turn_zero":
        after["frame"]["turn_tick"] += 1000
    else:
        after["classification"] = "unknown"
    with pytest.raises(DiagnosticError):
        capture.set_after(after)
    assert capture.after is None


def test_same_battle_can_advance_a_turn_after_x():
    capture = BonusComparison(100, 777)
    capture.set_before("equipment", snapshot())
    capture.set_after(snapshot(turn=1, tick=12400), user_result=True)
    assert capture.summary()["collection_user_reported"] is True
    assert not capture.summary()["collection_confirmed"]


@pytest.mark.parametrize("category,scene", [("weapons_unknown", "battle"), ("equipment", "map")])
def test_before_label_requires_supported_category_and_active_battle(category, scene):
    with pytest.raises(DiagnosticError):
        BonusComparison(100, 777).set_before(category, snapshot(scene=scene))


def test_arbitrary_memory_blocks_cannot_be_exported():
    capture = BonusComparison(100, 777)
    with pytest.raises(DiagnosticError, match="bloques"):
        capture.set_before("equipment", snapshot(), [("heap", 0x700000, b"private")])


def test_duplicate_code_blocks_are_rejected():
    name, address, size = BONUS_CODE_BLOCKS[0]
    block = (name, address, b"\x90" * size)
    with pytest.raises(DiagnosticError, match="bloques"):
        BonusComparison(100, 777).set_before("exp_books", snapshot(), [block, block])


def test_oversized_report_does_not_damage_existing_destination(tmp_path):
    capture = BonusComparison(100, 777)
    large = snapshot()
    large["padding"] = "x" * (256 * 1024)
    capture.set_before("equipment", large)
    path = tmp_path / "existing.zip"
    path.write_bytes(b"existing")
    with pytest.raises(DiagnosticError, match="límite"):
        capture.export(path)
    assert path.read_bytes() == b"existing" and len(list(tmp_path.iterdir())) == 1


def test_code_reader_only_reads_whitelisted_image_pages_and_reports_missing_blocks():
    calls = []

    def read(pid, address, size):
        calls.append((pid, address, size))
        if address == BONUS_CODE_BLOCKS[0][1]:
            raise DiagnosticError("Unavailable")
        return b"\x90" * size

    session = SimpleNamespace(
        process=SimpleNamespace(pid=100),
        system=SimpleNamespace(read_memory=read),
        snapshot=lambda: None,
    )
    blocks, errors = read_bonus_code(session)
    assert errors == [BONUS_CODE_BLOCKS[0][0]] and len(blocks) == len(BONUS_CODE_BLOCKS) - 1
    assert calls == [(100, address, size) for _, address, size in BONUS_CODE_BLOCKS]


def test_snapshot_allows_map_after_x_and_never_reads_combat_memory_there(monkeypatch):
    session = SimpleNamespace(
        process=SimpleNamespace(pid=100), creation_time=777, snapshot=lambda: None
    )
    detector = CombatDetector(100, 777, "local_context")
    obs = Observation(100, 777, 2, GridPosition(127, 47, 75), False, LocalState(1, -1, -1, 0))
    monkeypatch.setattr(
        "atlantica_bot.bonus.CombatDetector.for_supported_session", lambda _: detector
    )
    monkeypatch.setattr("atlantica_bot.bonus.observe_scene", lambda _: obs)
    monkeypatch.setattr(
        "atlantica_bot.bonus.read_battle_frame",
        lambda _: pytest.fail("Map must not inspect combat"),
    )
    result = capture_bonus_snapshot(session)
    assert result["classification"] == "map" and "memory" not in result


@pytest.mark.parametrize("changed", ["scene", "binding", "turn"])
def test_snapshot_rejects_changes_during_memory_sampling(monkeypatch, turn_frame, changed):
    session = SimpleNamespace(
        process=SimpleNamespace(pid=100), creation_time=777, snapshot=lambda: None
    )
    detector = CombatDetector(100, 777, "local_context")
    obs = Observation(100, 777, 2, GridPosition(127, 47, 75), False, LocalState(33, 0, -1, 0))
    observations = iter(
        [obs, replace(obs, local=LocalState(1, -1, -1, 0)) if changed == "scene" else obs]
    )
    after = turn_frame
    if changed == "binding":
        after = replace(turn_frame, context=replace(turn_frame.context, context=0x800000))
    if changed == "turn":
        after = replace(turn_frame, turn_number=2)
    frames = iter([turn_frame, after])
    monkeypatch.setattr(
        "atlantica_bot.bonus.CombatDetector.for_supported_session", lambda _: detector
    )
    monkeypatch.setattr("atlantica_bot.bonus.observe_scene", lambda _: next(observations))
    monkeypatch.setattr("atlantica_bot.bonus.read_battle_frame", lambda _: next(frames))
    monkeypatch.setattr("atlantica_bot.bonus.read_bonus_memory", lambda *a: {})
    with pytest.raises(SceneChanged):
        capture_bonus_snapshot(session)
