# -*- coding: utf-8 -*-
"""MuseTalk 1.5 权重下载（走官方 huggingface.co，逐文件可重跑）。

官方 download_weights.sh 用 hf-mirror.com + gdown(Google Drive)，
在 Kaggle 海外网络下实测只下到 2 个文件 96M，故改用 huggingface_hub API。

用法： /kaggle/working/mtenv/bin/python kaggle/dl_weights.py
"""
import os
import subprocess
import sys
import traceback
from huggingface_hub import hf_hub_download

M = "/kaggle/working/musetalk/models"

# (HF repo, 仓库内文件名, 落地子目录)
TASKS = [
    ("TMElyralab/MuseTalk", "musetalkV15/unet.pth", ""),
    ("TMElyralab/MuseTalk", "musetalkV15/musetalk.json", ""),
    ("TMElyralab/MuseTalk", "musetalk/musetalk.json", ""),
    ("TMElyralab/MuseTalk", "musetalk/pytorch_model.bin", ""),
    ("stabilityai/sd-vae-ft-mse", "config.json", "sd-vae"),
    ("stabilityai/sd-vae-ft-mse", "diffusion_pytorch_model.bin", "sd-vae"),
    ("openai/whisper-tiny", "config.json", "whisper"),
    ("openai/whisper-tiny", "pytorch_model.bin", "whisper"),
    ("openai/whisper-tiny", "preprocessor_config.json", "whisper"),
    ("yzd-v/DWPose", "dw-ll_ucoco_384.pth", "dwpose"),
    ("ByteDance/LatentSync", "latentsync_syncnet.pt", "syncnet"),
]


def main():
    for repo, fn, sub in TASKS:
        d = os.path.join(M, sub) if sub else M
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, os.path.basename(fn))
        # HF 仓库里带子目录的文件，落地时按官方目录结构摊平
        if sub == "":
            dest = os.path.join(M, fn)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest) and os.path.getsize(dest) > 1024:
            print("SKIP", dest, os.path.getsize(dest), flush=True)
            continue
        try:
            hf_hub_download(repo_id=repo, filename=fn,
                            local_dir=M if sub == "" else d,
                            local_dir_use_symlinks=False)
            print("OK  ", dest, flush=True)
        except Exception as e:
            print("FAIL", repo, fn, repr(e)[:160], flush=True)

    # face-parse-bisent：官方只在 Google Drive，Kaggle 上 gdown 实测不通
    # （会静默缺 79999_iter.pth，推理时报 FileNotFoundError）。
    # 改走 HF 镜像 ManyOtherFunctions/face-parse-bisent，逐文件可重跑。
    fp = os.path.join(M, "face-parse-bisent")
    os.makedirs(fp, exist_ok=True)
    a = os.path.join(fp, "79999_iter.pth")
    b = os.path.join(fp, "resnet18-5c106cde.pth")
    if not os.path.exists(a) or os.path.getsize(a) < 1024:
        try:
            hf_hub_download(repo_id="ManyOtherFunctions/face-parse-bisent",
                            filename="79999_iter.pth", local_dir=fp,
                            local_dir_use_symlinks=False)
            print("OK  ", a, flush=True)
        except Exception as e:
            print("FAIL face-parse 79999_iter.pth", repr(e)[:160], flush=True)
    if not os.path.exists(b):
        url = "https://download.pytorch.org/models/resnet18-5c106cde.pth"
        try:
            import urllib.request
            urllib.request.urlretrieve(url, b)
            print("OK  ", b, flush=True)
        except Exception as e:
            print("FAIL resnet18", repr(e)[:120], flush=True)

    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fns in os.walk(M) for f in fns)
    print("TOTAL_BYTES", total, "files",
          sum(len(fns) for _, _, fns in os.walk(M)), flush=True)


if __name__ == "__main__":
    main()
