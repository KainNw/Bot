#include "clock_control.h"
#include "clock_scaler.h"
#include <cstring>
#include <cwchar>
#include <iostream>
#include <string>
#include <tlhelp32.h>

static void* Allocate(uintptr_t address, size_t size) {
    return VirtualAlloc(reinterpret_cast<void*>(address), size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
}
template<class T> static void Put(uintptr_t address, T value) { *reinterpret_cast<T*>(address) = value; }
static DWORD Parent() {
    const auto snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32W entry = {}; entry.dwSize = sizeof entry;
    DWORD parent = 0;
    if (snapshot != INVALID_HANDLE_VALUE && Process32FirstW(snapshot, &entry)) do {
        if (entry.th32ProcessID == GetCurrentProcessId()) { parent = entry.th32ParentProcessID; break; }
    } while (Process32NextW(snapshot, &entry));
    if (snapshot != INVALID_HANDLE_VALUE) CloseHandle(snapshot);
    return parent;
}
static bool Owner(SharedCommand& command, DWORD pid) {
    const auto process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    FILETIME created = {}, exit = {}, kernel = {}, user = {};
    const bool ok = process && GetProcessTimes(process, &created, &exit, &kernel, &user);
    if (ok) {
        command.clock_owner_pid = pid;
        command.clock_created_lo = created.dwLowDateTime;
        command.clock_created_hi = created.dwHighDateTime;
    }
    if (process) CloseHandle(process);
    return ok;
}
static int RunTest(int argc, wchar_t** argv) {
    if (argc == 2 && std::wcscmp(argv[1], L"--owner-child") == 0) { Sleep(800); return 0; }
    // Synthetic game layout inside this executable; no game process is opened.
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
    Put<uint32_t>(manager, 0x042d8aa4); Put<uint32_t>(manager + 0x234c, 3);
    Put<uint32_t>(manager + 8, static_cast<uint32_t>(context)); Put<uint32_t>(context + 0x6c74, 1);
    HWND window = CreateWindowW(L"STATIC", L"Own general clock fixture", WS_OVERLAPPED,
        0, 0, 100, 100, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
    ShowWindow(window, SW_MINIMIZE);
    SharedCommand command = {};
    command.operation = ClockGeneralStart; command.nonce_lo = 100; command.nonce_hi = 200;
    const float factor = 1.5f; std::memcpy(&command.clock_rate_bits, &factor, 4);
    swprintf_s(command.cancel_name, L"Local\\AtlanticaPanel.Cancel.GeneralFixture.%lu", GetCurrentProcessId());
    const auto signal = CreateEventW(nullptr, TRUE, FALSE, command.cancel_name);
    if (!window || !signal || !Owner(command, Parent())) return 3;
    if (ClockExecute(&command, signal, window) != ClockArmed || clock_scaler::Rate() != factor) return 4;
    const auto info = reinterpret_cast<ClockTelemetry*>(command.clock_info_address);
    if (!info->armed || info->reason != 12 || info->apply_count != 1) return 5;
    auto competing = command; competing.operation = ClockStart;
    if (ClockExecute(&competing, signal, window) != ClockBusy || clock_scaler::Rate() != factor) return 6;
    Put<uint32_t>(actor + 0x318, 0); Put<uint32_t>(0x1539ce18, 1);
    ClockPoll(); Sleep(370); ClockPoll();
    if (clock_scaler::Rate() != factor || info->reason != 12) return 7; // Not the battle cap.
    Put<uint32_t>(manager + 0x234c, 2); ClockPoll();
    if (clock_scaler::Rate() != factor) return 8;
    Put<uint32_t>(manager + 0x234c, 3); Put<uint32_t>(0x1539ce18, 0); ClockPoll();
    if (clock_scaler::Rate() != factor) return 9;
    Put<uint32_t>(actor + 0x318, 0xffffffffu); ClockPoll();
    if (clock_scaler::Rate() != factor || info->restore_count) return 10;
    Put<uint32_t>(0x04a9290c, 0); ClockPoll();
    if (clock_scaler::Rate() != 1.f || !info->armed || info->reason != 13) return 11;
    Put<uint32_t>(0x04a9290c, static_cast<uint32_t>(owner)); ClockPoll();
    if (clock_scaler::Rate() != factor || info->apply_count != 2) return 12;
    Put<uint32_t>(actor + 0x208, 201); ClockPoll();
    if (clock_scaler::Rate() != 1.f || info->armed || info->reason != 10) return 13;
    Put<uint32_t>(actor + 0x208, 200);
    if (ClockExecute(&command, signal, window) != ClockArmed) return 14;
    SetEvent(signal); Sleep(60); GetTickCount64();
    if (clock_scaler::Rate() != 1.f || info->armed || info->reason != 7) return 15;
    ResetEvent(signal);
    if (ClockExecute(&command, signal, window) != ClockArmed) return 16;
    command.operation = ClockStop;
    if (ClockExecute(&command, signal, window) != ClockStopped || clock_scaler::Rate() != 1.f) return 17;
    // Existing battle mode retains its original map -> battle -> 1x behavior.
    command.operation = ClockStart;
    if (ClockExecute(&command, signal, window) != ClockArmed || clock_scaler::Rate() != 1.f) return 18;
    Put<uint32_t>(actor + 0x318, 0); Put<uint32_t>(0x1539ce18, 1);
    ClockPoll(); Sleep(230); ClockPoll();
    if (clock_scaler::Rate() != factor) return 19;
    Put<uint32_t>(actor + 0x318, 0xffffffffu); Put<uint32_t>(0x1539ce18, 0); ClockPoll();
    if (clock_scaler::Rate() != 1.f) return 20;
    command.operation = ClockStop;
    if (ClockExecute(&command, signal, window) != ClockStopped) return 21;
    // A terminated panel owner restores general mode without relying on its UI.
    wchar_t executable[32768] = {}; GetModuleFileNameW(nullptr, executable, 32768);
    std::wstring line = L"\"" + std::wstring(executable) + L"\" --owner-child";
    STARTUPINFOW startup = {}; startup.cb = sizeof startup;
    PROCESS_INFORMATION process = {};
    if (!CreateProcessW(nullptr, line.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &startup, &process)) return 22;
    command.operation = ClockGeneralStart;
    if (!Owner(command, process.dwProcessId) || ClockExecute(&command, signal, window) != ClockArmed) return 23;
    if (WaitForSingleObject(process.hProcess, 2000) != WAIT_OBJECT_0) return 24;
    ClockPoll();
    if (clock_scaler::Rate() != 1.f || info->armed || info->reason != 8 || !IsIconic(window)) return 25;
    CloseHandle(process.hThread); CloseHandle(process.hProcess); CloseHandle(signal); DestroyWindow(window);
    std::cout << "Own general fixture: map/battle, minimize, recovery, cancel, stop, owner exit and unchanged battle behavior passed.\n";
    return 0;
}
int wmain(int argc, wchar_t** argv) {
    const auto code = RunTest(argc, argv);
    if (code) std::cerr << "General clock fixture failed at stage " << code
        << "; Win32=" << GetLastError() << "; rate=" << clock_scaler::Rate() << '\n';
    return code;
}
