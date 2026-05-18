cmake_minimum_required(VERSION 3.22)
project(freesat_codec2 C)

# Codec2 source (downloaded separately)
set(CODEC2_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src/codec2")

# Build Codec2 as static library for Android NDK
add_library(codec2 STATIC
    ${CODEC2_SRC_DIR}/codec2.c
    ${CODEC2_SRC_DIR}/lpc.c
    ${CODEC2_SRC_DIR}/nlp.c
    ${CODEC2_SRC_DIR}/postfilter.c
    ${CODEC2_SRC_DIR}/sine.c
    ${CODEC2_SRC_DIR}/quantise.c
    ${CODEC2_SRC_DIR}/phase.c
    ${CODEC2_SRC_DIR}/interp.c
    ${CODEC2_SRC_DIR}/pack.c
    ${CODEC2_SRC_DIR}/codebook.c
    ${CODEC2_SRC_DIR}/newamp1.c
    ${CODEC2_SRC_DIR}/newamp2.c
)

target_include_directories(codec2 PUBLIC ${CODEC2_SRC_DIR})

# JNI Bridge
add_library(codec2_jni SHARED
    jni/codec2_jni.c
)

target_link_libraries(codec2_jni
    codec2
    log
)

target_include_directories(codec2_jni PRIVATE
    ${CODEC2_SRC_DIR}
)

# Install
install(TARGETS codec2_jni DESTINATION lib)
