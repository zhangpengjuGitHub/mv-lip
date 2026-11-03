# -*- coding: utf-8 -*-
"""本机合成：MuseTalk 输出 + 原完整混音 -> final.mp4，并抽帧生成质检拼图。

用法：python scripts/finish.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUTPUT, ffmpeg, ffprobe_duration, run

MIX = os.path.join(OUTPUT, "mix.wav")
LIP = os.path.join(OUTPUT, "lipsynced.mp4")
FINAL = os.path.join(OUTPUT, "final.mp4")
QC = os.path.join(OUTPUT, "qc_sheet.jpg")


def main():
    for p, why in [(MIX, "原始完整混音"), (LIP, "MuseTalk 输出的视频")]:
        if not os.path.exists(p):
            raise RuntimeError("缺少 %s：%s" % (p, why))

    # 口型有系统性偏移时，在这里用 -itsoffset 微调（秒），正值=音频延后
    offset = os.environ.get("MV_AUDIO_OFFSET", "0")
    cmd = [ffmpeg(), "-y", "-i", LIP]
    if float(offset) != 0:
        cmd += ["-itsoffset", offset]
    cmd += ["-i", MIX, "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", FINAL]
    run(cmd)
    print("[1/2] 成片 ->", FINAL)
    print(ffprobe_duration(FINAL))

    # 5 帧拼图：句首 / 前段 / 中段 / 后段 / 句尾
    vf = ("select='eq(n,5)+eq(n,90)+eq(n,200)+eq(n,320)+eq(n,420)',"
          "scale=384:216,tile=3x2")
    run([ffmpeg(), "-y", "-i", FINAL, "-vf", vf, "-frames:v", "1", QC])
    print("[2/2] 质检拼图 ->", QC)
    print("\n目检三件事：句首起音有没有张嘴、长音有没有保持、句尾有没有闭合。")
    print("间奏纯伴奏段如果嘴还在动 = 干声没分离干净，回第 1 步重做。")


if __name__ == "__main__":
    main()
