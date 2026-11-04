import hashlib
import json
import struct
from dataclasses import replace
from zipfile import ZipFile

import pytest

from atlantica_bot.battle_context import MemberSnapshot, NormalBattleContext
from atlantica_bot.capture import (
    ANCHOR_ADDRESS,
    ANCHOR_BYTES,
    CODE_BLOCKS,
    COMBAT_CODE_BLOCKS,
    COMBAT_READONLY_BLOCKS,
    export_code_context,
)
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import MARKER_NAME, HuntingResult
from atlantica_bot.report import Process
from atlantica_bot.session import GameSession, LiveState
from atlantica_bot.speed import (
    CONTEXT_ACCESS_ADDRESS,
    CONTEXT_ACCESS_BYTES,
    SPEED_CODE_BLOCKS,
    SPEED_GLOBAL_FIELDS,
    SPEED_READONLY_BLOCKS,
)
from atlantica_bot.world import GridPosition, LocalState, Observation

SPEED_CAPTURE_SIZE = sum(size for _, _, size in SPEED_CODE_BLOCKS + SPEED_READONLY_BLOCKS)


class CaptureSystem:
    def __init__(self):
        self.reads = []
        self.anchor = ANCHOR_BYTES
        self.short = False
        self.zero = False
        self.unsupported_table = False
        self.short_combat = False
        self.short_readonly = False
        self.short_normal_method = False
        self.many_normal_methods = False
        self.many_client_methods = False
        self.missing_speed = False

    def read_memory(self, pid, address, size):
        assert pid == 123
        self.reads.append((address, size))
        if address == ANCHOR_ADDRESS:
            return self.anchor
        if address == 0x04A9290C:
            return (0x30000000).to_bytes(4, "little")
        if address == 0x30000000:
            table = 0 if self.unsupported_table else 0x042A0000
            return table.to_bytes(4, "little")
        if address == 0x30000B98:
            return (2).to_bytes(4, "little", signed=True)
        if address == 0x042A0064:
            return (0x00500010).to_bytes(4, "little")
        if (address, size) == (0x00500000, 0x2000):
            return b"\x90" * size
        if (address, size) == (0x04303000, 256):
            if self.many_normal_methods:
                return struct.pack("<64I", *(0x700010 + n * 0x3000 for n in range(64)))
            return struct.pack("<64I", 0x700010, 0x700040, 0x8B0010, *([0] * 61))
        if (address, size) == (0x04304000, 256):
            if self.many_client_methods:
                return struct.pack("<64I", *(0x800010 + n * 0x3000 for n in range(64)))
            return struct.pack("<64I", 0x5A481F, 0x700010, 0x700040, *([0] * 61))
        if self.many_normal_methods and 0x700000 <= address < 0x7C0000 and size == 0x2000:
            return b"\x90" * size
        if self.many_client_methods and 0x800000 <= address < 0x8C0000 and size == 0x2000:
            return b"\x90" * size
        if (address, size) == (0x00700000, 0x2000):
            return b"\x90" * (size - int(self.short_normal_method))
        for _, candidate, fmt in SPEED_GLOBAL_FIELDS:
            if address == candidate and size == struct.calcsize(fmt):
                return struct.pack(fmt, 100 if fmt in ("<i", "<I") else 1.0)
        if (address, size) == (0x0060265C, 4):
            return struct.pack("<f", 1.0)
        if (address, size) == (CONTEXT_ACCESS_ADDRESS, len(CONTEXT_ACCESS_BYTES)):
            return bytes(size)  # An unresolved accessor must not follow pointers.
        speed_blocks = SPEED_CODE_BLOCKS + SPEED_READONLY_BLOCKS
        if self.missing_speed and (address, size) in [(a, s) for _, a, s in speed_blocks]:
            raise DiagnosticError("Página de investigación no disponible")
        assert (address, size) in [
            (address, size)
            for _, address, size in (
                CODE_BLOCKS + COMBAT_CODE_BLOCKS + COMBAT_READONLY_BLOCKS + speed_blocks
            )
        ]
        if self.short_combat and address == COMBAT_CODE_BLOCKS[0][1]:
            return bytes(size - 1)
        if self.short_readonly and address == COMBAT_READONLY_BLOCKS[0][1]:
            return bytes(size - 1)
        if self.short:
            return bytes(size - 1)
        return bytes(size) if self.zero else bytes([0x90]) * size


