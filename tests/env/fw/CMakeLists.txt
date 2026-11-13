# A Cortex-M4F program (flash at 0x08000000, RAM at 0x20000000: an STM32's map) with no C library: the files of
# `silik dev try build`, as a CMake project.
cmake_minimum_required(VERSION 3.20)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-linux-gnu-gcc)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
project(fw C)
set(CPU -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16)
add_executable(fw.elf main.c startup.c build_info.c)
# -ffile-prefix-map: the debug information names the sources relative to the project, not by this machine's path
target_compile_options(fw.elf PRIVATE ${CPU} -Os -g -ffreestanding -Wall -ffile-prefix-map=${CMAKE_SOURCE_DIR}=.)
target_link_options(fw.elf PRIVATE ${CPU} -nostdlib -T ${CMAKE_SOURCE_DIR}/cortex-m.ld)
