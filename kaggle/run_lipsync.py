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
PY = os.environ.get("MV_PY", "/kaggle/working/mtenv/bin/python")


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

    cmd = [PY, "-m", "scripts.inference",
           "--inference_config", cfg,
           "--result_dir", resdir,
           "--unet_model_path", model,
           "--unet_config", mcfg,
           "--version", a.version,
           "--bbox_shift", str(a.bbox_shift)]
    print("+", " ".join(cmd), flush=True)
    # Kaggle/Jupyter 会注入 MPLBACKEND=module://matplotlib_inline.backend_inline，
    # MuseTalk 依赖的老版 matplotlib 不认这个值，会抛 ValueError: Key backend
    env = dict(os.environ)
    env["MPLBACKEND"] = "Agg"
    subprocess.run(cmd, cwd=MT, check=True, env=env)

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

    # MuseTalk 在 bbox 越界时会跳过写帧，%08d.png 断档会让 ffmpeg 提前停止，
    # 结果推理 exit=0 但 mp4 只剩开头几帧（实测 250 帧 -> 8 帧）。必须校验。
    def frame_count(p):
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-count_frames", "-show_entries", "stream=nb_read_frames",
             "-of", "csv=p=0", p], capture_output=True, text=True)
        try:
            return int(r.stdout.strip().split(",")[0])
        except Exception:
            return -1

    n_in, n_out = frame_count(a.video), frame_count(a.out)
    print("帧数校验:", n_in, "->", n_out)
    if n_in > 0 and n_out > 0 and n_out < n_in * 0.95:
        raise SystemExit(
            "输出帧数不足 %d/%d：检查 bbox 越界，先跑 kaggle/patch_musetalk.py"
            % (n_out, n_in))


if __name__ == "__main__":
    main()
