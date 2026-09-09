#!/usr/bin/env bash
# worker-comfyui 5.10.0 start.sh + COMFY_ARGS 주입 (원본: runpod-workers/worker-comfyui src/start.sh)

if [ -n "$PUBLIC_KEY" ]; then
    mkdir -p ~/.ssh
    echo "$PUBLIC_KEY" > ~/.ssh/authorized_keys
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/authorized_keys
    for key_type in rsa ecdsa ed25519; do
        key_file="/etc/ssh/ssh_host_${key_type}_key"
        [ -f "$key_file" ] || ssh-keygen -t "$key_type" -f "$key_file" -q -N ''
    done
    service ssh start && echo "worker-comfyui: SSH server started" || echo "worker-comfyui: SSH server could not be started" >&2
fi

TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

echo "worker-comfyui: Checking GPU availability..."
if ! GPU_CHECK=$(python3 -c "
import torch
try:
    torch.cuda.init()
    name = torch.cuda.get_device_name(0)
    cap = torch.cuda.get_device_capability(0)
    _ = (torch.zeros(8, device='cuda') + 1).sum().item()
    torch.cuda.synchronize()
    print(f'OK: {name} (sm_{cap[0]}{cap[1]}), torch {torch.__version__}, cuda {torch.version.cuda}')
except Exception as e:
    print(f'FAIL: {e}')
    exit(1)
" 2>&1); then
    echo "worker-comfyui: GPU is not available or incompatible with this PyTorch build:"
    echo "worker-comfyui: $GPU_CHECK"
    exit 1
fi
echo "worker-comfyui: GPU available — $GPU_CHECK"

comfy-manager-set-mode offline || echo "worker-comfyui - Could not set ComfyUI-Manager network_mode" >&2

: "${COMFY_LOG_LEVEL:=INFO}"
# 추가 기동 인자 (예: --use-sage-attention --fast fp8_matrix_mult --highvram)
: "${COMFY_ARGS:=}"

# 빌드 없이 소형 모델(LoRA 등) 추가: EXTRA_MODELS="url|models/loras/a.safetensors,url|models/loras/b.safetensors"
# 이미 존재하면 건너뜀. 실패해도 기동은 계속(해당 모델만 없음).
if [ -n "$EXTRA_MODELS" ]; then
    IFS=',' read -ra _EM <<< "$EXTRA_MODELS"
    for item in "${_EM[@]}"; do
        url="${item%%|*}"; rel="${item##*|}"; dst="/comfyui/${rel}"
        if [ -s "$dst" ]; then echo "worker-comfyui: EXTRA_MODELS exists $rel"; continue; fi
        mkdir -p "$(dirname "$dst")"
        echo "worker-comfyui: EXTRA_MODELS downloading $rel"
        if ! wget -q --tries=3 -O "$dst.part" "$url"; then echo "worker-comfyui: EXTRA_MODELS FAILED $rel" >&2; rm -f "$dst.part"; continue; fi
        mv "$dst.part" "$dst"
    done
fi
echo "worker-comfyui: Starting ComfyUI (extra args: ${COMFY_ARGS})"

COMFY_PID_FILE="/tmp/comfyui.pid"
# 핸들러 선택: 기본 /handler.py, S3 래퍼 이미지는 /s3_handler.py
: "${HANDLER_PATH:=/handler.py}"
echo "worker-comfyui: handler = ${HANDLER_PATH}"

if [ "$SERVE_API_LOCALLY" == "true" ]; then
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata --listen --verbose "${COMFY_LOG_LEVEL}" --log-stdout ${COMFY_ARGS} &
    echo $! > "$COMFY_PID_FILE"
    echo "worker-comfyui: Starting RunPod Handler"
    python -u ${HANDLER_PATH} --rp_serve_api --rp_api_host=0.0.0.0
else
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata --verbose "${COMFY_LOG_LEVEL}" --log-stdout ${COMFY_ARGS} &
    echo $! > "$COMFY_PID_FILE"
    echo "worker-comfyui: Starting RunPod Handler"
    python -u ${HANDLER_PATH}
fi
