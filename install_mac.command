#!/bin/bash
# ═══════════════════════════════════════════════
#  PDF Image Upscaler - macOS 원클릭 설치 & 실행
# ═══════════════════════════════════════════════

set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

echo ""
echo "═══════════════════════════════════════════"
echo "  PDF Image Upscaler - macOS 설치 프로그램"
echo "═══════════════════════════════════════════"
echo ""

# ─── 사전 시스템 진단 (Python 설치 전) ───
echo "  [사전 진단] 시스템 환경을 확인합니다..."
echo ""

# RAM 확인
RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
RAM_GB=$((RAM_BYTES / 1073741824))

# CPU 확인
CPU_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo 0)
CPU_BRAND=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Unknown")

# GPU 확인
GPU_NAME=$(system_profiler SPDisplaysDataType 2>/dev/null | grep -E "Chipset Model:|Chip:" | head -1 | awk -F': ' '{print $2}' || echo "Unknown")

# 디스크 여유 확인
DISK_FREE_KB=$(df -k . | tail -1 | awk '{print $4}')
DISK_FREE_GB=$((DISK_FREE_KB / 1048576))

# 아키텍처
ARCH=$(uname -m)

echo "  ┌──────────────────────────────────────┐"
echo "  │  시스템 환경                          │"
echo "  ├──────────────────────────────────────┤"
printf "  │  CPU  : %-29s│\n" "$CPU_BRAND"
printf "  │  코어 : %-29s│\n" "${CPU_CORES}코어 ($ARCH)"
printf "  │  RAM  : %-29s│\n" "${RAM_GB}GB"
printf "  │  GPU  : %-29s│\n" "$GPU_NAME"
printf "  │  디스크: %-29s│\n" "여유 ${DISK_FREE_GB}GB"
echo "  └──────────────────────────────────────┘"
echo ""

# 호환성 판정
CAN_RUN=true
SPEED="normal"
WARNINGS=""

if [[ $RAM_GB -lt 4 ]]; then
    echo "  ❌ [오류] RAM ${RAM_GB}GB → 최소 4GB 필요합니다."
    CAN_RUN=false
elif [[ $RAM_GB -lt 8 ]]; then
    WARNINGS="${WARNINGS}\n    ! RAM ${RAM_GB}GB → 처리가 느릴 수 있습니다."
    SPEED="slow"
elif [[ $RAM_GB -ge 16 ]]; then
    SPEED="fast"
fi

if [[ $DISK_FREE_GB -lt 1 ]]; then
    echo "  ❌ [오류] 디스크 여유 공간 ${DISK_FREE_GB}GB → 최소 1GB 필요합니다."
    CAN_RUN=false
elif [[ $DISK_FREE_GB -lt 2 ]]; then
    WARNINGS="${WARNINGS}\n    ! 디스크 여유 ${DISK_FREE_GB}GB → 2GB 이상 권장"
fi

# GPU 가속 판정
if [[ "$ARCH" == "arm64" ]] || echo "$GPU_NAME" | grep -qi "apple"; then
    GPU_ACCEL="Metal (Apple Silicon)"
elif echo "$GPU_NAME" | grep -qiE "intel|amd|radeon"; then
    GPU_ACCEL="Metal"
else
    GPU_ACCEL="없음 (CPU 모드 - 느림)"
    WARNINGS="${WARNINGS}\n    ! GPU 가속 미지원 → CPU 모드로 3~5배 느립니다."
    SPEED="slow"
fi

# 속도 예상
if [[ "$SPEED" == "fast" ]]; then
    TIME_EST="15장 기준 약 1~2분"
elif [[ "$SPEED" == "normal" ]]; then
    TIME_EST="15장 기준 약 2~5분"
else
    TIME_EST="15장 기준 약 5~15분"
fi

if [[ "$CAN_RUN" == false ]]; then
    echo ""
    echo "  위 오류를 해결한 후 다시 실행해주세요."
    echo ""
    read -p "  아무 키나 눌러 종료..." -n1 -s
    exit 1
fi

echo "  ✓ 판정: 사용 가능 | 속도: $SPEED | GPU: $GPU_ACCEL"
echo "  ✓ 예상 시간: $TIME_EST"

if [[ -n "$WARNINGS" ]]; then
    echo ""
    echo "  [주의사항]"
    echo -e "$WARNINGS"
fi

echo ""
read -p "  설치를 계속하시겠습니까? (Y/n): " -n1 REPLY
echo ""

if [[ "$REPLY" =~ ^[Nn]$ ]]; then
    echo "  설치가 취소되었습니다."
    exit 0
fi

echo ""

# ─── Homebrew 확인/설치 ───
if ! command -v brew &>/dev/null; then
    echo ""
    echo "  ┌──────────────────────────────────────────────┐"
    echo "  │  Homebrew(패키지 관리자)가 필요합니다.         │"
    echo "  │  공식 사이트: https://brew.sh                 │"
    echo "  │  Homebrew를 설치하면 Python 3.12를            │"
    echo "  │  자동으로 설치할 수 있습니다.                  │"
    echo "  └──────────────────────────────────────────────┘"
    echo ""
    read -p "  Homebrew를 설치하시겠습니까? (Y/n): " -n1 BREW_REPLY
    echo ""
    if [[ "$BREW_REPLY" =~ ^[Nn]$ ]]; then
        echo "  Homebrew 없이는 Python 3.12를 자동 설치할 수 없습니다."
        echo "  https://www.python.org/downloads/ 에서 직접 설치 후 다시 실행해주세요."
        read -p "  아무 키나 눌러 종료..." -n1 -s
        exit 1
    fi
    echo "[1/4] Homebrew 설치 중... (macOS 패키지 관리자)"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
else
    echo "[1/4] Homebrew 확인 완료"
fi

# ─── Python 3.12 확인/설치 ───
PYTHON=""
for candidate in python3.12 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "[2/4] Python 3.12 설치 중..."
    brew install python@3.12
    if [[ -f /opt/homebrew/bin/python3.12 ]]; then
        PYTHON="/opt/homebrew/bin/python3.12"
    else
        PYTHON="/usr/local/bin/python3.12"
    fi
else
    echo "[2/4] Python 3.12 확인 완료 ($PYTHON)"
fi

# ─── 가상환경 생성 ───
VENV_DIR="$APP_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "[3/4] 가상환경 생성 및 의존성 설치 중... (약 1~2분)"
    "$PYTHON" -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q
    pip install -r "$APP_DIR/requirements.txt" -q
    echo "       설치 완료!"
else
    echo "[3/4] 가상환경 이미 존재 - 건너뜀"
    source "$VENV_DIR/bin/activate"
fi

# ─── 상세 진단 (Python + psutil 사용 가능) ───
echo ""
python "$APP_DIR/system_check.py" 2>/dev/null || true
echo ""

# ─── 앱 실행 ───
echo "[4/4] 웹 UI 실행 중..."
echo ""
echo "═══════════════════════════════════════════"
echo "  브라우저에서 자동으로 열립니다."
echo "  수동 접속: http://localhost:7860"
echo "  종료: 이 터미널에서 Ctrl+C"
echo "═══════════════════════════════════════════"
echo ""

python "$APP_DIR/app.py"
