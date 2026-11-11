/* silik dev try: flash at 0x08000000 and RAM at 0x20000000, where STM32 parts have them. The sizes are small on
   purpose and belong to no particular part: a real project takes its part's linker script. */
ENTRY(Reset_Handler)
MEMORY {
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 64K
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 16K
}
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
  .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
  .text : { *(.text*) *(.rodata*) KEEP(*(.init)) KEEP(*(.fini)) . = ALIGN(4); } > FLASH
  .ARM.exidx : { *(.ARM.exidx*) } > FLASH
  .init_array : { KEEP(*(.preinit_array*)) KEEP(*(.init_array*)) KEEP(*(.fini_array*)) } > FLASH
  _sidata = LOADADDR(.data);
  .data : { . = ALIGN(4); _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } > RAM AT > FLASH
  .bss : { . = ALIGN(4); _sbss = .; __bss_start__ = .; *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .; __bss_end__ = .; end = .; } > RAM
}
