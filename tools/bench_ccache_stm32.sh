#!/usr/bin/env bash
# bench_ccache_stm32.sh: is a firmware build faster with ccache? Run ON EL 9 with EPEL (an `almalinux:9` container;
# about 2 GB of disk for the ARM compiler's libraries). A real STM32 build: ST's STM32G4 HAL and LL drivers (every
# source file), CMSIS, a main that sets the clock and blinks a pin, linked for an STM32G474, with STM32CubeIDE's Debug
# flags. Built (make clean each time) without ccache, with ccache and an empty cache, with ccache and a full one, and
# through PATH as EPEL's /etc/profile.d/ccache.sh sets it; once with -fstack-usage (CubeIDE's default) and once
# without. Prints the seconds of each build and ccache's counts; the medians go to docs/POWER.md.
#   SILIK_BENCH_RUNS (3) builds of each; SILIK_BENCH_JOBS (2) make -j; SILIK_BENCH_WORK (/tmp/ccache-stm32)
set -u
RUNS=${SILIK_BENCH_RUNS:-3}
JOBS=${SILIK_BENCH_JOBS:-2}
B=${SILIK_BENCH_WORK:-/tmp/ccache-stm32}
dnf -y -q install epel-release >/dev/null 2>&1 || :
dnf -y -q install arm-none-eabi-gcc-cs arm-none-eabi-newlib make ccache git >/dev/null 2>&1 || { echo "install failed"; exit 1; }
rpm -q arm-none-eabi-gcc-cs arm-none-eabi-newlib make ccache
ls -la /usr/lib64/ccache | grep arm-none
nproc
mkdir -p "$B" && cd "$B" || exit 1
rm -rf stm32g4xx_hal_driver cmsis_device_g4 CMSIS_6 app out ccache Makefile
for r in stm32g4xx_hal_driver cmsis_device_g4; do
  git clone -q --depth 1 https://github.com/STMicroelectronics/$r.git || exit 1
  echo "$r $(git -C $r rev-parse HEAD) $(git -C $r log -1 --format=%cs)"
done
git clone -q --depth 1 --branch v6.1.0 https://github.com/ARM-software/CMSIS_6.git || exit 1
echo "CMSIS_6 v6.1.0 $(git -C CMSIS_6 rev-parse HEAD)"
mkdir -p app
cp stm32g4xx_hal_driver/Inc/stm32g4xx_hal_conf_template.h app/stm32g4xx_hal_conf.h
cp cmsis_device_g4/Source/Templates/gcc/startup_stm32g474xx.s app/
cp cmsis_device_g4/Source/Templates/system_stm32g4xx.c app/
cat > app/main.c <<'EOF'
#include "stm32g4xx_hal.h"
static void clock(void) {
  RCC_OscInitTypeDef o = {0}; RCC_ClkInitTypeDef c = {0};
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);
  o.OscillatorType = RCC_OSCILLATORTYPE_HSI; o.HSIState = RCC_HSI_ON; o.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  o.PLL.PLLState = RCC_PLL_ON; o.PLL.PLLSource = RCC_PLLSOURCE_HSI; o.PLL.PLLM = RCC_PLLM_DIV4; o.PLL.PLLN = 85;
  o.PLL.PLLP = RCC_PLLP_DIV2; o.PLL.PLLQ = RCC_PLLQ_DIV2; o.PLL.PLLR = RCC_PLLR_DIV2;
  HAL_RCC_OscConfig(&o);
  c.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  c.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK; c.AHBCLKDivider = RCC_SYSCLK_DIV1; c.APB1CLKDivider = RCC_HCLK_DIV1; c.APB2CLKDivider = RCC_HCLK_DIV1;
  HAL_RCC_ClockConfig(&c, FLASH_LATENCY_4);
}
int main(void) {
  GPIO_InitTypeDef g = {0};
  HAL_Init(); clock();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  g.Pin = GPIO_PIN_5; g.Mode = GPIO_MODE_OUTPUT_PP; HAL_GPIO_Init(GPIOA, &g);
  for (;;) { HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5); HAL_Delay(500); }
}
void SysTick_Handler(void) { HAL_IncTick(); }
EOF
cat > app/g474.ld <<'EOF'
ENTRY(Reset_Handler)
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 128K
         RAM (rwx)  : ORIGIN = 0x20000000, LENGTH = 128K }
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
  .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
  .text : { *(.text*) *(.rodata*) KEEP(*(.init)) KEEP(*(.fini)) . = ALIGN(4); } > FLASH
  .ARM.exidx : { *(.ARM.exidx*) } > FLASH
  .preinit_array : { PROVIDE_HIDDEN(__preinit_array_start = .); KEEP(*(.preinit_array*)) PROVIDE_HIDDEN(__preinit_array_end = .); } > FLASH
  .init_array : { PROVIDE_HIDDEN(__init_array_start = .); KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array*)) PROVIDE_HIDDEN(__init_array_end = .); } > FLASH
  .fini_array : { PROVIDE_HIDDEN(__fini_array_start = .); KEEP(*(.fini_array*)) PROVIDE_HIDDEN(__fini_array_end = .); } > FLASH
  _sidata = LOADADDR(.data);
  .data : { . = ALIGN(4); _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } > RAM AT > FLASH
  .bss : { . = ALIGN(4); _sbss = .; __bss_start__ = .; *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .; __bss_end__ = .; end = .; } > RAM
}
EOF
# CubeIDE's Debug configuration (Project > Properties > C/C++ Build, STM32G474): its compiler line
cat > Makefile <<'EOF'
CC = arm-none-eabi-gcc
CPU = -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
CFLAGS = $(CPU) -std=gnu11 -g3 -DDEBUG -DUSE_HAL_DRIVER -DUSE_FULL_LL_DRIVER -DSTM32G474xx -O0 -ffunction-sections -fdata-sections \
         -Wall -MMD -MP --specs=nano.specs $(EXTRA) -Iapp -Istm32g4xx_hal_driver/Inc -Icmsis_device_g4/Include -ICMSIS_6/CMSIS/Core/Include
