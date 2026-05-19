# Voice Codec Architecture — OpenOrbitLink

## Overview

OpenOrbitLink uses a **hybrid adaptive voice codec stack** that operates across wildly different link conditions — from 700bps LoRa mesh to WiFi/NTN paths. The system degrades gracefully, never assumes internet, and keeps neural enhancement strictly optional.

## Core Design Principles

1. **RF-First**: Codec2 owns the transport layer — deterministic, bandwidth-minimal, FEC-ready
2. **Neural-Optional**: Lyra-inspired enhancement is a receiver-side post-processor, never required
3. **Asynchronous Voice**: Push-to-talk voice messages, NOT real-time streaming
4. **Adaptive**: Codec selection responds to link conditions, battery, and regulatory constraints
5. **DTN-Native**: Voice chunks integrate with the store-and-forward bundle engine

## System Architecture

```mermaid
graph TB
    subgraph "Android App"
        MIC[Mic / AudioRecord]
        PTT[PushToTalkEngine]
        VCM[VoiceCodecManager<br/>Kotlin]
        SPK[Speaker / AudioTrack]
    end

    subgraph "Native Layer - C/C++ via JNI"
        JNI[codec_bridge_jni.c]
        
        subgraph "Codec Abstraction"
            CI[codec_interface.h<br/>OolCodecOps vtable]
            C2W[codec2_wrapper.c<br/>700C-3200]
            LYW[lyra_codec_wrapper.cc<br/>3200-9200]
        end
        
        subgraph "Enhancement"
            NE[neural_enhancer.cc<br/>SoundStream + LyraGAN]
            TFL[tflite_runtime.h<br/>Model management]
        end
        
        subgraph "Transport Prep"
            PLR[packet_loss_recovery.h<br/>PLC: repeat/interp/CNG]
            FEC[codec2_fec.c<br/>Golay + interleaving]
            CHK[voice_chunker.h<br/>80-byte LoRa chunks]
            ATC[airtime_calculator.h<br/>Duty cycle tracking]
        end
    end

    subgraph "Protocol Layer - Python"
        VT[voice_transport.py<br/>Chunk/reassembly]
        PKT[packet.py<br/>VOICE_CHUNK type]
        DTN[dtn.py<br/>queue_voice]
    end

    subgraph "Physical Layer"
        LORA[LoRa ISM 868MHz]
        WIFI[WiFi / BLE]
        NTN[Carrier NTN]
    end

    MIC --> PTT --> VCM
    VCM --> JNI
    JNI --> CI
    CI --> C2W
    CI --> LYW
    LYW --> TFL
    C2W --> FEC
    FEC --> CHK --> ATC
    CHK --> VT --> PKT --> DTN
    DTN --> LORA
    DTN --> WIFI
    DTN --> NTN
    
    LORA --> VT
    VT --> PLR --> CI --> NE --> SPK
```

## Codec Comparison

| Property | Codec2 700C | Codec2 1300 | Lyra 3200 | Lyra 9200 |
|----------|-------------|-------------|-----------|-----------|
| Bitrate | 700 bps | 1300 bps | 3200 bps | 9200 bps |
| Frame size | 4 bytes/40ms | 7 bytes/40ms | 8 bytes/20ms | 23 bytes/20ms |
| Quality (MOS) | ~2.5 | ~3.0 | ~3.5 | ~4.0 |
| CPU cost | Negligible | Negligible | ~50ms/s | ~50ms/s |
| Model size | 0 | 0 | 3.5 MB | 3.5 MB |
| LoRa-safe | ✅ | ✅ | ❌ | ❌ |
| Deterministic | ✅ | ✅ | ❌ | ❌ |

## Adaptive Mode Selection

```mermaid
stateDiagram-v2
    [*] --> Assess: Voice message recorded

    state Assess <<choice>>
    Assess --> C2_700C: LoRa ISM<br/>bandwidth < 1kbps
    Assess --> C2_1300: LoRa mesh<br/>bandwidth 1-2 kbps
    Assess --> Hybrid: Mixed path<br/>bandwidth 2-4 kbps
    Assess --> L_3200: WiFi local<br/>bandwidth 4-8 kbps
    Assess --> L_9200: WiFi/NTN<br/>bandwidth > 8 kbps

    state Hybrid {
        [*] --> TX_C2: Encode Codec2
        TX_C2 --> RX_Neural: Receive side
        RX_Neural --> [*]: Neural enhance
    }

    state OverrideCheck <<choice>>
    C2_700C --> OverrideCheck
    C2_1300 --> OverrideCheck
    Hybrid --> OverrideCheck
    L_3200 --> OverrideCheck
    L_9200 --> OverrideCheck

    OverrideCheck --> ForceC2: battery < 15%<br/>OR thermal hot<br/>OR amateur band
    OverrideCheck --> Proceed: Conditions OK

    ForceC2 --> ChunkForLoRa
    Proceed --> ChunkForLoRa
    ChunkForLoRa --> DTNQueue
    DTNQueue --> [*]
```

