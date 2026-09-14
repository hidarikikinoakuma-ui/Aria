"""
ARIA System Detector
====================
Runs once on startup. Detects GPU, RAM, CPU and sets
the right config so Aria runs optimally on any machine.

Player: Hidarikikinoaku
"""

import platform
import subprocess
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class SystemProfile:
    # CPU
    cpu_name: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0

    # RAM
    ram_gb: float = 0.0

    # GPU
    gpu_name: str = ""
    gpu_vram_gb: float = 0.0
    gpu_vendor: str = ""          # nvidia / amd / intel / none

    # Capability flags — set based on hardware
    can_run_stable_diffusion: bool = False   # Aria sprite generation locally
    can_run_whisper_local: bool = False      # local speech recognition
    can_run_coqui_tts: bool = False          # Aria voice locally
    can_run_llm_local: bool = False          # local LLM (Ollama)
    use_api_vision: bool = True              # GPT-4o Vision via API

    # Mode
    mode: str = "api"   # "local", "hybrid", or "api"


def detect_system() -> SystemProfile:
    """
    Auto-detect hardware and return a SystemProfile.
    Sets capability flags so every other module knows
    what it can and cannot run locally.
    """
    profile = SystemProfile()
    os_type = platform.system()

    logger.info("Aria System Detector starting...")

    # ── CPU ──────────────────────────────────────────────
    try:
        import psutil
        profile.cpu_cores = psutil.cpu_count(logical=False) or 0
        profile.cpu_threads = psutil.cpu_count(logical=True) or 0
        profile.ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except ImportError:
        logger.warning("psutil not installed — RAM/CPU detection skipped")

    profile.cpu_name = platform.processor()

    # ── GPU ──────────────────────────────────────────────
    if os_type == "Windows":
        profile = _detect_gpu_windows(profile)
    elif os_type == "Linux":
        profile = _detect_gpu_linux(profile)
    elif os_type == "Darwin":
        profile = _detect_gpu_mac(profile)

    # ── Set capability flags ──────────────────────────────
    profile = _set_capabilities(profile)

    logger.info(f"System detected: {profile.gpu_name} | "
                f"{profile.ram_gb}GB RAM | Mode: {profile.mode}")

    return profile


def _detect_gpu_windows(profile: SystemProfile) -> SystemProfile:
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController",
             "get", "name,AdapterRAM", "/format:csv"],
            capture_output=True, text=True, timeout=10
        )
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 3:
                vram_bytes_str = parts[1].strip()
                name = parts[2].strip()
                if name and name.lower() not in ("name", ""):
                    profile.gpu_name = name
                    try:
                        vram_bytes = int(vram_bytes_str)
                        profile.gpu_vram_gb = round(vram_bytes / (1024 ** 3), 1)
                    except (ValueError, TypeError):
                        profile.gpu_vram_gb = 0.0
                    break

        # Determine vendor
        name_lower = profile.gpu_name.lower()
        if "nvidia" in name_lower or "geforce" in name_lower or "rtx" in name_lower or "gtx" in name_lower:
            profile.gpu_vendor = "nvidia"
        elif "amd" in name_lower or "radeon" in name_lower or "rx " in name_lower:
            profile.gpu_vendor = "amd"
        elif "intel" in name_lower:
            profile.gpu_vendor = "intel"
        else:
            profile.gpu_vendor = "none"

    except Exception as e:
        logger.warning(f"GPU detection failed: {e}")

    return profile


