#include "clock_control.h"
#include "clock_scaler.h"
#include <atomic>
#include <cstring>
#include <cwchar>
#include <tlhelp32.h>

extern "C" { __declspec(dllexport) volatile LONG AtlanticaClockHooksInstalled = 0; }
namespace {
#ifdef ATLANTICA_CLOCK_TEST_LIMIT
constexpr ULONGLONG kBattleLimit = ATLANTICA_CLOCK_TEST_LIMIT;
#else
constexpr ULONGLONG kBattleLimit = 60000;
#endif
enum View : uint32_t { Unknown, Map, Battle, NotReady, Graphics };
enum Reason : uint32_t { None, Waiting, Boosted, ReturnedMap, GraphicsChanged,
    ReadinessChanged, TimeLimit, CancelledOwner, OwnerExited, ReadError, CharacterChanged, Stopped };
struct Frame {
    uint32_t owner, world, actor, manager, context, identity[3], index, other, phase, graphics;
    View view;
};
struct Control {
    bool armed = false, need_map = false;
    uint32_t owner_pid = 0, lo = 0, hi = 0, identity[3] = {}, configured = 0;
    uint32_t reason = None, applied = 0, restored = 0, error = 0, view = Unknown;
    uint32_t token_lo = 0, token_hi = 0;
    wchar_t cancel[96] = {};
    HANDLE owner = nullptr, cancellation = nullptr;
    HWND window = nullptr;
    ULONGLONG candidate_since = 0, deadline = 0;
    Frame candidate = {};
} control;
ClockTelemetry telemetry = {};
std::atomic_flag mutex = ATOMIC_FLAG_INIT;
thread_local bool in_control = false;
struct Scope {
    Scope() { in_control = true; }
    ~Scope() { in_control = false; }
};
struct Lock {
    Lock() { while (mutex.test_and_set(std::memory_order_acquire)) SwitchToThread(); }
    ~Lock() { mutex.clear(std::memory_order_release); }
};
template<class T> T Read(uintptr_t address) { return *reinterpret_cast<volatile const T*>(address); }
bool Pointer(uint32_t value, uint32_t size) { return value >= 0x10000 && value <= 0xffffffffu - size; }
bool ReadFrame(Frame* f) {
    __try {
        *f = {};
        f->owner = Read<uint32_t>(0x04a9290c);
        if (!Pointer(f->owner, 0x16395) || Read<int>(f->owner + 0xb98) != 2
            || Read<uint8_t>(f->owner + 0x16394) != 0 || Read<uint8_t>(0x04e52c5a) != 0) return false;
        f->world = Read<uint32_t>(f->owner + 0x828);
        if (!Pointer(f->world, 0x30)) return false;
        f->actor = Read<uint32_t>(f->world + 0x2c);
        if (!Pointer(f->actor, 0x320) || Read<uint32_t>(f->actor + 0x200) != 1
            || Read<uint32_t>(f->actor + 0x2c) != f->world) return false;
        for (unsigned i = 0; i < 3; ++i) f->identity[i] = Read<uint32_t>(f->actor + 0x204 + i * 4);
        f->index = Read<uint32_t>(f->actor + 0x318);
        f->other = Read<uint32_t>(f->actor + 0x254);
        f->graphics = Read<uint32_t>(0x1539ce18);
        if (f->graphics > 1) return false;
        if (f->index == 0xffffffffu && f->other == 0xffffffffu) { f->view = Map; return true; }
        if (f->index >= 128 || f->other != 0xffffffffu) return false;
        f->manager = Read<uint32_t>(f->owner + 0x91c);
        if (!Pointer(f->manager, 0x2350) || Read<uint32_t>(f->manager) != 0x042d8aa4) return false;
        f->phase = Read<uint32_t>(f->manager + 0x234c);
        if (f->phase != 3) { f->view = NotReady; return true; }
        f->context = Read<uint32_t>(f->manager + 8 + f->index * 4);
        if (!f->context) { f->view = NotReady; return true; }
        if (!Pointer(f->context, 0x6c78)) return false;
        if (Read<uint32_t>(f->context + 0x6c74) == 0xffffffffu) { f->view = NotReady; return true; }
        f->view = f->graphics == 1 ? Battle : Graphics;
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}
bool StableFrame(Frame* frame, bool strict = false) {
    Frame other;
    if (!ReadFrame(frame) || !ReadFrame(&other)) return false;
    if (std::memcmp(frame, &other, sizeof other) != 0) {
        if (strict) return false;
        *frame = other; frame->view = NotReady;
    }
    return true;
}
float Float(uint32_t bits) { float value; std::memcpy(&value, &bits, 4); return value; }
uint32_t Bits(float value) { uint32_t bits; std::memcpy(&bits, &value, 4); return bits; }
bool Allowed(float value) { return value == 1.25f || value == 1.5f || value == 2.f || value == 3.f || value == 4.f; }
bool SameOwner(const SharedCommand* cmd) {
    return cmd->clock_owner_pid == control.owner_pid && cmd->clock_created_lo == control.lo
        && cmd->clock_created_hi == control.hi && std::wmemcmp(cmd->cancel_name, control.cancel, 96) == 0;
}
void Restore(uint32_t reason, bool disarm) {
    if (clock_scaler::Rate() > 1.f) { clock_scaler::SetRate(1.f); ++control.restored; }
    control.reason = reason; control.deadline = 0; control.candidate_since = 0;
    if (disarm) {
        control.armed = false;
        if (control.window) KillTimer(control.window, reinterpret_cast<UINT_PTR>(&control));
        if (control.owner) { CloseHandle(control.owner); control.owner = nullptr; }
        if (control.cancellation) { CloseHandle(control.cancellation); control.cancellation = nullptr; }
    } else control.need_map = reason != ReturnedMap;
}
uint32_t ExistingClock() {
    const auto snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
    if (snapshot == INVALID_HANDLE_VALUE) return ClockUnavailable;
    HMODULE current = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            reinterpret_cast<LPCWSTR>(&ClockExecute), &current)) { CloseHandle(snapshot); return ClockUnavailable; }
    MODULEENTRY32W entry = {}; entry.dwSize = sizeof entry;
    uint32_t found = 0;
    if (Module32FirstW(snapshot, &entry)) do {
        if (GetProcAddress(entry.hModule, "InitializeSpeedhack")
            || _wcsnicmp(entry.szModule, L"speedhack", 9) == 0) { found = ClockExternal; break; }
        if (entry.hModule != current) {
            auto marker = GetProcAddress(entry.hModule, "AtlanticaClockHooksInstalled");
            if (!marker) marker = GetProcAddress(entry.hModule, "_AtlanticaClockHooksInstalled");
            if (marker && Read<LONG>(reinterpret_cast<uintptr_t>(marker)) != 0) {
                found = ClockOldPanel; break;
            }
        }
    } while (Module32NextW(snapshot, &entry));
    CloseHandle(snapshot); return found;
}
void Publish() {
    InterlockedIncrement(&telemetry.sequence);
    MemoryBarrier();
    telemetry.magic = kMagic; telemetry.version = 1; telemetry.pid = GetCurrentProcessId();
    telemetry.owner_pid = control.owner_pid; telemetry.created_lo = control.lo; telemetry.created_hi = control.hi;
    telemetry.token_lo = control.token_lo; telemetry.token_hi = control.token_hi;
    telemetry.armed = control.armed ? 1u : 0u; telemetry.current_bits = Bits(clock_scaler::Rate());
    telemetry.configured_bits = control.configured; telemetry.reason = control.reason;
    telemetry.apply_count = control.applied; telemetry.restore_count = control.restored;
    telemetry.error = control.error; telemetry.view = control.view;
    MemoryBarrier();
    InterlockedIncrement(&telemetry.sequence);
}
struct PublishOnExit { ~PublishOnExit() { Publish(); } };
void Fill(SharedCommand* cmd) {
    Publish();
    cmd->clock_armed = control.armed ? 1u : 0u;
    cmd->clock_current_bits = Bits(clock_scaler::Rate());
    cmd->clock_reason = control.reason; cmd->clock_apply_count = control.applied;
    cmd->clock_restore_count = control.restored; cmd->clock_error = control.error;
    cmd->clock_view = control.view;
    cmd->clock_info_address = reinterpret_cast<uint32_t>(&telemetry);
    cmd->clock_token_lo = control.token_lo; cmd->clock_token_hi = control.token_hi;
}
void CALLBACK Timer(HWND, UINT, UINT_PTR, DWORD) { ClockPoll(); }
}

