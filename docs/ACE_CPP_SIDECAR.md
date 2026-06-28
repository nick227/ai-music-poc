# ACE.cpp Sidecar Runtime

This document details the usage and integration of ACE.cpp as an experimental, separate sidecar runtime backend for the ai-music-poc project.

## Runtime Boundary

ACE.cpp operates as a completely separate process (a sidecar) rather than being tightly coupled with the main Python runtime. It is invoked via command-line execution from our Python diagnostic and comparison scripts. The main API/UI of ai-music-poc still defaults to the Python ACE runtime.

## Installation Path

The ACE.cpp repository should be cloned and built at the following location:
`/home/administrator/models/acestep.cpp`

## Model Format Difference

- **Python ACE Runtime:** Uses standard PyTorch `safetensors` checkpoints. These are located at `/home/administrator/models/ACE-Step-1.5/checkpoints`.
- **ACE.cpp Runtime:** Uses the specialized `GGUF` (GPT-Generated Unified Format) model format, which is optimized for C++ execution via GGML. These models should be placed in `/home/administrator/models/ace-gguf`.

## Building ACE.cpp with CUDA

To leverage GPU acceleration, build ACE.cpp with CUDA support.

1. Ensure you have `cmake`, `g++`, and the CUDA toolkit installed.
2. Navigate to the installation path:
   ```bash
   cd /home/administrator/models/acestep.cpp
   ```
3. Run the CUDA build script:
   ```bash
   ./buildcuda.sh
   ```
   *Note: If CUDA is unavailable, you can fall back to the CPU build using `./buildcpu.sh`.*

## Where GGUF Models Should Live

GGUF models should be stored in:
`/home/administrator/models/ace-gguf`

## Running a First Generation

Once the models are correctly placed and ACE.cpp is compiled, you can run a generation directly via the CLI.

Example command (adjust the prompt and model path as necessary):
```bash
cd /home/administrator/models/acestep.cpp/build/bin
./acestep -m /home/administrator/models/ace-gguf/ace-1.5-q4_k_m.gguf -p "A simple test prompt" --seed 42
```
The output file will typically be written to the current directory as a `.wav` file.

## Validating Output with `ffprobe`

You can use `ffprobe` (part of the `ffmpeg` suite) to validate the generated audio file to ensure its format, duration, and sample rate are correct.

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output.wav
```
This will print the duration of the generated audio in seconds.
