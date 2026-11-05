#include "clock_scaler.h"
#include <mmsystem.h>
#include <cmath>
#include <iostream>

static bool Sample(float rate) {
    clock_scaler::SetRate(rate);
    const auto real0 = clock_scaler::RealMilliseconds();
    const auto a = GetTickCount(); const auto b = GetTickCount64();
    const auto c = timeGetTime(); LARGE_INTEGER d, end, frequency;
    QueryPerformanceFrequency(&frequency); QueryPerformanceCounter(&d);
    Sleep(180);
    QueryPerformanceCounter(&end);
    const auto duration = static_cast<double>(clock_scaler::RealMilliseconds() - real0);
    const double values[] = {static_cast<double>(static_cast<DWORD>(GetTickCount() - a)),
        static_cast<double>(GetTickCount64() - b),
        static_cast<double>(static_cast<DWORD>(timeGetTime() - c)),
        static_cast<double>(end.QuadPart - d.QuadPart) * 1000. / static_cast<double>(frequency.QuadPart)};
    for (const auto value : values) {
        if (duration < 100. || std::abs(value / duration - static_cast<double>(rate)) > .45) {
            std::cerr << "Expected rate " << rate << ", clock delta=" << value
                << ", real duration=" << duration << '\n'; return false;
        }
    }
    return true;
}
static int RunTest() {
    DWORD error = 0;
    if (!clock_scaler::Initialize(nullptr, &error)) {
        std::cerr << "Clock hook initialization failed: " << error << '\n'; return 1;
    }
    if (!Sample(3.f)) return 2;
    const auto before = GetTickCount64();
    if (!Sample(1.f) || GetTickCount64() < before) return 3;
    const auto real = clock_scaler::RealMilliseconds();
    clock_scaler::SetRate(3.f, real + 100);
    const auto start = GetTickCount64();
    Sleep(300);
    const auto end = GetTickCount64();
    const auto elapsed = clock_scaler::RealMilliseconds() - real;
    clock_scaler::SetRate(1.f);
    // The boost must expire at the deadline even with no intervening reads.
    if (std::abs(static_cast<double>(end - start) - static_cast<double>(elapsed + 200)) > 90.) return 4;
    std::cout << "Own-process clocks scaled, restored monotonically, and expired without polling.\n";
    return 0;
}
int main() {
    const auto code = RunTest();
    if (code) std::cerr << "Own-process clocks failed at stage " << code
        << "; Win32=" << GetLastError() << '\n';
    return code;
}
