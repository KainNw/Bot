#include "auto_life.h"
#include <cstring>

namespace {
template<class T> T Read(uintptr_t address) { return *reinterpret_cast<volatile const T*>(address); }
bool Ready(uint32_t owner, uint32_t world, const SharedCommand* c) {
    return owner && Read<uint32_t>(0x04a9290c) == owner
        && Read<int>(owner + 0xb98) == 2 && !Read<uint8_t>(owner + 0x16394)
        && !Read<uint8_t>(0x04e52c5a) && Read<uint32_t>(owner + 0x828) == world
        && world && Read<uint32_t>(world + 0x2c) == c->life_player
        && c->life_player && Read<uint32_t>(c->life_player + 0x200) == 1
        && Read<uint32_t>(c->life_player + 0x2c) == world
        && Read<uint32_t>(c->life_player + 0x30) == c->life_info
        && Read<int>(c->life_player + 0x318) == -1 && Read<int>(c->life_player + 0x254) == -1
        && std::memcmp(reinterpret_cast<void*>(c->life_player + 0x204), c->actor_identity, 12) == 0;
}
}
uint32_t AutoLifeExecute(SharedCommand* c, HANDLE cancellation, HWND window) {
    if (c->life_key < 1 || c->life_key > 9 || c->life_threshold < 1 || c->life_threshold > 100)
        return LifeNotReady;
    const auto owner = Read<uint32_t>(0x04a9290c);
    if (!owner) return LifeNotReady;
    const auto world = Read<uint32_t>(owner + 0x828);
    if (!Ready(owner, world, c)) return LifeNotReady;
    const auto info_manager = Read<uint32_t>(owner + 0x830);
    if (!info_manager || Read<uint32_t>(info_manager + 4) < 2
        || Read<uint32_t>(info_manager) + 0x215b8 != c->life_info) return LifeChanged;
    using Bind = void(__thiscall*)(void*, uint32_t);
    using Calculate = void(__thiscall*)(void*);
    for (unsigned slot = 0; slot < 9; ++slot) {
        if (WaitForSingleObject(cancellation, 0) != WAIT_TIMEOUT) return Cancelled;
        const auto record = c->life_info + 0x4108 + slot * 0x488;
        const int kind = Read<int>(record + 8), hp = Read<int>(record + 0x4c);
        if (kind <= 0 || hp <= 0) continue;
        c->life_kinds[slot] = static_cast<uint32_t>(kind);
        c->life_hp[slot] = hp;
        c->life_mp[slot] = Read<int>(record + 0x50);
        if (kind >= 10000 || !Read<uint32_t>(record + 0x5c)) {
            c->life_unavailable |= 1u << slot; continue;
        }
        // Same scratch-stat sequence used by the client's AutoUseItem Life/Mana
        // check at 0043B624. No original character record is changed here.
        alignas(4) unsigned char stats[0x170] = {};
        reinterpret_cast<Bind>(0x44761a)(stats, record);
        reinterpret_cast<Calculate>(0x449ae8)(stats);
        const int maximum = *reinterpret_cast<int*>(stats + 0x88);
        c->life_max_mp[slot] = maximum;
        if (maximum <= 0 || c->life_mp[slot] < 0) c->life_unavailable |= 1u << slot;
        else if (LowMana(hp, c->life_mp[slot], maximum, c->life_threshold)) c->life_low |= 1u << slot;
    }
    if (!Ready(owner, world, c)) return LifeChanged;
    if (!c->life_low) return LifeChecked;
    bool still_low = false;
    for (unsigned slot = 0; slot < 9; ++slot) if (c->life_low & (1u << slot)) {
        const auto record = c->life_info + 0x4108 + slot * 0x488;
        if (Read<uint32_t>(record + 8) != c->life_kinds[slot]) return LifeChanged;
        still_low |= LowMana(Read<int>(record + 0x4c), Read<int>(record + 0x50),
            c->life_max_mp[slot], c->life_threshold);
    }
    if (WaitForSingleObject(cancellation, 0) != WAIT_TIMEOUT) return Cancelled;
    if (!still_low) return LifeChecked;
    return SendLifeKey(window, c->life_key) ? LifeKeySent : LifeNotReady;
}
