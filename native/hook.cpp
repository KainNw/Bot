#include "protocol.h"
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <limits>

template<class T> T Read(uintptr_t address) {
    return *reinterpret_cast<const T*>(address);
}
static bool Anchor(uintptr_t address, const unsigned char* bytes, size_t count) {
    return std::memcmp(reinterpret_cast<void*>(address), bytes, count) == 0;
}
static bool Supported() {
    if (GetModuleHandleW(L"Atlantica.exe") != GetModuleHandleW(nullptr)) return false;
    if (reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr)) != 0x00400000) return false;
    const unsigned char ctor[] = {0x55,0x8b,0xec,0x8b,0x45,0x0c,0x56,0x8b,0xf1};
    const unsigned char can[] = {0x55,0x8b,0xec,0x83,0xec,0x20,0x53};
    const unsigned char payload[] = {0x56,0xff,0x74,0x24,0x08,0x8b,0xf1,0x33,0xc0};
    const unsigned char dispatch[] = {0xe8,0xba,0xf0,0xff,0xff,0x84,0xc0,0x74,0x0b};
    return Anchor(0x40c4e9, ctor, sizeof ctor) && Anchor(0x433a4a, can, sizeof can)
        && Anchor(0x43bc26, payload, sizeof payload)
        && Anchor(0x43652d, dispatch, sizeof dispatch);
}
static bool Active(uint32_t index, uint32_t slot) {
    return index && slot > 0 && slot < 450 && Read<uint32_t>(index + (slot + 1) * 12) != 0;
}
static bool Identity(uint32_t actor, const SharedCommand* cmd) {
    return std::memcmp(reinterpret_cast<void*>(actor + 0x204), cmd->identity, 12) == 0;
}
static bool LockImport(uintptr_t address, const char* name, const char* rtl_name) {
    auto actual = Read<FARPROC>(address);
    return actual == GetProcAddress(GetModuleHandleW(L"kernel32.dll"), name)
        || actual == GetProcAddress(GetModuleHandleW(L"ntdll.dll"), rtl_name);
}
static bool IsCancelled(HANDLE signal) {
    return signal && WaitForSingleObject(signal, 0) != WAIT_TIMEOUT;
}
static bool HexAnchor(uintptr_t address, const char* hex) {
    const auto data = reinterpret_cast<const unsigned char*>(address);
    size_t offset = 0;
    while (*hex) {
        const auto digit = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
        const auto value = digit(hex[0]) * 16 + digit(hex[1]);
        if (data[offset++] != value) return false;
        hex += 2;
    }
    return true;
}
static bool NavigationSupported() {
    return HexAnchor(0x43c9d3,
        "83b900020000017513c6813410000000c6811210000001e956e7ffffc20c00")
        && HexAnchor(0x43b145,
        "83b90002000001578b3d0c29a9040f858a0000008b4424088b54240c53568b742418"
        "668981181000006689911a1000006689b11c1000008b1d0c29a9048b9ba40b0000"
        "89991410000083cbff6689991e10000033db3bc36689992010000066899922100000"
        "66899928100000c681780b0000017c083bd37e043bf37f12889912100000889935100000"
        "8899780b00008d87f71e0100803801750288185e5b5fc20c00")
        && HexAnchor(0x43b1e7,
        "83b90002000001751e8a4424048881351000008b4424088981381000008b44240c"
        "89813c100000c20c00")
        && HexAnchor(0x43b211,
        "568bf183be0002000001754553e828a0ffff508bcee810a0ffff506a018bcee8b2ffffff"
        "e84881000033db5353538bcee8a1ffffff53536affe8f6feffff889e12100000"
        "889e34100000899e301000005b5ec3");
}
static bool Idle(uint32_t player) {
    return !Read<uint8_t>(player + 0x1012) && !Read<uint8_t>(player + 0xb78);
}
static bool OwnRoute(uint32_t player, const SharedCommand* cmd) {
    return player == cmd->route_player && Read<uint32_t>(player + 0x1014) == cmd->route_tick
        && Read<int16_t>(player + 0x1018) == cmd->map_id
        && Read<int16_t>(player + 0x101a) == cmd->x
        && Read<int16_t>(player + 0x101c) == cmd->y;
}
static void ReadRoute(uint32_t player, SharedCommand* cmd) {
    cmd->route_player = player;
    cmd->route_tick = Read<uint32_t>(player + 0x1014);
    cmd->map_id = Read<int16_t>(player + 0x1018);
    cmd->x = Read<int16_t>(player + 0x101a);
    cmd->y = Read<int16_t>(player + 0x101c);
    cmd->route_active = Read<uint8_t>(player + 0x1012);
    cmd->route_moving = Read<uint8_t>(player + 0xb78);
}
static bool InsideArea(int map, int x, int y, const SharedCommand* cmd) {
    return cmd->radius >= 5 && cmd->radius <= kMaxSearchRadius && map == cmd->origin_map
        && x >= 0 && x <= 32767 && y >= 0 && y <= 32767
        && cmd->origin_x >= 0 && cmd->origin_x <= 32767
        && cmd->origin_y >= 0 && cmd->origin_y <= 32767
        && std::abs(x - cmd->origin_x) + std::abs(y - cmd->origin_y) <= static_cast<int>(cmd->radius);
}
static bool NativePursuitSupported() {
    // The captured Auto Battle far-target branch: goal fields and 0xAE5/20-byte payload.
    return HexAnchor(0x43ced0,
        "8b45fca34c2ce5048d45e0508bcfe837f7ffff8bf08dbb74160000a5a5a58b75f883a380160000008d45e0508bcec6838416"
        "000001e810f7ffff8bced9008d45a850d95dcce800f7ffffd940048d45b850d95dd08bcee8eff6ffffd9400833c0d95dd4d9"
        "ee6a01668945d8d95ddc8d45cc506a1468e50a00008d8d6c8affffe895f5fcff8b038d8d6c8affff518bcbff5064")
        && HexAnchor(0x43c61a,
        "56578b3d18ce39156a008bf1e8c7815c00518d86880a00008b108bcc89118b4004894104e8db815c008b4018"
        "ff7424148bc8e8f1815d0057e89b815c008b442410595f5ec20400");
}
static uint32_t SendQueue(uint32_t owner, uint32_t* outgoing) {
    if (Read<uint32_t>(Read<uint32_t>(owner) + 0x64) != 0x0095ec3a
        || !Read<uint8_t>(owner + 0x11d8e)) return Unsupported;
    const auto connection = Read<uint32_t>(owner + 0x1d70);
    if (!connection || !Read<uint32_t>(connection + 0x70)) return InvalidQueue;
    const auto queue = Read<uint32_t>(connection + 0x6c);
    if (!queue || Read<int>(queue + 0x44) != 0
        || !LockImport(0x03f850d0, "EnterCriticalSection", "RtlEnterCriticalSection")
        || !LockImport(0x03f850d4, "LeaveCriticalSection", "RtlLeaveCriticalSection")) return InvalidQueue;
    *outgoing = queue;
    return Verified;
}
static bool OwnNativePursuit(uint32_t owner, uint32_t player, const SharedCommand* cmd) {
    if (player != cmd->route_player || Read<uint8_t>(player + 0x1012) == 1) return false;
    for (unsigned i = 0; i < 3; ++i)
        if (Read<float>(owner + 0x1674 + i * 4) != cmd->world_goal[i]) return false;
    return true;
}
static bool WorldPoint(uint32_t actor, float (&point)[3]) {
    // Auto Battle uses this native getter for the movement command's destination.
    using Position = float*(__thiscall*)(void*, float*);
    for (float& value : point) value = std::numeric_limits<float>::quiet_NaN();
    if (reinterpret_cast<Position>(0x43c61a)(reinterpret_cast<void*>(actor), point) != point) return false;
    for (float value : point) if (!std::isfinite(value) || std::abs(value) > 1.e7f) return false;
    return true;
}
static uint32_t QueueNativePursuit(uint32_t owner, uint32_t player, uint32_t queue,
    const float (&goal)[3], SharedCommand* cmd, HANDLE cancellation, bool stopping) {
    alignas(4) unsigned char payload[20] = {}, message[64] = {};
    std::memcpy(payload, goal, 12);
    using Message = void*(__thiscall*)(void*, unsigned, int, const void*, int);
    using Send = int(__thiscall*)(void*, const void*);
    reinterpret_cast<Message>(0x40c4e9)(message, 0xae5, 20, payload, 1);
    if (Read<uint16_t>(reinterpret_cast<uintptr_t>(message)) != 29) return Unsupported;
    auto lock = reinterpret_cast<CRITICAL_SECTION*>(queue + 0x20);
    uint32_t result = NotQueued;
    EnterCriticalSection(lock);
    __try {
        const auto capacity = Read<int>(queue + 4), used = Read<int>(queue + 0x10);
        if (IsCancelled(cancellation)) result = Cancelled;
        else if (capacity <= 0 || used < 0 || used > capacity || capacity - used < 29) result = QueueFull;
        else {
            float previous_goal[3];
            std::memcpy(previous_goal, reinterpret_cast<void*>(owner + 0x1674), 12);
            const auto previous_progress = Read<uint32_t>(owner + 0x1680);
            const auto previous_pending = Read<uint8_t>(owner + 0x1684);
            std::memcpy(reinterpret_cast<void*>(owner + 0x1674), goal, 12);
            *reinterpret_cast<uint32_t*>(owner + 0x1680) = 0;
            *reinterpret_cast<uint8_t*>(owner + 0x1684) = 1;
            reinterpret_cast<Send>(0x0095ec3a)(reinterpret_cast<void*>(owner), message);
            const auto after = Read<int>(queue + 0x10);
            if (after == used + 29) {
                std::memcpy(cmd->world_goal, goal, 12);
                cmd->route_player = player;
                cmd->route_tick = Read<uint32_t>(owner + 0xba4);
                cmd->route_active = Read<uint8_t>(owner + 0x1684);
                result = stopping ? NativePursuitStopRequested : NativePursuitRequested;
            } else if (after == used
                && std::memcmp(reinterpret_cast<void*>(owner + 0x1674), goal, 12) == 0
                && Read<uint32_t>(owner + 0x1680) == 0 && Read<uint8_t>(owner + 0x1684) == 1) {
                // No command was copied; restore only the state still owned by this invocation.
                std::memcpy(reinterpret_cast<void*>(owner + 0x1674), previous_goal, 12);
                *reinterpret_cast<uint32_t*>(owner + 0x1680) = previous_progress;
                *reinterpret_cast<uint8_t*>(owner + 0x1684) = previous_pending;
            }
        }
    } __finally { LeaveCriticalSection(lock); }
    return result;
}
static bool BattleSupported() {
    // Exact normal-combat functions and the manual basic-action send branch.
    return HexAnchor(0x4f102f,
        "558bec33c056ff75208bf18d4e0c8321006689410466894106668b4508668906668b450c66894602668b451066894604"
        "668b451466894606668b451866894608e86a7ff4ff668b451c668946148bc65e5dc21c00")
        && HexAnchor(0x4fdc86,
        "8b44240469c0e80300000305f8e05504ff05f8e05504833df8e05504647e0ac705f8e0550401000000c3")
        && HexAnchor(0x4f200e,
        "8d455c506a00ff75788d4d34ff7570ffb594020000ffb5900200006a01e8ffefffff6a018d4534506a1868490f0000"
        "8d8df88affffe8a1a4f1ff8b0d0c29a9048b018d95f88affff52ff5064")
        && HexAnchor(0x431d81, "558bec81ecb40900005357ff750c8bd9e8d3f9ffff84c00f84f0010000")
        && HexAnchor(0x5a2955,
        "568bf1837e08007d0432c05ec3e803f1ffff85c07ef3a10c29a9048b90280800008b4e048b4c8a288b801c090000"
        "ffb1040200008b4808e81ec2f5ff84c074c9ff76088b8e1c020000e8e110ebff3c0174b783ec348bcc682ce58a08"
        "e8bc6be6ffff76088b8e1c020000e87a62ebff3c0174966a0068008000008bcee869efffff84c00f95c05ec3");
}
static int BattleGroup(uint32_t context, const uint32_t (&identity)[3]) {
    for (unsigned i = 0; i < 6; ++i)
        if (std::memcmp(reinterpret_cast<void*>(context + 0xb4 + i * 12), identity, 12) == 0)
            return Read<int16_t>(context + 0x11a + i * 2);
    return -1;
}
static bool SelectionSupported() {
    return HexAnchor(0x5a44ae,
        "a10c29a904538b981c09000085db74578d81d00000008b1085d2740e8b949138010000c682a800000000578b7c240c"
        "85ff742b5689388db4b9380100008b06c680a8000000018b0ee8228dffff80bb441a00000074078b0ee843d7ffff"
        "5e578bcbe8b104f5ff5f5bc20400")
        && HexAnchor(0x4f44ff,
        "a10c29a9048b88300800006a01c7458051000000c7458457000000c7458845000000c7458c52000000c7459054000000e83b8effff");
}
static bool MagicSupported() {
    return SelectionSupported()
        && HexAnchor(0x4f20b0,
        "558dac2478fdffffb89c770000e82e0e7e00a108b06f0433c58985840200008b8598020000538bd9568b350c29a904895d5085c07f07")
        && HexAnchor(0x4f2402,
        "8d454050ffb5a00200008d4d28ff7570ff756c53ffb5900200006a04e80cecffff6a018d4528506a1868490f0000"
        "8d8dec8affffe8aea0f1ff8b0d0c29a9048b018d95ec8affff52ff5064")
        && HexAnchor(0x4f24ef, "32c05f8b8d840200005e33cd5be803087e0081c588020000c9c21400")
        && HexAnchor(0x5445c1, "8b410853568b71042bc6b9a0000000998bd9f7fb5733ff85c07615");
}
static bool LootSupported() {
    // Search action 0x2a -> 004F1B21, action payload 3; native eligibility requires a dead target.
    return SelectionSupported()
        && HexAnchor(0x433701,
        "558bec5356578bf983bf18030000007d0732c0e9af010000a10c29a9048b88300800008db700020000ff36e83e9c0b00")
        && HexAnchor(0x433823,
        "69f68804000003f333ff39be104100000f8ed9feffff8d8e08410000e8cd4e100085c00f8fc6feffff")
        && HexAnchor(0x4f1b21,
        "558becb87c750000e8c2137e008b150c29a9045356578b7d108bf18955fc85ff0f8e91010000")
        && HexAnchor(0x4f1c7f,
        "8d45e85053ff75f88d4dc0ff75f4ff750cff75086a03e895f3ffff6a018d45c0506a1868490f0000"
        "8d8d848affffe837a8f1ff8b0d0c29a9048b018d95848affff52ff5064")
        && HexAnchor(0x4f1cd8, "5f5e5bc9c20c00");
}
static uint32_t BattleUnitIndex(uint32_t client, uint32_t unit) {
    for (unsigned i = 1; i < 100; ++i)
        if (Read<uint8_t>(client + 0xd4 + i) == 1 && Read<uint32_t>(client + 0x138 + i * 4) == unit)
            return i;
    return 0;
}
static bool ReadMagicBar(uint32_t manager, SharedCommand* cmd) {
    cmd->magic_count = Read<uint32_t>(manager + 0x25e8);
    if (cmd->magic_count > 5) return false;
    for (unsigned i = 0; i < 5; ++i) {
        cmd->magic_actions[i] = i < cmd->magic_count ? Read<uint32_t>(manager + 0x25ec + i * 4) : 0;
        if (i < cmd->magic_count && (!cmd->magic_actions[i] || cmd->magic_actions[i] > 0x7cf)) return false;
    }
    return true;
}
static bool BattleUnitMatches(uint32_t client, uint32_t unit, uint32_t world,
    uint32_t world_slot, uint32_t member, uint32_t info_base, uint32_t info_count, bool alive = true) {
    if (!unit || !world_slot || world_slot >= 450 || world_slot >= info_count || member < 1 || member > 9)
        return false;
    if (!BattleUnitIndex(client, unit)
        || Read<uint32_t>(unit + 4) != world_slot || Read<uint32_t>(unit + 8) != member - 1)
        return false;
    const auto actor = Read<uint32_t>(world + 0x28 + world_slot * 4);
    if (!actor || Read<uint32_t>(actor + 0x200) != world_slot || Read<uint32_t>(actor + 0x2c) != world)
        return false;
    const auto info = Read<uint32_t>(actor + 0x30);
    const auto record = info + 0x4108 + (member - 1) * 0x488;
    return info && info == info_base + world_slot * 0x215b8
        && Read<uint32_t>(unit + 0x21c) == info && Read<uint32_t>(unit + 0x230) == record
        && Read<int>(record + 8) > 0 && (alive ? Read<int>(record + 0x4c) > 0 : Read<int>(record + 0x4c) <= 0);
}
static bool EnemiesDefeated(uint32_t client, uint32_t world, uint32_t context, int own_group,
    uint32_t info_base, uint32_t info_count) {
    bool dead_enemy = false;
    for (unsigned i = 1; i < 100; ++i) {
        if (Read<uint8_t>(client + 0xd4 + i) != 1) continue;
        const auto unit = Read<uint32_t>(client + 0x138 + i * 4);
        if (!unit) return false;
        const auto slot = Read<uint32_t>(unit + 4), member = Read<uint32_t>(unit + 8) + 1;
        if (!slot || slot >= 450 || slot >= info_count) return false;
        const auto actor = Read<uint32_t>(world + 0x28 + slot * 4);
        if (!actor) return false;
        uint32_t identity[3];
        std::memcpy(identity, reinterpret_cast<void*>(actor + 0x204), 12);
        const int group = BattleGroup(context, identity);
        if (group < 0) return false;
        if (group == own_group || identity[0] < 3500 || identity[0] >= 22000) continue;
        // Own companions are not enemy formation members. Validate the enemy member before reading its record.
        if (member < 1 || member > 9) return false;
        if (!BattleUnitMatches(client, unit, world, slot, member, info_base, info_count, false)) return false;
        dead_enemy = true;
    }
    return dead_enemy;
}
static uint32_t InvokeBattle(uint32_t owner, uint32_t world, uint32_t player,
    SharedCommand* cmd, HANDLE cancellation) {
    if (!BattleSupported()) return Unsupported;
    const auto manager = Read<uint32_t>(owner + 0x91c);
    const auto client = Read<uint32_t>(owner + 0x16358);
    const int context_index = Read<int>(player + 0x318);
    if (context_index < 0 || context_index >= 128 || Read<int>(player + 0x254) >= 0
        || !manager || manager != cmd->battle_manager || !client || client != cmd->battle_client
        || Read<uint32_t>(manager) != 0x042d8aa4 || Read<uint32_t>(manager + 0x25e0) != client
        || Read<int>(manager + 0x234c) != 3) return BattleNotReady;
    const auto context = Read<uint32_t>(manager + 8 + static_cast<uint32_t>(context_index) * 4);
    if (!context || context != cmd->battle_context
        || Read<uint32_t>(context + 0x6c74) != cmd->turn_number
        || Read<uint32_t>(context + 0x6c60) != cmd->turn_tick) return BattleTurnChanged;
    if (std::memcmp(reinterpret_cast<void*>(player + 0x204), cmd->actor_identity, 12) != 0
        || !cmd->actor_identity[0] || cmd->actor_identity[0] > 32767) return BattleTargetChanged;
    const int own_group = BattleGroup(context, cmd->actor_identity);
    if (own_group < 0) return BattleTargetChanged;
    const auto info_manager = Read<uint32_t>(owner + 0x830);
    if (!info_manager) return BattleTargetChanged;
    const auto info_base = Read<uint32_t>(info_manager), info_count = Read<uint32_t>(info_manager + 4);
    if (!info_base || !BattleUnitMatches(client, cmd->source_unit, world, 1, cmd->mercenary, info_base, info_count))
        return BattleTargetChanged;
    if (cmd->operation == BattleSelect) {
        if (!SelectionSupported() || !Read<uint32_t>(owner + 0x11ee4)) return Unsupported;
        if (IsCancelled(cancellation)) return Cancelled;
        const auto selected = BattleUnitIndex(client, cmd->source_unit);
        using Select = void(__thiscall*)(void*, int);
        reinterpret_cast<Select>(0x5a44ae)(reinterpret_cast<void*>(client), static_cast<int>(selected));
        return Read<uint32_t>(client + 0xd0) == selected && ReadMagicBar(manager, cmd)
            ? MercenarySelected : BattleSelectionChanged;
    }
    if (Read<int>(context + 0x6c5c) != own_group) return BattleNotReady;
    if (!cmd->slot || cmd->slot >= 450) return BattleTargetChanged;
    const auto target = Read<uint32_t>(world + 0x28 + cmd->slot * 4);
    if (!target || !Identity(target, cmd)) return BattleTargetChanged;
    const int target_group = BattleGroup(context, cmd->identity);
    const bool own_target = cmd->operation == BattleMagic && cmd->slot == 1 && target_group == own_group;
    if (!own_target && (cmd->slot == 1 || target_group < 0 || target_group == own_group
        || cmd->identity[0] < 3500 || cmd->identity[0] >= 22000)) return BattleTargetChanged;
    if (!BattleUnitMatches(client, cmd->target_unit, world, cmd->slot, cmd->target_mercenary,
        info_base, info_count, cmd->operation != BattleLoot))
        return BattleTargetChanged;
    if (Read<uint8_t>(cmd->source_unit + 0x508) != 1) return BattleNotReady;
    using Ready = bool(__thiscall*)(void*);
    using Eligible = bool(__thiscall*)(void*, int, int, int, uint32_t*, int, int);
    if (cmd->operation == BattleBasic) {
      if (!reinterpret_cast<Ready>(0x5a2955)(reinterpret_cast<void*>(cmd->source_unit))) return BattleNotReady;
      if (!reinterpret_cast<Eligible>(0x431d81)(reinterpret_cast<void*>(player),
        static_cast<int>(cmd->mercenary - 1), static_cast<int>(cmd->identity[0]),
        static_cast<int>(cmd->target_mercenary - 1), cmd->battle_error, 0, 0)) return BattleNotEligible;
    } else if (cmd->operation == BattleLoot) {
        if (!LootSupported() || !Read<uint32_t>(owner + 0x11ee8)) return Unsupported;
        const auto selected = Read<uint32_t>(client + 0xd0);
        if (!selected || selected >= 100 || Read<uint32_t>(client + 0x138 + selected * 4) != cmd->source_unit)
            return BattleSelectionChanged;
        if (!EnemiesDefeated(client, world, context, own_group, info_base, info_count)) return BattleNotReady;
        if (!reinterpret_cast<Ready>(0x5a2955)(reinterpret_cast<void*>(cmd->source_unit))) return BattleNotReady;
        using SearchEligible = bool(__thiscall*)(void*, int, int, int, uint32_t*);
        if (!reinterpret_cast<SearchEligible>(0x433701)(reinterpret_cast<void*>(player),
            static_cast<int>(cmd->mercenary - 1), static_cast<int>(cmd->identity[0]),
            static_cast<int>(cmd->target_mercenary - 1), cmd->battle_error)) return BattleLootNotEligible;
    } else {
        if (!MagicSupported()) return Unsupported;
        const auto selected = Read<uint32_t>(client + 0xd0);
        if (!selected || selected >= 100 || Read<uint32_t>(client + 0x138 + selected * 4) != cmd->source_unit
            || !ReadMagicBar(manager, cmd) || !cmd->magic_key || cmd->magic_key > cmd->magic_count
            || cmd->magic_actions[cmd->magic_key - 1] != cmd->magic_action) return BattleSelectionChanged;
        const auto catalog = Read<uint32_t>(owner + 0x904);
        const auto policy = Read<uint32_t>(owner + 0x848);
        if (!catalog || !policy || !cmd->magic_action || cmd->magic_action > 0x7cf) return BattleMagicUnsupported;
        const auto action = catalog + 0xb9c + cmd->magic_action * 0x24;
        const auto magic = Read<int>(action + 0x10);
        using PartyMagic = bool(__thiscall*)(void*, int);
        // Party-wide special actions can replace the chosen source with the main character.
        if (Read<uint16_t>(action) != 0x10 || magic <= 0
            || reinterpret_cast<PartyMagic>(0x5445c1)(reinterpret_cast<void*>(policy), magic))
            return BattleMagicUnsupported;
    }
    uint32_t queue = 0;
    const auto validation = SendQueue(owner, &queue);
    if (validation != Verified) return validation;
    auto lock = reinterpret_cast<CRITICAL_SECTION*>(queue + 0x20);
    uint32_t result = NotQueued;
    EnterCriticalSection(lock);
    __try {
        const auto capacity = Read<int>(queue + 4), used = Read<int>(queue + 0x10);
        if (IsCancelled(cancellation)) result = Cancelled;
        else if (capacity <= 0 || used < 0 || used > capacity || capacity - used < 33) result = QueueFull;
        else if (cmd->operation == BattleLoot) {
            if (!EnemiesDefeated(client, world, context, own_group, info_base, info_count)) result = BattleNotReady;
            else {
                using Search = void(__thiscall*)(void*, int, int, int);
                reinterpret_cast<Search>(0x4f1b21)(reinterpret_cast<void*>(manager),
                    static_cast<int>(cmd->actor_identity[0]), static_cast<int>(cmd->mercenary - 1),
                    static_cast<int>(BattleUnitIndex(client, cmd->target_unit)));
                const auto after = Read<int>(queue + 0x10);
                result = after == used + 33 ? BattleLootQueued : after == used ? BattleLootNotEligible : NotQueued;
            }
        } else if (cmd->operation == BattleMagic) {
            using Cast = bool(__thiscall*)(void*, int, int, int, int, int);
            const auto accepted = reinterpret_cast<Cast>(0x4f20b0)(reinterpret_cast<void*>(manager),
                static_cast<int>(cmd->actor_identity[0]), static_cast<int>(cmd->mercenary - 1),
                static_cast<int>(BattleUnitIndex(client, cmd->target_unit)), 0, static_cast<int>(cmd->magic_action));
            const auto after = Read<int>(queue + 0x10);
            result = accepted && after == used + 33 ? BattleMagicQueued
                : after == used ? BattleMagicNotEligible : NotQueued;
        } else {
            // Same native nonce, payload constructor and sender as the manual basic branch.
            // No keyboard input, selection changes, turn flags or stat writes.
            alignas(4) unsigned char payload[24] = {}, message[64] = {};
            using Nonce = uint32_t(__cdecl*)(uint32_t);
            using Payload = void*(__thiscall*)(void*, int, int, int, int, int, int, const void*);
            using Message = void*(__thiscall*)(void*, unsigned, int, const void*, int);
            using Send = int(__thiscall*)(void*, const void*);
            uint32_t nonce_data[2] = {
                reinterpret_cast<Nonce>(0x4fdc86)(Read<uint32_t>(cmd->source_unit + 0xc)), 0
            };
            reinterpret_cast<Payload>(0x4f102f)(payload, 1, static_cast<int>(cmd->actor_identity[0]),
                static_cast<int>(cmd->mercenary - 1), static_cast<int>(cmd->identity[0]),
                static_cast<int>(cmd->target_mercenary - 1), 0, nonce_data);
            reinterpret_cast<Message>(0x40c4e9)(message, 0xf49, 24, payload, 1);
            if (Read<uint16_t>(reinterpret_cast<uintptr_t>(message)) != 33) result = Unsupported;
            else {
                reinterpret_cast<Send>(0x0095ec3a)(reinterpret_cast<void*>(owner), message);
                if (Read<int>(queue + 0x10) == used + 33) result = BattleBasicQueued;
            }
        }
    } __finally { LeaveCriticalSection(lock); }
    return result;
}
static uint32_t Invoke(SharedCommand* cmd, HANDLE cancellation) {
    if (IsCancelled(cancellation)) return Cancelled;
    if (!Supported()) return Unsupported;
    const auto owner = Read<uint32_t>(0x04a9290c);
    if (!owner || Read<int>(owner + 0xb98) != 2) return InvalidScene;
    if (Read<uint8_t>(owner + 0x16394) || Read<uint8_t>(0x04e52c5a)) return NativeHunting;
    const auto manager = Read<uint32_t>(owner + 0x828);
    if (!manager) return InvalidScene;
    const auto index = Read<uint32_t>(manager + 0x24);
    if (!Active(index, 1)) return TargetChanged;
    const auto player = Read<uint32_t>(manager + 0x2c);
    if (!player || Read<uint32_t>(player + 0x200) != 1
        || Read<uint32_t>(player + 0x2c) != manager) return TargetChanged;
    if (cmd->operation >= BattleBasic && cmd->operation <= BattleLoot)
        return InvokeBattle(owner, manager, player, cmd, cancellation);
    if (Read<int>(player + 0x318) >= 0 || Read<int>(player + 0x254) >= 0)
        return cmd->operation == StopNativePursuit ? NativePursuitInBattle : InvalidScene;
    if (cmd->operation == StopNativePursuit) {
        if (!NativePursuitSupported()) return Unsupported;
        const auto info = Read<uint32_t>(player + 0x30);
        if (!info || Read<int16_t>(info + 0xca) != cmd->map_id
            || !OwnNativePursuit(owner, player, cmd)) return NativePursuitChanged;
        float current[3];
        if (!WorldPoint(player, current)) return RangeUnavailable;
        cmd->x = Read<int16_t>(info + 0xcc);
        cmd->y = Read<int16_t>(info + 0xce);
        if (cmd->x < 0 || cmd->y < 0) return RangeUnavailable;
        uint32_t queue = 0;
        const auto validation = SendQueue(owner, &queue);
        if (validation != Verified) return validation;
        return QueueNativePursuit(owner, player, queue, current, cmd, cancellation, true);
    }
    if (cmd->operation == StopMovement) {
        if (!NavigationSupported()) return Unsupported;
        if (Idle(player)) { ReadRoute(player, cmd); return MovementStopped; }
        if (!OwnRoute(player, cmd)) { ReadRoute(player, cmd); return MovementChanged; }
        if (IsCancelled(cancellation)) return Cancelled;
        using Stop = void(__thiscall*)(void*);
        reinterpret_cast<Stop>(0x43b211)(reinterpret_cast<void*>(player));
        ReadRoute(player, cmd);
        return Idle(player) ? MovementStopped : MovementNotConfirmed;
    }
    if (!Active(index, cmd->slot) || cmd->slot == 1) return TargetChanged;
    const auto target = Read<uint32_t>(manager + 0x28 + cmd->slot * 4);
    if (!target || Read<uint32_t>(target + 0x200) != cmd->slot || !Identity(target, cmd)) return TargetChanged;
    const auto flags = Read<uint32_t>(target + 0x388);
    const auto state = Read<uint8_t>(target + 0x38);
    if (cmd->identity[0] < 3500 || cmd->identity[0] >= 22000 || (flags & 0x810)
        || state == 0x22 || state == 0x23 || Read<int>(target + 0x318) >= 0
        || Read<int>(target + 0x254) >= 0) return Blocked;
    const auto pi = Read<uint32_t>(player + 0x30), ti = Read<uint32_t>(target + 0x30);
    if (!pi || !ti || Read<int16_t>(pi + 0xca) != Read<int16_t>(ti + 0xca)) return TargetChanged;
    float distance = 0;
    for (unsigned offset = 0xb8c; offset <= 0xb94; offset += 4) {
        const float delta = Read<float>(player + offset) - Read<float>(target + offset);
        distance += delta * delta;
    }
    cmd->distance_squared = distance;
    const auto limit = Read<float>(0x045079ec);
    cmd->range_limit_squared = limit;
    if (!std::isfinite(distance) || !std::isfinite(limit) || limit <= 0 || limit > 1.e8f)
        return RangeUnavailable;
    if (cmd->operation == Approach) {
        if (!NavigationSupported()) return Unsupported;
        if (distance <= limit) return AlreadyInRange;
        const auto linked = Read<uint32_t>(player + 0x14);
        if (Read<uint8_t>(player + 0x338) == 1 || !linked || Read<int>(linked + 0x380) != 2) return Blocked;
        // This byte is compared with exactly 1 by the client's route consumer.
        // +B78 is diagnostic here; starting requires the observed actor and route revision.
        if (Read<uint8_t>(player + 0x1012) == 1) { ReadRoute(player, cmd); return MovementBusy; }
        if (player != cmd->route_player || Read<uint32_t>(player + 0x1014) != cmd->route_tick) {
            ReadRoute(player, cmd); return MovementChanged;
        }
        if (cmd->map_id != Read<int16_t>(ti + 0xca) || cmd->x != Read<int16_t>(ti + 0xcc)
            || cmd->y != Read<int16_t>(ti + 0xce)) return TargetChanged;
        if (cmd->map_id < 0 || cmd->map_id > 0x157b || cmd->x <= 0 || cmd->x > 32767
            || cmd->y <= 0 || cmd->y > 32767
            || !InsideArea(cmd->map_id, cmd->x, cmd->y, cmd)
            || !InsideArea(Read<int16_t>(pi + 0xca), Read<int16_t>(pi + 0xcc), Read<int16_t>(pi + 0xce), cmd))
            return OutsideArea;
        if (IsCancelled(cancellation)) return Cancelled;
        using Move = void(__thiscall*)(void*, int, int, int);
        reinterpret_cast<Move>(0x43c9d3)(reinterpret_cast<void*>(player), cmd->map_id, cmd->x, cmd->y);
        ReadRoute(player, cmd);
        return Read<uint8_t>(player + 0x1012) == 1 ? ApproachRequested : MovementNotConfirmed;
    }
    if (cmd->operation == NativeAttack) {
        if (!NativePursuitSupported()) return Unsupported;
        if (!InsideArea(Read<int16_t>(ti + 0xca), Read<int16_t>(ti + 0xcc), Read<int16_t>(ti + 0xce), cmd)
            || !InsideArea(Read<int16_t>(pi + 0xca), Read<int16_t>(pi + 0xcc), Read<int16_t>(pi + 0xce), cmd))
            return OutsideArea;
        if (cmd->route_player && !OwnNativePursuit(owner, player, cmd)) return NativePursuitChanged;
    } else if (distance > limit) return OutOfRange;
    uint32_t queue = 0;
    const auto validation = SendQueue(owner, &queue);
    if (validation != Verified) return validation;
    if (Read<uint8_t>(player + 0x1012) == 1) { ReadRoute(player, cmd); return MovementBusy; }
    if (cmd->operation == Probe) return Verified; // Probe never calls any client function.
    if (cmd->operation != Attack && cmd->operation != NativeAttack) return Unsupported;
    if (IsCancelled(cancellation)) return Cancelled;
    using Can = int(__thiscall*)(void*, int);
    using Ready = bool(__thiscall*)(void*);
    using Payload = void*(__thiscall*)(void*, const void*, int, int);
    using Message = void*(__thiscall*)(void*, unsigned, int, const void*, int);
    using Send = int(__thiscall*)(void*, const void*);
    if (!reinterpret_cast<Ready>(0x4355ec)(reinterpret_cast<void*>(player))) return Blocked;
    if (!reinterpret_cast<Can>(0x433a4a)(reinterpret_cast<void*>(player), static_cast<int>(cmd->slot))) return Blocked;
    if (IsCancelled(cancellation)) return Cancelled;
    if (Read<uint32_t>(0x04a9290c) != owner || !Identity(target, cmd)
        || Read<uint32_t>(owner + 0x828) != manager || Read<uint32_t>(manager + 0x2c) != player
        || Read<uint32_t>(manager + 0x28 + cmd->slot * 4) != target
        || Read<uint32_t>(target + 0x200) != cmd->slot || !Active(index, cmd->slot)) return TargetChanged;
    if (Read<int>(owner + 0xb98) != 2 || Read<int>(player + 0x318) >= 0
        || Read<int>(player + 0x254) >= 0) return InvalidScene;
    if (Read<uint8_t>(owner + 0x16394) || Read<uint8_t>(0x04e52c5a)) return NativeHunting;
    if (Read<uint8_t>(player + 0x1012) == 1) { ReadRoute(player, cmd); return MovementBusy; }
    if (cmd->operation == NativeAttack && cmd->route_player
        && !OwnNativePursuit(owner, player, cmd)) return NativePursuitChanged;
    if (cmd->operation == NativeAttack && distance > limit) {
        float goal[3];
        if (!WorldPoint(target, goal)) return RangeUnavailable;
        cmd->map_id = Read<int16_t>(ti + 0xca);
        cmd->x = Read<int16_t>(ti + 0xcc);
        cmd->y = Read<int16_t>(ti + 0xce);
        return QueueNativePursuit(owner, player, queue, goal, cmd, cancellation, false);
    }
    alignas(4) unsigned char payload[16] = {}, message[64] = {};
    reinterpret_cast<Payload>(0x43bc26)(payload, reinterpret_cast<void*>(target + 0x204), 1, 0);
    reinterpret_cast<Message>(0x40c4e9)(message, 0xae2, 16, payload, 1);
    if (Read<uint16_t>(reinterpret_cast<uintptr_t>(message)) != 25) return Unsupported;
    auto lock = reinterpret_cast<CRITICAL_SECTION*>(queue + 0x20);
    EnterCriticalSection(lock);
    uint32_t result = NotQueued;
    __try {
        const auto capacity = Read<int>(queue + 4), used = Read<int>(queue + 0x10);
        if (IsCancelled(cancellation)) {
            result = Cancelled;
        } else if (capacity <= 0 || used < 0 || used > capacity || capacity - used < 25) {
            result = QueueFull;
        } else {
            // The client's queue lock is recursive; this serializes the capacity check and copy.
            reinterpret_cast<Send>(0x43652d)(reinterpret_cast<void*>(player), message);
            if (Read<int>(queue + 0x10) == used + 25) result = Queued;
        }
    } __finally {
        LeaveCriticalSection(lock);
    }
    return result;
}
static void GuardedInvoke(SharedCommand* cmd) {
    HANDLE cancellation = nullptr;
    __try {
        if (cmd->operation != Probe && !cmd->cancel_name[0]) {
            cmd->result = CancellationUnavailable; return;
        }
        if (cmd->cancel_name[0]) {
            if (cmd->cancel_name[95] != 0) { cmd->result = CancellationUnavailable; return; }
            cancellation = OpenEventW(SYNCHRONIZE, FALSE, cmd->cancel_name);
            if (!cancellation) { cmd->result = CancellationUnavailable; return; }
        }
        cmd->result = Invoke(cmd, cancellation);
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        cmd->exception = GetExceptionCode();
        cmd->result = ClientException;
    }
    if (cancellation) CloseHandle(cancellation);
}
extern "C" LRESULT CALLBACK AtlanticaHookProc(int code, WPARAM removed, LPARAM data) {
    if (code >= 0 && removed == PM_REMOVE) {
        auto msg = reinterpret_cast<const MSG*>(data);
        if (msg->message == RegisterWindowMessageW(kWakeName)) {
            DWORD pid = 0;
            const auto thread = GetWindowThreadProcessId(msg->hwnd, &pid);
            if (pid == GetCurrentProcessId() && thread == GetCurrentThreadId()) {
                wchar_t name[128];
                MappingName(name, pid, static_cast<DWORD>(msg->wParam), static_cast<DWORD>(msg->lParam));
                const auto mapping = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, name);
                if (mapping) {
                    auto cmd = static_cast<SharedCommand*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(SharedCommand)));
                    if (cmd) {
                        if (cmd->magic == kMagic && cmd->version == 8 && cmd->pid == pid
                            && cmd->nonce_lo == msg->wParam && cmd->nonce_hi == static_cast<DWORD>(msg->lParam)
                            && InterlockedCompareExchange(&cmd->state, 2, 1) == 1) {
                            cmd->thread_id = GetCurrentThreadId();
                            GuardedInvoke(cmd);
                            InterlockedExchange(&cmd->state, 3);
                        }
                        UnmapViewOfFile(cmd);
                    }
                    CloseHandle(mapping);
                }
            }
        }
    }
    return CallNextHookEx(nullptr, code, removed, data);
}
