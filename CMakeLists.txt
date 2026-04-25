cmake_minimum_required(VERSION 3.20)
project(latent_somatic LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_TYPE Release CACHE STRING "")

# ---------------------------------------------------------------------------
# LibTorch
# ---------------------------------------------------------------------------
# Set TORCH_DIR via -DTORCH_DIR=/path/to/libtorch/share/cmake/Torch
# or install PyTorch and point to its cmake dir.
find_package(Torch REQUIRED PATHS ${TORCH_DIR})

# ---------------------------------------------------------------------------
# llama.cpp
# ---------------------------------------------------------------------------
# Clone llama.cpp alongside this project: git clone https://github.com/ggml-org/llama.cpp
# Then: -DLLAMA_DIR=/path/to/llama.cpp
#
# Build llama.cpp first:
#   cd llama.cpp && cmake -B build -DLLAMA_CUDA=ON && cmake --build build --config Release -j$(nproc)
set(LLAMA_DIR "" CACHE PATH "Path to llama.cpp source directory")
if(NOT LLAMA_DIR)
    message(FATAL_ERROR "Set -DLLAMA_DIR=/path/to/llama.cpp")
endif()

add_library(llama SHARED IMPORTED)
set_target_properties(llama PROPERTIES
    IMPORTED_LOCATION "${LLAMA_DIR}/build/bin/libllama.so"
    INTERFACE_INCLUDE_DIRECTORIES "${LLAMA_DIR}/include;${LLAMA_DIR}/ggml/include"
)
# ggml runtime libs needed alongside libllama.so
add_library(ggml      SHARED IMPORTED)
add_library(ggml_base SHARED IMPORTED)
add_library(ggml_cpu  SHARED IMPORTED)
set_target_properties(ggml      PROPERTIES IMPORTED_LOCATION "${LLAMA_DIR}/build/bin/libggml.so")
set_target_properties(ggml_base PROPERTIES IMPORTED_LOCATION "${LLAMA_DIR}/build/bin/libggml-base.so")
set_target_properties(ggml_cpu  PROPERTIES IMPORTED_LOCATION "${LLAMA_DIR}/build/bin/libggml-cpu.so")

# ---------------------------------------------------------------------------
# Main executable
# ---------------------------------------------------------------------------
set(SOURCES
    src/main.cpp
    src/hw_interface.cpp
    src/somatic_projector.cpp
    src/llm_bridge.cpp
)

add_executable(latent_somatic ${SOURCES})

target_include_directories(latent_somatic PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${TORCH_INCLUDE_DIRS}
)

target_link_libraries(latent_somatic PRIVATE
    ${TORCH_LIBRARIES}
    llama
    ggml
    ggml_base
    ggml_cpu
)

# Match the CXX11 ABI that this PyTorch wheel was compiled with
target_compile_definitions(latent_somatic PRIVATE _GLIBCXX_USE_CXX11_ABI=1)

# Real-time priority for sensor thread (requires CAP_SYS_NICE or root on Linux)
if(UNIX)
    target_link_libraries(latent_somatic PRIVATE pthread)
    # I2C
    find_library(I2C_LIB i2c)
    if(I2C_LIB)
        target_link_libraries(latent_somatic PRIVATE ${I2C_LIB})
        target_compile_definitions(latent_somatic PRIVATE HAVE_LIBI2C)
    endif()
endif()

# ---------------------------------------------------------------------------
# Build instructions (printed at configure time)
# ---------------------------------------------------------------------------
message(STATUS "
  Build with:
    cmake -B build \\
      -DTORCH_DIR=$(python3 -c 'import torch; print(torch.utils.cmake_prefix_path)') \\
      -DLLAMA_DIR=/path/to/llama.cpp
    cmake --build build -j\$(nproc)

  Run:
    ./build/latent_somatic models/llama3-8b-q4.gguf
")
