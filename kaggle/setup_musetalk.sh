#!/usr/bin/env bash
# Kaggle 上部署 MuseTalk 1.5（uv 独立 Python 3.10 环境，不碰系统 Python 3.13 / ComfyUI）
# 用法： bash kaggle/setup_musetalk.sh > /kaggle/working/mt_setup.log 2>&1
# 幂等：末尾打印 SETUP_MUSETALK_DONE 表示成功
set -e
cd /kaggle/working

if [ -f /kaggle/working/musetalk/SETUP_MUSETALK_DONE ]; then
  echo "already installed"; exit 0
fi

echo "=== 0/5 环境 ==="
python3 -V
uv --version
df -h /kaggle/working | tail -1
[ -d musetalk ] || git clone -q https://github.com/TMElyralab/MuseTalk.git musetalk

echo "=== 1/5 建 Python 3.10 venv ==="
# Kaggle 默认 Python 3.13 / torch 2.11 / CUDA 12.8；MuseTalk 官方要求 3.10 + torch 2.0.1 + cu118。
# MMLab(mmcv/mmdet/mmpose) 在 3.13 上没有 wheel，必须用独立 3.10 环境。
if [ ! -x /kaggle/working/mtenv/bin/python ]; then
  uv venv --python 3.10 /kaggle/working/mtenv
else
  echo "mtenv already exists, skip"
fi
PY=/kaggle/working/mtenv/bin/python
$PY -V

echo "=== 2/5 torch cu118 ==="
uv pip install --python $PY \
  "torch==2.0.1+cu118" "torchvision==0.15.2+cu118" "torchaudio==2.0.2+cu118" \
  --index-url https://download.pytorch.org/whl/cu118
$PY -c "import torch;print('torch',torch.__version__,'cuda',torch.version.cuda,torch.cuda.is_available())"

echo "=== 3/5 精简依赖（去掉推理不需要的 tensorflow / tensorboard / gradio）==="
uv pip install --python $PY \
  "numpy<2" "opencv-python==4.9.0.80" "soundfile==0.12.1" \
  "transformers==4.39.2" "diffusers==0.30.2" "accelerate==0.28.0" \
  "huggingface_hub==0.30.2" "librosa==0.11.0" "einops==0.8.1" \
  "imageio[ffmpeg]" "omegaconf" "ffmpeg-python" "moviepy" "gdown" "requests"

echo "=== 4/5 MMLab ==="
# uv venv 默认不带 setuptools，而 mim 依赖 pkg_resources，不补会报
# ModuleNotFoundError: No module named 'pkg_resources'
# Python 3.10 下 mmengine/yapf 会 fallback 到 toml；numpy 必须 <2，
# 否则 mmcv/cv2 的 1.x ABI wheel 会报 numpy.core.multiarray failed to import
uv pip install --python $PY "setuptools<81" wheel "numpy==1.26.4" toml "yapf==0.40.2"
# chumpy(mmpose 老依赖) 的 PEP 517 隔离构建会因缺 numpy 失败，
# 必须 --no-build-isolation 用当前环境先装好，mim install 才会跳过它
uv pip install --python $PY chumpy --no-build-isolation
uv pip install --python $PY -U openmim
MIM=/kaggle/working/mtenv/bin/mim
$MIM install mmengine
$MIM install "mmcv==2.0.1"
$MIM install "mmdet==3.1.0"
$MIM install "mmpose>=1.1.0"

echo "=== 5/5 权重 ==="
# 官方 download_weights.sh 用 hf-mirror.com + gdown(Google Drive)，
# Kaggle 海外网络实测只下到 2 个文件，改走官方 HF 逐文件下载
$PY /kaggle/working/mv-lip/kaggle/dl_weights.py
find models -maxdepth 2 -type f | head -20

echo "=== verify ==="
$PY -c "import torch,cv2,diffusers,transformers,mmcv,mmpose;print('OK torch',torch.__version__,'mmcv',mmcv.__version__)"
touch /kaggle/working/musetalk/SETUP_MUSETALK_DONE
echo SETUP_MUSETALK_DONE