SRC = $(filter-out %_template.c,$(wildcard stm32g4xx_hal_driver/Src/*.c)) app/main.c app/system_stm32g4xx.c
OBJ = $(patsubst %.c,out/%.o,$(SRC)) out/startup.o
out/fw.elf: $(OBJ)
	$(CC) $(CPU) --specs=nano.specs --specs=nosys.specs -Tapp/g474.ld -Wl,--gc-sections -o $@ $(OBJ)
out/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<
out/startup.o: app/startup_stm32g474xx.s
	@mkdir -p out
	$(CC) $(CPU) -g3 -c -x assembler-with-cpp -o $@ $<
clean:
	rm -rf out
-include $(OBJ:.o=.d)
EOF
echo "sources: $(ls stm32g4xx_hal_driver/Src/*.c | grep -vc _template.c) of the HAL/LL + main + system + startup"
export CCACHE_DIR=$B/ccache     # (its own cache: the user's is not touched)
TIMEFORMAT=%R
one() {  # one clean build, its seconds
  make clean >/dev/null
  { time make -j$JOBS -s CC="$1" EXTRA="$2" >/tmp/make.log 2>&1; } 2>&1 | tail -1
}
for extra in "-fstack-usage" ""; do
  echo "== flags extra: '${extra}'"
  make clean >/dev/null; make -j$JOBS -s EXTRA="$extra" > /tmp/make.log 2>&1 || { tail -30 /tmp/make.log; exit 1; }
  arm-none-eabi-size out/fw.elf
  echo "warnings: $(grep -c warning: /tmp/make.log)"
  r=""; for i in $(seq $RUNS); do r="$r $(one arm-none-eabi-gcc "$extra")"; done; echo "plain:$r"
  r=""; for i in $(seq $RUNS); do ccache -C >/dev/null; ccache -z >/dev/null; r="$r $(one "ccache arm-none-eabi-gcc" "$extra")"; done; echo "ccache-cold:$r"
  ccache -s | grep -i -e hit -e miss -e uncacheable -e 'unsupported' -e 'cache size'
  ccache -z >/dev/null
  r=""; for i in $(seq $RUNS); do r="$r $(one "ccache arm-none-eabi-gcc" "$extra")"; done; echo "ccache-warm:$r"
  ccache -s | grep -i -e hit -e miss -e uncacheable -e 'unsupported' -e 'cache size'
  # through the PATH, as EPEL's /etc/profile.d/ccache.sh sets it for every login shell
  ccache -z >/dev/null
  r=""; for i in $(seq $RUNS); do r="$r $(PATH=/usr/lib64/ccache:$PATH one arm-none-eabi-gcc "$extra")"; done; echo "ccache-warm-via-PATH:$r"
  ccache -s | grep -i -e 'hits' -e miss
  du -sh $CCACHE_DIR
done
