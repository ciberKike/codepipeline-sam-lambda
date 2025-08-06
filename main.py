"""Simple CLI for local tests: process all videos in a folder."""

from __future__ import annotations
import argparse
import os
from processor import process_single_file, VIDEO_EXTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("work_folder", help="Folder with input videos")
    parser.add_argument("height", type=int)
    parser.add_argument("prod_format", choices=["50", "60"])
    args = parser.parse_args()

    output = os.path.join(args.work_folder, "transcoded_files")
    os.makedirs(output, exist_ok=True)

    for f in os.listdir(args.work_folder):
        if f.lower().endswith(VIDEO_EXTS):
            process_single_file(
                os.path.join(args.work_folder, f), args.height, args.prod_format, output
            )


if __name__ == "__main__":
    main()
