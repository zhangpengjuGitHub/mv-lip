# -*- coding: utf-8 -*-
"""Kaggle 侧：生成 MuseTalk 推理 YAML 并跑 v1.5。

用法：
  python3 kaggle/run_lipsync.py \
      --video output/cut_25fps.mp4 \
      --audio output/vocal_dry.wav \
      --bbox_shift 0

产出 output/lipsynced.mp4
"""
import argparse
import os
import shutil
import subprocess

MT = "/kaggle/working/musetalk"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--bbox_shift", type=int, default=0,
                    help="嘴巴张开度：正值增大、负值减小。唱歌长音建议 3~7")
    ap.add_argument("--version", default="v15", choices=["v15", "v1"])
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "lipsynced.mp4"))
    a = ap.parse_args()

    for p in (a.video, a.audio):
        if not os.path.exists(p):
            raise SystemExit("找不到输入: " + p)

    cfg = os.path.join(MT, "configs", "inference", "mv_lip.yaml")
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    with open(cfg, "w", encoding="utf-8") as f:
        f.write("task_0:\n")
        f.write('  video_path: "%s"\n' % os.path.abspath(a.video))
        f.write('  audio_path: "%s"\n' % os.path.abspath(a.audio))
    print("配置:", cfg)
    print(open(cfg, encoding="utf-8").read())

    resdir = os.path.join(MT, "results", "mv_lip")
    if a.version == "v15":
        model = os.path.join(MT, "models", "musetalkV15", "unet.pth")
        mcfg = os.path.join(MT, "models", "musetalkV15", "musetalk.json")
    else:
        model = os.path.join(MT, "models", "musetalk", "pytorch_model.bin")
        mcfg = os.path.join(MT, "models", "musetalk", "musetalk.json")
    for p in (model, mcfg):
        if not os.path.exists(p):
            raise SystemExit("缺权重: %s\n先跑 bash kaggle/setup_musetalk.sh" % p)

    cmd = ["python3", "-m", "scripts.inference",
           "--inference_config", cfg,
           "--result_dir", resdir,
           "--unet_model_path", model,
           "--unet_config", mcfg,
           "--version", a.version,
           "--bbox_shift", str(a.bbox_shift)]
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=MT, check=True)

    # 找出结果 mp4（脚本一般落在 resdir 下）
    found = []
    for dp, _, fns in os.walk(resdir):
        for fn in fns:
            if fn.lower().endswith(".mp4"):
                found.append(os.path.join(dp, fn))
    if not found:
        raise SystemExit("推理跑完但没找到 mp4，检查 " + resdir)
    found.sort(key=os.path.getmtime, reverse=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    shutil.copy2(found[0], a.out)
    print("产出:", a.out, os.path.getsize(a.out), "bytes")


if __name__ == "__main__":
    main()
