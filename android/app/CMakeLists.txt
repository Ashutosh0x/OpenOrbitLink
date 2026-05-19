cmake_minimum_required(VERSION 3.22.1)

# ── OpenOrbitLink Android NDK Build ─────────────────────────────
# Builds native libraries for the Android APK:
#   - codec2_jni: Codec2 voice codec + FEC via JNI
#
# C sources live in ../../native/src/
# Headers live in ../../native/include/

project(openorbitlink_native C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# ── Source paths ────────────────────────────────────────────────
set(NATIVE_SRC_DIR ${CMAKE_SOURCE_DIR}/../../native/src)
set(NATIVE_INC_DIR ${CMAKE_SOURCE_DIR}/../../native/include)

# ── Codec2 JNI Bridge ──────────────────────────────────────────
# Core voice codec: Codec2 700C encoding/decoding + Golay FEC
add_library(codec2_jni SHARED
    ${NATIVE_SRC_DIR}/codec2_wrapper.c
    ${NATIVE_SRC_DIR}/codec2_fec.c
)

target_include_directories(codec2_jni PRIVATE
    ${NATIVE_INC_DIR}
)

target_link_libraries(codec2_jni
    android
    log
)

# Compiler warnings
target_compile_options(codec2_jni PRIVATE
    -Wall -Wextra -Wno-unused-parameter
)

# ── Future: Lyra neural codec (C++ / TFLite) ──────────────────
# Uncomment when TFLite is vendored:
#
# add_library(lyra_jni SHARED
#     ${NATIVE_SRC_DIR}/lyra_codec_wrapper.cc
#     ${NATIVE_SRC_DIR}/neural_enhancer.cc
# )
# target_include_directories(lyra_jni PRIVATE ${NATIVE_INC_DIR})
# target_link_libraries(lyra_jni android log)
