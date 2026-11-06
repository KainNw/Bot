import hashlib
import json
import struct
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from atlantica_bot.errors import DiagnosticError, SceneChanged
from atlantica_bot.tbs import (
    MAX_SAMPLES,
    TBS_ANCHORS,
    TBS_CODE_BLOCKS,
    TbsResearch,
    TbsTrace,
    capture_tbs_snapshot,
    read_tbs_code,
)


class Memory:
    def __init__(self):
        self.data, self.reads = {}, []
        self.on_read = None

    def put(self, address, data):
        self.data.update({address + index: value for index, value in enumerate(data)})

    def word(self, address, value):
        self.put(address, struct.pack("<I", value & 0xFFFFFFFF))

    def read_memory(self, pid, address, size):
        assert pid == 123
        self.reads.append((address, size))
        if self.on_read:
            self.on_read(address, size)
        try:
            return bytes(self.data[address + index] for index in range(size))
        except KeyError as exc:
            raise DiagnosticError("Lectura incompleta simulada") from exc


@pytest.fixture
def tbs():
    memory = Memory()
    for address, expected in TBS_ANCHORS:
        memory.put(address, expected)
    for address, value in (
        (0x04A9290C, 0x300000),
        (0x300B98, 2),
        (0x300828, 0x400000),
        (0x40002C, 0x500000),
        (0x500200, 1),
        (0x50002C, 0x400000),
        (0x500318, -1),
        (0x500254, 0),
        (0x300000 + 0x16360, 0x600000),
        (0x500030, 0xA00000),
        (0x600000, 0x04368DB0),
        (0x600008, 0x043691DC),
        (0x600858, 0x04368C9C),
        (0x600860, 3),
        (0x600864, 0x900000),
        (0x600008 + 0x798, 3),
        (0x600008 + 0x7B8, 0),
        (0x600858 + 0x13C, 0),
        (0x600858 + 0x14C, 0),
    ):
        memory.word(address, value)
    memory.put(0x500204, struct.pack("<3I", 1001, 54321, 0))
    memory.put(0xA000CA, struct.pack("<3h", 52, 193, 335))
    memory.put(0x600008 + 0x7B7, b"\0")
    memory.put(0x600858 + 0x114, struct.pack("<9i", 0, *([-1] * 8)))
    for index in range(3):
        address = 0x900000 + index * 0x33B0
        header = bytearray(40)
        struct.pack_into("<3i", header, 0, index if index < 2 else -1, 1001 + index, 0)
        struct.pack_into("<2h", header, 16, 2 + index, 3)
        memory.put(address + 0x2194, header)
        if index == 2:
            continue
        memory.word(address, 0x0436803C)
        memory.word(address + 0x2038, 100)
        memory.word(address + 0x2040, 10)
        memory.put(address + 0x2AC8, b"\0")
        memory.word(address + 0x1FA8, 0xB00000 + index * 0x488)
        memory.put(0xB0004C + index * 0x488, struct.pack("<2i", 100, 50))
    state = SimpleNamespace(
        auto_battle=False, hunting=False, files=SimpleNamespace(marker_present=False)
    )
    session = SimpleNamespace(
        process=SimpleNamespace(pid=123), creation_time=777, system=memory, snapshot=lambda: state
    )
    return session, memory, state


def test_bf_uses_eight_byte_subobject_and_own_pool_without_normal_combat(tbs):
    session, memory, _ = tbs
    result = capture_tbs_snapshot(session)
    assert result["route"] == "bf_context_b_candidate"
    bf = result["bf"]
    assert (bf["common"], bf["pool"], bf["status"]) == ("00600008", "00600858", "captured")
    assert bf["capacity"] == 3 and len(bf["units"]) == 2
    main, enemy = bf["units"]
    assert main["matches_local_identity_word"] and not enemy["matches_local_identity_word"]
    assert main["grid_candidate"] == [2, 3] and main["member_values_4c_50"] == [100, 50]
    assert result["world_grid"] == [52, 193, 335]
    assert not result["tbs_mode_confirmed"] and not result["turn_execution_available"]
    assert not result["grid_semantics_verified"] and not result["writes_or_client_commands"]
    assert (0x30091C, 4) not in memory.reads
    assert (0x300000 + 0x16358, 4) not in memory.reads


