import os
import sys
import subprocess
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
    binary_path1 = os.path.join(repo_path, "build", "bin", "acestep")
    binary_path2 = os.path.join(repo_path, "build", "acestep")
    
    if os.path.exists(binary_path1):
        binary_path = binary_path1
    elif os.path.exists(binary_path2):
        binary_path = binary_path2
    else:
        print("ACE.cpp binary not found.")
        return 0, False

    gguf_model = "/home/administrator/models/ace-gguf/ace-1.5-q4_k_m.gguf"
    if not os.path.exists(gguf_model):
        # try to find any gguf model
        models_dir = "/home/administrator/models/ace-gguf"
        if os.path.exists(models_dir):
            ggufs = [f for f in os.listdir(models_dir) if f.endswith(".gguf")]
            if ggufs:
                gguf_model = os.path.join(models_dir, ggufs[0])
            else:
                print("No GGUF model found.")
                return 0, False
        else:
            print("GGUF models directory not found.")
            return 0, False

    # Example command, adjusting to possible arguments
    # We will map duration to whatever the binary supports or just omit if unsupported
    cmd = [
        binary_path,
        "-m", gguf_model,
        "-p", prompt,
        "--seed", str(seed),
        "-o", str(output_path)
    ]
    
    start_time = time.time()
    try:
        subprocess.run(cmd, check=True)
        elapsed = time.time() - start_time
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
