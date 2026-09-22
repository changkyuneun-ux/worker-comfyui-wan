# Wan 2.2 i2v 모델 내장 이미지 — RunPod GitHub 빌드용 (Dockerfile Path: bake/Dockerfile)
# base: SageAttention + fp8 + highvram 이미지 (GHCR public). 컴파일 없음 → RunPod 30분 빌드 제한 내.
# 총 크기 ≈ 11GB(base) + 38GB(모델) + 1.75GB(내부 전용 LoRA 4종) ≈ 51GB (RunPod 한도 80GB)
# 내부 전용 LoRA 4종은 외부 미노출 — 이미지는 이 엔드포인트 전용으로만 pull 가능(RunPod 정책), 워크플로 style=nsfw|dr34ml4y 로만 호출

FROM ghcr.io/changkyuneun-ux/worker-comfyui-wan:5.10.0-sage

# HF 공개 저장소 — 토큰 불필요. 파일명은 워크플로(wan22_5s.json 등)와 동일해야 함.
ARG W22=https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files
ARG W21=https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files

# 내부 전용 LoRA (S3 presigned URL, 2026-09-22 발급, 7일 유효 — 빌드 1회용. 만료 후 재빌드 필요 시 재발급해서 교체)
# 외부 미노출 대상: s3://dobedub-studio/internal/loras/ (계정 471112500555, ap-northeast-2)
ARG LORA_NSFW_H="https://dobedub-studio.s3.ap-northeast-2.amazonaws.com/internal/loras/NSFW-22-H-e8.safetensors?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAW3MD6IVFR7YQRX4Z%2F20260922%2Fap-northeast-2%2Fs3%2Faws4_request&X-Amz-Date=20260922T234757Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=7cca90193472e053f0bc585f1af05e7a4f9826506bd219004e776dadad70b259"
ARG LORA_NSFW_L="https://dobedub-studio.s3.ap-northeast-2.amazonaws.com/internal/loras/NSFW-22-L-e8.safetensors?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAW3MD6IVFR7YQRX4Z%2F20260922%2Fap-northeast-2%2Fs3%2Faws4_request&X-Amz-Date=20260922T234829Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=d011b918407d6f15bb97aad48ee47b1dcbe1f8f98e79ab296892e41d03b36626"
ARG LORA_DR34_H="https://dobedub-studio.s3.ap-northeast-2.amazonaws.com/internal/loras/DR34ML4Y_I2V_14B_HIGH_V2.safetensors?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAW3MD6IVFR7YQRX4Z%2F20260922%2Fap-northeast-2%2Fs3%2Faws4_request&X-Amz-Date=20260922T234844Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=6e315bd4c199e7a9924c698d9ab2530dac95c84e18d0899e8e1bcf184d1db640"
ARG LORA_DR34_L="https://dobedub-studio.s3.ap-northeast-2.amazonaws.com/internal/loras/DR34ML4Y_I2V_14B_LOW_V2.safetensors?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAW3MD6IVFR7YQRX4Z%2F20260922%2Fap-northeast-2%2Fs3%2Faws4_request&X-Amz-Date=20260922T234857Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=ca7b0a99045ccf650b278e5bacbc8021cf246ace8021887d7b696a27a1ae57d7"

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

# 내부 전용 LoRA 4종 (S3 presigned, 위 ARG 참고). 레이어 캐시를 위해 파일별 분리.
RUN comfy model download --url "${LORA_NSFW_H}" \
      --relative-path models/loras --filename NSFW-22-H-e8.safetensors
RUN comfy model download --url "${LORA_NSFW_L}" \
      --relative-path models/loras --filename NSFW-22-L-e8.safetensors
RUN comfy model download --url "${LORA_DR34_H}" \
      --relative-path models/loras --filename DR34ML4Y_I2V_14B_HIGH_V2.safetensors
RUN comfy model download --url "${LORA_DR34_L}" \
      --relative-path models/loras --filename DR34ML4Y_I2V_14B_LOW_V2.safetensors

# 무결성: 크기 확인 (HF 메타데이터 기준, 2026-09-08 / 로컬 실측 sha256 대조는 운영가이드 참고, 2026-09-22)
RUN set -e; cd /comfyui/models; \
    check() { s=$(stat -c %s "$1"); [ "$s" -eq "$2" ] || { echo "SIZE MISMATCH $1 $s != $2"; exit 1; }; echo "OK $1 $s"; }; \
    check vae/wan_2.1_vae.safetensors 253815318; \
    check loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors 1226977424; \
    check loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors 1226977424; \
    check clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors 6735906897; \
    check diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors 14294742832; \
    check diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors 14294742832; \
    check loras/NSFW-22-H-e8.safetensors 613516752; \
    check loras/NSFW-22-L-e8.safetensors 613516752; \
    check loras/DR34ML4Y_I2V_14B_HIGH_V2.safetensors 306807976; \
    check loras/DR34ML4Y_I2V_14B_LOW_V2.safetensors 306807976

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