## Voice Chunk Wire Format

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤
│     MAGIC (0x564D)    │              MESSAGE_ID                   │
├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤
│          ...          │          SEQUENCE_NUM          │   FLAGS   │
├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤
│  CODEC_MODE  │                PAYLOAD (≤70 bytes)                 │
├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤
│                            ...                                    │
└───────────────────────────────────────────────────────────────────┘
Total: 10-byte header + ≤70-byte payload = ≤80 bytes (LoRa safe)
```

## Voice Message Lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant P as PTT Engine
    participant C as Codec Manager
    participant K as Chunker
    participant D as DTN Engine
    participant L as LoRa TX
    participant R as Receiver

    U->>P: Press PTT
    P->>P: Start AudioRecord (8kHz)
    P->>C: Query link conditions
    C-->>P: Use Codec2 700C

    loop Every 40ms frame
        P->>C: PCM (320 samples)
        C->>C: Codec2 encode → 4 bytes
    end

    U->>P: Release PTT
    P->>K: 125 encoded frames
    K->>K: Pack into LoRa chunks (≤80B)
    K->>D: Queue 8 chunks (priority=1)

    Note over D,L: Wait for TX window

    loop Each chunk
        D->>L: Transmit chunk
        L-->>R: LoRa packet
    end

    R->>R: Reassemble chunks
    R->>R: Detect missing → PLC
    R->>R: Codec2 decode
    R->>R: Neural enhance (optional)
    R->>R: Play audio
```

## LoRa Airtime Budget

| Duration | Frames | Data | Chunks | Airtime | Budget | Fits? |
|----------|--------|------|--------|---------|--------|-------|
| 1s | 25 | 100B | 2 | ~2.2s | 36.0s | ✅ |
| 5s | 125 | 500B | 8 | ~8.9s | 36.0s | ✅ |
| 10s | 250 | 1000B | 15 | ~16.6s | 36.0s | ✅ |
| 30s | 750 | 3000B | 45 | ~49.9s | 36.0s | ❌ |

> **Note**: 30-second messages at 700C exceed the 1% ISM duty cycle. The maximum practical voice message on LoRa is approximately **20 seconds**.

## File Structure

```
native/
├── include/
│   ├── codec_interface.h        # Universal codec vtable
│   ├── codec_registry.h         # Codec factory & enumeration
│   ├── audio_frame.h            # Frame container & wire format
│   ├── packet_loss_recovery.h   # PLC strategies
│   ├── adaptive_codec_manager.h # RF-aware codec selection
│   ├── voice_chunker.h          # LoRa-aware chunking
│   ├── airtime_calculator.h     # Semtech formula timing
│   ├── neural_enhancer.h        # Neural enhancement API
│   └── tflite_runtime.h         # TFLite model management
├── src/
│   ├── codec2_wrapper.c         # Codec2 implementation
│   ├── codec2_fec.c             # FEC for voice frames
│   ├── neural_enhancer.cc       # Neural enhancement impl
│   └── lyra_codec_wrapper.cc    # Lyra TFLite implementation
├── jni/
│   └── codec_bridge_jni.c       # Unified JNI bridge
└── CMakeLists.txt               # NDK build

android/app/src/main/java/org/freesat/codec/
├── VoiceCodecManager.kt         # Main codec manager
├── NeuralEnhancer.kt            # Neural enhancement wrapper
├── PushToTalkEngine.kt          # PTT lifecycle
├── VoiceMessage.kt              # Message + chunk data classes
├── AirtimeTracker.kt            # (in VoiceMessage.kt)
└── Codec2Native.kt              # Legacy wrapper (deprecated)

protocol/
├── packet.py                    # VOICE_CHUNK/VOICE_META types
├── voice_transport.py           # Chunking & reassembly
└── dtn.py                       # queue_voice() integration
```
