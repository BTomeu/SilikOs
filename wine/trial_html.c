/* wine/trial_html.c: the trial of Wine Gecko (workflow Wine). A Windows program asks the system for an HTML document,
 * as a program with an embedded browser or an installer with an HTML page does. Wine's HTML engine (mshtml) needs
 * Gecko for it: with silik-wine-gecko on the system it loads Gecko's library (xul.dll) into the program; without, it
 * offers a download. Exit 0 when the document was made and Gecko's library is loaded. */
#include <initguid.h>
#include <windows.h>
#include <ole2.h>
#include <ocidl.h>
#include <stdio.h>

DEFINE_GUID(CLSID_SilikHTMLDocument, 0x25336920, 0x03f9, 0x11cf, 0x8f, 0xd0, 0x00, 0xaa, 0x00, 0x68, 0x6f, 0x13);

int main(void) {
    IPersistStreamInit *init = NULL;
    HRESULT hr;
    MSG m;
    int i, gecko;

    CoInitialize(NULL);
    hr = CoCreateInstance(&CLSID_SilikHTMLDocument, NULL, CLSCTX_INPROC_SERVER, &IID_IPersistStreamInit, (void **)&init);
    if (FAILED(hr) || !init) { printf("no HTML document: %08lx\n", (unsigned long)hr); return 2; }
    hr = init->lpVtbl->InitNew(init);
    for (i = 0; i < 60 && !GetModuleHandleA("xul.dll"); i++) {      /* up to three seconds, with the messages served */
        while (PeekMessageA(&m, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageA(&m); }
        Sleep(50);
    }
    gecko = GetModuleHandleA("xul.dll") != NULL;
    printf("an HTML document was made (InitNew %08lx); Gecko's library is %s\n", (unsigned long)hr, gecko ? "loaded" : "NOT loaded");
    fflush(stdout);
    return gecko ? 0 : 1;
}
