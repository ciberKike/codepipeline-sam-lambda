"""Small helpers around ffprobe/ffmpeg with clear error handling."""

from __future__ import annotations
import subprocess
from dataclasses import dataclass


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe command fails."""

    pass


def _run(cmd: list[str]) -> str:
    """Run a subprocess command and return stdout or raise FFmpegError."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"Command failed: {' '.join(cmd)}\n{e.stderr}") from e


def get_fps(path: str) -> float | None:
    """Return rounded FPS from a video or None if it cannot be determined."""
    out = _run(
        [
            "ffprobe",
            "-v",
            "0",
            "-of",
            "csv=p=0",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate",
            path,
        ]
    )
    if not out:
        return None
    if "/" in out:
        n, d = out.split("/")
        return round(float(n) / float(d))
    return round(float(out))


def get_resolution(path: str) -> str | None:
    """Return "<width>x<height>" or None."""
    out = _run(
        [
            "ffprobe",
            "-v",
            "0",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            path,
        ]
    )
    return out if "x" in out else None


def get_height(path: str) -> int | None:
    """Return video height as int or None."""
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ]
    )
    try:
        return int(out)
    except (TypeError, ValueError):
        return None


@dataclass
class TranscodeParams:
    target_height: int
    set_fps: int | None


def build_ffmpeg_cmd(src: str, dst: str, params: TranscodeParams) -> list[str]:
    """Build the ffmpeg command according to params."""
    cmd = ["ffmpeg", "-i", src, "-vf", f"scale=-2:{params.target_height}"]
    if params.set_fps is not None:
        cmd += ["-r", str(params.set_fps)]
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-y",
        dst,
    ]
    return cmd


# def run_ffmpeg(cmd: list[str]) -> None:
#     """Execute ffmpeg and raise FFmpegError on failure."""
#     try:
#         subprocess.run(cmd, check=True)
#     except subprocess.CalledProcessError as e:
#         raise FFmpegError(f"ffmpeg failed: {' '.join(cmd)}\n{e.stderr}") from e

def run_ffmpeg(cmd: list[str]) -> None:
    """Execute ffmpeg and raise FFmpegError on failure, logging stderr for debugging."""
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        # Limit stderr length to avoid gigantic logs
        truncated_err = (proc.stderr or "")[:4000]
        raise FFmpegError(f"ffmpeg failed (rc={proc.returncode}): {' '.join(cmd)} STDERR: {truncated_err}")