@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM ═══════════════════════════════════════════════
REM  PDF Image Upscaler - Windows 원클릭 설치 및 실행
REM ═══════════════════════════════════════════════

cd /d "%~dp0"

echo.
echo ═══════════════════════════════════════════════
echo   PDF Image Upscaler - Windows 설치 프로그램
echo ═══════════════════════════════════════════════
echo.

REM ─── 사전 시스템 진단 (PowerShell 사용) ───
echo   [사전 진단] 시스템 환경을 확인합니다...
echo.

REM RAM 확인 (PowerShell로 64비트 안전 계산)
set "RAM_GB=0"
for /f "usebackq" %%a in (`powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)"`) do (
    set "RAM_GB=%%a"
)

REM CPU 확인
set "CPU_CORES=0"
set "CPU_NAME=Unknown"
for /f "usebackq" %%a in (`powershell -NoProfile -Command "(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors"`) do (
    set "CPU_CORES=%%a"
)
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-CimInstance Win32_Processor).Name"`) do (
    set "CPU_NAME=%%a"
)

REM GPU 확인
set "GPU_NAME=Unknown"
set "HAS_GPU=0"
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-CimInstance Win32_VideoController).Name | Select-Object -First 1"`) do (
    set "GPU_NAME=%%a"
)
echo !GPU_NAME! | findstr /i "nvidia amd radeon geforce rtx gtx intel" >nul 2>&1
if !errorlevel!==0 set "HAS_GPU=1"

REM 디스크 여유 확인 (PowerShell로 64비트 안전 계산)
set "DISK_FREE_GB=0"
for /f "usebackq" %%a in (`powershell -NoProfile -Command "[math]::Round((Get-PSDrive -Name ($pwd.Drive.Name)).Free / 1GB)"`) do (
    set "DISK_FREE_GB=%%a"
)

echo   ┌──────────────────────────────────────┐
echo   │  시스템 환경                          │
echo   ├──────────────────────────────────────┤
echo   │  CPU  : !CPU_NAME!
echo   │  코어 : !CPU_CORES!코어
echo   │  RAM  : !RAM_GB!GB
echo   │  GPU  : !GPU_NAME!
echo   │  디스크: 여유 !DISK_FREE_GB!GB
echo   └──────────────────────────────────────┘
echo.

REM ─── 호환성 판정 ───
set "CAN_RUN=1"
set "SPEED=normal"

if !RAM_GB! LSS 4 (
    echo   ❌ [오류] RAM !RAM_GB!GB → 최소 4GB 필요합니다.
    set "CAN_RUN=0"
) else if !RAM_GB! LSS 8 (
    echo     ! [주의] RAM !RAM_GB!GB → 처리가 느릴 수 있습니다.
    set "SPEED=slow"
) else if !RAM_GB! GEQ 16 (
    set "SPEED=fast"
)

if !DISK_FREE_GB! LSS 1 (
    echo   ❌ [오류] 디스크 여유 !DISK_FREE_GB!GB → 최소 1GB 필요합니다.
    set "CAN_RUN=0"
) else if !DISK_FREE_GB! LSS 2 (
    echo     ! [주의] 디스크 여유 !DISK_FREE_GB!GB → 2GB 이상 권장
)

if !HAS_GPU!==0 (
    echo     ! [주의] GPU 가속 미지원 → CPU 모드로 3~5배 느릴 수 있습니다.
    set "SPEED=slow"
) else (
    echo   ✓ GPU 가속: Vulkan 지원
)

if "!SPEED!"=="fast" (
    echo   ✓ 예상 시간: 15장 기준 약 1~2분
) else if "!SPEED!"=="normal" (
    echo   ✓ 예상 시간: 15장 기준 약 2~5분
) else (
    echo   ✓ 예상 시간: 15장 기준 약 5~15분
)

if !CAN_RUN!==0 (
    echo.
    echo   위 오류를 해결한 후 다시 실행해주세요.
    echo.
    pause
    exit /b 1
)

echo.
set /p "CONTINUE=  설치를 계속하시겠습니까? (Y/n): "
if /i "!CONTINUE!"=="n" (
    echo   설치가 취소되었습니다.
    exit /b 0
)
echo.

REM ─── Python 3.12 확인 ───
set "PYTHON="

where python 2>nul >nul
if %errorlevel%==0 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
    echo !PYVER! | findstr /b "3.12" >nul
    if !errorlevel!==0 (
        set "PYTHON=python"
        goto :python_found
    )
)

where py 2>nul >nul
if %errorlevel%==0 (
    py -3.12 --version 2>nul >nul
    if !errorlevel!==0 (
        set "PYTHON=py -3.12"
        goto :python_found
    )
)

REM winget 설치 시도
echo [1/4] Python 3.12 설치 중...
where winget 2>nul >nul
if %errorlevel%==0 (
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements -s winget
    if !errorlevel!==0 (
        echo       설치 완료. PATH 반영을 위해 재시작이 필요합니다.
        echo       이 창을 닫고 install_windows.bat를 다시 더블클릭해주세요.
        pause
        exit /b 0
    )
)

echo.
echo   ┌─────────────────────────────────────────────┐
echo   │  Python 3.12 자동 설치에 실패했습니다.       │
echo   │                                              │
echo   │  아래에서 직접 설치해주세요:                  │
echo   │  https://www.python.org/downloads/           │
echo   │                                              │
echo   │  설치 시 "Add Python to PATH" 반드시 체크!   │
echo   │  설치 후 이 파일을 다시 더블클릭하세요.       │
echo   └─────────────────────────────────────────────┘
echo.
pause
exit /b 1

:python_found
echo [1/4] Python 3.12 확인 완료

REM ─── 가상환경 생성 ───
if not exist ".venv" (
    echo [2/4] 가상환경 생성 중...
    %PYTHON% -m venv .venv
) else (
    echo [2/4] 가상환경 이미 존재 - 건너뜀
)

call .venv\Scripts\activate.bat

REM ─── 의존성 설치 ───
pip show gradio >nul 2>&1
if %errorlevel% neq 0 (
    echo [3/4] 의존성 설치 중... (처음 실행 시 2~5분 소요)
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo       설치 완료!
) else (
    echo [3/4] 의존성 이미 설치됨 - 건너뜀
)

REM ─── 상세 진단 ───
echo.
python system_check.py 2>nul
echo.

REM ─── 앱 실행 ───
echo [4/4] 웹 UI 실행 중...
echo.
echo ═══════════════════════════════════════════
echo   브라우저에서 자동으로 열립니다.
echo   수동 접속: http://localhost:7860
echo   종료: 이 창에서 Ctrl+C
echo ═══════════════════════════════════════════
echo.

python app.py

pause
