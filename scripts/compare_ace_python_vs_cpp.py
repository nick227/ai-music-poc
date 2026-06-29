import os
import sys
import shutil
import subprocess
import tempfile
import time
import argparse
from pathlib import Path
from datetime import datetime
import json

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings
from app.domain.models import GenerationRequest
from app.generators.registry import create_default_registry
from scripts.verify_ace_model_version_comparison import validate_generated_audio

def run_python_ace(prompt, seed, duration, output_path):
    print("Running Python ACE generation...")
    settings = Settings()
    registry = create_default_registry(settings)
    generator = registry.get("ace-step-command")

    request = GenerationRequest(prompt=prompt, seed=seed, duration_seconds=duration)

    start_time = time.time()
    try:
        result = generator.generate(request, output_path)
        elapsed = time.time() - start_time
        print(f"Python ACE generation completed in {elapsed:.2f}s")
        return elapsed, True
    except Exception as e:
        print(f"Python ACE generation failed: {e}")
        return 0, False

def run_cpp_ace(prompt, seed, duration, output_path):
    print("Running ACE.cpp generation...")
    repo_path = "/home/administrator/models/acestep.cpp"
    binary_lm = os.path.join(repo_path, "build", "ace-lm")
    binary_synth = os.path.join(repo_path, "build", "ace-synth")

    if not (os.path.exists(binary_lm) and os.path.exists(binary_synth)):
        print("ACE.cpp binaries (ace-lm or ace-synth) not found.")
        return 0, False

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        request_file = temp_path / "request.json"
        request_data = {
            "caption": prompt,
            "seed": seed,
            "output_format": "wav16" if str(output_path).endswith('.wav') else "mp3",
        }
        with open(request_file, "w") as f:
            json.dump(request_data, f)

        start_time = time.time()
        try:
            lm_cmd = [
                binary_lm,
                "--models", "/home/administrator/models/ace-gguf",
                "--request", str(request_file),
            ]
            print(f"Running: {' '.join(lm_cmd)}")
            subprocess.run(lm_cmd, check=True)

            synth_request_file = temp_path / "request0.json"
            if not synth_request_file.exists():
                print(f"ace-lm did not produce expected {synth_request_file}")
                return 0, False

            synth_cmd = [
                binary_synth,
                "--models", "/home/administrator/models/ace-gguf",
                "--request", str(synth_request_file),
            ]
            print(f"Running: {' '.join(synth_cmd)}")
            subprocess.run(synth_cmd, check=True)

            elapsed = time.time() - start_time

            ext = "wav" if request_data["output_format"].startswith("wav") else "mp3"
            generated_audio = temp_path / f"request00.{ext}"
            if not generated_audio.exists():
                print(f"ace-synth did not produce expected {generated_audio}")
                return elapsed, False

            shutil.copy(generated_audio, output_path)
            print(f"ACE.cpp generation completed in {elapsed:.2f}s")
            return elapsed, True
        except subprocess.CalledProcessError as e:
            print(f"ACE.cpp generation failed: {e}")
            return 0, False
        except Exception as e:
            print(f"Error running ACE.cpp: {e}")
            return 0, False

def main():
    parser = argparse.ArgumentParser(description="Compare ACE Python vs ACE.cpp runtimes")
    parser.add_argument("--prompt", type=str, default="A beautiful ambient soundscape", help="Prompt for generation")
    parser.add_argument("--seed", type=int, default=42, help="Seed for generation")
    parser.add_argument("--duration", type=int, default=10, help="Duration in seconds")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = Path(f"data/experiments/ace-python-vs-cpp/{timestamp}")
    experiment_dir.mkdir(parents=True, exist_ok=True)

    python_out = experiment_dir / "python_out.wav"
    cpp_out = experiment_dir / "cpp_out.wav"

    py_elapsed, py_success = run_python_ace(args.prompt, args.seed, args.duration, python_out)
    cpp_elapsed, cpp_success = run_cpp_ace(args.prompt, args.seed, args.duration, cpp_out)

    report = {
        "timestamp": timestamp,
        "prompt": args.prompt,
        "seed": args.seed,
        "duration_requested": args.duration,
        "python_ace": {
            "success": py_success,
            "time_seconds": py_elapsed,
            "stats": {}
        },
        "cpp_ace": {
            "success": cpp_success,
            "time_seconds": cpp_elapsed,
            "stats": {}
        },
        "conclusion": "No automatic quality improvement claimed. Manual listening required."
    }

    if py_success and python_out.exists():
        try:
            report["python_ace"]["stats"] = validate_generated_audio(python_out)
        except Exception as e:
            report["python_ace"]["stats"] = {"error": str(e)}

    if cpp_success and cpp_out.exists():
        try:
            report["cpp_ace"]["stats"] = validate_generated_audio(cpp_out)
        except Exception as e:
            report["cpp_ace"]["stats"] = {"error": str(e)}

    report_file = experiment_dir / "report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nExperiment finished. Report written to {report_file}")
    print("Note: Do not claim quality improvement automatically. Listen to both outputs to evaluate.")

if __name__ == "__main__":
    main()
