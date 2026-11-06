#include "auto_life.h"
#include <iostream>

static HWND selected = nullptr;
static unsigned downs = 0, ups = 0, other = 0;
static bool bad = false, foreign_thread = true;
static WPARAM last_key = 0;
static LRESULT CALLBACK WindowProc(HWND window, UINT msg, WPARAM key, LPARAM flags) {
    if (msg == WM_KEYDOWN || msg == WM_KEYUP) {
        if (window != selected) { ++other; return 0; }
        if (key < VK_F1 || key > VK_F9 || !(flags & 1)) bad = true;
        if (msg == WM_KEYDOWN) {
            ++downs; last_key = key;
            if (flags & static_cast<LPARAM>(0xc0000000u)) bad = true;
        } else {
            ++ups;
            if (key != last_key || (flags & static_cast<LPARAM>(0xc0000000u))
                != static_cast<LPARAM>(0xc0000000u)) bad = true;
        }
        return 0;
    }
    return DefWindowProcW(window, msg, key, flags);
}
static DWORD WINAPI WrongThread(void*) {
    foreign_thread = SendLifeKey(selected, 1);
    return 0;
}
int wmain() {
    if (!LowMana(1, 49, 100, 50) || LowMana(1, 50, 100, 50)
        || !LowMana(1, 0, 100, 50) || LowMana(0, 0, 100, 50)
        || LowMana(1, -1, 100, 50) || LowMana(1, 0, 0, 50)
        || LowMana(1, 0, 100, 0) || LowMana(1, 0, 100, 101)) return 1;
    WNDCLASSW wc = {}; wc.lpfnWndProc = WindowProc;
    wc.hInstance = GetModuleHandleW(nullptr); wc.lpszClassName = L"OwnAutoLifeFixture";
    if (!RegisterClassW(&wc)) return 2;
    selected = CreateWindowW(wc.lpszClassName, L"Selected fixture", WS_OVERLAPPED,
        0, 0, 100, 100, nullptr, nullptr, wc.hInstance, nullptr);
    const auto unrelated = CreateWindowW(wc.lpszClassName, L"Other fixture", WS_OVERLAPPED,
        0, 0, 100, 100, nullptr, nullptr, wc.hInstance, nullptr);
    if (!selected || !unrelated) return 3;
    ShowWindow(selected, SW_MINIMIZE);
    const auto foreground = GetForegroundWindow();
    for (unsigned key = 1; key <= 9; ++key)
        if (!SendLifeKey(selected, key) || last_key != VK_F1 + key - 1) return 4;
    if (SendLifeKey(selected, 0) || SendLifeKey(selected, 10) || SendLifeKey(nullptr, 1)) return 5;
    EnableWindow(selected, FALSE);
    if (SendLifeKey(selected, 1)) return 6;
    EnableWindow(selected, TRUE);
    const auto thread = CreateThread(nullptr, 0, WrongThread, nullptr, 0, nullptr);
    if (!thread || WaitForSingleObject(thread, 2000) != WAIT_OBJECT_0) return 7;
    CloseHandle(thread);
    if (foreign_thread || downs != 9 || ups != 9 || other || bad || !IsIconic(selected)
        || foreground != GetForegroundWindow()) return 8;
    DestroyWindow(selected); DestroyWindow(unrelated);
    std::cout << "Auto Life: strict MP threshold and F1-F9 isolated minimized-window input passed.\n";
    return 0;
}
