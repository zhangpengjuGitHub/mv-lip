#!/usr/bin/env bash
# Kaggle 上部署 MuseTalk 1.5（独立目录，不碰 ComfyUI）
# 用法： bash kaggle/setup_musetalk.sh
# 幂等：末尾打印 SETUP_MUSETALK_DONE 表示成功
set -e
cd /kaggle/working

echo "=== 磁盘检查 ==="
df -h /kaggle/working | tail -1

# ⚠️ 关键：Kaggle working 只有 19.5G，InfiniteTalk 模型占 16.9G。
# 成片下载到本机之后，才可以用下面这行释放空间（默认注释，需手动打开）。
# rm -rf /kaggle/working/ComfyUI/models /kaggle/working/ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper

if [ -f /kaggle/working/musetalk/SETUP_MUSETALK_DONE ]; then
  echo "already installed"
  exit 0
fi

echo "=== 1/4 clone ==="
[ -d musetalk ] || git clone -q https://github.com/TMElyralab/MuseTalk.git musetalk
cd /kaggle/working/musetalk

echo "=== 2/4 python deps ==="
pip install -q -r requirements.txt
pip install -q -U openmim
mim install -q mmengine
mim install -q "mmcv>=2.0.1"
mim install -q "mmdet>=3.1.0"
mim install -q "mmpose>=1.1.0"

echo "=== 3/4 ffmpeg ==="
python3 -c "import imageio_ffmpeg,os;print(imageio_ffmpeg.get_ffmpeg_exe())" > /kaggle/working/ffmpeg_path.txt 2>/dev/null || true
export FFMPEG_PATH=$(cat /kaggle/working/ffmpeg_path.txt 2>/dev/null || echo ffmpeg)
echo "FFMPEG_PATH=$FFMPEG_PATH"

echo "=== 4/4 weights ==="
if [ -f download_weights.sh ]; then
  sh download_weights.sh || echo "download_weights.sh failed, see README for manual download"
else
  pip install -q -U "huggingface_hub[cli]"
  huggingface-cli download TMElyralab/MuseTalk --local-dir models/
fi
find models -maxdepth 2 -type f | head -20

echo "=== verify ==="
python3 -c "import torch,cv2;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),'cv2',cv2.__version__)"
touch /kaggle/working/musetalk/SETUP_MUSETALK_DONE
echo SETUP_MUSETALK_DONE
