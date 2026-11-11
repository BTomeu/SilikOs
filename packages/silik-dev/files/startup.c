/* silik dev try: the start of a Cortex-M program. The vector table (the stack's top, then the reset handler) goes
 * first in flash; the reset handler copies the initial values of the data to RAM, clears the rest and calls main. */
#include <stdint.h>

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
int main(void);

void Reset_Handler(void) {
    uint32_t *src = &_sidata, *dst = &_sdata;
    while (dst < &_edata) *dst++ = *src++;
    for (dst = &_sbss; dst < &_ebss; dst++) *dst = 0;
    main();
    for (;;) { }
}

void Default_Handler(void) { for (;;) { } }

__attribute__((section(".isr_vector"), used))
const void *const g_vectors[16] = {
    &_estack, Reset_Handler,
    Default_Handler, Default_Handler, Default_Handler, Default_Handler, Default_Handler,   /* NMI, HardFault, MemManage, BusFault, UsageFault */
    0, 0, 0, 0,
    Default_Handler, Default_Handler, 0, Default_Handler, Default_Handler,                 /* SVCall, DebugMon, -, PendSV, SysTick */
};
