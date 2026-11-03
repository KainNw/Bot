#include "protocol.h"
#include <wincrypt.h>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <cwchar>
#include <iostream>
#include <string>

constexpr char kHash[] = "BC87A0CC5826AA7FB5E4FF10B6B7C1A349962BD8B146AD28EC3FFA9453FE04E6";
static uint64_t Number(const wchar_t* text) {
    if (!text || !*text || *text == L'-') throw 1;
    wchar_t* end = nullptr;
    errno = 0;
    auto value = wcstoull(text, &end, 10);
    if (errno || !end || *end) throw 1;
    return value;
}
static bool FileHash(const wchar_t* path) {
    HCRYPTPROV provider = 0;
    HCRYPTHASH hash = 0;
    HANDLE file = INVALID_HANDLE_VALUE;
    bool good = false;
    if (CryptAcquireContextW(&provider, nullptr, nullptr, PROV_RSA_AES, CRYPT_VERIFYCONTEXT)
        && CryptCreateHash(provider, CALG_SHA_256, 0, 0, &hash)) {
        file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file != INVALID_HANDLE_VALUE) {
            std::array<BYTE, 65536> buffer;
            DWORD read = 0;
            good = true;
            for (;;) {
                if (!ReadFile(file, buffer.data(), static_cast<DWORD>(buffer.size()), &read, nullptr)) { good = false; break; }
                if (!read) break;
                if (!CryptHashData(hash, buffer.data(), read, 0)) { good = false; break; }
            }
            BYTE digest[32]; DWORD size = sizeof digest;
            if (!good || !CryptGetHashParam(hash, HP_HASHVAL, digest, &size, 0)) good = false;
            if (good) {
                char hex[65] = {};
                for (unsigned i = 0; i < 32; ++i) sprintf_s(hex + i * 2, 3, "%02X", static_cast<unsigned>(digest[i]));
                good = std::strcmp(hex, kHash) == 0;
            }
        }
    }
    if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    if (hash) CryptDestroyHash(hash);
    if (provider) CryptReleaseContext(provider, 0);
    return good;
}
static int Run(HWND window, DWORD pid, SharedCommand command, SharedCommand* response = nullptr) {
    DWORD owner = 0;
    const auto tid = GetWindowThreadProcessId(window, &owner);
    if (!tid || owner != pid || !IsWindowEnabled(window) || IsIconic(window)) return 20;
    wchar_t mutex_name[80]; swprintf_s(mutex_name, L"Local\\AtlanticaPanel.Control.%lu", pid);
    auto mutex = CreateMutexW(nullptr, FALSE, mutex_name);
    if (!mutex) return 21;
    auto acquired = WaitForSingleObject(mutex, 0);
    if (acquired != WAIT_OBJECT_0 && acquired != WAIT_ABANDONED) { CloseHandle(mutex); return 22; }
    HCRYPTPROV provider = 0;
    DWORD nonce[2] = {};
    bool random_ok = false;
    if (CryptAcquireContextW(&provider, nullptr, nullptr, PROV_RSA_AES, CRYPT_VERIFYCONTEXT)) {
        random_ok = CryptGenRandom(provider, sizeof nonce, reinterpret_cast<BYTE*>(nonce)) != FALSE;
        CryptReleaseContext(provider, 0);
    }
    if (!random_ok || !(nonce[0] | nonce[1])) { ReleaseMutex(mutex); CloseHandle(mutex); return 23; }
    wchar_t mapping_name[128]; MappingName(mapping_name, pid, nonce[0], nonce[1]);
    auto mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(SharedCommand), mapping_name);
    auto shared = mapping ? static_cast<SharedCommand*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(SharedCommand))) : nullptr;
    wchar_t module_path[32768] = {};
    const auto path_size = GetModuleFileNameW(nullptr, module_path, 32768);
    std::wstring dll_path(module_path); dll_path.resize(dll_path.find_last_of(L"\\/") + 1); dll_path += L"AtlanticaHook.dll";
    auto library = path_size && path_size < 32768 ? LoadLibraryW(dll_path.c_str()) : nullptr;
    auto callback = library ? reinterpret_cast<HOOKPROC>(GetProcAddress(library, "AtlanticaHookProc")) : nullptr;
    auto hook = callback ? SetWindowsHookExW(WH_GETMESSAGE, callback, library, tid) : nullptr;
    if (!shared || !hook) std::cerr << "Bridge setup error: " << GetLastError() << std::endl;
    int code = 24;
    if (shared && hook) {
        command.magic = kMagic; command.version = 1; command.pid = pid;
        command.nonce_lo = nonce[0]; command.nonce_hi = nonce[1]; command.state = 1;
        *shared = command;
        if (PostMessageW(window, RegisterWindowMessageW(kWakeName), nonce[0], nonce[1])) {
            for (unsigned retry = 0; retry < 200; ++retry) {
                if (InterlockedCompareExchange(&shared->state, 3, 3) == 3) { code = 0; break; }
                Sleep(10);
            }
        }
        if (code == 0) {
            if (response) *response = *shared;
            std::cout << "{\"pid\":" << pid << ",\"status\":" << shared->result
                << ",\"exception\":" << shared->exception << ",\"thread_id\":" << shared->thread_id
                << ",\"slot\":" << shared->slot << ",\"distance_squared\":";
            if (std::isfinite(shared->distance_squared)) std::cout << shared->distance_squared;
            else std::cout << "null";
            std::cout << ",\"range_limit_squared\":";
            if (std::isfinite(shared->range_limit_squared)) std::cout << shared->range_limit_squared;
            else std::cout << "null";
            std::cout << "}" << std::endl;
        } else {
            InterlockedCompareExchange(&shared->state, 4, 1);
        }
    }
    if (hook) UnhookWindowsHookEx(hook);
    // This one-shot helper retains its local DLL until process exit. A callback may
    // still be returning after UnhookWindowsHookEx, including in the self-test.
    if (shared) UnmapViewOfFile(shared);
    if (mapping) CloseHandle(mapping);
    ReleaseMutex(mutex); CloseHandle(mutex);
    return code;
}
struct TestWindow { HANDLE ready; HWND window; };
static DWORD WINAPI WindowThread(void* parameter) {
    auto test = static_cast<TestWindow*>(parameter);
    WNDCLASSW klass = {}; klass.lpfnWndProc = DefWindowProcW;
    klass.hInstance = GetModuleHandleW(nullptr); klass.lpszClassName = L"AtlanticaBridgeTest";
    RegisterClassW(&klass);
    test->window = CreateWindowW(klass.lpszClassName, L"Bridge self-test", 0, 0, 0, 0, 0, nullptr, nullptr, klass.hInstance, nullptr);
    SetEvent(test->ready);
    MSG message;
    while (GetMessageW(&message, nullptr, 0, 0) > 0) DispatchMessageW(&message);
    DestroyWindow(test->window);
    return 0;
}
static int SelfTest() {
    TestWindow test = {}; test.ready = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    DWORD tid = 0;
    auto thread = CreateThread(nullptr, 0, WindowThread, &test, 0, &tid);
    if (!thread || WaitForSingleObject(test.ready, 5000) != WAIT_OBJECT_0 || !test.window) return 30;
    SharedCommand command = {};
    SharedCommand response = {};
    const int code = Run(test.window, GetCurrentProcessId(), command, &response);
    PostThreadMessageW(tid, WM_QUIT, 0, 0);
    WaitForSingleObject(thread, 5000); CloseHandle(thread); CloseHandle(test.ready);
    // The bridge executable's base/build must be rejected before any client address is read.
    const int result = code ? code : (response.result == Unsupported && response.thread_id == tid ? 0 : 31);
    if (result) std::cerr << "Self-test failure: " << result << ", response: " << response.result << std::endl;
    return result;
}
int wmain(int argc, wchar_t** argv) {
    if (argc == 2 && std::wcscmp(argv[1], L"--self-test") == 0) return SelfTest();
    try {
        DWORD pid = 0; uint64_t created = 0, hwnd = 0; SharedCommand command = {};
        bool operation = false;
        for (int i = 1; i < argc; ++i) {
            std::wstring key(argv[i]);
            if (key == L"--attack" || key == L"--probe") { command.attack = key == L"--attack"; operation = true; continue; }
            if (i + 1 >= argc) return 2;
            auto value = Number(argv[++i]);
            if (key == L"--created") created = value;
            else if (key == L"--window") { if (value > UINT32_MAX) return 2; hwnd = value; }
            else {
                if (value > UINT32_MAX) return 2;
                const auto small = static_cast<uint32_t>(value);
                if (key == L"--pid") pid = small;
                else if (key == L"--slot") command.slot = small;
                else if (key == L"--kind") command.identity[0] = small;
                else if (key == L"--serial") command.identity[1] = small;
                else if (key == L"--unique") command.identity[2] = small;
                else return 2;
            }
        }
        if (!pid || !hwnd || !created || !operation || command.slot < 2 || command.slot >= 450) return 2;
        auto process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, pid);
        if (!process) return 3;
        FILETIME start, exit_time, kernel, user;
        wchar_t path[32768]; DWORD length = 32768;
        const bool valid = GetProcessTimes(process, &start, &exit_time, &kernel, &user)
            && ((static_cast<uint64_t>(start.dwHighDateTime) << 32) | start.dwLowDateTime) == created
            && QueryFullProcessImageNameW(process, 0, path, &length) && FileHash(path)
            && WaitForSingleObject(process, 0) == WAIT_TIMEOUT;
        const int result = valid ? Run(reinterpret_cast<HWND>(static_cast<uintptr_t>(hwnd)), pid, command) : 4;
        CloseHandle(process);
        return result;
    } catch (...) { return 2; }
}