@pytest.mark.parametrize(
    "a,b,route",
    [(-1, -1, "map_candidate"), (0, -1, "normal_context_a"), (0, 0, "ambiguous_contexts")],
)
def test_inactive_or_ambiguous_bf_never_follows_stale_client_pointer(tbs, a, b, route):
    session, memory, _ = tbs
    memory.word(0x500318, a)
    memory.word(0x500254, b)
    memory.word(0x300000 + 0x16360, 0xDEADBEEF)
    result = capture_tbs_snapshot(session)
    assert result["route"] == route and "bf" not in result
    assert not any(0xDEADBEEF <= address < 0xDEADBEEF + 0x1000 for address, _ in memory.reads)


@pytest.mark.parametrize("address,_", TBS_ANCHORS)
def test_changed_code_is_rejected_before_following_bf_layout(tbs, address, _):
    session, memory, _ = tbs
    memory.put(address, b"\0")
    with pytest.raises(DiagnosticError, match="código analizado"):
        capture_tbs_snapshot(session)
    assert (0x04A9290C, 4) not in memory.reads


@pytest.mark.parametrize("field", ["auto_battle", "hunting", "marker_present"])
def test_native_automation_must_be_off_during_research(tbs, field):
    session, memory, state = tbs
    setattr(state.files if field == "marker_present" else state, field, True)
    with pytest.raises(DiagnosticError, match="apagados"):
        capture_tbs_snapshot(session)
    assert not memory.reads


@pytest.mark.parametrize("changed", ["context", "actor", "selection", "collection", "unit"])
def test_transition_during_capture_cannot_be_reported_as_a_coherent_frame(tbs, changed):
    session, memory, _ = tbs
    fired = False

    def change(address, size):
        nonlocal fired
        if address == 0x900000 + 0x2040 and not fired:
            fired = True
            if changed == "context":
                memory.word(0x500254, -1)
            elif changed == "actor":
                memory.word(0x500204, 9999)
            elif changed == "selection":
                memory.word(0x600008 + 0x7B8, 1)
            elif changed == "collection":
                memory.word(0x600860, 4)
            else:
                memory.put(0x902194 + 16, struct.pack("<h", 15))

    memory.on_read = change
    with pytest.raises(SceneChanged):
        capture_tbs_snapshot(session)


def test_reused_pid_is_checked_again_after_reading(tbs):
    session, _, _ = tbs
    calls = 0
    original = session.snapshot

    def lifetime():
        nonlocal calls
        calls += 1
        if calls > 1:
            raise DiagnosticError("La instancia cambió")
        return original()

    session.snapshot = lifetime
    with pytest.raises(DiagnosticError, match="instancia cambió"):
        capture_tbs_snapshot(session)


@pytest.mark.parametrize("table", [0x600000, 0x600008, 0x600858])
def test_unknown_bf_tables_are_reported_without_following_units(tbs, table):
    session, memory, _ = tbs
    memory.word(table, 0x1234)
    bf = capture_tbs_snapshot(session)["bf"]
    assert bf["status"] == "unrecognized_layout"
    assert not any(address >= 0x900000 for address, _ in memory.reads if address < 0xA00000)


def test_unknown_unit_class_is_reported_without_dereferencing_its_member_info(tbs):
    session, memory, _ = tbs
    memory.word(0x900000, 0x1234)
    row = capture_tbs_snapshot(session)["bf"]["units"][0]
    assert row["status"] == "unrecognized_unit_table"
    assert (0x900000 + 0x1FA8, 4) not in memory.reads