@pytest.fixture
def session(executable, monkeypatch):
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    monkeypatch.setattr("atlantica_bot.hunting.SUPPORTED_CLIENT_SHA256", digest)
    session = GameSession(
        CaptureSystem(), Process(123, "Atlantica.exe"), executable, executable.parent
    )
    monkeypatch.setattr(
        session, "snapshot", lambda: LiveState(False, 17, False, HuntingResult(False, False, False))
    )

    def unavailable(_):
        raise DiagnosticError("Contexto normal no disponible en esta muestra simulada.")

    monkeypatch.setattr("atlantica_bot.capture.read_normal_battle", unavailable)
    monkeypatch.setattr(
        "atlantica_bot.capture.observe_scene", lambda _: battle_observation(active=False)
    )
    return session


def test_exports_only_bounded_code_and_manifest_with_auto_battle_off(session, tmp_path):
    output = tmp_path / "context.zip"
    export_code_context(session, output)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == (
            len(CODE_BLOCKS) + len(SPEED_CODE_BLOCKS) + len(SPEED_READONLY_BLOCKS) + 2
        )
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["state_at_start"]["auto_battle"] is False
        assert str(session.directory) not in json.dumps(manifest)
        assert sum(block["size"] for block in manifest["blocks"]) == (
            100 * 1024 + SPEED_CAPTURE_SIZE
        )
        speed = manifest["speed_diagnostic"]
        assert speed["scene_before"]["local"]["context_a"] == -1
        assert speed["scene_after"]["local"]["context_a"] == -1
        assert not speed["speed_control_available"] and not speed["writes_or_client_commands"]
        assert manifest["dispatch_resolution"] == {
            "owner_context_code": 2,
            "status": "captured",
            "function_address": "00500010",
        }
        for block in manifest["blocks"]:
            data = archive.read(block["file"])
            assert len(data) == block["size"]
            assert hashlib.sha256(data).hexdigest() == block["sha256"]
    assert not (session.directory / MARKER_NAME).exists()


def battle_observation(*, active=True, native=False, pid=123, created=777):
    return Observation(
        pid,
        created,
        2,
        GridPosition(127, 35, 72),
        native,
        LocalState(33, 0 if active else -1, -1, 20496),
    )


def test_combat_export_contains_fixed_code_dependencies_readonly_tables_and_controls(
    session, tmp_path, monkeypatch
):
    session.creation_time = 777
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: battle_observation())
    output = tmp_path / "battle.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_version"] == 4 and manifest["purpose"] == "battle_turn_diagnostic"
        assert sum(b["size"] for b in manifest["blocks"]) == 892 * 1024 + SPEED_CAPTURE_SIZE
        assert len(archive.namelist()) == (
            len(CODE_BLOCKS)
            + len(COMBAT_CODE_BLOCKS)
            + len(COMBAT_READONLY_BLOCKS)
            + len(SPEED_CODE_BLOCKS)
            + len(SPEED_READONLY_BLOCKS)
            + 2
        )
        for block in manifest["blocks"]:
            data = archive.read(block["file"])
            assert len(data) == block["size"]
            assert hashlib.sha256(data).hexdigest() == block["sha256"]
            address = int(block["address"], 16)
            if block["kind"] == "readonly_constants":
                assert 0x03F85000 <= address < address + block["size"] <= 0x044F9000
            else:
                assert block["kind"] == "code"
                assert 0x00401000 <= address < address + block["size"] <= 0x03F85000
        constants = [b for b in manifest["blocks"] if b["kind"] == "readonly_constants"]
        assert sorted(b["size"] for b in constants) == [4 * 1024] * 3 + [8 * 1024, 16 * 1024]
    combat = manifest["combat"]
    assert combat["before"]["local"]["context_a"] == combat["after"]["local"]["context_a"] == 0
    assert combat["reported_controls"]["magic_shortcuts"] == list("QWERT")
    assert combat["reported_controls"]["loot"] == "X"
    assert not combat["turn_state_verified"] and not combat["turn_execution_available"]
    assert str(session.directory) not in json.dumps(manifest)
    assert not (session.directory / MARKER_NAME).exists()


