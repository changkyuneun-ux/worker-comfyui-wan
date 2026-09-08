# worker-comfyui-wan

RunPod `worker-comfyui:5.10.0-base` + **SageAttention2++** (sm_89 / sm_120) + `--fast fp8_matrix_mult` + `--highvram`.
Wan 2.2 i2v fp8_scaled 워크플로용 서버리스 이미지.

## 빌드
- GitHub Actions(`.github/workflows/build.yml`)가 `main` push 시 `ghcr.io/<owner>/worker-comfyui-wan:5.10.0-sage`로 빌드·푸시.
- 로컬: `docker build --platform linux/amd64 -t worker-comfyui-wan:5.10.0-sage .` (SageAttention 컴파일 20~40분)
- GHCR 패키지는 **Public**으로 설정해야 RunPod가 인증 없이 pull 가능 (Package settings → Change visibility).

## 엔드포인트 설정
| 항목 | 값 |
| --- | --- |
| Image | `ghcr.io/<owner>/worker-comfyui-wan:5.10.0-sage` |
| GPU pools | BLACKWELL_96, ADA_48_PRO |
| env `COMFY_ARGS` | 기본값 `--use-sage-attention --fast fp8_matrix_mult --highvram` (이미지 ENV). 문제 시 env로 덮어쓰기, 예: `--use-sage-attention` 만 |
| env `COMFY_LOG_LEVEL` | INFO |

## 검증 로그
워커 로그에서 확인:
- `Using sage attention`
- `Enabled fp8 compute` / `fp8_matrix_mult`
- `Set vram state to: HIGH_VRAM`
- 스텝 진행 `xx s/it` — 81f 720² 기준 목표 25~40 s/it (기존 128 s/it@161f)

## 롤백
엔드포인트 Image를 `runpod/worker-comfyui:5.10.0-base`(또는 기존 Hub 이미지)로 되돌리기. env `COMFY_ARGS`는 원본 start.sh에서 무시됨.
