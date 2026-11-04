import struct
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.errors import DiagnosticError, SceneChanged
from atlantica_bot.speed import CONTEXT_STRIDE, CONTEXT_TABLE_ADDRESS
from atlantica_bot.speed_observation import read_speed_sample
from atlantica_bot.speed_trial import SpeedPlan
from atlantica_bot.world import OWNER_ADDRESS


@pytest.fixture
def sample_env():
    roots = tuple(
        tuple(base + index * 0x1000 for base in (0x20000000, 0x30000000, 0x40000000, 0x50000000))
        for index in (0, 1)
    )
    owner, world, player, manager, context = 0x100000, 0x110000, 0x800000, 0x600000, 0x700000
    plan = SpeedPlan(
        100, 777, manager, context, player, (1455, 69669193, 0), 2, 800, 0x10000000, roots
    )
    memory = {}

    def put(address, value, fmt="<I"):
        memory[address] = struct.pack(fmt, value)

    for address, value in (
        (OWNER_ADDRESS, owner),
        (owner + 0x828, world),
        (world + 0x2C, player),
        (owner + 0x91C, manager),
        (owner + 0xB98, 2),
        (player + 0x200, 1),
        (player + 0x2C, world),
        (manager, 0x042D8AA4),
        (player + 0x318, 0),
        (player + 0x254, 0xFFFFFFFF),
        (manager + 8, context),
        (CONTEXT_TABLE_ADDRESS, plan.table),
        (0x1539CE18, 1),
        (manager + 0x234C, 3),
        (context + 0x6C74, 2),
        (context + 0x6C60, 800),
        (owner + 0xBA4, 12345),
    ):
        put(address, value)
    memory[player + 0x204] = struct.pack("<3I", *plan.actor_identity)
    for index, (wrapper, backend, node, clock) in enumerate(roots):
        put(plan.table + index * CONTEXT_STRIDE + 0x18, wrapper)
        put(wrapper + 0xC, backend)
        put(backend, node)
        put(node + 0x120, clock)
        put(clock + 0x50, 1.45 if index else 1.0, "<f")
    put(manager + 0x265C, 1.45, "<f")
    calls = []

    def read(pid, address, size):
        assert pid == 100
        calls.append(address)
        value = memory[address]
        assert len(value) == size
        return value

    session = SimpleNamespace(
        process=SimpleNamespace(pid=100),
        creation_time=777,
        system=SimpleNamespace(process_creation_time=lambda _: 777, read_memory=read),
    )
    return session, plan, memory, calls


def test_sample_reads_current_verified_rates_and_tick_without_commands(sample_env):
    session, plan, _, calls = sample_env
    result = read_speed_sample(session, plan)
    assert result["manager_rate"] == pytest.approx(1.45)
    assert result["battle_graphics_rate"] == pytest.approx(1.45)
    assert result["map_graphics_rate"] == 1.0
    assert result["client_tick"] == 12345 and result["turn_number"] == 2
    assert calls.count(OWNER_ADDRESS) == 2
    assert all(address >= 0x100000 for address in calls)


def test_foreign_session_or_reused_pid_rejected_before_memory_access(sample_env):
    session, plan, _, calls = sample_env
    with pytest.raises(DiagnosticError, match="otra instancia"):
        read_speed_sample(session, replace(plan, creation_time=778))
    session.system.process_creation_time = lambda _: 778
    with pytest.raises(SceneChanged, match="instancia terminó"):
        read_speed_sample(session, plan)
    assert not calls


def test_clock_replaced_before_sample_never_reads_the_old_clock(sample_env):
    session, plan, memory, calls = sample_env
    memory[plan.roots[1][2] + 0x120] = struct.pack("<I", 0x50101000)
    with pytest.raises(SceneChanged, match="gráficos cambiaron"):
        read_speed_sample(session, plan)
    assert plan.roots[1][3] + 0x50 not in calls
    assert 0x50101050 not in calls


def test_clock_replaced_during_sample_discards_the_reading(sample_env):
    session, plan, _, _ = sample_env
    read = session.system.read_memory
    reads = 0

    def replaced(pid, address, size):
        nonlocal reads
        if address == plan.roots[1][2] + 0x120:
            reads += 1
            if reads == 2:
                return struct.pack("<I", 0x50101000)
        return read(pid, address, size)

    session.system.read_memory = replaced
    with pytest.raises(SceneChanged):
        read_speed_sample(session, plan)


def test_instance_reused_during_sample_discards_the_reading(sample_env):
    session, plan, _, _ = sample_env
    creations = iter((777, 778))
    session.system.process_creation_time = lambda _: next(creations)
    with pytest.raises(SceneChanged, match="instancia terminó"):
        read_speed_sample(session, plan)


def test_different_player_rejected_before_saved_manager_rate_is_read(sample_env):
    session, plan, memory, calls = sample_env
    memory[0x110000 + 0x2C] = struct.pack("<I", 0x900000)
    with pytest.raises(SceneChanged, match="personaje o gestor"):
        read_speed_sample(session, plan)
    assert plan.manager + 0x265C not in calls


def test_nonfinite_rate_is_reported_as_unavailable(sample_env):
    session, plan, memory, _ = sample_env
    memory[plan.manager + 0x265C] = struct.pack("<f", float("nan"))
    with pytest.raises(DiagnosticError, match="número válido"):
        read_speed_sample(session, plan)
