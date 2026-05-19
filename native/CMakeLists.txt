cmake_minimum_required(VERSION 3.22)
project(openorbitlink_voice C CXX)

set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 17)

# ── Options ──────────────────────────────────────────────────────────────── #

option(OOL_WITH_CODEC2     "Build with Codec2 support"         ON)
option(OOL_WITH_TFLITE     "Build with TFLite neural support"  OFF)
option(OOL_CODEC2_700C     "Enable Codec2 700C mode"           ON)
option(OOL_CODEC2_1300     "Enable Codec2 1300 mode"           ON)
option(OOL_CODEC2_ALL      "Enable all Codec2 modes"           ON)

# ── Paths ────────────────────────────────────────────────────────────────── #

set(OOL_NATIVE_DIR    ${CMAKE_CURRENT_SOURCE_DIR})
set(OOL_INCLUDE_DIR   ${OOL_NATIVE_DIR}/include)
set(CODEC2_REPO_DIR   ${CMAKE_CURRENT_SOURCE_DIR}/../codec2)
set(CODEC2_SRC_DIR    ${CODEC2_REPO_DIR}/src)

# ── OpenOrbitLink Voice Core Library ─────────────────────────────────────── #

set(OOL_CORE_SOURCES
    src/codec2_wrapper.c
    src/codec2_fec.c
)

add_library(ool_voice_core STATIC ${OOL_CORE_SOURCES})

target_include_directories(ool_voice_core PUBLIC
    ${OOL_INCLUDE_DIR}
)

# ── Codec2 Static Library ───────────────────────────────────────────────── #

if(OOL_WITH_CODEC2 AND EXISTS ${CODEC2_SRC_DIR}/codec2.c)
    message(STATUS "Building with Codec2 from: ${CODEC2_SRC_DIR}")

    # Codec2 compile-time mode selection for binary size optimization
    if(NOT OOL_CODEC2_ALL)
        add_definitions(-DCODEC2_MODE_EN_DEFAULT=0)
        if(OOL_CODEC2_700C)
            add_definitions(-DCODEC2_MODE_700C_EN=1)
        endif()
        if(OOL_CODEC2_1300)
            add_definitions(-DCODEC2_MODE_1300_EN=1)
        endif()
    endif()

    set(CODEC2_SOURCES
        ${CODEC2_SRC_DIR}/codec2.c
        ${CODEC2_SRC_DIR}/lpc.c
        ${CODEC2_SRC_DIR}/nlp.c
        ${CODEC2_SRC_DIR}/postfilter.c
        ${CODEC2_SRC_DIR}/sine.c
        ${CODEC2_SRC_DIR}/quantise.c
        ${CODEC2_SRC_DIR}/phase.c
        ${CODEC2_SRC_DIR}/interp.c
        ${CODEC2_SRC_DIR}/pack.c
        ${CODEC2_SRC_DIR}/lsp.c
        ${CODEC2_SRC_DIR}/newamp1.c
        ${CODEC2_SRC_DIR}/codec2_fft.c
        ${CODEC2_SRC_DIR}/kiss_fft.c
        ${CODEC2_SRC_DIR}/kiss_fftr.c
        ${CODEC2_SRC_DIR}/golay23.c
        ${CODEC2_SRC_DIR}/dump.c
        ${CODEC2_SRC_DIR}/filter.c
        ${CODEC2_SRC_DIR}/sd.c
        ${CODEC2_SRC_DIR}/mbest.c
    )

    add_library(codec2 STATIC ${CODEC2_SOURCES})

    target_include_directories(codec2 PUBLIC ${CODEC2_SRC_DIR})

    # Suppress warnings in upstream Codec2 code
    target_compile_options(codec2 PRIVATE
        -Wno-unused-variable
        -Wno-unused-function
        -Wno-sign-compare
    )

    target_compile_definitions(ool_voice_core PRIVATE OOL_HAS_CODEC2=1)
    target_link_libraries(ool_voice_core PUBLIC codec2)

    # Generate version.h that codec2.h includes
    if(NOT EXISTS ${CODEC2_SRC_DIR}/codec2/version.h)
        file(MAKE_DIRECTORY ${CODEC2_SRC_DIR}/codec2)
        file(WRITE ${CODEC2_SRC_DIR}/codec2/version.h
            "#ifndef CODEC2_VERSION_H\n"
            "#define CODEC2_VERSION_H\n"
            "#define CODEC2_VERSION_MAJOR 1\n"
            "#define CODEC2_VERSION_MINOR 2\n"
            "#define CODEC2_VERSION_PATCH 0\n"
            "#define CODEC2_VERSION \"1.2.0\"\n"
            "#endif\n"
        )
    endif()

else()
    message(WARNING "Codec2 source not found at ${CODEC2_SRC_DIR} — building without Codec2")
endif()

# ── JNI Bridge (Android NDK) ────────────────────────────────────────────── #

if(ANDROID)
    add_library(ool_voice_jni SHARED
        jni/codec_bridge_jni.c
    )

    target_link_libraries(ool_voice_jni
        ool_voice_core
        log
    )

    target_include_directories(ool_voice_jni PRIVATE
        ${OOL_INCLUDE_DIR}
    )
endif()

# ── TFLite Integration (optional) ───────────────────────────────────────── #

if(OOL_WITH_TFLITE)
    # TFLite headers and library should be provided externally
    # For Android, use the TFLite AAR or pre-built .so
    find_library(TFLITE_LIB tensorflowlite HINTS ${TFLITE_LIB_DIR})
    if(TFLITE_LIB)
        target_compile_definitions(ool_voice_core PRIVATE OOL_HAS_TFLITE=1)
        target_link_libraries(ool_voice_core PUBLIC ${TFLITE_LIB})
    else()
        message(WARNING "TFLite library not found — neural codecs disabled")
    endif()
endif()

# ── Install ──────────────────────────────────────────────────────────────── #

install(TARGETS ool_voice_core DESTINATION lib)
install(DIRECTORY ${OOL_INCLUDE_DIR}/ DESTINATION include)

if(ANDROID)
    install(TARGETS ool_voice_jni DESTINATION lib)
endif()
