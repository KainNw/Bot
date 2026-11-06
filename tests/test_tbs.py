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
