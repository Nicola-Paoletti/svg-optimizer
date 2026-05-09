#!/usr/bin/env python3
"""
SVG Optimizer — Automatic watcher
Drop a .svg file into this folder and it will be optimized automatically.
The original file is kept intact; a new <name>_optimized.svg is created.
AUTHOR: NICOLA PAOLETTI.
I LOVE SVG AND I LOVE OPTIMIZATION.
DONT TOUCH THIS FILE.
ITALIAN DO IT BETTER
"""

import re
import base64
import time
import logging
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image

# Path to oxipng binary (installed via Homebrew)
OXIPNG = shutil.which("oxipng")

# ── Configuration ───────────────────────────────────────────────
SCALE        = 2     # 1 = standard, 2 = retina (sharper images on HiDPI screens)
QUALITY_JPEG = 85    # JPEG quality 0-100 (opaque images)
QUALITY_WEBP = 85    # WebP quality 0-100 (transparent images — web mode only)

# "web" → WebP for transparency (smaller, modern browsers)
# "pdf" → PNG for transparency (larger, required by Apache Batik / PDF export)
TARGET = "pdf"
# ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

WATCH_DIR = Path(__file__).parent


def parse_svg_dimensions(content):
    m = re.search(
        r'<svg[^>]+?width=["\']([0-9.]+)["\'][^>]+?height=["\']([0-9.]+)["\']', content
    )
    if not m:
        m = re.search(
            r'<svg[^>]+?height=["\']([0-9.]+)["\'][^>]+?width=["\']([0-9.]+)["\']', content
        )
        if m:
            return float(m.group(2)), float(m.group(1))
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def optimize_image(img_bytes, target_w, target_h):
    img = Image.open(BytesIO(img_bytes))
    orig_w, orig_h = img.size
    has_alpha = img.mode in ("RGBA", "LA", "PA")

    # Resize only if the image is larger than the target
    new_w, new_h = orig_w, orig_h
    if target_w and target_h:
        ratio = min(target_w / orig_w, target_h / orig_h)
        if ratio < 1.0:
            new_w = max(1, int(orig_w * ratio))
            new_h = max(1, int(orig_h * ratio))
            img = img.resize((new_w, new_h), Image.LANCZOS)

    # Check if alpha channel is actually used (real transparency)
    real_alpha = False
    if has_alpha:
        real_alpha = img.getchannel("A").getextrema()[0] < 255

    buf = BytesIO()
    if real_alpha:
        if TARGET == "web":
            # WebP: far smaller than PNG, supported by all modern browsers
            img.save(buf, format="WEBP", quality=QUALITY_WEBP, method=6)
            out_fmt = "webp"
        else:
            # PNG: required for Apache Batik / PDF export pipelines
            img.save(buf, format="PNG", optimize=True, compress_level=9)
            png_bytes = buf.getvalue()
            # Run oxipng for extra lossless compression if available
            if OXIPNG:
                try:
                    result = subprocess.run(
                        [OXIPNG, "-o", "4", "--strip", "all", "--quiet", "--stdout", "-"],
                        input=png_bytes,
                        capture_output=True,
                    )
                    if result.returncode == 0 and len(result.stdout) < len(png_bytes):
                        png_bytes = result.stdout
                except Exception:
                    pass  # oxipng failed silently, keep Pillow output
            return png_bytes, "png", orig_w, orig_h, new_w, new_h
    else:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=QUALITY_JPEG, optimize=True, progressive=True)
        out_fmt = "jpeg"

    return buf.getvalue(), out_fmt, orig_w, orig_h, new_w, new_h


def process_svg(svg_path: Path):
    out_path = svg_path.parent / f"{svg_path.stem}_optimized{svg_path.suffix}"

    original_size = svg_path.stat().st_size
    log.info(f"▶  {svg_path.name}  ({original_size / 1024:.0f} KB)")

    try:
        content = svg_path.read_text(encoding="utf-8")
    except Exception as e:
        log.error(f"   Failed to read file: {e}")
        return

    svg_w, svg_h = parse_svg_dimensions(content)
    if svg_w:
        target_w, target_h = svg_w * SCALE, svg_h * SCALE
        log.info(f"   Canvas {svg_w:.0f}×{svg_h:.0f} → target {target_w:.0f}×{target_h:.0f} (scale={SCALE}x)")
    else:
        target_w = target_h = None
        log.warning("   SVG dimensions not found, resize disabled.")

    pattern = re.compile(
        r'(data:image/(?:png|jpeg|jpg|gif|webp);base64,)([A-Za-z0-9+/]+=*)',
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(content))

    if not matches:
        log.info("   No embedded images found — file copied unchanged.")
        out_path.write_text(content, encoding="utf-8")
        return

    parts = []
    prev_end = 0

    for i, m in enumerate(matches):
        img_bytes = base64.b64decode(m.group(2))
        orig_kb = len(img_bytes) / 1024

        new_bytes, new_fmt, ow, oh, nw, nh = optimize_image(img_bytes, target_w, target_h)
        new_kb = len(new_bytes) / 1024
        savings = (1 - new_kb / orig_kb) * 100

        resize = f"{ow}×{oh} → {nw}×{nh}" if (nw != ow or nh != oh) else f"{ow}×{oh}"
        log.info(f"   Img {i+1}: {resize}  |  {orig_kb:.0f} KB → {new_kb:.0f} KB  (-{savings:.0f}%)  [{new_fmt.upper()}]")

        parts.append(content[prev_end : m.start()])
        parts.append(f"data:image/{new_fmt};base64," + base64.b64encode(new_bytes).decode())
        prev_end = m.end()

    parts.append(content[prev_end:])
    out_path.write_text("".join(parts), encoding="utf-8")

    new_size = out_path.stat().st_size
    total_savings = (1 - new_size / original_size) * 100
    log.info(f"   ✓  {original_size/1024:.0f} KB → {new_size/1024:.0f} KB  (-{total_savings:.0f}%)  →  {out_path.name}\n")


class SVGHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".svg":
            return
        if path.stem.endswith("_optimized"):
            return
        # Short pause to ensure the file has been fully written to disk
        time.sleep(0.5)
        process_svg(path)

    def on_moved(self, event):
        # Handles drag-and-drop, which on macOS triggers a move event internally
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if path.suffix.lower() != ".svg":
            return
        if path.stem.endswith("_optimized"):
            return
        time.sleep(0.5)
        process_svg(path)


def main():
    mode_label = "PDF/Batik (PNG)" if TARGET == "pdf" else "Web (WebP)"
    oxipng_label = f"oxipng {subprocess.run([OXIPNG, '--version'], capture_output=True, text=True).stdout.strip()}" if OXIPNG else "oxipng not found (install via Homebrew)"
    log.info("══════════════════════════════════════")
    log.info(" SVG Optimizer — watching for files...")
    log.info(f" Folder: {WATCH_DIR}")
    log.info(f" Mode: {mode_label}  |  Scale: {SCALE}x  |  JPEG quality: {QUALITY_JPEG}")
    log.info(f" PNG optimizer: {oxipng_label}")
    log.info(" Drop a .svg file here to optimize it.")
    log.info(" Ctrl+C to quit.")
    log.info("══════════════════════════════════════\n")

    observer = Observer()
    observer.schedule(SVGHandler(), str(WATCH_DIR), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        log.info("Stopped.")
    observer.join()


if __name__ == "__main__":
    main()
