#include "clock_scaler.h"
#include "third_party/minhook/include/MinHook.h"
#include <atomic>
#include <cmath>
#include <limits>

namespace clock_scaler {
namespace {
using Tick32 = DWORD (WINAPI*)();
using Tick64 = ULONGLONG (WINAPI*)();
using Qpc = BOOL (WINAPI*)(LARGE_INTEGER*);
Tick32 original_tick = nullptr, original_mm = nullptr;
Tick64 original_tick64 = nullptr;
Qpc original_qpc = nullptr;
std::atomic_flag lock = ATOMIC_FLAG_INIT;
std::atomic_flag polling = ATOMIC_FLAG_INIT;
std::atomic<ULONGLONG> next_poll{0};
std::atomic<float> current_rate{1.f};
std::atomic<Poll> poll_callback{nullptr};
ULONGLONG expiration = 0;
std::atomic<bool> initialized{false};
bool attempted = false;
thread_local bool inside = false;
struct Guard {
    bool old;
    Guard() : old(inside) { inside = true; }
    ~Guard() { inside = old; }
};
struct Lock {
    Lock() { while (lock.test_and_set(std::memory_order_acquire)) SwitchToThread(); }
    ~Lock() { lock.clear(std::memory_order_release); }
};
struct Timeline {
    ULONGLONG real = 0, at_ms = 0;
    long double value = 0;
    bool wrapping = false;
};
Timeline tick, tick64, mm, qpc;

ULONGLONG Advance(Timeline& time, ULONGLONG real, ULONGLONG now) {
    const auto delta = time.wrapping ? static_cast<ULONGLONG>(static_cast<DWORD>(real - time.real))
        : real >= time.real ? real - time.real : 0;
    long double rate = static_cast<long double>(current_rate.load(std::memory_order_relaxed));
    if (expiration && now > expiration) {
        if (time.at_ms >= expiration) rate = 1;
        else if (now > time.at_ms)
            rate = 1 + (rate - 1) * static_cast<long double>(expiration - time.at_ms)
                / static_cast<long double>(now - time.at_ms);
    }
    time.value += static_cast<long double>(delta) * rate;
    time.real = real;
    time.at_ms = now;
    if (time.wrapping) return static_cast<DWORD>(std::fmod(time.value, 4294967296.0L));
    const auto limit = static_cast<long double>((std::numeric_limits<LONGLONG>::max)());
    return static_cast<ULONGLONG>(time.value < limit ? time.value : limit);
}
void PollOnce() {
    const auto callback = poll_callback.load(std::memory_order_acquire);
    if (!callback || polling.test_and_set(std::memory_order_acquire)) return;
    const auto now = original_tick64();
    if (now >= next_poll.load(std::memory_order_relaxed)) {
        next_poll.store(now + 50, std::memory_order_relaxed);
        callback();
    }
    polling.clear(std::memory_order_release);
}
DWORD WINAPI HookTick() {
    if (inside) return original_tick();
    Guard guard; PollOnce(); Lock held;
    return static_cast<DWORD>(Advance(tick, original_tick(), original_tick64()));
}
ULONGLONG WINAPI HookTick64() {
    if (inside) return original_tick64();
    Guard guard; PollOnce(); Lock held;
    const auto now = original_tick64();
    return Advance(tick64, now, now);
}
DWORD WINAPI HookMM() {
    if (inside) return original_mm();
    Guard guard; PollOnce(); Lock held;
    return static_cast<DWORD>(Advance(mm, original_mm(), original_tick64()));
}
BOOL WINAPI HookQpc(LARGE_INTEGER* value) {
    if (inside) return original_qpc(value);
    Guard guard; PollOnce();
    Lock held;
    LARGE_INTEGER real;
    const auto result = original_qpc(&real);
    if (!result || !value) return result;
    value->QuadPart = static_cast<LONGLONG>(Advance(qpc,
        static_cast<ULONGLONG>(real.QuadPart), original_tick64()));
    return result;
}
}

ULONGLONG RealMilliseconds() {
    Guard guard;
    return original_tick64 ? original_tick64() : GetTickCount64();
}
float Rate() { return current_rate.load(std::memory_order_acquire); }
void SetRate(float rate, ULONGLONG expires) {
    Guard guard; Lock held;
    if (!initialized.load(std::memory_order_acquire) || !std::isfinite(rate) || rate < 1.f || rate > 4.f) return;
    const auto now = original_tick64();
    LARGE_INTEGER real;
    if (!original_qpc(&real)) return;
    Advance(tick, original_tick(), now);
    Advance(tick64, now, now);
    Advance(mm, original_mm(), now);
    Advance(qpc, static_cast<ULONGLONG>(real.QuadPart), now);
    expiration = rate > 1.f ? expires : 0;
    current_rate.store(rate, std::memory_order_release);
}
bool Initialize(Poll poll, DWORD* error) {
    Guard guard;
    if (initialized.load(std::memory_order_acquire)) { poll_callback.store(poll); return true; }
    if (attempted) { if (error) *error = ERROR_INVALID_STATE; return false; }
    attempted = true;
    auto status = MH_Initialize();
    if (status != MH_OK && status != MH_ERROR_ALREADY_INITIALIZED) {
        if (error) *error = static_cast<DWORD>(status); return false;
    }
    const auto kernel = GetModuleHandleW(L"kernel32.dll");
    const auto multimedia = LoadLibraryW(L"winmm.dll");
    void* targets[4] = {
        reinterpret_cast<void*>(GetProcAddress(kernel, "GetTickCount")),
        reinterpret_cast<void*>(GetProcAddress(kernel, "GetTickCount64")),
        reinterpret_cast<void*>(GetProcAddress(kernel, "QueryPerformanceCounter")),
        multimedia ? reinterpret_cast<void*>(GetProcAddress(multimedia, "timeGetTime")) : nullptr};
    void* hooks[4] = {reinterpret_cast<void*>(HookTick), reinterpret_cast<void*>(HookTick64),
        reinterpret_cast<void*>(HookQpc), reinterpret_cast<void*>(HookMM)};
    void* originals[4] = {};
    unsigned created = 0;
    for (; created < 4; ++created) {
        if (!targets[created]) { status = MH_ERROR_FUNCTION_NOT_FOUND; break; }
        status = MH_CreateHook(targets[created], hooks[created], &originals[created]);
        if (status != MH_OK) break;
    }
    if (created != 4) {
        while (created) MH_RemoveHook(targets[--created]);
        if (error) *error = static_cast<DWORD>(status); return false;
    }
    original_tick = reinterpret_cast<Tick32>(originals[0]);
    original_tick64 = reinterpret_cast<Tick64>(originals[1]);
    original_qpc = reinterpret_cast<Qpc>(originals[2]);
    original_mm = reinterpret_cast<Tick32>(originals[3]);
    const auto now = original_tick64();
    LARGE_INTEGER real;
    if (!original_qpc(&real)) { if (error) *error = GetLastError(); return false; }
    {
        Lock held;
        const auto first_tick = original_tick(), first_mm = original_mm();
        tick = {first_tick, now, static_cast<long double>(first_tick), true};
        tick64 = {now, now, static_cast<long double>(now), false};
        mm = {first_mm, now, static_cast<long double>(first_mm), true};
        qpc = {static_cast<ULONGLONG>(real.QuadPart), now, static_cast<long double>(real.QuadPart), false};
    }
    for (auto target : targets) {
        status = MH_QueueEnableHook(target);
        if (status != MH_OK) break;
    }
    if (status == MH_OK) status = MH_ApplyQueued();
    if (status != MH_OK) {
        for (auto target : targets) MH_DisableHook(target);
        if (error) *error = static_cast<DWORD>(status); return false;
    }
    initialized.store(true, std::memory_order_release);
    poll_callback.store(poll, std::memory_order_release);
    return true;
}
}
