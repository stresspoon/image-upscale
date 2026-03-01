#!/usr/bin/env python3
"""
PDF Image Upscaler - Gradio 웹 UI

브라우저에서 PDF를 드래그&드롭으로 업로드하면
AI(Real-ESRGAN)로 2배 업스케일된 PDF를 다운로드할 수 있습니다.
"""

import os
import tempfile
import gradio as gr
from upscale_pdf import process_pdf, get_system_info, MAX_PAGES


MAX_FILE_SIZE_MB = 100  # 최대 업로드 파일 크기


def upscale_handler(pdf_file, progress=gr.Progress()):
    """Gradio에서 호출되는 업스케일 핸들러."""
    if pdf_file is None:
        raise gr.Error("PDF 파일을 업로드해주세요.")

    input_path = pdf_file.name if hasattr(pdf_file, "name") else str(pdf_file)

    if not input_path.lower().endswith(".pdf"):
        raise gr.Error("PDF 파일만 업로드할 수 있습니다.")

    # 파일 크기 제한
    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise gr.Error(f"파일 크기가 {file_size_mb:.1f}MB입니다. 최대 {MAX_FILE_SIZE_MB}MB까지 지원합니다.")

    # PDF 매직바이트 검증
    with open(input_path, "rb") as f:
        magic = f.read(5)
    if magic != b"%PDF-":
        raise gr.Error("유효한 PDF 파일이 아닙니다.")

    output_dir = tempfile.mkdtemp(prefix="upscale_result_")
    basename = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(output_dir, f"{basename}_upscaled_2x.pdf")

    progress(0, desc="PDF 분석 중...")

    def gradio_progress(completed, total):
        progress(completed / total, desc=f"업스케일 중... ({completed}/{total}장)")

    try:
        result = process_pdf(
            input_path,
            output_pdf_path=output_path,
            dpi=300,
            progress_callback=gradio_progress,
        )
    except ValueError as e:
        raise gr.Error(str(e))
    except FileNotFoundError as e:
        raise gr.Error(str(e))

    status = (
        f"완료! {result['pages']}장, {result['elapsed']}초 소요\n"
        f"파일 크기: {result['size_mb']} MB | 워커: {result['workers']}개"
    )
    if result["failed"]:
        status += f"\n({result['failed']}장 실패 - 원본으로 대체됨)"

    return output_path, status


def build_ui():
    """Gradio 인터페이스를 구성합니다."""
    sys_info = get_system_info()
    sys_desc = f"CPU {sys_info['cpu_count']}코어 | RAM {sys_info['total_ram_gb']}GB"

    with gr.Blocks(
        title="PDF Image Upscaler",
        theme=gr.themes.Soft(),
        css="""
        .main-title { text-align: center; margin-bottom: 0.5em; }
        .sub-desc { text-align: center; color: #666; font-size: 0.9em; margin-bottom: 1.5em; }
        """,
    ) as app:
        gr.HTML("<h1 class='main-title'>PDF Image Upscaler</h1>")
        gr.HTML(
            f"<p class='sub-desc'>"
            f"이미지 PDF를 AI(Real-ESRGAN)로 2배 업스케일합니다. "
            f"최대 {MAX_PAGES}장 | {sys_desc}"
            f"</p>"
        )

        with gr.Row():
            with gr.Column(scale=1):
                pdf_input = gr.File(
                    label="PDF 업로드 (드래그 & 드롭)",
                    file_types=[".pdf"],
                    type="filepath",
                )
                upscale_btn = gr.Button("2x 업스케일 시작", variant="primary", size="lg")

            with gr.Column(scale=1):
                pdf_output = gr.File(label="업스케일된 PDF 다운로드")
                status_text = gr.Textbox(label="결과", interactive=False, lines=3)

        upscale_btn.click(
            fn=upscale_handler,
            inputs=[pdf_input],
            outputs=[pdf_output, status_text],
        )

        gr.HTML(
            "<p style='text-align:center; color:#999; font-size:0.8em; margin-top:2em;'>"
            "Real-ESRGAN (realesr-animevideov3-x2) | 로컬 GPU 가속 | "
            "모든 처리는 이 컴퓨터에서 수행됩니다"
            "</p>"
        )

    return app


if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        inbrowser=True,
    )
