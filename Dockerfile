# worker-comfyui + SageAttention2++ (sm_89 Ada, sm_120 Blackwell) + fp8 native matmul
# 대상 GPU 풀: BLACKWELL_96 (RTX PRO 6000), ADA_48_PRO (L40S / RTX 6000 Ada)

ARG WORKER_VERSION=5.10.0
ARG TORCH_VERSION=2.11.0
ARG TORCHVISION_VERSION=0.26.0
ARG SAGE_REF=main

# ---------- Stage 1: SageAttention 휠 빌드 (nvcc 필요, GPU 불필요) ----------
FROM nvidia/cuda:12.8.1-devel-ubuntu24.04 AS sage-builder
ARG TORCH_VERSION
ARG TORCHVISION_VERSION
ARG SAGE_REF
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y python3.12 python3.12-venv python3.12-dev git ninja-build \
    && rm -rf /var/lib/apt/lists/*
RUN python3.12 -m venv /venv
ENV PATH=/venv/bin:$PATH
# worker-comfyui 5.10.0 base와 동일한 torch (cu128) — ABI 일치 필수
RUN pip install --no-cache-dir -U pip setuptools wheel packaging ninja \
    && pip install --no-cache-dir torch==${TORCH_VERSION} torchvision==${TORCHVISION_VERSION} \
       --index-url https://download.pytorch.org/whl/cu128
RUN git clone --depth 1 --branch ${SAGE_REF} https://github.com/thu-ml/SageAttention.git /src/SageAttention
# 8.9 = L40S / RTX 6000 Ada, 12.0 = RTX PRO 6000 Blackwell
ENV TORCH_CUDA_ARCH_LIST="8.9;12.0" EXT_PARALLEL=4 MAX_JOBS=4 NVCC_APPEND_FLAGS="--threads 4"
RUN cd /src/SageAttention && pip wheel . --no-build-isolation --no-deps -w /wheels

# ---------- Stage 2: 최종 이미지 ----------
FROM runpod/worker-comfyui:${WORKER_VERSION}-base
COPY --from=sage-builder /wheels/sageattention-*.whl /tmp/wheels/
RUN uv pip install /tmp/wheels/sageattention-*.whl && rm -rf /tmp/wheels
# import 스모크 테스트 (GPU 없이 모듈 로드만 확인)
RUN python -c "import sageattention, torch; print('sageattention', sageattention.__name__, 'torch', torch.__version__)"

# ComfyUI 기동 인자를 env(COMFY_ARGS)로 주입할 수 있는 start.sh
COPY start.sh /start.sh
RUN chmod +x /start.sh
ENV COMFY_ARGS="--use-sage-attention --fast fp8_matrix_mult --highvram"
CMD ["/start.sh"]
