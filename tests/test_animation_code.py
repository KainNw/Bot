import struct
from types import SimpleNamespace

import pytest

from atlantica_bot import animation_code as trace
from atlantica_bot.errors import DiagnosticError


def call(source, target, opcode=b"\xe8"):
    return opcode + struct.pack("<i", target - source - 5)


def page(address, code):
    data = bytearray(b"\xcc" * trace.PAGE_SIZE)
    offset = address % trace.PAGE_SIZE
    data[offset : offset + len(code)] = code
    return bytes(data)


def environment(monkeypatch, code, pages=None):
    monkeypatch.setattr(trace, "ANCHORS", {trace.ROOT: code[:1]})
    monkeypatch.setattr(trace, "STATIC_METHOD_EXPECTED", {})
    blocks = [("captured-root", trace.ROOT & ~0xFFF, page(trace.ROOT, code))]
    calls = []

    def read(pid, address, size):
        assert pid == 100 and size == trace.PAGE_SIZE
        assert trace.ENGINE_RANGE[0] <= address < trace.ENGINE_RANGE[1] or (
            trace.DATA_RANGE[0] <= address < trace.DATA_RANGE[1]
        )
        calls.append(address)
        if address not in (pages or {}):
            raise DiagnosticError("No disponible")
        return pages[address]

    session = SimpleNamespace(
        process=SimpleNamespace(pid=100), system=SimpleNamespace(read_memory=read)
    )
    return session, blocks, calls


def test_decoder_probe_uses_fixed_bytes_only():
    assert trace.decoder_probe()


def test_collects_direct_calls_both_branches_and_static_data_without_following_indirect_calls(
    monkeypatch,
):
    first, second, data = 0xA52010, 0xA53010, 0x043E1000
    code = (
        call(trace.ROOT, first)
        + b"\x74\x05"
        + call(trace.ROOT + 7, second)
        + b"\xff\xd0\x68"
        + struct.pack("<I", data)
        + b"\xc3"
    )
    session, blocks, calls = environment(
        monkeypatch,
        code,
        {
            first & ~0xFFF: page(first, b"\xc3"),
            second & ~0xFFF: page(second, b"\xc3"),
            data: b"labels\0" + bytes(trace.PAGE_SIZE - 7),
        },
    )
    report = trace.capture_animation_dependencies(session, blocks)
    assert report["status"] == "captured" and len(report["nodes"]) == 3
    assert set(calls) == {first & ~0xFFF, second & ~0xFFF, data}
    assert len(blocks) == 4
    assert any(r["kind"] == "indirect_call" and r["target"] is None for r in report["references"])
    assert report["new_data_pages"] == [f"{data:08X}"]
    assert not report["semantics_verified"] and not report["coverage_complete"]
    assert not report["executes_client_functions"]


def test_changed_anchor_never_causes_additional_page_reads(monkeypatch):
    session, blocks, calls = environment(monkeypatch, b"\xc3")
    monkeypatch.setattr(trace, "ANCHORS", {trace.ROOT: b"\xe8"})
    report = trace.capture_animation_dependencies(session, blocks)
    assert report["reason"] == "update_code_changed" and not calls
    assert len(blocks) == 1


def test_missing_fixed_anchor_never_reads_it_from_an_unverified_target(monkeypatch):
    session, _, calls = environment(monkeypatch, b"\xc3")
    report = trace.capture_animation_dependencies(session, [])
    assert report["reason"] == "update_anchor_not_captured" and not calls


def test_cycles_and_repeated_calls_capture_each_function_once(monkeypatch):
    child = 0xA52010
    code = call(trace.ROOT, child) + call(trace.ROOT + 5, child) + b"\xc3"
    session, blocks, calls = environment(
        monkeypatch, code, {child & ~0xFFF: page(child, call(child, trace.ROOT) + b"\xc3")}
    )
    report = trace.capture_animation_dependencies(session, blocks)
    assert len(report["nodes"]) == 2 and calls == [child & ~0xFFF]


def test_depth_limit_records_but_does_not_read_deeper_callees(monkeypatch):
    child, deeper = 0xA52010, 0xA53010
    monkeypatch.setattr(trace, "MAX_DEPTH", 1)
    session, blocks, calls = environment(
        monkeypatch,
        call(trace.ROOT, child) + b"\xc3",
        {child & ~0xFFF: page(child, call(child, deeper) + b"\xc3")},
    )
    report = trace.capture_animation_dependencies(session, blocks)
    assert "depth" in report["limits_reached"]
    assert calls == [child & ~0xFFF] and len(report["nodes"]) == 2


