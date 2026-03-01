#!/usr/bin/env python3
"""
시스템 호환성 진단 스크립트

설치 전에 실행하여 현재 컴퓨터에서 PDF 업스케일러를
사용할 수 있는지 확인합니다.
"""

import os
import sys
import platform
import shutil
import subprocess


def get_ram_gb() -> float:
    """총 RAM을 GB 단위로 반환합니다."""
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except ImportError:
        pass

    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True
            )
            return round(int(result.stdout.strip()) / (1024 ** 3), 1)
        elif system == "Windows":
            result = subprocess.run(
                ["wmic", "computersystem", "get", "totalphysicalmemory"],
                capture_output=True, text=True,
            )
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip().isdigit()]
            if lines:
                return round(int(lines[0]) / (1024 ** 3), 1)
        elif system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 ** 2), 1)
    except Exception:
        pass
    return 0.0


def get_cpu_info() -> dict:
    """CPU 정보를 반환합니다."""
    cores = os.cpu_count() or 0
    arch = platform.machine()
    processor = platform.processor() or "Unknown"
    return {"cores": cores, "arch": arch, "processor": processor}


def get_gpu_info() -> dict:
    """GPU 정보를 반환합니다."""
    system = platform.system()
    gpu_name = "감지되지 않음"
    has_vulkan = False
    has_metal = False

    try:
        if system == "Darwin":
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.split("\n"):
                if "Chipset Model:" in line or "Chip:" in line:
                    gpu_name = line.split(":")[-1].strip()
                    break
            # Apple Silicon = Metal 지원
            if platform.machine() == "arm64" or "Apple" in gpu_name:
                has_metal = True
                has_vulkan = True  # MoltenVK
            # Intel Mac도 Metal 지원 (2012+)
            elif "Intel" in gpu_name or "AMD" in gpu_name:
                has_metal = True
                has_vulkan = True

        elif system == "Windows":
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True, text=True, timeout=10,
            )
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip() and l.strip() != "Name"]
            if lines:
                gpu_name = lines[0]
                # NVIDIA/AMD = Vulkan 지원
                if any(x in gpu_name.upper() for x in ["NVIDIA", "AMD", "RADEON", "GEFORCE", "RTX", "GTX"]):
                    has_vulkan = True
                # Intel UHD/Iris도 Vulkan 지원 (6세대+)
                elif "INTEL" in gpu_name.upper():
                    has_vulkan = True

        elif system == "Linux":
            result = subprocess.run(
                ["lspci"], capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.split("\n"):
                if "VGA" in line or "3D" in line:
                    gpu_name = line.split(":")[-1].strip()
                    has_vulkan = True
                    break

    except Exception:
        pass

    return {"name": gpu_name, "vulkan": has_vulkan, "metal": has_metal}


def get_disk_free_gb(path: str = ".") -> float:
    """디스크 여유 공간을 GB 단위로 반환합니다."""
    try:
        usage = shutil.disk_usage(path)
        return round(usage.free / (1024 ** 3), 1)
    except Exception:
        return 0.0


def run_check() -> dict:
    """전체 시스템 진단을 실행합니다.

    Returns:
        {"can_run": bool, "speed": "fast"|"normal"|"slow", "warnings": list, "info": dict}
    """
    system = platform.system()
    ram_gb = get_ram_gb()
    cpu = get_cpu_info()
    gpu = get_gpu_info()
    disk_free = get_disk_free_gb()

    warnings = []
    errors = []
    speed = "normal"

    # Python 버전 확인
    py_ver = sys.version_info
    if py_ver < (3, 9):
        errors.append(f"Python {py_ver.major}.{py_ver.minor} → 3.9 이상 필요합니다.")
    elif py_ver >= (3, 13):
        errors.append(f"Python {py_ver.major}.{py_ver.minor} → 3.12 이하 필요합니다. (realesrgan-ncnn-py 미지원)")

    # RAM 확인
    if ram_gb < 4:
        errors.append(f"RAM {ram_gb}GB → 최소 4GB 필요합니다.")
    elif ram_gb < 8:
        warnings.append(f"RAM {ram_gb}GB → 한 번에 1~2장씩만 처리하므로 느릴 수 있습니다.")
        speed = "slow"
    elif ram_gb >= 16:
        speed = "fast"

    # GPU 확인
    has_gpu = gpu["vulkan"] or gpu["metal"]
    if not has_gpu:
        warnings.append("GPU가 감지되지 않았습니다. CPU 모드로 실행되며 3~5배 느릴 수 있습니다.")
        if speed == "fast":
            speed = "normal"
        else:
            speed = "slow"

    # 디스크 확인
    if disk_free < 1:
        errors.append(f"디스크 여유 공간 {disk_free}GB → 최소 1GB 필요합니다.")
    elif disk_free < 2:
        warnings.append(f"디스크 여유 공간이 {disk_free}GB로 부족할 수 있습니다. 2GB 이상 권장.")

    # CPU 코어
    if cpu["cores"] < 2:
        warnings.append("CPU 코어가 1개뿐입니다. 병렬 처리가 불가하여 느릴 수 있습니다.")
        speed = "slow"

    can_run = len(errors) == 0

    # 예상 시간
    if speed == "fast":
        time_est = "15장 기준 약 1~2분"
    elif speed == "normal":
        time_est = "15장 기준 약 2~5분"
    else:
        time_est = "15장 기준 약 5~15분 (또는 그 이상)"

    return {
        "can_run": can_run,
        "speed": speed,
        "time_estimate": time_est,
        "errors": errors,
        "warnings": warnings,
        "info": {
            "os": f"{system} {platform.release()}",
            "python": f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}",
            "cpu": f"{cpu['processor']} ({cpu['cores']}코어, {cpu['arch']})",
            "ram": f"{ram_gb} GB",
            "gpu": gpu["name"],
            "gpu_accel": "Metal" if gpu["metal"] else ("Vulkan" if gpu["vulkan"] else "없음 (CPU 모드)"),
            "disk_free": f"{disk_free} GB",
        },
    }


