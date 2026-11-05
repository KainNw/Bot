#pragma once
#include <windows.h>
#include <cstdint>
#include <cstdio>

constexpr uint32_t kMagic = 0x414F5031;
constexpr uint32_t kMaxSearchRadius = 500;
constexpr wchar_t kWakeName[] = L"AtlanticaPanel.Command.12";
enum Operation : uint32_t {
    Probe = 0, Attack = 1, Approach = 2, StopMovement = 3,
    NativeAttack = 4, StopNativePursuit = 5, BattleBasic = 6,
    BattleSelect = 7, BattleMagic = 8, BattleLoot = 9, StationaryAttack = 10,
    SpeedApply = 11, SpeedRestore = 12, ClockStart = 13, ClockStop = 14, ClockStatus = 15,
    BattleDefend = 16, BattlePass = 17
};
inline bool IsBattleOperation(uint32_t operation) {
    return (operation >= BattleBasic && operation <= BattleLoot)
        || operation == BattleDefend || operation == BattlePass;
}
enum Result : uint32_t {
    Verified = 0, Queued = 1, Blocked = 2, OutOfRange = 3, InvalidScene = 4,
    NativeHunting = 5, TargetChanged = 6, InvalidQueue = 7, QueueFull = 8,
    Unsupported = 9, ClientException = 10, NotQueued = 11, RangeUnavailable = 12,
    Cancelled = 13, CancellationUnavailable = 14, ApproachRequested = 15,
    MovementStopped = 16, MovementChanged = 17, OutsideArea = 18,
    AlreadyInRange = 19, MovementBusy = 20, MovementNotConfirmed = 21,
    NativePursuitRequested = 22, NativePursuitStopRequested = 23,
    NativePursuitChanged = 24, NativePursuitInBattle = 25,
    BattleBasicQueued = 26, BattleNotReady = 27, BattleTurnChanged = 28,
    BattleTargetChanged = 29, BattleNotEligible = 30, MercenarySelected = 31,
    BattleMagicQueued = 32, BattleSelectionChanged = 33,
    BattleMagicNotEligible = 34, BattleMagicUnsupported = 35,
    BattleLootQueued = 36, BattleLootNotEligible = 37,
    SpeedApplied = 38, SpeedRestored = 39, SpeedChanged = 40, SpeedRejected = 41,
    SpeedRetired = 42, ClockArmed = 43, ClockStopped = 44, ClockReported = 45,
    ClockBusy = 46, ClockRejected = 47, ClockExternal = 48, ClockUnavailable = 49,
    ClockOldPanel = 50, BattleDefendQueued = 51, BattlePassQueued = 52,
    BattleDefendNotEligible = 53, BattlePassNotEligible = 54
};
struct SharedCommand {
    uint32_t magic, version, pid, nonce_lo, nonce_hi, operation, slot;
    uint32_t identity[3];
    volatile LONG state; // pending=1, executing=2, done=3, cancelled=4
    uint32_t result, exception, thread_id;
    float distance_squared;
    float range_limit_squared;
    wchar_t cancel_name[96];
    int32_t map_id, x, y;
    uint32_t route_tick, route_player;
    int32_t origin_map, origin_x, origin_y;
    uint32_t radius;
    uint32_t route_active, route_moving;
    float world_goal[3]; // Destination for pursuit; expected source position for StationaryAttack.
    uint32_t battle_manager, battle_context, battle_client, turn_number, turn_tick;
    uint32_t mercenary, target_mercenary, source_unit, target_unit;
    uint32_t actor_identity[3], battle_error[4];
    uint32_t magic_key, magic_action, magic_count, magic_actions[5];
    uint32_t speed_table, speed_roots[2][4], speed_player;
    uint32_t speed_original_bits, speed_requested_bits;
    float speed_after_manager, speed_after_graphics;
    float speed_map_before, speed_map_after;
    uint32_t speed_map_owned_restore;
    uint32_t clock_rate_bits, clock_owner_pid, clock_created_lo, clock_created_hi;
    uint32_t clock_armed, clock_current_bits, clock_reason, clock_apply_count;
    uint32_t clock_restore_count, clock_error, clock_view;
    uint32_t clock_info_address, clock_token_lo, clock_token_hi;
};
static_assert(sizeof(SharedCommand) == 532, "IPC layout must match the x86 helper and hook");
struct ClockTelemetry {
    uint32_t magic, version, pid, owner_pid, created_lo, created_hi, token_lo, token_hi;
    volatile LONG sequence;
    uint32_t armed, current_bits, configured_bits, reason, apply_count, restore_count, error, view;
};
static_assert(sizeof(ClockTelemetry) == 68, "Clock telemetry layout must match its Python reader");
inline void MappingName(wchar_t (&name)[128], DWORD pid, DWORD lo, DWORD hi) {
    swprintf_s(name, L"Local\\AtlanticaPanel.%lu.%08lX.%08lX", pid, lo, hi);
}
