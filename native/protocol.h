#pragma once
#include <windows.h>
#include <cstdint>
#include <cstdio>

constexpr uint32_t kMagic = 0x414F5031;
constexpr uint32_t kMaxSearchRadius = 500;
constexpr wchar_t kWakeName[] = L"AtlanticaPanel.Command.8";
enum Operation : uint32_t {
    Probe = 0, Attack = 1, Approach = 2, StopMovement = 3,
    NativeAttack = 4, StopNativePursuit = 5, BattleBasic = 6,
    BattleSelect = 7, BattleMagic = 8, BattleLoot = 9
};
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
    BattleLootQueued = 36, BattleLootNotEligible = 37
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
    float world_goal[3];
    uint32_t battle_manager, battle_context, battle_client, turn_number, turn_tick;
    uint32_t mercenary, target_mercenary, source_unit, target_unit;
    uint32_t actor_identity[3], battle_error[4];
    uint32_t magic_key, magic_action, magic_count, magic_actions[5];
};
static_assert(sizeof(SharedCommand) == 408, "IPC layout must match the x86 helper and hook");
inline void MappingName(wchar_t (&name)[128], DWORD pid, DWORD lo, DWORD hi) {
    swprintf_s(name, L"Local\\AtlanticaPanel.%lu.%08lX.%08lX", pid, lo, hi);
}