def test_export_includes_bounded_animation_dependencies_and_labels_static_data(
    session, tmp_path, monkeypatch
):
    from atlantica_bot.animation_code import ANCHORS, ROOT

    session.creation_time = 777
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: battle_observation())
    update = bytearray(b"\xcc" * 0x3000)
    for address, expected in ANCHORS.items():
        update[address - 0xA19000 : address - 0xA19000 + len(expected)] = expected
    child, static = 0xA527C0, 0x043E1000
    body = (
        b"\x68"
        + struct.pack("<I", static)
        + b"\xe8"
        + struct.pack("<i", child - (ROOT + 16 + 5) - 5)
        + b"\xc3"
    )
    update[ROOT - 0xA19000 + 16 : ROOT - 0xA19000 + 16 + len(body)] = body
    child_page = bytearray(b"\xcc" * 4096)
    child_page[child % 4096] = 0xC3
    extra = {
        (0xA19000, 0x3000): bytes(update),
        (0xA52000, 4096): bytes(child_page),
        (static, 4096): b"labels\0" + bytes(4089),
    }
    original = session.system.read_memory
    monkeypatch.setattr(
        session.system,
        "read_memory",
        lambda pid, address, size: (
            extra[(address, size)] if (address, size) in extra else original(pid, address, size)
        ),
    )
    output = tmp_path / "animation.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        graph = manifest["animation_dependencies"]
        assert graph["status"] == "captured" and len(graph["nodes"]) == 2
        assert graph["new_code_pages"] == ["00A52000"] and graph["new_data_pages"] == ["043E1000"]
        blocks = {block["address"]: block for block in manifest["blocks"]}
        assert blocks["043E1000"]["kind"] == "readonly_constants"
        assert blocks["00A52000"]["kind"] == "code"
        for address in ("043E1000", "00A52000"):
            block = blocks[address]
            assert hashlib.sha256(archive.read(block["file"])).hexdigest() == block["sha256"]


def test_incomplete_method_tables_are_not_saved_as_a_complete_battle_capture(
    session, tmp_path, monkeypatch
):
    session.creation_time = 777
    session.system.short_readonly = True
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: battle_observation())
    output = tmp_path / "battle.zip"
    with pytest.raises(DiagnosticError, match="incompleta"):
        export_code_context(session, output, include_combat=True)
    assert not output.exists()


def test_missing_speed_research_pages_do_not_block_the_existing_battle_export(
    session, tmp_path, monkeypatch
):
    session.creation_time = 777
    session.system.missing_speed = True
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: battle_observation())
    output = tmp_path / "battle.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert archive.testzip() is None
    speed = manifest["combat"]["speed_diagnostic"]
    assert speed["unavailable_blocks"] == [
        name for name, _, _ in SPEED_CODE_BLOCKS + SPEED_READONLY_BLOCKS
    ]
    assert sum(b["size"] for b in manifest["blocks"]) == 892 * 1024
    assert speed["before"]["fields"]["rate_input"]["value"] == 100
    assert not speed["speed_control_available"]


@pytest.fixture
def normal_context(session, monkeypatch):
    session.creation_time = 777
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: battle_observation())
    context = NormalBattleContext(
        123,
        777,
        0x500000,
        (1001, 123456, 0),
        0x600000,
        0,
        0x700000,
        0x04303000,
        0x10215B8,
        tuple(MemberSnapshot(n, 1000 + n, 100, 50) for n in range(1, 10)),
    )
    monkeypatch.setattr("atlantica_bot.capture.read_normal_battle", lambda _: context)
    return context


