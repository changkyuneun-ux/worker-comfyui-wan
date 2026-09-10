# Wan 2.2 i2v 모델 내장 이미지 — RunPod GitHub 빌드용 (Dockerfile Path: bake/Dockerfile)
# base: SageAttention + fp8 + highvram 이미지 (GHCR public). 컴파일 없음 → RunPod 30분 빌드 제한 내.
# 총 크기 ≈ 11GB(base) + 38GB(모델) = 49GB (RunPod 한도 80GB)

FROM ghcr.io/changkyuneun-ux/worker-comfyui-wan:5.10.0-sage

# HF 공개 저장소 — 토큰 불필요. 파일명은 워크플로(wan22_5s.json 등)와 동일해야 함.
ARG W22=https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files
ARG W21=https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files

# 레이어 캐시를 위해 파일별 RUN 분리 (작은 파일 먼저)
RUN comfy model download --url ${W21}/vae/wan_2.1_vae.safetensors \
      --relative-path models/vae --filename wan_2.1_vae.safetensors
RUN comfy model download --url ${W22}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors \
      --relative-path models/loras --filename wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors
RUN comfy model download --url ${W22}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors \
      --relative-path models/loras --filename wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors
RUN comfy model download --url ${W21}/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors \
      --relative-path models/clip --filename umt5_xxl_fp8_e4m3fn_scaled.safetensors
RUN comfy model download --url ${W22}/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors \
      --relative-path models/diffusion_models --filename wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors
RUN comfy model download --url ${W22}/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors \
      --relative-path models/diffusion_models --filename wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors

# 무결성: 크기 확인 (HF 메타데이터 기준, 2026-09-08)
RUN set -e; cd /comfyui/models; \
    check() { s=$(stat -c %s "$1"); [ "$s" -eq "$2" ] || { echo "SIZE MISMATCH $1 $s != $2"; exit 1; }; echo "OK $1 $s"; }; \
    check vae/wan_2.1_vae.safetensors 253815318; \
    check loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors 1226977424; \
    check loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors 1226977424; \
    check clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors 6735906897; \
    check diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors 14294742832; \
    check diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors 14294742832

# S3 입출력 래퍼 핸들러 (dobedub-studio): boto3 + s3_handler.py
RUN uv pip install "boto3>=1.34"
COPY s3_handler.py /s3_handler.py
ENV HANDLER_PATH=/s3_handler.py

# start.sh 갱신 (EXTRA_MODELS 부팅 시 다운로드, HANDLER_PATH 지원)
COPY start.sh /start.sh
RUN chmod +x /start.sh
# --highvram 제외: hd(720p급) 10s 체인에서 두 14B 모델 상주 + 활성화 메모리로 96GB 초과(OOM). 기본 모드는 필요 시 자동 언로드.
ENV COMFY_ARGS="--use-sage-attention --fast fp8_matrix_mult"
CMD ["/start.sh"]
