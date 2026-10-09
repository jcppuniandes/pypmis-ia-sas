from __future__ import annotations

import argparse
import importlib.util
import subprocess
import uuid
from pathlib import Path, PureWindowsPath

import pypdfium2 as pdfium


SKILL_RENDERER = Path(
    r"C:\Users\Ricardo\.codex\plugins\cache\openai-primary-runtime\documents\26.826.12353\skills\documents\render_docx.py"
)
IMAGE = "lscr.io/linuxserver/libreoffice:latest"


def load_renderer():
    spec = importlib.util.spec_from_file_location("canonical_render_docx", SKILL_RENDERER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load canonical renderer: {SKILL_RENDERER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def docker_path(path: str) -> str:
    value = PureWindowsPath(Path(path).resolve())
    if value.drive.upper() != "C:":
        raise RuntimeError(f"Docker renderer only maps drive C:; got {value.drive}")
    return "/hostc/" + "/".join(value.parts[1:])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--dpi", type=int, default=160)
    parser.add_argument("--emit_pdf", action="store_true")
    args = parser.parse_args()

    renderer = load_renderer()

    def convert_to_pdf(doc_path, user_profile, convert_tmp_dir, stem, verbose=False):
        del user_profile, verbose
        host_out = Path(convert_tmp_dir).resolve()
        host_out.mkdir(parents=True, exist_ok=True)
        profile = f"file:///tmp/lo-profile-{uuid.uuid4().hex}"
        command = [
            "docker",
            "run",
            "--rm",
            "-v",
            r"C:\:/hostc",
            "--entrypoint",
            "soffice",
            IMAGE,
            f"-env:UserInstallation={profile}",
            "--invisible",
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            docker_path(str(host_out)),
            docker_path(doc_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        log = "\n".join(
            [
                "CMD: " + " ".join(command),
                f"EXIT: {completed.returncode}",
                completed.stdout.strip(),
                completed.stderr.strip(),
            ]
        )
        pdf_path = host_out / f"{stem}.pdf"
        return (str(pdf_path) if pdf_path.exists() else "", log)

    renderer.convert_to_pdf = convert_to_pdf

    def convert_from_path(
        pdf_path,
        *,
        dpi,
        fmt,
        thread_count,
        output_folder,
        paths_only,
        output_file,
    ):
        del fmt, thread_count, paths_only
        document = pdfium.PdfDocument(pdf_path)
        rendered = []
        scale = dpi / 72.0
        for index in range(len(document)):
            page = document[index]
            bitmap = page.render(scale=scale)
            target = Path(output_folder) / f"{output_file}-{index + 1:02d}.png"
            bitmap.to_pil().save(target, format="PNG")
            rendered.append(str(target))
            bitmap.close()
            page.close()
        document.close()
        return rendered

    renderer.convert_from_path = convert_from_path
    pages = renderer.rasterize(
        str(Path(args.input).resolve()),
        str(Path(args.output_dir).resolve()),
        args.dpi,
        verbose=False,
        emit_pdf=args.emit_pdf,
    )
    print(f"Rendered {len(pages)} page(s)")


if __name__ == "__main__":
    main()
