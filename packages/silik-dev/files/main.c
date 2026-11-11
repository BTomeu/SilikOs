/* silik dev try: a small program for a Cortex-M4 with a floating-point unit. It touches no peripheral (it is linked
 * for no particular part): it counts, and keeps a filtered value, so that there is code, data and arithmetic. */
#include <stdint.h>

volatile uint32_t ticks;
volatile float level = 1.0f;        /* an initial value: kept in flash, copied to RAM at reset */

static float filter(float x) {
    level += 0.125f * (x - level);
    return level;
}

int main(void) {
    for (;;) {
        ticks++;
        (void)filter((float)(ticks & 0xff));
    }
}
