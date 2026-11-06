#pragma once
#include "protocol.h"

inline bool LowMana(int hp, int mp, int maximum, uint32_t threshold) {
    return hp > 0 && mp >= 0 && maximum > 0 && threshold >= 1 && threshold <= 100
        && static_cast<int64_t>(mp) * 100 < static_cast<int64_t>(maximum) * threshold;
}
inline bool SendLifeKey(HWND window, uint32_t key) {
    DWORD pid = 0;
    const auto thread = GetWindowThreadProcessId(window, &pid);
    if (key < 1 || key > 9 || pid != GetCurrentProcessId()
        || thread != GetCurrentThreadId() || !IsWindowEnabled(window)) return false;
    const auto vk = VK_F1 + key - 1;
    const auto scan = MapVirtualKeyW(vk, MAPVK_VK_TO_VSC);
    const auto down = static_cast<LPARAM>((scan << 16) | 1);
    SendMessageW(window, WM_KEYDOWN, vk, down);
    SendMessageW(window, WM_KEYUP, vk, down | static_cast<LPARAM>(0xc0000000u));
    return true;
}
uint32_t AutoLifeExecute(SharedCommand* command, HANDLE cancellation, HWND window);