def test_normal_context_capture_follows_only_verified_image_methods_and_reuses_code_blocks(
    session, normal_context, tmp_path
):
    output = tmp_path / "normal.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        report = manifest["combat"]
        assert report["normal_combat"]["context"] == normal_context.context
        assert len(report["normal_combat"]["members"]) == 9
        methods = report["normal_method_resolution"]
        assert methods["status"] == "captured" and len(methods["entries"]) == 3
        assert not methods["limit_reached"]
        assert methods["entries"][0]["block"] == methods["entries"][1]["block"]
        assert methods["entries"][2]["block"] == "battle-client-actions"
        assert sum(b["size"] for b in manifest["blocks"]) == (900 * 1024 + 256 + SPEED_CAPTURE_SIZE)
        speed = report["speed_diagnostic"]
        assert speed["before"]["fields"]["manager_rate_candidate"]["value"] == 1.0
        assert speed["after"]["manager"] == normal_context.manager
        assert not speed["speed_control_available"] and not speed["writes_or_client_commands"]
        table = next(b for b in manifest["blocks"] if b["address"] == "04303000")
        assert table["kind"] == "readonly_constants"
        assert archive.testzip() is None


@pytest.mark.parametrize(
    "field,resolution",
    [
        ("method_table_candidate", "normal_method_resolution"),
        ("client_method_table_candidate", "normal_client_method_resolution"),
    ],
)
def test_object_table_outside_readonly_image_is_never_followed(
    session, normal_context, tmp_path, monkeypatch, field, resolution
):
    context = replace(normal_context, **{field: 0x30010000})
    monkeypatch.setattr("atlantica_bot.capture.read_normal_battle", lambda _: context)
    output = tmp_path / "normal.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        report = json.loads(archive.read("manifest.json"))["combat"]
        assert report[resolution]["status"] == "unavailable"
    assert not any(address == 0x30010000 for address, _ in session.system.reads)


def test_related_client_table_is_captured_and_reuses_normal_client_and_manager_blocks(
    session, normal_context, tmp_path, monkeypatch
):
    context = replace(
        normal_context,
        context_word=0x50100001,
        client_object=0x900000,
        client_method_table_candidate=0x04304000,
    )
    monkeypatch.setattr("atlantica_bot.capture.read_normal_battle", lambda _: context)
    output = tmp_path / "normal.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    report = manifest["combat"]
    methods = report["normal_client_method_resolution"]
    assert methods["status"] == "captured" and len(methods["entries"]) == 3
    assert methods["entries"][0]["block"] == "normal-battle-client"
    assert methods["entries"][1]["block"] == "normal-manager-method-00"
    assert methods["entries"][2]["block"] == "normal-manager-method-00"
    tables = [b for b in manifest["blocks"] if b["size"] == 256]
    assert len(tables) == 2 and all(b["kind"] == "readonly_constants" for b in tables)
    assert sum(b["size"] for b in manifest["blocks"]) == 900 * 1024 + 512 + SPEED_CAPTURE_SIZE
    assert (context.context_word, 256) not in session.system.reads


@pytest.mark.parametrize(
    "field,value",
    [
        ("context", 0x700100),
        ("method_table_candidate", 0x04303100),
        ("client_object", 0x900000),
    ],
)
def test_context_or_method_owner_replacement_during_capture_never_creates_a_valid_zip(
    session, normal_context, tmp_path, monkeypatch, field, value
):
    versions = iter((normal_context, replace(normal_context, **{field: value})))
    monkeypatch.setattr("atlantica_bot.capture.read_normal_battle", lambda _: next(versions))
    output = tmp_path / "normal.zip"
    with pytest.raises(DiagnosticError, match="contexto del combate cambió"):
        export_code_context(session, output, include_combat=True)
    assert not output.exists()