@pytest.mark.parametrize("count,base", [(-1, 0x900000), (65537, 0x900000), (2, 0), (2, 0xFFFFFF00)])
def test_invalid_collection_bounds_do_not_trigger_unit_reads(tbs, count, base):
    session, memory, _ = tbs
    memory.word(0x600860, count)
    memory.word(0x600864, base)
    assert capture_tbs_snapshot(session)["bf"]["status"] == "invalid_collection"
    assert (0x902194, 40) not in memory.reads


def test_collection_limit_is_explicit_and_never_silently_claims_completeness(tbs, monkeypatch):
    session, memory, _ = tbs
    monkeypatch.setattr("atlantica_bot.tbs.MAX_UNITS", 1)
    bf = capture_tbs_snapshot(session)["bf"]
    assert bf["truncated"] and bf["observed_entries"] == 1 and bf["capacity"] == 3
    assert (0x900000 + 0x33B0 + 0x2194, 40) not in memory.reads


def test_incomplete_unit_does_not_erase_other_evidence_or_claim_a_complete_capture(tbs):
    session, memory, _ = tbs
    del memory.data[0x900000 + 0x33B0 + 0x2038]
    bf = capture_tbs_snapshot(session)["bf"]
    assert bf["status"] == "partial" and len(bf["units"]) == 1
    assert bf["unavailable_units"][0]["index"] == 1


def sample(pid=123, created=777):
    return {"pid": pid, "creation_time": created, "route": "bf_context_b_candidate"}


def test_partial_labelled_sequence_exports_user_mission_and_code_hashes(tmp_path):
    research = TbsResearch(123, 777)
    snap = sample()
    research.add("entered", snap, note="Seleccioné Main")
    snap["route"] = "changed"
    name, address, size = TBS_CODE_BLOCKS[0]
    data = b"\x90" * size
    research.set_code([(name, address, data)], [TBS_CODE_BLOCKS[-1][0]])
    destination = tmp_path / "Scourge.zip"
    research.export(destination, mission="Scourge")
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        report = json.loads(archive.read("manifest.json"))
        assert report["mission"] == "Scourge" and report["formation"] == "Solo Main"
        assert report["mission_and_formation_source"] == "user_reported"
        assert report["samples"][0]["snapshot"]["route"] == "bf_context_b_candidate"
        assert report["samples"][0]["label_source"] == "user_reported"
        assert not report["tbs_mode_confirmed"] and not report["writes_or_client_commands"]
        entry = report["blocks"][0]
        assert archive.read(entry["file"]) == data
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert report["unavailable_code"] == [TBS_CODE_BLOCKS[-1][0]]


@pytest.mark.parametrize("snap", [sample(pid=124), sample(created=778)])
def test_sequence_cannot_mix_pids_or_reused_process_ids(snap):
    research = TbsResearch(123, 777)
    with pytest.raises(DiagnosticError, match="otra instancia"):
        research.add("entered", snap)
    assert not research.samples


def test_sequence_and_note_are_bounded():
    research = TbsResearch(123, 777)
    with pytest.raises(DiagnosticError):
        research.add("entered", sample(), note="x" * 301)
    with pytest.raises(DiagnosticError):
        research.add("made_up_stage", sample())
    for _ in range(MAX_SAMPLES):
        research.add("player_turn", sample())
    with pytest.raises(DiagnosticError):
        research.add("enemy_turn", sample())
    assert len(research.samples) == MAX_SAMPLES


def test_arbitrary_heap_pages_and_duplicate_code_cannot_be_exported():
    research = TbsResearch(123, 777)
    with pytest.raises(DiagnosticError, match="bloques"):
        research.set_code([("heap", 0x900000, b"data")], [])
    name, address, size = TBS_CODE_BLOCKS[0]
    block = (name, address, b"\x90" * size)
    with pytest.raises(DiagnosticError, match="bloques"):
        research.set_code([block, block], [])


