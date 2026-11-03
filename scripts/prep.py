# -*- coding: utf-8 -*-
"""本机准备（CPU 即可）：抽音轨 -> Demucs 分离干声 -> 视频统一 25fps。

用法：python scripts/prep.py
产出：output/mix.wav（原始完整混音，最终要叠回去）
      output/vocal_dry.wav（只作驱动信号）
      output/cut_25fps.mp4（给 MuseTalk 的画面）
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUTPUT, PY, ffmpeg, ffprobe_duration, input_video, run

MIX = os.path.join(OUTPUT, "mix.wav")
DRY = os.path.join(OUTPUT, "vocal_dry.wav")
VID25 = os.path.join(OUTPUT, "cut_25fps.mp4")
DEMUC_DIR = os.path.join(OUTPUT, "demucs")


def main():
    src = input_video()
    print("输入视频:", src)
    print(ffprobe_duration(src))

    # 1) 抽音轨：PCM 16bit 44.1k 单声道？不要改声道，保留原样，MuseTalk 自己会处理
    run([ffmpeg(), "-y", "-i", src, "-vn", "-acodec", "pcm_s16le",
         "-ar", "44100", MIX])
    print("[1/3] 原混音 ->", MIX)

    # 2) Demucs 分离干声（本机 C:\\Python311 已装 demucs 4.1.0，CPU 跑得动）
    os.makedirs(DEMUC_DIR, exist_ok=True)
    run([PY, "-m", "demucs", "--two-stems", "vocals", "-d", "cpu",
         "-n", "htdemucs", "-o", DEMUC_DIR, MIX])
    cand = os.path.join(DEMUC_DIR, "htdemucs", "mix", "vocals.wav")
    if not os.path.exists(cand):
        base = os.path.splitext(os.path.basename(MIX))[0]
        cand = os.path.join(DEMUC_DIR, "htdemucs", base, "vocals.wav")
    if not os.path.exists(cand):
        raise RuntimeError("demucs 没找到 vocals.wav，检查 " + DEMUC_DIR)
    shutil.copy2(cand, DRY)
    print("[2/3] 干声 ->", DRY, os.path.getsize(DRY), "bytes")

    # 3) 画面统一 25fps（不改时长、不碰音轨，音轨用上面的 mix.wav）
    run([ffmpeg(), "-y", "-i", src, "-an", "-vf", "fps=25",
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", VID25])
    print("[3/3] 25fps 画面 ->", VID25)

    print("\n准备完成。接下来把这两个文件传到 Kaggle：")
    print("  ", VID25)
    print("  ", DRY)
    print("（mix.wav 留在本机，最后合成要用，不要拿干声当音轨）")


if __name__ == "__main__":
    main()
