# Android NDK Setup — Voice Codec Build Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Android Studio | 2024.2+ | IDE with NDK manager |
| Android NDK | r26c+ | C/C++ cross-compilation |
| CMake | 3.22+ | Build system |
| JDK | 17+ | Kotlin/JNI compilation |

## Setup Steps

### 1. Install NDK via Android Studio

```
Android Studio → Settings → Languages & Frameworks →
Android SDK → SDK Tools → ✓ NDK (Side by side)
```

Or via command line:
```bash
sdkmanager --install "ndk;26.3.11579264"
```

### 2. Configure Gradle for Native Build

In `android/app/build.gradle.kts`:

```kotlin
android {
    // ...
    externalNativeBuild {
        cmake {
            path = file("../../native/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    
    defaultConfig {
        ndk {
            // Target ARM64 and x86_64 (emulator)
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
        
        externalNativeBuild {
            cmake {
                arguments(
                    "-DANDROID_STL=c++_shared",
                    "-DOOL_WITH_CODEC2=ON",
                    "-DOOL_WITH_TFLITE=OFF"  // Enable when TFLite integration is ready
                )
            }
        }
    }
}
```

### 3. Verify Codec2 Source

Ensure the Codec2 repository is cloned at the expected path:

```
freestat/
├── codec2/          ← git clone https://github.com/drowe67/codec2
│   └── src/
│       ├── codec2.c
│       ├── codec2.h
│       ├── codec2_internal.h
│       └── ...
├── native/          ← OpenOrbitLink voice core
│   ├── CMakeLists.txt
│   ├── include/
│   └── src/
└── android/
    └── app/
```

### 4. Build from Command Line

```bash
# From android/ directory
./gradlew assembleDebug

# Or build native only
cd native
cmake -B build -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
      -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-26
cmake --build build
```

### 5. TFLite Integration (Optional)

When ready to enable neural codecs:

1. Download TFLite AAR:
```bash
# Add to android/app/build.gradle.kts
dependencies {
    implementation("org.tensorflow:tensorflow-lite:2.16.1")
    implementation("org.tensorflow:tensorflow-lite-gpu:2.16.1")
}
```

2. Copy model files to assets:
```
android/app/src/main/assets/models/
├── soundstream_encoder.tflite   (1.7 MB)
├── quantizer.tflite             (329 KB)
└── lyragan.tflite               (1.5 MB)
```

3. Enable in CMake:
```bash
cmake -DOOL_WITH_TFLITE=ON -DTFLITE_LIB_DIR=/path/to/tflite/libs
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `codec2.h not found` | Verify `codec2/src/` path in CMakeLists.txt |
| `version.h missing` | CMake auto-generates it; rebuild |
| `UnsatisfiedLinkError` | Check ABI filter matches device |
| `TFLite models missing` | Copy `.tflite` files to assets |
