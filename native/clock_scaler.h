#pragma once
#include <windows.h>

namespace clock_scaler {
using Poll = void (*)();
bool Initialize(Poll poll, DWORD* error);
void SetRate(float rate, ULONGLONG expires = 0);
float Rate();
ULONGLONG RealMilliseconds();
}