def print_report(result: dict) -> None:
    """진단 결과를 터미널에 출력합니다."""
    info = result["info"]

    print()
    print("┌──────────────────────────────────────────┐")
    print("│       시스템 호환성 진단 결과             │")
    print("├──────────────────────────────────────────┤")
    print(f"│  OS      : {info['os']:<29}│")
    print(f"│  Python  : {info['python']:<29}│")
    print(f"│  CPU     : {info['cpu']:<29}│")
    print(f"│  RAM     : {info['ram']:<29}│")
    print(f"│  GPU     : {info['gpu']:<29}│")
    print(f"│  GPU가속 : {info['gpu_accel']:<29}│")
    print(f"│  디스크  : {info['disk_free']:<29}│")
    print("├──────────────────────────────────────────┤")

    if result["can_run"]:
        speed_label = {"fast": "빠름", "normal": "보통", "slow": "느림"}
        speed_icon = {"fast": "⚡", "normal": "✓", "slow": "⏳"}
        s = result["speed"]
        print(f"│  판정    : 사용 가능  {speed_icon[s]} {speed_label[s]:<19}│")
        print(f"│  예상시간: {result['time_estimate']:<29}│")
    else:
        print(f"│  판정    : ❌ 사용 불가                  │")

    print("└──────────────────────────────────────────┘")

    if result["errors"]:
        print()
        print("  [오류]")
        for err in result["errors"]:
            print(f"    ✗ {err}")

    if result["warnings"]:
        print()
        print("  [주의]")
        for warn in result["warnings"]:
            print(f"    ! {warn}")

    print()


if __name__ == "__main__":
    result = run_check()
    print_report(result)

    if not result["can_run"]:
        print("  위 오류를 해결한 후 다시 시도해주세요.")
        sys.exit(1)
    else:
        print("  설치를 계속 진행합니다...")
