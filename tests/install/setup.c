/* tests/install/setup.c: a small installer for the installation test, as installers do it: it copies the program
 * next to it (win.exe) to C:\Program Files\SilikTest\siliktest.exe and makes the start-menu shortcut
 * Programs\SilikTest\Silik Test.lnk through the shell. "setup.exe /uninstall" removes both. SilikOS must then list
 * the program among its applications (`silik win apps`, Start, the COMMAND bar). */
#define COBJMACROS
#include <windows.h>
#include <shlobj.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    char here[MAX_PATH], src[MAX_PATH], dir[MAX_PATH], dst[MAX_PATH], menu[MAX_PATH], lnkdir[MAX_PATH], lnk[MAX_PATH];
    WCHAR wlnk[MAX_PATH];
    IShellLinkA *sl;
    IPersistFile *pf;
    HRESULT hr;
    char *s;

    GetModuleFileNameA(NULL, here, sizeof here);
    s = strrchr(here, '\\');
    if (s) *s = 0;
    snprintf(src, sizeof src, "%s\\win.exe", here);
    SHGetFolderPathA(NULL, CSIDL_PROGRAM_FILES, NULL, 0, dir);
    strcat(dir, "\\SilikTest");
    snprintf(dst, sizeof dst, "%s\\siliktest.exe", dir);
    SHGetFolderPathA(NULL, CSIDL_PROGRAMS, NULL, 0, menu);
    snprintf(lnkdir, sizeof lnkdir, "%s\\SilikTest", menu);
    snprintf(lnk, sizeof lnk, "%s\\Silik Test.lnk", lnkdir);
    if (argc > 1 && !strcmp(argv[1], "/uninstall")) {
        DeleteFileA(lnk); RemoveDirectoryA(lnkdir); DeleteFileA(dst); RemoveDirectoryA(dir);
        printf("uninstalled\n");
        return 0;
    }
    CreateDirectoryA(dir, NULL);
    if (!CopyFileA(src, dst, FALSE)) { printf("cannot copy %s to %s (error %lu)\n", src, dst, GetLastError()); return 1; }
    CreateDirectoryA(lnkdir, NULL);
    CoInitialize(NULL);
    if (FAILED(CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER, &IID_IShellLinkA, (void **)&sl))) { printf("no IShellLink\n"); return 1; }
    IShellLinkA_SetPath(sl, dst);
    IShellLinkA_SetWorkingDirectory(sl, dir);
    IShellLinkA_SetDescription(sl, "A test program installed by setup.exe");
    IShellLinkA_QueryInterface(sl, &IID_IPersistFile, (void **)&pf);
    MultiByteToWideChar(CP_ACP, 0, lnk, -1, wlnk, MAX_PATH);
    hr = IPersistFile_Save(pf, wlnk, TRUE);
    IPersistFile_Release(pf); IShellLinkA_Release(sl); CoUninitialize();
    printf("installed %s, shortcut %s (hr %08lx)\n", dst, lnk, (unsigned long)hr);
    fflush(stdout);
    return FAILED(hr);
}
