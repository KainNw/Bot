#include "protocol.h"
#include <cmath>
#include <cstring>

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
static uint32_t Invoke(SharedCommand* cmd) {
    if (!Supported()) return Unsupported;
    const auto owner = Read<uint32_t>(0x04a9290c);
    if (!owner || Read<int>(owner + 0xb98) != 2) return InvalidScene;
    if (Read<uint8_t>(owner + 0x16394) || Read<uint8_t>(0x04e52c5a)) return NativeHunting;
    const auto manager = Read<uint32_t>(owner + 0x828);
    if (!manager) return InvalidScene;
    const auto index = Read<uint32_t>(manager + 0x24);
    if (!Active(index, 1) || !Active(index, cmd->slot) || cmd->slot == 1) return TargetChanged;
    const auto player = Read<uint32_t>(manager + 0x2c);
    const auto target = Read<uint32_t>(manager + 0x28 + cmd->slot * 4);
    if (!player || !target || Read<uint32_t>(player + 0x200) != 1
        || Read<uint32_t>(player + 0x2c) != manager
        || Read<uint32_t>(target + 0x200) != cmd->slot || !Identity(target, cmd)) return TargetChanged;
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
    if (!cmd->attack) return Verified; // Probe never calls any client function.
    using Can = int(__thiscall*)(void*, int);
    using Ready = bool(__thiscall*)(void*);
    using Payload = void*(__thiscall*)(void*, const void*, int, int);
    using Message = void*(__thiscall*)(void*, unsigned, int, const void*, int);
    using Send = int(__thiscall*)(void*, const void*);
    if (!reinterpret_cast<Ready>(0x4355ec)(reinterpret_cast<void*>(player))) return Blocked;
    if (!reinterpret_cast<Can>(0x433a4a)(reinterpret_cast<void*>(player), static_cast<int>(cmd->slot))) return Blocked;
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
        if (capacity <= 0 || used < 0 || used > capacity || capacity - used < 25) {
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
    __try {
        cmd->result = Invoke(cmd);
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        cmd->exception = GetExceptionCode();
        cmd->result = ClientException;
    }
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
                        if (cmd->magic == kMagic && cmd->version == 1 && cmd->pid == pid
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