@pytest.mark.parametrize("failure", [False, True])
def test_code_page_budget_counts_failed_attempts_too(monkeypatch, failure):
    first, second = 0xA52010, 0xA53010
    monkeypatch.setattr(trace, "MAX_CODE_PAGES", 1)
    pages = {} if failure else {first & ~0xFFF: page(first, b"\xc3")}
    session, blocks, calls = environment(
        monkeypatch, call(trace.ROOT, first) + call(trace.ROOT + 5, second) + b"\xc3", pages
    )
    report = trace.capture_animation_dependencies(session, blocks)
    assert calls == [first & ~0xFFF]
    assert len(report["attempted_code_pages"]) == 1
    assert "new_code_pages" in report["limits_reached"]
    assert len(blocks) == 1 + int(not failure)


def test_data_page_budget_never_follows_heap_values(monkeypatch):
    first, second = 0x043E1000, 0x043E2000
    monkeypatch.setattr(trace, "MAX_DATA_PAGES", 1)
    code = b"".join(b"\x68" + struct.pack("<I", a) for a in (first, second, 0x60000000)) + b"\xc3"
    session, blocks, calls = environment(monkeypatch, code, {first: b"x" * trace.PAGE_SIZE})
    report = trace.capture_animation_dependencies(session, blocks)
    assert calls == [first] and len(report["new_data_pages"]) == 1
    assert "new_data_pages" in report["limits_reached"]
    assert all(r["target"] != "60000000" for r in report["references"])


def test_register_relative_displacement_is_not_treated_as_a_static_data_address(monkeypatch):
    static = 0x043E1000
    # MOV EAX,[ECX+static] cannot be resolved without a live register. MOV EAX,[static] can.
    session, blocks, calls = environment(
        monkeypatch, b"\x8b\x81" + struct.pack("<I", static) + b"\xc3"
    )
    report = trace.capture_animation_dependencies(session, blocks)
    assert not calls and not report["new_data_pages"]
    session, blocks, calls = environment(
        monkeypatch,
        b"\xa1" + struct.pack("<I", static) + b"\xc3",
        {static: b"x" * trace.PAGE_SIZE},
    )
    report = trace.capture_animation_dependencies(session, blocks)
    assert calls == [static] and report["new_data_pages"] == [f"{static:08X}"]


def test_instruction_budget_and_local_jump_cycle_terminate(monkeypatch):
    monkeypatch.setattr(trace, "MAX_INSTRUCTIONS", 3)
    session, blocks, calls = environment(monkeypatch, b"\x90" * 10 + b"\xc3")
    report = trace.capture_animation_dependencies(session, blocks)
    assert report["nodes"][0]["instructions"] == 3
    assert "instructions_per_node" in report["limits_reached"] and not calls
    session, blocks, _ = environment(monkeypatch, b"\xeb\xfe")
    report = trace.capture_animation_dependencies(session, blocks)
    assert report["nodes"][0]["instructions"] == 1


def test_node_budget_keeps_later_targets_unread(monkeypatch):
    first, second = 0xA52010, 0xA53010
    monkeypatch.setattr(trace, "MAX_NODES", 2)
    session, blocks, calls = environment(
        monkeypatch,
        call(trace.ROOT, first) + call(trace.ROOT + 5, second) + b"\xc3",
        {first & ~0xFFF: page(first, b"\xc3")},
    )
    report = trace.capture_animation_dependencies(session, blocks)
    assert len(report["nodes"]) == 2 and calls == [first & ~0xFFF]
    assert "nodes" in report["limits_reached"]


def test_partial_page_is_recorded_but_never_exported(monkeypatch):
    child = 0xA52010
    session, blocks, _ = environment(
        monkeypatch, call(trace.ROOT, child) + b"\xc3", {child & ~0xFFF: b"\xc3"}
    )
    report = trace.capture_animation_dependencies(session, blocks)
    assert not report["new_code_pages"] and len(blocks) == 1
    assert report["unavailable_pages"] and report["nodes"][1]["status"] == "partial"


def test_outside_engine_calls_are_recorded_without_reading_their_targets(monkeypatch):
    session, blocks, calls = environment(monkeypatch, call(trace.ROOT, 0x00401000) + b"\xc3")
    report = trace.capture_animation_dependencies(session, blocks)
    assert len(report["nodes"]) == 1 and not calls
    assert report["references"][0]["target"] == "00401000"


def test_missing_decoder_keeps_the_fixed_capture_usable(monkeypatch):
    import sys

    session, blocks, calls = environment(monkeypatch, b"\xc3")
    monkeypatch.setitem(sys.modules, "capstone", None)
    report = trace.capture_animation_dependencies(session, blocks)
    assert report["reason"] == "decoder_unavailable" and not calls and len(blocks) == 1


