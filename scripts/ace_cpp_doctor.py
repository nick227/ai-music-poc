import os
import shutil
import subprocess

def check_path_exists(path, name):
    if os.path.exists(path):
        print(f"[\u2713] {name} exists at {path}")
        return True
    else:
        print(f"[\u2717] {name} missing at {path}")
        return False

def check_command(cmd, name):
    if shutil.which(cmd):
        print(f"[\u2713] {name} command found ({cmd})")
        return True
    else:
        print(f"[\u2717] {name} command missing")
        return False

def check_cuda_support(binary_path):
    try:
        # We can check ldd output for libcublas or libcudart
        result = subprocess.run(["ldd", binary_path], capture_output=True, text=True)
        if "cuda" in result.stdout.lower() or "cublas" in result.stdout.lower():
            print(f"[\u2713] ACE.cpp binary appears to be built with CUDA support")
        else:
            print(f"[!] ACE.cpp binary does NOT appear to have CUDA support linked dynamically")
    except Exception as e:
        print(f"[?] Could not determine CUDA support: {e}")

def main():
    print("--- ACE.cpp Environment Doctor ---")
    
    # 1. Check repo
    repo_path = "/home/administrator/models/acestep.cpp"
    check_path_exists(repo_path, "ACE.cpp repository")
    
    # 2. Check binary
    binary_path1 = os.path.join(repo_path, "build", "bin", "acestep")
    binary_path2 = os.path.join(repo_path, "build", "acestep")
    
    binary_exists = False
    if os.path.exists(binary_path1):
        binary_exists = True
        binary_path = binary_path1
    elif os.path.exists(binary_path2):
        binary_exists = True
        binary_path = binary_path2
    else:
        binary_path = None
        
    if binary_exists:
        print(f"[\u2713] ACE.cpp binary exists at {binary_path}")
        # Check for CUDA
        check_cuda_support(binary_path)
    else:
        print(f"[\u2717] ACE.cpp binary missing (checked {binary_path1} and {binary_path2})")
        
    # 3. Check GGUF models dir
    models_dir = "/home/administrator/models/ace-gguf"
    dir_exists = check_path_exists(models_dir, "GGUF models directory")
    
    # 4. Check GGUF model files
    if dir_exists:
        files = os.listdir(models_dir)
        gguf_files = [f for f in files if f.endswith(".gguf")]
        if gguf_files:
            print(f"[\u2713] Found {len(gguf_files)} GGUF model(s): {', '.join(gguf_files)}")
        else:
            print(f"[\u2717] No .gguf files found in {models_dir}")
            
    # 5. Check ffmpeg/ffprobe
    check_command("ffmpeg", "ffmpeg")
    check_command("ffprobe", "ffprobe")
    
    print("----------------------------------")

if __name__ == "__main__":
    main()
