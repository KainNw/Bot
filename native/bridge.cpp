#include "protocol.h"
#include <wincrypt.h>
#include <array>
#include <cerrno>
#include <cmath>
#include <iomanip>
#include <limits>
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
static int Run(HWND window, DWORD pid, SharedCommand command, SharedCommand* response = nullptr, bool quiet = false, DWORD expected_thread = 0) {
    DWORD owner = 0;
    const auto tid = GetWindowThreadProcessId(window, &owner);
    if (!tid || owner != pid || (expected_thread && tid != expected_thread)
        || !IsWindowEnabled(window) || IsIconic(window)) return 20;
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
        command.magic = kMagic; command.version = 8; command.pid = pid;
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
            if (!quiet) {
            std::cout << std::setprecision(std::numeric_limits<float>::max_digits10);
            std::cout << "{\"pid\":" << pid << ",\"status\":" << shared->result
                << ",\"exception\":" << shared->exception << ",\"thread_id\":" << shared->thread_id
                << ",\"operation\":" << shared->operation
                << ",\"slot\":" << shared->slot << ",\"distance_squared\":";
            if (std::isfinite(shared->distance_squared)) std::cout << shared->distance_squared;
            else std::cout << "null";
            std::cout << ",\"range_limit_squared\":";
            if (std::isfinite(shared->range_limit_squared)) std::cout << shared->range_limit_squared;
            else std::cout << "null";
            std::cout << ",\"navigation\":";
            if (shared->result == ApproachRequested || shared->result == MovementStopped
                || shared->result == MovementNotConfirmed || shared->result == MovementChanged
                || shared->result == MovementBusy) {
                std::cout << "{\"player_address\":" << shared->route_player
                    << ",\"tick\":" << shared->route_tick << ",\"map_id\":" << shared->map_id
                    << ",\"x\":" << shared->x << ",\"y\":" << shared->y
                    << ",\"active\":" << (shared->route_active == 1 ? "true" : "false")
                    << ",\"moving\":" << (shared->route_moving == 0 ? "false" : shared->route_moving == 1 ? "true" : "null")
                    << ",\"active_raw\":" << shared->route_active
                    << ",\"moving_raw\":" << shared->route_moving << "}";
            } else std::cout << "null";
            std::cout << ",\"pursuit\":";
            if (shared->result == NativePursuitRequested || shared->result == NativePursuitStopRequested) {
                std::cout << "{\"player_address\":" << shared->route_player
                    << ",\"issued_tick\":" << shared->route_tick << ",\"map_id\":" << shared->map_id
                    << ",\"x\":" << shared->x << ",\"y\":" << shared->y
                    << ",\"world_goal\":[" << shared->world_goal[0] << "," << shared->world_goal[1]
                    << "," << shared->world_goal[2] << "],\"pending_raw\":" << shared->route_active << "}";
            } else std::cout << "null";
            std::cout << ",\"battle\":";
            if (shared->operation >= BattleBasic && shared->operation <= BattleLoot) {
            std::cout << "{\"manager\":" << shared->battle_manager
                << ",\"context\":" << shared->battle_context << ",\"client\":" << shared->battle_client
                << ",\"turn_number\":" << shared->turn_number << ",\"turn_tick\":" << shared->turn_tick
                << ",\"mercenary_slot\":" << shared->mercenary << ",\"target_member_slot\":" << shared->target_mercenary
                << ",\"source_unit\":" << shared->source_unit << ",\"target_unit\":" << shared->target_unit
                << ",\"native_error\":[" << shared->battle_error[0] << "," << shared->battle_error[1]
                << "," << shared->battle_error[2] << "," << shared->battle_error[3] << "]"
                << ",\"magic_key\":" << shared->magic_key << ",\"magic_action\":" << shared->magic_action
                << ",\"magic_count\":" << shared->magic_count << ",\"magic_actions\":[";
            for (unsigned i = 0; i < 5; ++i) {
                if (i) std::cout << ",";
                std::cout << shared->magic_actions[i];
            }
            std::cout << "]}";
            } else std::cout << "null";
            std::cout << "}" << std::endl;
            }
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
    wchar_t cancel_name[96];
    swprintf_s(cancel_name, L"Local\\AtlanticaPanel.Cancel.SelfTest.%lu", GetCurrentProcessId());
    auto cancellation = CreateEventW(nullptr, TRUE, TRUE, cancel_name);
    SharedCommand cancelled = {}, cancelled_response = {}, missing_response = {};
    cancelled.operation = Attack;
    cancelled.slot = 2;
    wcscpy_s(cancelled.cancel_name, cancel_name);
    const int cancelled_code = cancellation ? Run(test.window, GetCurrentProcessId(), cancelled, &cancelled_response, true) : 32;
    SharedCommand move_response = {}, stop_response = {};
    cancelled.operation = Approach;
    const int move_code = cancellation ? Run(test.window, GetCurrentProcessId(), cancelled, &move_response, true) : 32;
    cancelled.operation = StopMovement;
    const int stop_code = cancellation ? Run(test.window, GetCurrentProcessId(), cancelled, &stop_response, true) : 32;
    SharedCommand native_response = {}, native_stop_response = {};
    cancelled.operation = NativeAttack;
    const int native_code = cancellation ? Run(test.window, GetCurrentProcessId(), cancelled, &native_response, true) : 32;
    cancelled.operation = StopNativePursuit;
    const int native_stop_code = cancellation ? Run(test.window, GetCurrentProcessId(), cancelled, &native_stop_response, true) : 32;
    SharedCommand battle_response = {};
    cancelled.operation = BattleBasic;
    const int battle_code = cancellation ? Run(test.window, GetCurrentProcessId(), cancelled, &battle_response, true) : 32;
    SharedCommand select_response = {}, magic_response = {};
    cancelled.operation = BattleSelect;
    const int select_code = cancellation ? Run(test.window, GetCurrentProcessId(), cancelled, &select_response, true) : 32;
    cancelled.operation = BattleMagic;
    const int magic_code = cancellation ? Run(test.window, GetCurrentProcessId(), cancelled, &magic_response, true) : 32;
    SharedCommand loot_response = {};
    cancelled.operation = BattleLoot;
    const int loot_code = cancellation ? Run(test.window, GetCurrentProcessId(), cancelled, &loot_response, true) : 32;
    if (cancellation) CloseHandle(cancellation);
    const int missing_code = Run(test.window, GetCurrentProcessId(), cancelled, &missing_response, true);
    SharedCommand empty_channel = {}, empty_response = {};
    empty_channel.operation = Approach;
    const int empty_code = Run(test.window, GetCurrentProcessId(), empty_channel, &empty_response, true);
    PostThreadMessageW(tid, WM_QUIT, 0, 0);
    WaitForSingleObject(thread, 5000); CloseHandle(thread); CloseHandle(test.ready);
    // The bridge executable's base/build must be rejected before any client address is read.
    const int result = code ? code : (
        response.result == Unsupported && response.thread_id == tid
        && !cancelled_code && cancelled_response.result == Cancelled
        && !move_code && move_response.result == Cancelled
        && !stop_code && stop_response.result == Cancelled
        && !native_code && native_response.result == Cancelled
        && !native_stop_code && native_stop_response.result == Cancelled
        && !battle_code && battle_response.result == Cancelled
        && !select_code && select_response.result == Cancelled
        && !magic_code && magic_response.result == Cancelled
        && !loot_code && loot_response.result == Cancelled
        && !missing_code && missing_response.result == CancellationUnavailable
        && !empty_code && empty_response.result == CancellationUnavailable ? 0 : 31);
    if (result) std::cerr << "Self-test failure: " << result << ", response: " << response.result
        << ", cancelled: " << cancelled_code << "/" << cancelled_response.result
        << ", missing: " << missing_code << "/" << missing_response.result
        << ", empty: " << empty_code << "/" << empty_response.result << std::endl;
    return result;
}
int wmain(int argc, wchar_t** argv) {
    if (argc == 2 && std::wcscmp(argv[1], L"--self-test") == 0) return SelfTest();
    try {
        DWORD pid = 0, expected_thread = 0; uint64_t created = 0, hwnd = 0; SharedCommand command = {};
        bool operation = false; unsigned goal_fields = 0, battle_fields = 0, magic_fields = 0;
        for (int i = 1; i < argc; ++i) {
            std::wstring key(argv[i]);
            if (key == L"--attack" || key == L"--probe" || key == L"--approach" || key == L"--stop-move"
                || key == L"--native-attack" || key == L"--stop-native" || key == L"--battle-basic"
                || key == L"--battle-select" || key == L"--battle-magic" || key == L"--battle-loot") {
                if (operation) return 2;
                command.operation = key == L"--attack" ? Attack : key == L"--probe" ? Probe
                    : key == L"--approach" ? Approach : key == L"--stop-move" ? StopMovement
                    : key == L"--native-attack" ? NativeAttack : key == L"--stop-native" ? StopNativePursuit
                    : key == L"--battle-basic" ? BattleBasic : key == L"--battle-select" ? BattleSelect
                    : key == L"--battle-magic" ? BattleMagic : BattleLoot;
                operation = true; continue;
            }
            if (i + 1 >= argc) return 2;
            if (key == L"--goal-x" || key == L"--goal-y" || key == L"--goal-z") {
                std::wstring value(argv[++i]); size_t used = 0;
                const float coordinate = std::stof(value, &used);
                if (used != value.size() || !std::isfinite(coordinate) || std::abs(coordinate) > 1.e7f) return 2;
                command.world_goal[key == L"--goal-x" ? 0 : key == L"--goal-y" ? 1 : 2] = coordinate;
                goal_fields |= key == L"--goal-x" ? 1 : key == L"--goal-y" ? 2 : 4;
                continue;
            }
            if (key == L"--cancel-event") {
                const auto name = argv[++i];
                constexpr wchar_t prefix[] = L"Local\\AtlanticaPanel.Cancel.";
                if (wcslen(name) >= 96 || wcsncmp(name, prefix, wcslen(prefix)) != 0) return 2;
                wcscpy_s(command.cancel_name, name);
                continue;
            }
            auto value = Number(argv[++i]);
            if (key == L"--created") created = value;
            else if (key == L"--window") { if (value > UINT32_MAX) return 2; hwnd = value; }
            else {
                if (value > UINT32_MAX) return 2;
                const auto small = static_cast<uint32_t>(value);
                if (key == L"--pid") pid = small;
                else if (key == L"--thread") expected_thread = small;
                else if (key == L"--slot") command.slot = small;
                else if (key == L"--kind") command.identity[0] = small;
                else if (key == L"--serial") command.identity[1] = small;
                else if (key == L"--unique") command.identity[2] = small;
                else if (key == L"--map" && small <= 0x157b) command.map_id = static_cast<int32_t>(small);
                else if (key == L"--x" && small <= 32767) command.x = static_cast<int32_t>(small);
                else if (key == L"--y" && small <= 32767) command.y = static_cast<int32_t>(small);
                else if (key == L"--route-tick") command.route_tick = small;
                else if (key == L"--route-player") command.route_player = small;
                else if (key == L"--origin-map" && small <= 0x157b) command.origin_map = static_cast<int32_t>(small);
                else if (key == L"--origin-x" && small <= 32767) command.origin_x = static_cast<int32_t>(small);
                else if (key == L"--origin-y" && small <= 32767) command.origin_y = static_cast<int32_t>(small);
                else if (key == L"--radius" && small >= 5 && small <= kMaxSearchRadius) command.radius = small;
                else if (key == L"--magic-key" && !(magic_fields & 1) && small >= 1 && small <= 5) {
                    command.magic_key = small; magic_fields |= 1;
                } else if (key == L"--magic-action" && !(magic_fields & 2) && small >= 1 && small <= 0x7cf) {
                    command.magic_action = small; magic_fields |= 2;
                }
                else {
                    const wchar_t* names[] = {L"--battle-manager", L"--battle-context", L"--battle-client",
                        L"--turn-number", L"--turn-tick", L"--mercenary", L"--enemy-member", L"--source-unit",
                        L"--target-unit", L"--actor-kind", L"--actor-serial", L"--actor-unique"};
                    uint32_t* fields[] = {&command.battle_manager, &command.battle_context, &command.battle_client,
                        &command.turn_number, &command.turn_tick, &command.mercenary, &command.target_mercenary,
                        &command.source_unit, &command.target_unit, &command.actor_identity[0],
                        &command.actor_identity[1], &command.actor_identity[2]};
                    bool matched = false;
                    for (unsigned n = 0; n < 12; ++n) if (key == names[n]) {
                        if (battle_fields & (1u << n)) return 2;
                        *fields[n] = small; battle_fields |= 1u << n; matched = true;
                    }
                    if (!matched) return 2;
                }
            }
        }
        if (!pid || !hwnd || !created || !expected_thread || !operation) return 2;
        if (command.operation == StopMovement) {
            if (!command.route_player || !command.x || !command.y) return 2;
        } else if (command.operation == StopNativePursuit) {
            if (!command.route_player) return 2;
        } else if (command.operation == BattleSelect) {
            if (command.slot) return 2;
        } else if (command.slot < (command.operation == BattleMagic ? 1u : 2u) || command.slot >= 450) return 2;
        if (command.operation >= BattleBasic && command.operation <= BattleLoot) {
            const auto expected_fields = command.operation == BattleSelect ? 0xebfu : 0xfffu;
            if (battle_fields != expected_fields || !command.battle_manager || !command.battle_context
                || !command.battle_client || !command.source_unit || command.mercenary < 1 || command.mercenary > 9)
                return 2;
            if (command.operation != BattleSelect && (!command.target_unit
                || command.target_mercenary < 1 || command.target_mercenary > 9)) return 2;
            if (command.operation == BattleMagic && magic_fields != 3) return 2;
            if (command.operation != BattleMagic && magic_fields) return 2;
        }
        if (command.operation == Approach && (!command.radius || !command.x || !command.y || !command.route_player)) return 2;
        if (command.operation == NativeAttack && !command.radius) return 2;
        if ((command.operation == StopNativePursuit
            || command.operation == NativeAttack && command.route_player) && goal_fields != 7) return 2;
        auto process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, pid);
        if (!process) return 3;
        FILETIME start, exit_time, kernel, user;
        wchar_t path[32768]; DWORD length = 32768;
        const bool valid = GetProcessTimes(process, &start, &exit_time, &kernel, &user)
            && ((static_cast<uint64_t>(start.dwHighDateTime) << 32) | start.dwLowDateTime) == created
            && QueryFullProcessImageNameW(process, 0, path, &length) && FileHash(path)
            && WaitForSingleObject(process, 0) == WAIT_TIMEOUT;
        const int result = valid ? Run(reinterpret_cast<HWND>(static_cast<uintptr_t>(hwnd)), pid, command, nullptr, false, expected_thread) : 4;
        CloseHandle(process);
        return result;
    } catch (...) { return 2; }
}