def _detect_gpu_linux(profile: SystemProfile) -> SystemProfile:
    # Try nvidia-smi first
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            if len(parts) >= 2:
                profile.gpu_name = parts[0].strip()
                profile.gpu_vram_gb = round(float(parts[1].strip()) / 1024, 1)
                profile.gpu_vendor = "nvidia"
                return profile
    except FileNotFoundError:
        pass

    # Try lspci for AMD
    try:
        result = subprocess.run(
            ["lspci"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if "VGA" in line or "3D" in line:
                profile.gpu_name = line.split(":")[-1].strip()
                if "AMD" in line or "Radeon" in line:
                    profile.gpu_vendor = "amd"
                elif "NVIDIA" in line:
                    profile.gpu_vendor = "nvidia"
                elif "Intel" in line:
                    profile.gpu_vendor = "intel"
                break
    except FileNotFoundError:
        pass

    return profile


def _detect_gpu_mac(profile: SystemProfile) -> SystemProfile:
    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if "Chipset Model" in line:
                profile.gpu_name = line.split(":")[-1].strip()
                if "Apple" in profile.gpu_name:
                    profile.gpu_vendor = "apple"
                break
    except Exception:
        pass
    return profile


def _set_capabilities(profile: SystemProfile) -> SystemProfile:
    """
    Set capability flags based on detected hardware.
    Conservative estimates — better to use API than crash.
    """
    vram = profile.gpu_vram_gb
    ram = profile.ram_gb
    vendor = profile.gpu_vendor

    # Coqui TTS — runs on CPU, just needs RAM
    # Ryzen 9 7900X with any RAM can handle this
    if ram >= 8:
        profile.can_run_coqui_tts = True

    # Stable Diffusion — needs 4GB+ VRAM (NVIDIA/AMD)
    # Used for generating Aria's sprite sheet (one-time)
    if vendor in ("nvidia", "amd") and vram >= 4.0:
        profile.can_run_stable_diffusion = True

    # Whisper local speech recognition — needs 4GB+ VRAM or 16GB RAM
    if (vendor in ("nvidia", "amd") and vram >= 4.0) or ram >= 16:
        profile.can_run_whisper_local = True

    # Local LLM (Ollama) — needs 8GB+ VRAM for 7B model
    if vendor in ("nvidia", "amd") and vram >= 8.0:
        profile.can_run_llm_local = True

    # GPT-4o Vision API — always available if API key present
    # Used for fight analysis — most accurate option anyway
    profile.use_api_vision = True

    # Set overall mode
    if profile.can_run_stable_diffusion and profile.can_run_coqui_tts:
        if profile.can_run_llm_local:
            profile.mode = "local"      # almost everything runs locally
        else:
            profile.mode = "hybrid"     # local TTS/art, API for vision
    else:
        profile.mode = "api"            # API for vision + art generation

    return profile


def save_profile(profile: SystemProfile, path: str = None) -> str:
    """Save detected profile to config/system_profile.json"""
    if path is None:
        base = Path(__file__).parent.parent
        path = base / "config" / "system_profile.json"

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w") as f:
        json.dump(asdict(profile), f, indent=2)

    logger.info(f"System profile saved to {path}")
    return str(path)


def load_profile(path: str = None) -> SystemProfile:
    """Load existing profile, or detect fresh if not found."""
    if path is None:
        base = Path(__file__).parent.parent
        path = base / "config" / "system_profile.json"

    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        return SystemProfile(**data)

    # No saved profile — detect fresh
    profile = detect_system()
    save_profile(profile, path)
    return profile


def print_profile(profile: SystemProfile):
    """Print a clean readable summary of the system profile."""
    print("\n" + "="*55)
    print("  ARIA — SYSTEM PROFILE")
    print("="*55)
    print(f"  CPU:    {profile.cpu_name}")
    print(f"          {profile.cpu_cores} cores / {profile.cpu_threads} threads")
    print(f"  RAM:    {profile.ram_gb} GB")
    print(f"  GPU:    {profile.gpu_name if profile.gpu_name else 'Not detected'}")
    print(f"  VRAM:   {profile.gpu_vram_gb} GB")
    print(f"  Vendor: {profile.gpu_vendor.upper()}")
    print("-"*55)
    print(f"  Mode:   {profile.mode.upper()}")
    print("-"*55)
    print(f"  Aria Voice (local):    {'✅' if profile.can_run_coqui_tts else '❌ (API fallback)'}")
    print(f"  Aria Art (local):      {'✅' if profile.can_run_stable_diffusion else '❌ (API generation)'}")
    print(f"  Fight Analysis (API):  {'✅' if profile.use_api_vision else '❌'}")
    print(f"  Local LLM:             {'✅' if profile.can_run_llm_local else '❌ (GPT-4o API)'}")
    print("="*55 + "\n")


if __name__ == "__main__":
    profile = detect_system()
    print_profile(profile)
    save_profile(profile)
    print(f"Profile saved. Mode: {profile.mode.upper()}")
