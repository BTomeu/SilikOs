/* tests/install/window.c: a small Windows program with a window, for the installation test. Opened from the COMMAND
 * bar (a typed path), it must draw on the installed system's screen and appear in the rail as a program of its own.
 * It closes by itself after ten minutes. */
#include <windows.h>

static LRESULT CALLBACK proc(HWND w, UINT m, WPARAM wp, LPARAM lp) {
    if (m == WM_PAINT) {
        PAINTSTRUCT ps; HDC dc = BeginPaint(w, &ps); RECT r;
        GetClientRect(w, &r);
        DrawTextA(dc, "A Windows program on SilikOS", -1, &r, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        EndPaint(w, &ps);
        return 0;
    }
    if (m == WM_TIMER || m == WM_DESTROY) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(w, m, wp, lp);
}

int WINAPI WinMain(HINSTANCE inst, HINSTANCE prev, LPSTR cmd, int show) {
    WNDCLASSA c = {0};
    MSG m;
    HWND w;
    (void)prev; (void)cmd;
    c.lpfnWndProc = proc; c.hInstance = inst; c.lpszClassName = "SilikTest";
    c.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1); c.hCursor = LoadCursor(NULL, IDC_ARROW);
    RegisterClassA(&c);
    w = CreateWindowA("SilikTest", "Silik Test", WS_OVERLAPPEDWINDOW, 300, 180, 520, 300, NULL, NULL, inst, NULL);
    if (!w) return 3;
    ShowWindow(w, show);
    SetTimer(w, 1, 600000, NULL);
    while (GetMessageA(&m, NULL, 0, 0) > 0) { TranslateMessage(&m); DispatchMessageA(&m); }
    return 0;
}