def test_existing_export_is_preserved(tmp_path):
    research = TbsResearch(123, 777)
    research.add("entered", sample())
    path = tmp_path / "existing.zip"
    path.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        research.export(path, mission="Scourge")
    assert path.read_bytes() == b"existing"


def test_code_capture_reads_only_fixed_image_pages_and_reports_unavailable_blocks():
    calls = []

    def read(pid, address, size):
        calls.append((pid, address, size))
        return b"\x90" * size if address != TBS_CODE_BLOCKS[-1][1] else b""

    session = SimpleNamespace(
        process=SimpleNamespace(pid=123),
        system=SimpleNamespace(read_memory=read),
        snapshot=lambda: None,
    )
    blocks, unavailable = read_tbs_code(session)
    assert unavailable == [TBS_CODE_BLOCKS[-1][0]] and len(blocks) == len(TBS_CODE_BLOCKS) - 1
    assert calls == [(123, address, size) for _, address, size in TBS_CODE_BLOCKS]


def publish_turn(memory, *, group=0, counter=5):
    memory.put(0x600008 + 0x3B8, struct.pack("<BBHIH", 2, group, 0, 10000, counter))
    memory.put(0x600008 + 0x7B6, b"\0")
    memory.put(0x600858 + 0x110, b"\0")
    memory.word(0x600008 + 0xE8, 4)
    memory.word(0x600008 + 0xE4, 1)


def test_turn_group_counter_and_state_remain_distinct_from_general_phase(tbs):
    session, memory, _ = tbs
    publish_turn(memory, group=1, counter=7)
    result = capture_tbs_snapshot(session)
    assert result["bf"]["controls"]["phase_798"] == 3
    assert result["bf"]["turn"]["active_group"] == 1
    assert result["bf"]["turn"]["turn_counter"] == 7
    assert result["view"]["main_turn_relation"] == "other_group"
    assert not result["view"]["turn_execution_available"]


def test_turn_change_while_reading_discards_the_frame(tbs):
    session, memory, _ = tbs
    publish_turn(memory)

    def change(address, size):
        if address == 0x900000 + 0x2040:
            publish_turn(memory, group=1, counter=6)

    memory.on_read = change
    with pytest.raises(SceneChanged):
        capture_tbs_snapshot(session)


def publish_grid(memory, *, width=5, height=5):
    memory.word(0x600858 + 0x10, 0xC00000)
    memory.put(
        0xC00004, struct.pack("<8I", 0xD00000, 0xE00000, 0, 0x600008, 0, 0xF00000, width, height)
    )
    for y in range(height):
        memory.word(0xF00000 + y * 4, y * width)
        for x in range(width):
            memory.put(0xD00000 + (y * width + x) * 8, struct.pack("<HhhBB", 0, -1, -1, 0, 0))
            memory.put(0xE00000 + (y * width + x) * 8, struct.pack("<4H", 1, 2, 3, 4))


def test_bounded_nearby_grid_preserves_cells_without_inventing_green_destinations(tbs):
    session, memory, _ = tbs
    publish_grid(memory)
    grid = capture_tbs_snapshot(session)["bf"]["terrain"]
    assert grid["status"] == "captured" and grid["center"] == [2, 3]
    assert grid["width"] == grid["height"] == 5 and len(grid["cells"]) == 25
    assert grid["cells"][0]["unit_index_word"] == -1
    assert grid["cells"][0]["secondary_words"] == [1, 2, 3, 4]
    assert not grid["green_destinations_verified"] and not grid["pathfinding_executed"]


@pytest.mark.parametrize("change", ["dimensions", "room", "row_bounds"])
def test_invalid_grid_cannot_be_used_as_reachable_cells(tbs, change):
    session, memory, _ = tbs
    publish_grid(memory)
    if change == "dimensions":
        memory.word(0xC0001C, 4097)
    elif change == "room":
        memory.word(0xC00010, 0xABCDEF)
    else:
        memory.word(0xF00000, 26)
    grid = capture_tbs_snapshot(session)["bf"]["terrain"]
    assert grid["status"] == "unavailable" and "cells" not in grid
    assert not any(0xD00000 <= address < 0xE10000 for address, _ in memory.reads)


