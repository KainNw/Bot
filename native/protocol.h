#pragma once
#include <windows.h>
#include <cstdint>
#include <cstdio>

constexpr uint32_t kMagic = 0x414F5031;
constexpr wchar_t kWakeName[] = L"AtlanticaPanel.Command.1";
enum Result : uint32_t {
    Verified = 0, Queued = 1, Blocked = 2, OutOfRange = 3, InvalidScene = 4,
    NativeHunting = 5, TargetChanged = 6, InvalidQueue = 7, QueueFull = 8,
    Unsupported = 9, ClientException = 10, NotQueued = 11, RangeUnavailable = 12
};
struct SharedCommand {
    uint32_t magic, version, pid, nonce_lo, nonce_hi, attack, slot;
    uint32_t identity[3];
    volatile LONG state; // pending=1, executing=2, done=3, cancelled=4
    uint32_t result, exception, thread_id;
    float distance_squared;
    float range_limit_squared;
};
static_assert(sizeof(SharedCommand) == 64, "IPC layout must match the x86 helper and hook");
inline void MappingName(wchar_t (&name)[128], DWORD pid, DWORD lo, DWORD hi) {
    swprintf_s(name, L"Local\\AtlanticaPanel.%lu.%08lX.%08lX", pid, lo, hi);
}