void ClockPoll() {
    if (in_control) return;
    Scope scope;
    Lock held;
    PublishOnExit publish;
    if (!control.armed) return;
    if (WaitForSingleObject(control.cancellation, 0) != WAIT_TIMEOUT) { Restore(CancelledOwner, true); return; }
    if (WaitForSingleObject(control.owner, 0) != WAIT_TIMEOUT) { Restore(OwnerExited, true); return; }
    Frame frame;
    if (!StableFrame(&frame)) { control.view = Unknown; Restore(ReadError, true); return; }
    control.view = frame.view;
    if (std::memcmp(frame.identity, control.identity, 12) != 0) { Restore(CharacterChanged, true); return; }
    if (frame.view == Map) {
        if (clock_scaler::Rate() > 1.f) Restore(ReturnedMap, false);
        control.need_map = false; control.candidate_since = 0; return;
    }
    if (frame.view == Graphics || frame.view == NotReady) {
        if (clock_scaler::Rate() > 1.f) Restore(frame.view == Graphics ? GraphicsChanged : ReadinessChanged, false);
        control.candidate_since = 0; return;
    }
    const auto now = clock_scaler::RealMilliseconds();
    if (clock_scaler::Rate() > 1.f) {
        if (now >= control.deadline) Restore(TimeLimit, false);
        return;
    }
    if (control.need_map) return;
    if (!control.candidate_since || std::memcmp(&frame, &control.candidate, sizeof frame)) {
        control.candidate = frame; control.candidate_since = now; return;
    }
    if (now - control.candidate_since < 200) return;
    control.deadline = now + kBattleLimit;
    clock_scaler::SetRate(Float(control.configured), control.deadline);
    control.need_map = true; control.reason = Boosted; ++control.applied;
}

