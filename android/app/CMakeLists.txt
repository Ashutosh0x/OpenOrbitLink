cmake_minimum_required(VERSION 3.22)

# FreeSat Android NDK Build Configuration
# Builds the Codec2 JNI bridge used by the Kotlin app.

project(freesat_native C)

set(CMAKE_C_STANDARD 11)

add_library(codec2_jni SHARED
    ../../codec2-android/jni/codec2_jni.c
)

target_include_directories(codec2_jni PRIVATE
    ../../codec2-android/jni
)

target_link_libraries(codec2_jni
    android
    log
)
