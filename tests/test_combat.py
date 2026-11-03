from dataclasses import replace

import pytest

from atlantica_bot.combat import CombatCalibration, CombatDetector
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.world import GridPosition, LocalState, Observation

MAP = Observation(100, 777, 2, GridPosition(52, 193, 340), local=LocalState(0, -1, -1, 0, 2))
BATTLE = replace(MAP, local=LocalState(1, 8, -1, 0, 2))


def calibrate(before=MAP, battle=BATTLE, after=MAP):
    calibration = CombatCalibration(100, 777)
    for stage, sample in zip(
        ("map_before", "battle", "map_after"), (before, battle, after), strict=True
    ):
        calibration.capture(stage, (sample,) * 3)
    return calibration


def test_calibrates_combat_when_scene_code_remains_two():
    calibration = calibrate()
    detector = calibration.detector()
    assert detector.signal == "local_context"
    assert detector.classify(MAP) == "map"
    assert detector.classify(BATTLE) == "battle"
    assert detector.classify(replace(BATTLE, local=LocalState(2, -1, 4, 0))) == "battle"
    assert calibration.summary()["samples"]["battle"][0]["scene_code"] == 2


def test_scene_rule_requires_a_labelled_round_trip_instead_of_assuming_one_means_battle():
    detector = calibrate(battle=replace(MAP, scene_code=1, player=None)).detector()
    assert detector.signal == "scene_transition"
    assert detector.classify(MAP) == "map"
    assert detector.classify(replace(MAP, scene_code=1, player=None)) == "battle"
    assert detector.classify(replace(MAP, scene_code=3, player=None)) == "unknown"


@pytest.mark.parametrize("battle", [MAP, replace(MAP, local=None), replace(MAP, scene_code=3)])
def test_unchanged_missing_or_unmapped_signals_do_not_create_a_detector(battle):
    calibration = calibrate(battle=battle)
    with pytest.raises(DiagnosticError, match="no permiten distinguir"):
        calibration.detector()
    assert "battle" in calibration.summary()["samples"]


@pytest.mark.parametrize(
    "changed",
    [replace(MAP, pid=200), replace(MAP, creation_time=888), replace(MAP, native_active=True)],
)
def test_calibration_rejects_a_different_instance_or_native_mode(changed):
    calibration = CombatCalibration(100, 777)
    with pytest.raises(DiagnosticError):
        calibration.capture("map_before", (changed,) * 3)
    assert calibration.samples == {}


def test_unstable_position_and_incomplete_sequence_cannot_arm_a_detector():
    calibration = CombatCalibration(100, 777)
    moved = replace(MAP, player=GridPosition(52, 194, 340))
    with pytest.raises(DiagnosticError, match="se movió"):
        calibration.capture("map_before", (MAP, moved, MAP))
    with pytest.raises(DiagnosticError):
        calibration.capture("battle", (BATTLE,) * 3)
    with pytest.raises(DiagnosticError):
        calibration.capture("map_before", (MAP,))
    with pytest.raises(DiagnosticError, match="Faltan"):
        calibration.detector()


def test_mixed_combat_samples_or_context_that_does_not_return_are_rejected():
    calibration = CombatCalibration(100, 777)
    calibration.capture("map_before", (MAP,) * 3)
    calibration.capture("battle", (BATTLE, MAP, BATTLE))
    calibration.capture("map_after", (MAP,) * 3)
    with pytest.raises(DiagnosticError, match="no permiten distinguir"):
        calibration.detector()
    with pytest.raises(DiagnosticError):
        calibrate(after=BATTLE).detector()


def test_return_to_another_map_does_not_validate_the_cycle():
    after = replace(MAP, player=GridPosition(53, 1, 1))
    with pytest.raises(DiagnosticError, match="mismo mapa"):
        calibrate(after=after).detector()


def test_detector_does_not_transfer_to_a_reused_pid_or_classify_missing_context_as_map():
    detector = CombatDetector(100, 777, "local_context")
    assert detector.classify(replace(MAP, local=None)) == "unknown"
    assert detector.classify(replace(BATTLE, creation_time=888)) == "unknown"
    assert detector.classify(replace(MAP, pid=200)) == "unknown"
