/* silik dev try: the same start with the C library (newlib-nano): formatted text into a buffer. Links only when the
 * library for this processor (thumb, hard float) is on the system. */
#include <stdio.h>
#include <string.h>

char line[48];

int main(void) {
    int n = snprintf(line, sizeof line, "count %d of %s", 10, "ten");
    return n == (int)strlen(line) ? 0 : 1;
}
