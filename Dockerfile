# worker-comfyui + SageAttention2++ (sm_89 Ada, sm_120 Blackwell) + fp8 native matmul
# 대상 GPU 풀: BLACKWELL_96 (RTX PRO 6000), ADA_48_PRO (L40S / RTX 6000 Ada)
#
# 빌더도 worker-comfyui base를 그대로 사용 → python/torch/ABI가 최종 이미지와 100% 일치.
# nvcc만 NVIDIA apt 저장소에서 추가 설치(cuda-minimal-build-12-8).

ARG WORKER_VERSION=5.10.0

# ---------- Stage 1: SageAttention 휠 빌드 ----------
FROM runpod/worker-comfyui:${WORKER_VERSION}-base AS sage-builder
ARG SAGE_REF=main
ENV DEBIAN_FRONTEND=noninteractive
# 진단용: 현재 환경 출력
RUN cat /etc/os-release | head -3; python --version; ls /etc/apt/sources.list.d/ || true
# (1) 빌드 도구
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3-dev git wget ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*
# (2) NVIDIA apt 저장소 — base(nvidia/cuda) 이미지에 이미 등록돼 있으면 건너뜀
RUN if ! ls /etc/apt/sources.list.d/ | grep -qi cuda; then \
      wget -qO /tmp/cuda-keyring.deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb \
      && dpkg -i /tmp/cuda-keyring.deb && rm /tmp/cuda-keyring.deb; \
    fi
# (3) nvcc + cudart 헤더
RUN apt-get update && apt-get install -y --no-install-recommends cuda-minimal-build-12-8 \
    && rm -rf /var/lib/apt/lists/*
ENV CUDA_HOME=/usr/local/cuda-12.8 PATH=/usr/local/cuda-12.8/bin:/opt/venv/bin:$PATH
RUN python -c "import torch, sys; print('torch', torch.__version__, 'py', sys.version)" && nvcc --version
RUN uv pip install ninja packaging setuptools wheel
RUN git clone --depth 1 --branch ${SAGE_REF} https://github.com/thu-ml/SageAttention.git /src/SageAttention
# 8.9 = L40S / RTX 6000 Ada, 12.0 = RTX PRO 6000 Blackwell
ENV TORCH_CUDA_ARCH_LIST="8.9;12.0" EXT_PARALLEL=4 MAX_JOBS=4 NVCC_APPEND_FLAGS="--threads 4"
RUN cd /src/SageAttention && python -m pip wheel . --no-build-isolation --no-deps -w /wheels && ls -la /wheels

# ---------- Stage 2: 최종 이미지 ----------
FROM runpod/worker-comfyui:${WORKER_VERSION}-base
COPY --from=sage-builder /wheels/sageattention-*.whl /tmp/wheels/
RUN uv pip install /tmp/wheels/sageattention-*.whl && rm -rf /tmp/wheels
# import 스모크 테스트 (GPU 없이 모듈 로드만 확인)
RUN python -c "import sageattention, torch; print('sageattention OK, torch', torch.__version__)"

# ComfyUI 기동 인자를 env(COMFY_ARGS)로 주입할 수 있는 start.sh
COPY start.sh /start.sh
RUN chmod +x /start.sh
ENV COMFY_ARGS="--use-sage-attention --fast fp8_matrix_mult --highvram"
CMD ["/start.sh"]
