#include "clock_control.h"
#include <cwchar>
#include "clock_scaler.h"
#include <tlhelp32.h>
#include <cstring>
#include <iostream>
#include <string>

static void* Allocate(uintptr_t address, size_t size) {
    return VirtualAlloc(reinterpret_cast<void*>(address), size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
}
template<class T> static void Put(uintptr_t address, T value) { *reinterpret_cast<T*>(address) = value; }
static DWORD Parent() {
    const auto s = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32W p = {}; p.dwSize = sizeof p;
    DWORD id = 0;
    if (s != INVALID_HANDLE_VALUE && Process32FirstW(s, &p)) do {
        if (p.th32ProcessID == GetCurrentProcessId()) { id = p.th32ParentProcessID; break; }
    } while (Process32NextW(s, &p));
    if (s != INVALID_HANDLE_VALUE) CloseHandle(s);
    return id;
}
static bool Owner(SharedCommand& command, DWORD pid) {
    const auto process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    FILETIME created = {}, exit = {}, kernel = {}, user = {};
    const bool ok = process && GetProcessTimes(process, &created, &exit, &kernel, &user);
    if (ok) { command.clock_owner_pid = pid; command.clock_created_lo = created.dwLowDateTime; command.clock_created_hi = created.dwHighDateTime; }
    if (process) CloseHandle(process);
    return ok;
}
int wmain(int argc, wchar_t** argv) {
    if (argc == 2 && std::wcscmp(argv[1], L"--owner-child") == 0) { Sleep(800); return 0; }
    // Synthetic data in this test process; never attach to or execute the game.
    if (!Allocate(0x04a90000, 0x10000) || !Allocate(0x04e50000, 0x10000)
        || !Allocate(0x15390000, 0x10000)) return 1;
    const auto owner = reinterpret_cast<uintptr_t>(Allocate(0, 0x17000));
    const auto world = reinterpret_cast<uintptr_t>(Allocate(0, 0x100));
    const auto actor = reinterpret_cast<uintptr_t>(Allocate(0, 0x400));
    const auto manager = reinterpret_cast<uintptr_t>(Allocate(0, 0x2400));
    const auto context = reinterpret_cast<uintptr_t>(Allocate(0, 0x6d00));
    if (!owner || !world || !actor || !manager || !context) return 2;
    Put<uint32_t>(0x04a9290c, static_cast<uint32_t>(owner));
    Put<int>(owner + 0xb98, 2); Put<uint32_t>(owner + 0x828, static_cast<uint32_t>(world));
    Put<uint32_t>(owner + 0x91c, static_cast<uint32_t>(manager));
    Put<uint32_t>(world + 0x2c, static_cast<uint32_t>(actor));
    Put<uint32_t>(actor + 0x2c, static_cast<uint32_t>(world)); Put<uint32_t>(actor + 0x200, 1);
    Put<uint32_t>(actor + 0x204, 100); Put<uint32_t>(actor + 0x208, 200);
    Put<uint32_t>(actor + 0x254, 0xffffffffu); Put<uint32_t>(actor + 0x318, 0xffffffffu);
    Put<uint32_t>(manager, 0x042d8aa4); Put<uint32_t>(manager + 0x234c, 2);
    Put<uint32_t>(manager + 8, static_cast<uint32_t>(context)); Put<uint32_t>(context + 0x6c74, 1);
    HWND window = CreateWindowW(L"STATIC", L"Own clock controller fixture", WS_OVERLAPPED,
        0, 0, 100, 100, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
    SharedCommand command = {};
    command.operation = ClockStart; command.nonce_lo = 123; command.nonce_hi = 456;
    const float factor = 3.f; std::memcpy(&command.clock_rate_bits, &factor, 4);
    swprintf_s(command.cancel_name, L"Local\\AtlanticaPanel.Cancel.Fixture.%lu", GetCurrentProcessId());
    const auto signal = CreateEventW(nullptr, TRUE, FALSE, command.cancel_name);
    if (!window || !signal || !Owner(command, Parent())) return 3;
    if (ClockExecute(&command, signal, window) != ClockArmed || clock_scaler::Rate() != 1.f) return 4;
    Put<uint32_t>(actor + 0x318, 0); Put<uint32_t>(0x1539ce18, 1);
    ClockPoll(); Sleep(230); ClockPoll();
    if (clock_scaler::Rate() != 1.f) return 5; // Phase 2 is not ready.
    Put<uint32_t>(manager + 0x234c, 3); ClockPoll(); Sleep(230); ClockPoll();
    if (clock_scaler::Rate() != 3.f) return 6;
    Put<uint32_t>(actor + 0x318, 0xffffffffu); Put<uint32_t>(0x1539ce18, 0); ClockPoll();
    if (clock_scaler::Rate() != 1.f) return 7;
    const auto info = reinterpret_cast<ClockTelemetry*>(command.clock_info_address);
    if (info->reason != 3 || info->apply_count != 1 || info->restore_count != 1) return 8;
    Put<uint32_t>(actor + 0x318, 0); Put<uint32_t>(0x1539ce18, 1); ClockPoll(); Sleep(230); ClockPoll();
    if (clock_scaler::Rate() != 3.f) return 9;
    Sleep(370); ClockPoll();
    if (clock_scaler::Rate() != 1.f || info->reason != 6) return 10;
    Sleep(230); ClockPoll(); if (clock_scaler::Rate() != 1.f) return 11; // No repeat in the same encounter.
    Put<uint32_t>(actor + 0x318, 0xffffffffu); Put<uint32_t>(0x1539ce18, 0); ClockPoll();
    Put<uint32_t>(actor + 0x318, 0); Put<uint32_t>(0x1539ce18, 1); ClockPoll(); Sleep(230); ClockPoll();
    if (clock_scaler::Rate() != 3.f) return 12;
    SetEvent(signal); Sleep(60); GetTickCount64();
    if (clock_scaler::Rate() != 1.f || info->armed || info->reason != 7) return 13;
    // A stale owner cannot stop a newer run.
    ResetEvent(signal); command.nonce_lo += 1; command.operation = ClockStart;
    if (ClockExecute(&command, signal, window) != ClockArmed) return 14;
    auto stranger = command; stranger.clock_owner_pid += 1; stranger.operation = ClockStop;
    if (ClockExecute(&stranger, signal, window) != ClockBusy) return 15;
    command.operation = ClockStop;
    if (ClockExecute(&command, signal, window) != ClockStopped || clock_scaler::Rate() != 1.f) return 16;
    // Owner exit is detected by a process handle; only this fixture is accelerated.
    wchar_t executable[32768] = {}; GetModuleFileNameW(nullptr, executable, 32768);
    std::wstring line = L"\"" + std::wstring(executable) + L"\" --owner-child";
    STARTUPINFOW startup = {}; startup.cb = sizeof startup;
    PROCESS_INFORMATION process = {};
    if (!CreateProcessW(nullptr, line.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &startup, &process)) return 17;
    command.operation = ClockStart;
    if (!Owner(command, process.dwProcessId) || ClockExecute(&command, signal, window) != ClockArmed) return 18;
    ClockPoll(); Sleep(230); ClockPoll();
    if (clock_scaler::Rate() != 3.f) return 19;
    if (WaitForSingleObject(process.hProcess, 2000) != WAIT_OBJECT_0) return 20;
    ClockPoll();
    if (clock_scaler::Rate() != 1.f || info->armed || info->reason != 8) return 21;
    CloseHandle(process.hThread); CloseHandle(process.hProcess); CloseHandle(signal); DestroyWindow(window);
    std::cout << "Own fixture: readiness, repeated battles, map restore, cap, cancellation, owner scope and exit passed.\n";
    return 0;
}