def test_known_normal_table_stops_before_utf16_label_words_that_resemble_code_pointers(
    session, normal_context, tmp_path, monkeypatch
):
    context = replace(normal_context, method_table_candidate=0x042D8AA4)
    monkeypatch.setattr("atlantica_bot.capture.read_normal_battle", lambda _: context)
    original_read = session.system.read_memory
    methods = (
        0x4F5168,
        0x4F0675,
        0x4F6C02,
        0x4F5923,
        0x4F41DF,
        0x4F8987,
        0x4F4A30,
        0x4F5F28,
        0x4F5F86,
        0x538BC3,
        0x4F070A,
        0x4F4CB9,
        0x4F3C95,
    )
    table = struct.pack("<13I", *methods) + "$leftturn".encode("utf-16le") + bytes(186)
    assert len(table) == 256

    def read(pid, address, size):
        if (address, size) == (0x042D8AA4, 256):
            return table
        return original_read(pid, address, size)

    session.system.read_memory = read
    output = tmp_path / "known-normal.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    resolution = manifest["combat"]["normal_method_resolution"]
    assert resolution["entry_limit"] == 13 and len(resolution["entries"]) == 13
    assert resolution["boundary_source"] == "verified_table_end_before_utf16_label"
    assert sum(b["size"] for b in manifest["blocks"]) == 892 * 1024 + 256 + SPEED_CAPTURE_SIZE
    assert (0x6C0000, 0x2000) not in session.system.reads


def test_incomplete_dynamically_resolved_method_is_not_saved(session, normal_context, tmp_path):
    session.system.short_normal_method = True
    output = tmp_path / "normal.zip"
    with pytest.raises(DiagnosticError, match="incompleta"):
        export_code_context(session, output, include_combat=True)
    assert not output.exists()


def test_large_method_table_cannot_expand_export_beyond_the_documented_limit(
    session, normal_context, tmp_path
):
    session.system.many_normal_methods = True
    output = tmp_path / "normal.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    methods = manifest["combat"]["normal_method_resolution"]
    assert methods["limit_reached"] and len(methods["entries"]) == 64
    assert sum(b["size"] for b in manifest["blocks"]) == 1404 * 1024 + 256 + SPEED_CAPTURE_SIZE


def test_two_large_tables_stay_within_combined_limit_and_reuse_existing_code(
    session, normal_context, tmp_path, monkeypatch
):
    session.system.many_normal_methods = True
    session.system.many_client_methods = True
    context = replace(normal_context, client_method_table_candidate=0x04304000)
    monkeypatch.setattr("atlantica_bot.capture.read_normal_battle", lambda _: context)
    output = tmp_path / "normal.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    for key in ("normal_method_resolution", "normal_client_method_resolution"):
        methods = manifest["combat"][key]
        assert methods["limit_reached"] and len(methods["entries"]) == 64
    # Every new entry adds at most 8 KiB; fixed client blocks can cover multiple entries.
    assert sum(b["size"] for b in manifest["blocks"]) <= 1916 * 1024 + 512
    assert len({b["file"] for b in manifest["blocks"]}) == len(manifest["blocks"])


@pytest.mark.parametrize(
    "sample",
    [
        battle_observation(active=False),
        battle_observation(native=True),
        battle_observation(pid=999),
        battle_observation(created=888),
    ],
)
def test_combat_export_rejects_wrong_scene_mode_or_instance_before_code_reads(
    session, tmp_path, monkeypatch, sample
):
    session.creation_time = 777
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: sample)
    output = tmp_path / "battle.zip"
    with pytest.raises(DiagnosticError):
        export_code_context(session, output, include_combat=True)
    assert not output.exists() and session.system.reads == []


def test_battle_ending_during_export_does_not_create_mislabelled_archive(
    session, tmp_path, monkeypatch
):
    session.creation_time = 777
    samples = iter((battle_observation(), battle_observation(active=False)))
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: next(samples))
    output = tmp_path / "battle.zip"
    with pytest.raises(DiagnosticError, match="combate cambió"):
        export_code_context(session, output, include_combat=True)
    assert not output.exists()


