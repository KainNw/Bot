#pragma once
#include "protocol.h"
uint32_t ClockExecute(SharedCommand* cmd, HANDLE cancellation, HWND window);
void ClockPoll();
