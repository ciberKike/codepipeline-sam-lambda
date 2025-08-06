"""Pure logic to decide between transcoding vs copying and to organize outputs."""

import logging
import os
import shutil
from typing import Optional, List

from ffutils import (
    get_fps,
    get_height,
    get_resolution,
    TranscodeParams,
    build_ffmpeg_cmd,
    run_ffmpeg,
)

VIDEO_EXTS = (".mp4", ".mov", ".mpeg", ".avi")

logger = logging.getLogger("transcoder-worker")
logger.setLevel(logging.INFO)

def decide_fps(production_format: str, fps: Optional[float]) -> Optional[int]:
    """Return target fps (25/30) or None if it should not change."""
    if production_format == "50":
        return 25 if fps != 25 else None
    if production_format == "60":
        return 30 if fps != 30 else None
    return None


def process_single_file(
    input_file: str, target_height: int, prod_format: str, output_root: str
) -> str:
    """Process a single file.
    Returns a list of resulting paths (copy or transcoded). It may be empty if nothing was needed.
    """
    base = os.path.basename(input_file)
    name, _ = os.path.splitext(base)

    fps = get_fps(input_file)
    current_height = get_height(input_file)
    set_fps = decide_fps(prod_format, fps)

    logger.debug(f"Current height: {current_height}")
    logger.debug(f"Target height: {target_height}")
    logger.debug(f"FPS: {fps}")
    logger.debug(f"Target FPS: {set_fps}")

    same_height = current_height == target_height
    same_fps = (set_fps is None) or (fps == set_fps)

    if same_height and same_fps:
        # Just copy, no transcode
        resolution = get_resolution(input_file) or "unknown"
        dest_dir = os.path.join(output_root, resolution)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, f"{name}_{resolution}.mp4")
        shutil.copy2(input_file, dest)
        return dest

    # Transcode path
    tmp_out = os.path.join(output_root, f"{name}_TMP.mp4")
    params = TranscodeParams(target_height, set_fps)
    cmd = build_ffmpeg_cmd(input_file, tmp_out, params)

    logger.debug(f"Tmp out: {tmp_out}")
    logger.debug(f"CMD: {cmd}")

    run_ffmpeg(cmd)

    resolution = get_resolution(tmp_out) or "unknown"
    dest_dir = os.path.join(output_root, resolution)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{name}_{resolution}.mp4")
    os.replace(tmp_out, dest)
    return dest
