#include "protocol.h"
#include <cmath>
#include <cstring>
#include <cstdlib>

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
    return cmd->radius >= 5 && cmd->radius <= 120 && map == cmd->origin_map
        && cmd->origin_x >= 0 && cmd->origin_x <= 32767
        && cmd->origin_y >= 0 && cmd->origin_y <= 32767
        && std::abs(x - cmd->origin_x) + std::abs(y - cmd->origin_y) <= static_cast<int>(cmd->radius);
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
    if (Read<int>(player + 0x318) >= 0 || Read<int>(player + 0x254) >= 0) return InvalidScene;
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
    if (distance > limit) return OutOfRange;
    if (Read<uint32_t>(Read<uint32_t>(owner) + 0x64) != 0x0095ec3a
        || !Read<uint8_t>(owner + 0x11d8e)) return Unsupported;
    const auto connection = Read<uint32_t>(owner + 0x1d70);
    if (!connection || !Read<uint32_t>(connection + 0x70)) return InvalidQueue;
    const auto queue = Read<uint32_t>(connection + 0x6c);
    if (!queue || Read<int>(queue + 0x44) != 0
        || !LockImport(0x03f850d0, "EnterCriticalSection", "RtlEnterCriticalSection")
        || !LockImport(0x03f850d4, "LeaveCriticalSection", "RtlLeaveCriticalSection"))
        return InvalidQueue;
    if (cmd->operation == Probe) return Verified; // Probe never calls any client function.
    if (cmd->operation != Attack) return Unsupported;
    if (IsCancelled(cancellation)) return Cancelled;
    using Can = int(__thiscall*)(void*, int);
    using Ready = bool(__thiscall*)(void*);
    using Payload = void*(__thiscall*)(void*, const void*, int, int);
    using Message = void*(__thiscall*)(void*, unsigned, int, const void*, int);
    using Send = int(__thiscall*)(void*, const void*);
    if (!reinterpret_cast<Ready>(0x4355ec)(reinterpret_cast<void*>(player))) return Blocked;
    if (!reinterpret_cast<Can>(0x433a4a)(reinterpret_cast<void*>(player), static_cast<int>(cmd->slot))) return Blocked;
    if (IsCancelled(cancellation)) return Cancelled;
    if (Read<uint32_t>(0x04a9290c) != owner || !Identity(target, cmd)) return TargetChanged;
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
                        if (cmd->magic == kMagic && cmd->version == 4 && cmd->pid == pid
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
