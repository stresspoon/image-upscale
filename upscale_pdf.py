#!/usr/bin/env python3
"""
PDF Image Upscaler - AI 기반 PDF 이미지 2배 업스케일링 엔진

이미지로 구성된 PDF(최대 15장)의 각 페이지를 Real-ESRGAN AI 모델로
2배 업스케일한 후 새 PDF로 재조립합니다.

시스템 리소스(RAM, CPU)를 자동 감지하여 최적의 병렬 처리를 수행합니다.
Gradio 웹 UI(app.py) 및 CLI에서 모두 사용 가능합니다.
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import psutil
import fitz  # PyMuPDF
from PIL import Image

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────
MODEL_ID = 0          # realesr-animevideov3-x2 (2x 업스케일)
MODEL_NAME = "realesr-animevideov3-x2"
SCALE = 2
MEMORY_PER_IMAGE = 200 * 1024 * 1024  # ~200MB per image
MAX_PAGES = 15


# ──────────────────────────────────────────────
# 시스템 리소스 감지
# ──────────────────────────────────────────────
def get_system_info() -> dict:
    """시스템 리소스 정보를 수집합니다."""
    mem = psutil.virtual_memory()
    return {
        "cpu_count": os.cpu_count() or 4,
        "total_ram_gb": round(mem.total / (1024 ** 3), 1),
        "available_ram_gb": round(mem.available / (1024 ** 3), 1),
        "available_ram_bytes": mem.available,
    }


def detect_optimal_workers(num_images: int) -> int:
    """시스템 리소스에 따라 최적의 워커 수를 결정합니다."""
    info = get_system_info()
    ram_based = int(info["available_ram_bytes"] * 0.6 / MEMORY_PER_IMAGE)
    cpu_based = max(1, info["cpu_count"] - 2)
    optimal = min(ram_based, cpu_based, num_images)
    return max(1, min(optimal, 6))


# ──────────────────────────────────────────────
# PDF → 이미지 추출
# ──────────────────────────────────────────────
def extract_pages_as_images(pdf_path: str, dpi: int = 300) -> tuple[list[tuple[int, str]], str]:
    """PDF의 각 페이지를 이미지 파일로 추출합니다.

    Returns:
        (page_images, temp_dir) 튜플
    """
    doc = fitz.open(pdf_path)
    page_count = len(doc)

    if page_count > MAX_PAGES:
        doc.close()
        raise ValueError(f"PDF가 {page_count}장입니다. 최대 {MAX_PAGES}장까지 지원합니다.")

    if page_count == 0:
        doc.close()
        raise ValueError("PDF에 페이지가 없습니다.")

    temp_dir = tempfile.mkdtemp(prefix="upscale_pdf_")
    results = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for i in range(page_count):
        page = doc[i]
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img_path = os.path.join(temp_dir, f"page_{i:03d}.png")
        pix.save(img_path)
        results.append((i, img_path))

    doc.close()
    return results, temp_dir


# ──────────────────────────────────────────────
# 단일 이미지 업스케일 (워커 프로세스에서 실행)
# ──────────────────────────────────────────────
def _upscale_worker(args: tuple) -> tuple[int, str, bool, str]:
    """워커 프로세스에서 단일 이미지를 업스케일합니다."""
    page_idx, input_path, output_path, gpu_id, tile_size = args
    original_stderr = sys.stderr

    try:
        # GPU 감지 로그 억제 (contextlib 대신 직접 처리 - 워커 프로세스 안전성)
        sys.stderr = open(os.devnull, "w")

        from realesrgan_ncnn_py import Realesrgan
        upscaler = Realesrgan(gpuid=gpu_id, tta_mode=False, tilesize=tile_size, model=MODEL_ID)

        img = Image.open(input_path).convert("RGB")
        result = upscaler.process_pil(img)
        result.save(output_path, "PNG", optimize=True)
        return (page_idx, output_path, True, "OK")

    except Exception as e:
        try:
            Image.open(input_path).save(output_path, "PNG")
        except Exception:
            pass
        return (page_idx, output_path, False, str(e))

    finally:
        sys.stderr = original_stderr


# ──────────────────────────────────────────────
# 병렬 업스케일링
# ──────────────────────────────────────────────
def upscale_images(
    page_images: list[tuple[int, str]],
    workers: int | None = None,
    tile_size: int = 0,
    gpu_id: int = 0,
    progress_callback=None,
) -> tuple[list[tuple[int, str]], str, int]:
    """여러 이미지를 병렬로 업스케일합니다.

    Args:
        progress_callback: (completed, total) 호출되는 콜백 함수 (Gradio용)

    Returns:
        (upscaled_images, temp_dir, failed_count)
    """
    if workers is None:
        workers = detect_optimal_workers(len(page_images))

    temp_dir = tempfile.mkdtemp(prefix="upscale_output_")

    tasks = []
    for page_idx, input_path in page_images:
        output_path = os.path.join(temp_dir, f"upscaled_{page_idx:03d}.png")
        tasks.append((page_idx, input_path, output_path, gpu_id, tile_size))

    results = []
    failed = 0

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_upscale_worker, task): task[0] for task in tasks}

        completed = 0
        for future in as_completed(futures):
            page_idx, output_path, success, msg = future.result()
            if not success:
                failed += 1
            results.append((page_idx, output_path))
            completed += 1
            if progress_callback:
                progress_callback(completed, len(tasks))

    results.sort(key=lambda x: x[0])
    return results, temp_dir, failed


# ──────────────────────────────────────────────
# 이미지 → PDF 재조립
# ──────────────────────────────────────────────
def create_pdf(image_paths: list[tuple[int, str]], output_path: str) -> None:
    """업스케일된 이미지들을 하나의 PDF로 조립합니다."""
    images = []
    for _, img_path in image_paths:
        img = Image.open(img_path).convert("RGB")
        images.append(img)

    if not images:
        raise ValueError("업스케일된 이미지가 없습니다.")

    first = images[0]
    rest = images[1:] if len(images) > 1 else []

    first.save(output_path, "PDF", save_all=True, append_images=rest, resolution=300.0)

    for img in images:
        img.close()


# ──────────────────────────────────────────────
# 메인 파이프라인 (Gradio + CLI 공용)
# ──────────────────────────────────────────────
def process_pdf(
    input_pdf_path: str,
    output_pdf_path: str | None = None,
    dpi: int = 300,
    workers: int | None = None,
    progress_callback=None,
) -> dict:
    """PDF 업스케일 전체 파이프라인을 실행합니다.

    Returns:
        {"output_path": str, "pages": int, "elapsed": float, "size_mb": float, "failed": int, "workers": int}
    """
    input_path = os.path.abspath(input_pdf_path)

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {input_path}")

    if not input_path.lower().endswith(".pdf"):
        raise ValueError("PDF 파일이 아닙니다.")

    if output_pdf_path is None:
        stem = Path(input_path).stem
        parent = Path(input_path).parent
        output_pdf_path = str(parent / f"{stem}_upscaled_2x.pdf")

    start = time.time()
    extract_dir = None
    output_dir = None

    try:
        # 1. 추출
        page_images, extract_dir = extract_pages_as_images(input_path, dpi=dpi)
        num_pages = len(page_images)

        # 2. 워커 결정
        actual_workers = workers if workers else detect_optimal_workers(num_pages)

        # 3. 업스케일
        upscaled, output_dir, failed = upscale_images(
            page_images, workers=actual_workers, progress_callback=progress_callback,
        )

        # 4. PDF 재조립
        create_pdf(upscaled, output_pdf_path)

        elapsed = time.time() - start
        size_mb = os.path.getsize(output_pdf_path) / (1024 * 1024)

        return {
            "output_path": output_pdf_path,
            "pages": num_pages,
            "elapsed": round(elapsed, 1),
            "size_mb": round(size_mb, 1),
            "failed": failed,
            "workers": actual_workers,
        }

    finally:
        # 임시 디렉토리 정리 (예외 발생 시에도 반드시 실행)
        if extract_dir:
            shutil.rmtree(extract_dir, ignore_errors=True)
        if output_dir:
            shutil.rmtree(output_dir, ignore_errors=True)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
def main():
    import argparse
    from tqdm import tqdm

    parser = argparse.ArgumentParser(
        description="PDF Image Upscaler - AI 기반 2배 업스케일링",
        epilog="예시: python upscale_pdf.py input.pdf -o output.pdf",
    )
    parser.add_argument("input_pdf", help="입력 PDF 파일 경로")
    parser.add_argument("--output", "-o", default=None, help="출력 PDF 경로")
    parser.add_argument("--dpi", type=int, default=300, help="추출 DPI (기본값: 300)")
    parser.add_argument("--workers", "-w", type=int, default=None, help="병렬 워커 수 (기본값: 자동)")
    parser.add_argument("--gpu", type=int, default=0, help="GPU ID (기본값: 0, CPU: -1)")

    args = parser.parse_args()

    sys_info = get_system_info()
    print("\n" + "=" * 50)
    print("  PDF Image Upscaler  (2x, Real-ESRGAN)")
    print("=" * 50)
    print(f"  시스템 : CPU {sys_info['cpu_count']}코어 | RAM {sys_info['total_ram_gb']}GB "
          f"(가용 {sys_info['available_ram_gb']}GB)")
    print(f"  입력   : {os.path.basename(args.input_pdf)}")
    print(f"  모델   : {MODEL_NAME} (2x)")
    print("-" * 50)

    pbar = None

    def cli_progress(completed, total):
        nonlocal pbar
        if pbar is None:
            pbar = tqdm(total=total, unit="장", desc="  업스케일", ncols=60)
        pbar.update(1)

    try:
        result = process_pdf(
            args.input_pdf,
            output_pdf_path=args.output,
            dpi=args.dpi,
            workers=args.workers,
            progress_callback=cli_progress,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"\n[오류] {e}")
        sys.exit(1)

    if pbar:
        pbar.close()

    print("-" * 50)
    print(f"  완료! ({result['elapsed']}초, 워커 {result['workers']}개)")
    print(f"  출력 : {result['output_path']}")
    print(f"  크기 : {result['size_mb']} MB")
    if result["failed"]:
        print(f"  경고 : {result['failed']}장 실패 (원본으로 대체)")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