def test_incomplete_battle_code_is_not_saved(session, tmp_path, monkeypatch):
    session.creation_time = 777
    session.system.short_combat = True
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: battle_observation())
    output = tmp_path / "battle.zip"
    with pytest.raises(DiagnosticError, match="incompleta"):
        export_code_context(session, output, include_combat=True)
    assert not output.exists()


def test_unsupported_dynamic_table_is_reported_without_exporting_arbitrary_memory(
    session, tmp_path
):
    session.system.unsupported_table = True
    output = tmp_path / "context.zip"
    export_code_context(session, output)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["dispatch_resolution"]["status"] == "unavailable"
        assert len(archive.namelist()) == (
            len(CODE_BLOCKS) + len(SPEED_CODE_BLOCKS) + len(SPEED_READONLY_BLOCKS) + 1
        )


def test_existing_output_is_not_overwritten(session, tmp_path):
    output = tmp_path / "existing.zip"
    output.write_bytes(b"user file")
    with pytest.raises(FileExistsError):
        export_code_context(session, output)
    assert output.read_bytes() == b"user file"


def test_export_includes_same_instance_history_without_profile_names_or_arbitrary_fields(
    session, tmp_path
):
    session.creation_time = 777
    report = {
        "pid": 123,
        "detector": {"instance_creation_time": 777},
        "events": [{"event": "attack_not_confirmed", "elapsed_seconds": 30}],
        "target_history": [{"slot": 6, "identity": [14801, 67723769, 0]}],
        "native_attack": {"enabled": True, "requests": 1, "search_radius": 60},
        "combat": {
            "enabled": True,
            "roster": [{"slot": 1, "name": "private-mercenary-label", "present": True}],
        },
        "profile": {"name": "private-mercenary-label"},
        "directory": "private-installation-path",
    }
    output = tmp_path / "context.zip"
    export_code_context(session, output, bot_context=report)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["bot_context"]["events"] == report["events"]
    assert manifest["bot_context"]["target_history"] == report["target_history"]
    assert manifest["bot_context"]["native_attack"] == report["native_attack"]
    assert manifest["bot_context"]["combat"]["roster"] == [{"slot": 1, "present": True}]
    assert report["combat"]["roster"][0]["name"] == "private-mercenary-label"
    assert "private-mercenary-label" not in json.dumps(manifest)
    assert "private-installation-path" not in json.dumps(manifest)


@pytest.mark.parametrize("pid,created", [(999, 777), (123, 888)])
def test_foreign_context_is_rejected_before_code_read_or_file_creation(
    session, tmp_path, pid, created
):
    session.creation_time = 777
    output = tmp_path / "context.zip"
    with pytest.raises(DiagnosticError, match="otra instancia"):
        export_code_context(
            session,
            output,
            bot_context={
                "pid": pid,
                "detector": {"instance_creation_time": created},
            },
        )
    assert not output.exists() and session.system.reads == []


@pytest.mark.parametrize("failure", ["anchor", "short", "zero"])
def test_bad_or_incomplete_memory_never_creates_an_archive(session, tmp_path, failure):
    if failure == "anchor":
        session.system.anchor = bytes(len(ANCHOR_BYTES))
    else:
        setattr(session.system, failure, True)
    output = tmp_path / "context.zip"
    with pytest.raises(DiagnosticError):
        export_code_context(session, output)
    assert not output.exists()


def test_process_exit_during_capture_does_not_leave_a_valid_report(session, tmp_path, monkeypatch):
    def snapshot():
        if session.system.reads:
            raise DiagnosticError("El cliente se cerró durante la lectura.")
        return LiveState(False, 17, False, HuntingResult(False, False, False))

    monkeypatch.setattr(session, "snapshot", snapshot)
    output = tmp_path / "context.zip"
    with pytest.raises(DiagnosticError, match="cerró"):
        export_code_context(session, output)
    assert not output.exists()


def test_changed_build_is_rejected_before_reading_code(session, tmp_path):
    session.executable.write_bytes(b"different client")
    with pytest.raises(DiagnosticError, match="compilación"):
        export_code_context(session, tmp_path / "context.zip")
    assert session.system.reads == []