uint32_t ClockExecute(SharedCommand* cmd, HANDLE cancellation, HWND window) {
    ClockPoll();
    Scope scope;
    Lock held;
    if (cmd->operation != ClockStart) {
        if (!SameOwner(cmd)) { Fill(cmd); return ClockBusy; }
        if (cmd->operation == ClockStop) Restore(Stopped, true);
        Fill(cmd); return cmd->operation == ClockStop ? ClockStopped : ClockReported;
    }
    if (control.armed) { Fill(cmd); return ClockBusy; }
    if (!Allowed(Float(cmd->clock_rate_bits)) || !cancellation || WaitForSingleObject(cancellation, 0) != WAIT_TIMEOUT
        || !cmd->clock_owner_pid || cmd->clock_owner_pid == GetCurrentProcessId()) return ClockRejected;
    const auto existing = ExistingClock();
    if (existing) return existing;
    Frame frame;
    if (!StableFrame(&frame, true)) return ClockRejected;
    const auto owner = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, cmd->clock_owner_pid);
    FILETIME created, exit, kernel, user;
    if (!owner) return ClockRejected;
    if (!GetProcessTimes(owner, &created, &exit, &kernel, &user)
        || created.dwLowDateTime != cmd->clock_created_lo || created.dwHighDateTime != cmd->clock_created_hi
        || WaitForSingleObject(owner, 0) != WAIT_TIMEOUT) { CloseHandle(owner); return ClockRejected; }
    const auto signal = OpenEventW(SYNCHRONIZE, FALSE, cmd->cancel_name);
    if (!signal) { CloseHandle(owner); return ClockRejected; }
    HMODULE pinned = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&ClockExecute), &pinned)) {
        CloseHandle(signal); CloseHandle(owner); Fill(cmd); return ClockUnavailable;
    }
    InterlockedExchange(&AtlanticaClockHooksInstalled, 1);
    DWORD clock_error = 0;
    if (!clock_scaler::Initialize(ClockPoll, &clock_error)) {
        control.error = clock_error;
        CloseHandle(signal); CloseHandle(owner); Fill(cmd); return ClockUnavailable;
    }
    control.owner_pid = cmd->clock_owner_pid; control.lo = cmd->clock_created_lo; control.hi = cmd->clock_created_hi;
    std::memcpy(control.cancel, cmd->cancel_name, sizeof control.cancel);
    std::memcpy(control.identity, frame.identity, sizeof control.identity);
    control.owner = owner; control.cancellation = signal; control.window = window;
    control.token_lo = cmd->nonce_lo; control.token_hi = cmd->nonce_hi;
    control.configured = cmd->clock_rate_bits; control.view = frame.view;
    control.need_map = frame.view == Graphics; control.candidate_since = 0;
    control.applied = control.restored = 0; control.reason = Waiting; control.armed = true;
    if (!SetTimer(window, reinterpret_cast<UINT_PTR>(&control), 50, Timer)) {
        control.error = GetLastError(); Restore(ReadError, true); Fill(cmd); return ClockUnavailable;
    }
    Fill(cmd); return ClockArmed;
}
