from __future__ import annotations

from collections import deque

from .errors import DiagnosticError
from .session import GameSession

PAGE_SIZE = 0x1000
ENGINE_RANGE = (0x00980000, 0x00C00000)
DATA_RANGE = (0x03F85000, 0x044F9000)
ROOT = 0x00A1A82E
MAX_DEPTH = 4
MAX_NODES = 64
MAX_CODE_PAGES = 48
MAX_DATA_PAGES = 8
MAX_INSTRUCTIONS = 256
MAX_REFERENCES = 1024
ANCHORS = {
    ROOT: bytes.fromhex("5583ec346a64b88d1dd700e8d5842b00"),
    0x00A1A937: bytes.fromhex("e830fdffff"),
    0x00A1A93E: bytes.fromhex("e85df6ffff"),
}
# Repeated timing/logging helpers surrounding the captured update dispatcher.
COMMON_HELPERS = frozenset((0x009B2200, 0x009B28A0, 0x009B2930))


def decoder_probe() -> bool:
    """Exercise the packaged decoder on fixed bytes, without a client or process read."""
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs

    instructions = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(b"\xc3", ROOT))
    return len(instructions) == 1 and instructions[0].mnemonic == "ret"


def capture_animation_dependencies(session: GameSession, blocks: list) -> dict:
    """Capture a bounded candidate call graph; execute none of the decoded instructions."""
    report = {
        "status": "unavailable",
        "root": f"{ROOT:08X}",
        "read_only": True,
        "executes_client_functions": False,
        "semantics_verified": False,
        "coverage_complete": False,
        "engine_range": [f"{a:08X}" for a in ENGINE_RANGE],
        "readonly_range": [f"{a:08X}" for a in DATA_RANGE],
        "excluded_common_helpers": [f"{a:08X}" for a in sorted(COMMON_HELPERS)],
        "candidate_code_may_be_protected": True,
        "limits": {
            "depth": MAX_DEPTH,
            "nodes": MAX_NODES,
            "code_pages": MAX_CODE_PAGES,
            "data_pages": MAX_DATA_PAGES,
            "instructions_per_node": MAX_INSTRUCTIONS,
            "bytes_from_entry": PAGE_SIZE,
            "references": MAX_REFERENCES,
        },
        "nodes": [],
        "references": [],
        "new_code_pages": [],
        "new_data_pages": [],
        "attempted_code_pages": [],
        "attempted_data_pages": [],
        "unavailable_pages": [],
        "limits_reached": [],
    }

    def existing(address: int, size: int) -> bytes | None:
        for _, start, data in blocks:
            if start <= address and address + size <= start + len(data):
                return data[address - start : address - start + size]
        return None

    # Reuse the fixed verified capture before allowing any additional page read.
    for address, expected in ANCHORS.items():
        data = existing(address, len(expected))
        if data is None or data != expected:
            report["reason"] = (
                "update_anchor_not_captured" if data is None else "update_code_changed"
            )
            return report
    try:
        from capstone import CS_ARCH_X86, CS_GRP_CALL, CS_GRP_JUMP, CS_GRP_RET, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_INVALID
    except ImportError:
        report["reason"] = "decoder_unavailable"
        return report
    decoder = Cs(CS_ARCH_X86, CS_MODE_32)
    decoder.detail = True
    failed_pages = set()
    references = set()
    queued = {ROOT}
    pending = deque(((ROOT, 0),))

    def limit(reason: str) -> None:
        if reason not in report["limits_reached"]:
            report["limits_reached"].append(reason)

    def page(address: int, *, data: bool = False) -> None:
        start = address & ~(PAGE_SIZE - 1)
        bounds = DATA_RANGE if data else ENGINE_RANGE
        if not bounds[0] <= start <= bounds[1] - PAGE_SIZE:
            raise DiagnosticError("Página fuera del ámbito de la investigación.")
        if existing(start, PAGE_SIZE) is not None:
            return
        if start in failed_pages:
            raise DiagnosticError("Página ya registrada como inaccesible.")
        key, maximum = (
            ("new_data_pages", MAX_DATA_PAGES) if data else ("new_code_pages", MAX_CODE_PAGES)
        )
        attempts_key = "attempted_data_pages" if data else "attempted_code_pages"
        if len(report[attempts_key]) >= maximum:
            limit(key)
            raise DiagnosticError("Se alcanzó el límite de páginas.")
        report[attempts_key].append(f"{start:08X}")
        try:
            raw = session.system.read_memory(session.process.pid, start, PAGE_SIZE)
            if len(raw) != PAGE_SIZE or not any(raw):
                raise DiagnosticError("Página incompleta o vacía.")
        except (DiagnosticError, OSError) as exc:
            failed_pages.add(start)
            report["unavailable_pages"].append({"address": f"{start:08X}", "error": str(exc)})
            raise
        name = "graphics-dependency-data" if data else "graphics-dependency-code"
        blocks.append((name, start, raw))
        report[key].append(f"{start:08X}")

    def instruction(address: int, end: int):
        count = min(15, ENGINE_RANGE[1] - address, end - address)
        raw = existing(address, count)
        if raw is None:
            page(address)
            end = address + count - 1
            if address // PAGE_SIZE != end // PAGE_SIZE:
                page(end)
            # A read may straddle two separately captured pages.
            raw = b"".join(existing(a, 1) or b"" for a in range(address, address + count))
        return next(decoder.disasm(raw, address, count=1), None)

    def reference(source: int, target: int | None, kind: str, depth: int) -> None:
        key = (source, target, kind)
        if key in references:
            return
        if len(references) >= MAX_REFERENCES:
            limit("references")
            return
        references.add(key)
        report["references"].append(
            {
                "source": f"{source:08X}",
                "target": f"{target:08X}" if target is not None else None,
                "kind": kind,
            }
        )
        if kind not in ("call", "tail_jump") or target in COMMON_HELPERS:
            return
        if target is None or not ENGINE_RANGE[0] <= target < ENGINE_RANGE[1] or target in queued:
            return
        if depth >= MAX_DEPTH:
            limit("depth")
            return
        if len(queued) >= MAX_NODES:
            limit("nodes")
            return
        queued.add(target)
        pending.append((target, depth + 1))

    while pending:
        entry, depth = pending.popleft()
        node = {"address": f"{entry:08X}", "depth": depth, "instructions": 0, "status": "decoded"}
        report["nodes"].append(node)
        paths, visited = deque((entry,)), set()
        while paths and len(visited) < MAX_INSTRUCTIONS:
            address = paths.popleft()
            if address in visited:
                continue
            if not entry <= address < min(entry + PAGE_SIZE, ENGINE_RANGE[1]):
                limit("bytes_from_entry")
                continue
            visited.add(address)
            try:
                ins = instruction(address, entry + PAGE_SIZE)
            except (DiagnosticError, OSError) as exc:
                node.update(status="partial", error=str(exc))
                continue
            if ins is None:
                node["status"] = "decode_incomplete"
                continue
            node["instructions"] += 1
            for operand in ins.operands:
                target = (
                    operand.imm
                    if operand.type == X86_OP_IMM
                    else operand.mem.disp
                    if operand.type == X86_OP_MEM
                    and operand.mem.base == operand.mem.index == X86_REG_INVALID
                    else None
                )
                if target is not None and DATA_RANGE[0] <= target < DATA_RANGE[1]:
                    reference(ins.address, target, "readonly_data", depth)
                    try:
                        page(target, data=True)
                    except (DiagnosticError, OSError):
                        pass
            target = (
                ins.operands[0].imm if ins.operands and ins.operands[0].type == X86_OP_IMM else None
            )
            if ins.group(CS_GRP_CALL):
                reference(
                    ins.address, target, "call" if target is not None else "indirect_call", depth
                )
            if ins.group(CS_GRP_JUMP):
                if target is None:
                    reference(ins.address, None, "indirect_jump", depth)
                elif entry <= target < min(entry + PAGE_SIZE, ENGINE_RANGE[1]):
                    paths.append(target)
                else:
                    reference(
                        ins.address,
                        target,
                        "tail_jump" if ins.mnemonic == "jmp" else "far_branch",
                        depth,
                    )
                if ins.mnemonic == "jmp":
                    continue
            if ins.group(CS_GRP_RET) or ins.mnemonic in ("int3", "ud2", "hlt", "int", "ljmp"):
                continue
            paths.append(address + ins.size)
        if paths:
            limit("instructions_per_node")
            node["status"] = "instruction_limit"
    report["status"] = "captured"
    return report
