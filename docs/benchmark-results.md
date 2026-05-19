# Voice Codec Benchmark Results

## Test Environment

| Parameter | Value |
|-----------|-------|
| Date | _pending_ |
| Device | _pending_ |
| Android API | _pending_ |
| NDK Version | _pending_ |
| Codec2 Version | 1.2.0 |
| Lyra Models | v1.0 (SoundStream + RVQ + LyraGAN) |

## Codec Sizing Results

| Mode | Bitrate | Frame ms | Frame Bytes | Frames/Chunk | LoRa Safe |
|------|---------|----------|-------------|--------------|-----------|
| Codec2 700C | 700 bps | 40 | 4 | 17 | Yes |
| Codec2 1200 | 1200 bps | 40 | 6 | 11 | Yes |
| Codec2 1300 | 1300 bps | 40 | 7 | 10 | Yes |
| Codec2 1600 | 1600 bps | 40 | 8 | 8 | Yes |
| Codec2 2400 | 2400 bps | 20 | 6 | 11 | No |
| Codec2 3200 | 3200 bps | 20 | 8 | 8 | No |
| Lyra 3200 | 3200 bps | 20 | 8 | 8 | No |
| Lyra 6000 | 6000 bps | 20 | 15 | 4 | No |
| Lyra 9200 | 9200 bps | 20 | 23 | 3 | No |

## Voice Message Sizing (Codec2 700C)

| Duration | Frames | Data Bytes | Chunks | Est. Airtime | Fits 1% Duty |
|----------|--------|------------|--------|--------------|--------------|
| 1s | 25 | 100 | 2 | ~2.2s | Yes |
| 2s | 50 | 200 | 3 | ~3.3s | Yes |
| 5s | 125 | 500 | 8 | ~8.9s | Yes |
| 10s | 250 | 1000 | 15 | ~16.6s | Yes |
| 20s | 500 | 2000 | 30 | ~33.2s | Yes |
| 30s | 750 | 3000 | 45 | ~49.9s | No |

## Chunk Payload Efficiency

| Mode | Payload/Chunk | Wire/Chunk | Efficiency |
|------|---------------|------------|------------|
| Codec2 700C | 68B | 78B | 87.2% |
| Codec2 1300 | 70B | 80B | 87.5% |
| Lyra 3200 | 64B | 74B | 86.5% |
| Lyra 9200 | 69B | 79B | 87.3% |

## Encode/Decode Latency

_To be measured on target hardware_

| Mode | Encode (ms) | Decode (ms) | Decode + Enhance (ms) |
|------|-------------|-------------|----------------------|
| Codec2 700C | _pending_ | _pending_ | _pending_ |
| Codec2 1300 | _pending_ | _pending_ | _pending_ |
| Lyra 3200 | _pending_ | _pending_ | N/A |
| Lyra 9200 | _pending_ | _pending_ | N/A |

## Packet Loss Resilience

_To be measured with Gilbert-Elliott channel model_

| Scenario | Loss Rate | Chunks Delivered | Message Usable |
|----------|-----------|------------------|----------------|
| Good channel | ~1% | _pending_ | _pending_ |
| Urban ISM | ~10% | _pending_ | _pending_ |
| Dense IoT | ~20% | _pending_ | _pending_ |
| Hostile RF | ~40% | _pending_ | _pending_ |

## Android Battery Impact

_To be measured on target device_

| Mode | CPU Usage | Battery per 5s msg | Notes |
|------|-----------|-------------------|-------|
| Codec2 700C | _pending_ | _pending_ | DSP only |
| Codec2 + Neural | _pending_ | _pending_ | + TFLite inference |
| Lyra 3200 | _pending_ | _pending_ | Full neural pipeline |
