# -*- coding: utf-8 -*-
"""公共工具：路径、ffmpeg 定位、输入发现。"""
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT = os.path.join(ROOT, "input")
OUTPUT = os.path.join(ROOT, "output")
os.makedirs(OUTPUT, exist_ok=True)

PY = os.environ.get("MV_PY", r"C:\Python311\python.exe")


def ffmpeg():
    """优先环境变量 → PATH → 同级 music-mv 仓库里自包含的 ffmpeg.exe。"""
    p = os.environ.get("FFMPEG")
    if p and os.path.exists(p):
        return p
    p = shutil.which("ffmpeg")
    if p:
        return p
    p = os.path.join(os.path.dirname(ROOT), "music-mv", "tools", "ffmpeg.exe")
    if os.path.exists(p):
        return p
    raise RuntimeError(
        "找不到 ffmpeg。设置环境变量 FFMPEG 指向 ffmpeg.exe，"
        "或把 ffmpeg 放进 PATH。")


def ffprobe_duration(path):
    """本机没有 ffprobe，用 ffmpeg -i 的 stderr 抓 Duration。"""
    r = subprocess.run([ffmpeg(), "-i", path], capture_output=True, text=True,
                       errors="replace")
    for line in r.stderr.splitlines():
        if "Duration:" in line:
            return line.strip()
    return "(unknown duration)"


def input_video():
    vids = [f for f in sorted(os.listdir(INPUT))
            if f.lower().endswith((".mp4", ".mov", ".mkv"))]
    if not vids:
        raise RuntimeError("input/ 里没有视频。把剪好的 mp4 放进去再运行。")
    return os.path.join(INPUT, vids[0])


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)