def test_instruction_crossing_page_boundary_is_decoded_from_both_pages(monkeypatch):
    root, child = 0xA1AFFE, 0xA52010
    monkeypatch.setattr(trace, "ROOT", root)
    code = call(root, child) + b"\xc3"
    session, _, calls = environment(monkeypatch, b"\xe8")
    first = bytearray(b"\xcc" * trace.PAGE_SIZE)
    first[-2:] = code[:2]
    second = bytearray(b"\xcc" * trace.PAGE_SIZE)
    second[:4] = code[2:]
    pages = {0xA1B000: bytes(second), child & ~0xFFF: page(child, b"\xc3")}
    session.system.read_memory = lambda pid, address, size: (calls.append(address), pages[address])[
        1
    ]
    blocks = [("split-root", 0xA1A000, bytes(first))]
    report = trace.capture_animation_dependencies(session, blocks)
    assert len(report["nodes"]) == 2
    assert calls == [0xA1B000, child & ~0xFFF]


def test_reference_budget_does_not_keep_enqueuing_callees(monkeypatch):
    first, second = 0xA52010, 0xA53010
    monkeypatch.setattr(trace, "MAX_REFERENCES", 1)
    session, blocks, calls = environment(
        monkeypatch,
        call(trace.ROOT, first) + call(trace.ROOT + 5, second) + b"\xc3",
        {first & ~0xFFF: page(first, b"\xc3")},
    )
    report = trace.capture_animation_dependencies(session, blocks)
    assert len(report["references"]) == 1 and len(report["nodes"]) == 2
    assert calls == [first & ~0xFFF] and "references" in report["limits_reached"]


@pytest.fixture
def static_methods_env(monkeypatch):
    expected = dict(trace.STATIC_METHOD_EXPECTED)
    table = bytearray(trace.PAGE_SIZE)
    for offset, target in expected.items():
        struct.pack_into("<I", table, trace.STATIC_METHOD_TABLE % trace.PAGE_SIZE + offset, target)
    pages = {trace.STATIC_METHOD_TABLE & ~0xFFF: bytes(table)}
    session, blocks, calls = environment(monkeypatch, b"\xc3", pages)
    monkeypatch.setattr(trace, "STATIC_METHOD_EXPECTED", expected)
    for start in {target & ~0xFFF for target in expected.values()}:
        data = bytearray(b"\xcc" * trace.PAGE_SIZE)
        for target in expected.values():
            if target & ~0xFFF == start:
                data[target % trace.PAGE_SIZE] = 0xC3
        blocks.append(("existing-methods", start, bytes(data)))
    return session, blocks, calls, pages, table


def test_verified_static_table_adds_candidate_roots_without_a_runtime_receiver(static_methods_env):
    session, blocks, calls, _, _ = static_methods_env
    report = trace.capture_animation_dependencies(session, blocks)
    methods = report["static_methods"]
    assert methods["status"] == "matched" and not methods["runtime_receiver_verified"]
    assert len(methods["entries"]) == 5 and len(report["nodes"]) == 5
    assert {n["static_table_offset"] for n in report["nodes"] if "static_table_offset" in n} == {
        0x4C,
        0x50,
        0xA4,
        0xA8,
    }
    assert calls == [trace.STATIC_METHOD_TABLE & ~0xFFF]
    assert not report["new_code_pages"] and not report["executes_client_functions"]


def test_changed_static_table_never_turns_its_values_into_code_roots(static_methods_env):
    session, blocks, calls, pages, table = static_methods_env
    struct.pack_into("<I", table, trace.STATIC_METHOD_TABLE % trace.PAGE_SIZE + 0xA8, 0x60000000)
    pages[trace.STATIC_METHOD_TABLE & ~0xFFF] = bytes(table)
    report = trace.capture_animation_dependencies(session, blocks)
    assert report["static_methods"]["status"] == "changed"
    assert len(report["nodes"]) == 1 and report["nodes"][0]["address"] == f"{trace.ROOT:08X}"
    assert calls == [trace.STATIC_METHOD_TABLE & ~0xFFF]


def test_unavailable_static_table_keeps_the_original_graph_usable(static_methods_env):
    session, blocks, calls, pages, _ = static_methods_env
    pages.clear()
    report = trace.capture_animation_dependencies(session, blocks)
    assert report["status"] == "captured" and len(report["nodes"]) == 1
    assert report["static_methods"]["status"] == "unavailable"
    assert calls == [trace.STATIC_METHOD_TABLE & ~0xFFF]
    assert report["unavailable_pages"]


def test_static_roots_respect_the_shared_node_budget(static_methods_env, monkeypatch):
    session, blocks, _, _, _ = static_methods_env
    monkeypatch.setattr(trace, "MAX_NODES", 2)
    report = trace.capture_animation_dependencies(session, blocks)
    assert len(report["nodes"]) == 2 and "nodes" in report["limits_reached"]
    assert report["nodes"][0]["static_table_offset"] == 0xA4