def test_changed_terrain_is_unavailable_without_losing_coherent_unit_evidence(tbs):
    session, memory, _ = tbs
    publish_grid(memory)
    reads = 0

    def change(address, size):
        nonlocal reads
        if address == 0xD00000:
            reads += 1
            if reads > 1:
                memory.put(0xD00000, b"\x02")

    memory.on_read = change
    bf = capture_tbs_snapshot(session)["bf"]
    assert bf["terrain"]["status"] == "unavailable" and bf["status"] == "captured"
    assert len(bf["units"]) == 2


def test_turn_trace_omits_terrain_reads_for_fast_observation(tbs):
    session, memory, _ = tbs
    grid = capture_tbs_snapshot(session, include_grid=False)["bf"]["terrain"]
    assert grid["status"] == "skipped_for_turn_trace"
    assert (0x600858 + 0x10, 4) not in memory.reads


def make_trace(*, outcomes=None, used=0):
    research = TbsResearch(123, 777)
    for _ in range(used):
        research.add("player_turn", sample())
    clock = [0.0]
    calls = []
    outcomes = iter(outcomes or [sample()] * 50)

    def capture(session, *, include_grid):
        calls.append(include_grid)
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    session = SimpleNamespace(process=SimpleNamespace(pid=123), creation_time=777)
    trace = TbsTrace(research, session, clock=lambda: clock[0], capture=capture)
    return research, trace, clock, calls


def test_trace_stops_on_real_time_budget_and_marks_automatic_samples():
    research, trace, clock, calls = make_trace()
    assert trace.step() == sample()
    clock[0] = 11.9
    assert trace.step() == sample()
    clock[0] = 12
    assert trace.step() is None and not trace.running
    assert calls == [False, False] and trace.reason == "time_budget"
    assert research.samples[0]["stage"] == "turn_trace"
    assert research.samples[0]["label_source"] == "automatic_sampler"
    assert research.trace_runs[0]["samples"] == 2
    trace.stop()
    assert len(research.trace_runs) == 1


def test_trace_stops_manually_or_when_the_zip_sample_limit_is_reached():
    research, trace, _, calls = make_trace(used=MAX_SAMPLES - 1)
    trace.step()
    assert not trace.running and trace.reason == "sample_limit"
    assert len(research.samples) == MAX_SAMPLES and calls == [False]
    _, trace, _, calls = make_trace()
    trace.stop()
    assert trace.step() is None and not calls


def test_trace_retries_transient_reads_and_stops_on_uncertain_instance():
    research, trace, _, calls = make_trace(
        outcomes=[SceneChanged("Cargando"), sample(), DiagnosticError("Instancia cambió")]
    )
    assert trace.step() is None and trace.running and trace.transient_reads == 1
    assert trace.step() == sample() and len(research.samples) == 1
    assert trace.step() is None and not trace.running and len(calls) == 3
    assert research.trace_runs[0]["reason"] == "read_error"


def test_trace_cannot_accept_a_sample_from_reused_pid_or_other_instance():
    research, trace, _, _ = make_trace(outcomes=[sample(created=778)])
    assert trace.step() is None and not trace.running and not research.samples


def test_trace_control_rejects_foreign_connection_and_unbounded_runs():
    research = TbsResearch(123, 777)
    session = SimpleNamespace(process=SimpleNamespace(pid=124), creation_time=778)
    with pytest.raises(DiagnosticError, match="otra instancia"):
        TbsTrace(research, session)
    session = SimpleNamespace(process=SimpleNamespace(pid=123), creation_time=777)
    for _ in range(4):
        TbsTrace(research, session).stop()
    with pytest.raises(DiagnosticError, match="Guarda el ZIP"):
        TbsTrace(research, session)
