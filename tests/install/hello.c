/* tests/install/hello.c: a small Windows program for the installation test. Run through `silik win open`, it writes
 * what it can see to W:\silikos-ci.txt (W: is the one folder a Windows program shares with the rest of the system):
 * that it ran, and whether a file of the user's home outside the shared folders is visible (it must not be).
 * hello.exe [FILE-TO-LOOK-FOR [FILE-TO-WRITE]]; the same source is also built as a 32-bit program. */
#include <stdio.h>

int main(int argc, char **argv) {
    FILE *o = fopen(argc > 2 ? argv[2] : "W:\\silikos-ci.txt", "w");
    if (!o) return 3;
    FILE *s = fopen(argc > 1 ? argv[1] : "Z:\\home\\tester\\.ssh\\id_test", "r");
    fprintf(o, "ran secret=%s\n", s ? "VISIBLE" : "hidden");
    if (s) fclose(s);
    fclose(o);
    return 0;
}
