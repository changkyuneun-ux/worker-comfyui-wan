"""
s3_handler.py — worker-comfyui 핸들러의 S3 입출력 래퍼 (dobedub-studio)

입력 (ECS → RunPod):
{
  "input": {
    "workflow": {...},                       # ComfyUI API 포맷 (LoadImage.image == images[].name)
    "images": [
      {"assetId": "asset_input_001", "s3Uri": "s3://bucket/.../inputs/asset_input_001/scene.png", "name": "scene.png"},
                                                         # name 필수 = ComfyUI 파일명 = workflow LoadImage.image
      {"name": "x.png", "image": "<base64>"}             # 기존 방식도 계속 지원
    ],
    "output": {                                          # 있으면(mode 생략 또는 "s3") 결과를 S3에 업로드
      "mode": "s3",
      "bucket": "dobedub-studio",
      "prefix": "prod/request-batches/<rpb>/items/<rpi>/jobs/<job>/outputs",   # assetId 는 넣지 않음
      "manifestKey": "prod/request-batches/<rpb>/items/<rpi>/jobs/<job>/manifests/runpod-result.json",
      "appJobId": "task_xxx",                             # ECS job id → manifest.appJobId (jobId 는 RunPod id)
      "filename": "final.mp4",                           # (선택) 기본 final.<ComfyUI 확장자>
      "assetIdPrefix": "asset_output_"                   # (선택) 기본 asset_output_ → asset_output_001, 002 ...
    }
  }
}
결과 키: <prefix>/<assetId>/<filename>

출력 (RunPod → ECS): output 지정 시 base64 는 반환하지 않고 S3 위치만 반환 (응답 크기 절감)
{
  "status": "success" | "error",
  "outputs": [{"type": "video", "assetId": "asset_output_001", "bucket": "...", "key": "...", "filename": "...", "contentType": "video/mp4", "sizeBytes": 123, "s3Uri": "s3://..."}],
  "manifestKey": "...",
  "errors": [...]
}

manifest (manifestKey 에 저장):
{
  "schemaVersion": 1, "jobId": "<runpod id>", "appJobId": "<appJobId>", "status": "success"|"error", "createdAt": "ISO8601",
  "inputs": [{"assetId": "...", "s3Uri": "...", "name": "...", "sizeBytes": 123}],
  "outputs": [{"type": "video", "assetId": "asset_output_001", "bucket": "...", "key": "...", "filename": "...", "contentType": "video/mp4", "sizeBytes": 123, "s3Uri": "..."}],
  "errors": [...], "timings": {"totalSec": 38.1, "downloadSec": 0.4, "generateSec": 36.9, "uploadSec": 0.8},
  "worker": {"id": "...", "endpointId": "...", "imageRev": "..."}
}

자격증명: 엔드포인트 env (RunPod Secrets 권장) — AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION + AWS_DEFAULT_REGION

가드 (모든 요청에 적용, GPU 실행 전 검사):
  WanImageToVideo 등 영상 노드의 width*height > WAN_MAX_PIXELS(기본 921600=720p) 또는 length > WAN_MAX_FRAMES(기본 81),
  전체 length 합계 > WAN_MAX_TOTAL_FRAMES(기본 162) → 즉시 실패. 응답/manifest 의 "generation": [{nodeId, classType, width, height, length}] 에 실제 값 기록.
"""

import base64
import json
import mimetypes
import os
import sys
import time
import traceback
from datetime import datetime, timezone

import boto3
from botocore.config import Config

sys.path.insert(0, "/")
import handler as base  # noqa: E402  (worker-comfyui 원본 핸들러)
import runpod  # noqa: E402

_S3 = None


def _s3():
    global _S3
    if _S3 is None:
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        _S3 = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=os.environ.get("AWS_S3_ENDPOINT_URL") or None,
            config=Config(retries={"max_attempts": 5, "mode": "standard"}),
        )
    return _S3


def _parse_s3_uri(uri):
    if not uri.startswith("s3://"):
        raise ValueError(f"invalid s3Uri: {uri}")
    bucket, _, key = uri[5:].partition("/")
    if not bucket or not key:
        raise ValueError(f"invalid s3Uri: {uri}")
    return bucket, key


def _now():
    return datetime.now(timezone.utc).isoformat()


_VIDEO_NODES = ("WanImageToVideo", "WanFirstLastFrameToVideo", "WanFunControlToVideo", "WanVaceToVideo",
                "EmptyHunyuanLatentVideo", "Wan22ImageToVideoLatent")
MAX_PIXELS = int(os.environ.get("WAN_MAX_PIXELS", "921600"))   # 1280*720 (720p 상한). 480p 운영 시 409600
MAX_FRAMES = int(os.environ.get("WAN_MAX_FRAMES", "81"))          # 노드(세그먼트)당 프레임
MAX_TOTAL_FRAMES = int(os.environ.get("WAN_MAX_TOTAL_FRAMES", "162"))  # 워크플로 전체 합계 (10s 체인 = 81+81)


def _resolve(workflow, val, depth=0):
    """링크([node_id, idx])면 Primitive*/ComfyMathExpression 을 따라가 상수로 환원. 불가하면 None."""
    if not (isinstance(val, list) and len(val) == 2 and isinstance(val[0], str)):
        return val
    if depth > 8:
        return None
    src = workflow.get(val[0]) or {}
    ct, inp = src.get("class_type"), src.get("inputs") or {}
    if ct in ("PrimitiveInt", "PrimitiveFloat", "PrimitiveBoolean", "PrimitiveString"):
        return inp.get("value")
    if ct == "ComfyMathExpression":
        expr = str(inp.get("expression", ""))
        vals = {k.split(".", 1)[1]: _resolve(workflow, v, depth + 1) for k, v in inp.items() if k.startswith("values.")}
        if any(v is None for v in vals.values()):
            return None
        try:
            import math
            return eval(expr, {"__builtins__": {}}, {**vals, "floor": math.floor, "ceil": math.ceil, "round": round,
                                                     "min": min, "max": max, "abs": abs})
        except Exception:  # noqa: BLE001
            return None
    return None


def _inspect_workflow(workflow):
    """영상 생성 노드의 width/height/length 수집 + 한도 검사. 반환: (generation 리스트, 위반 메시지 리스트)"""
    gen, violations = [], []
    workflow = workflow or {}
    for nid, node in workflow.items():
        if not isinstance(node, dict) or node.get("class_type") not in _VIDEO_NODES:
            continue
        inp = node.get("inputs") or {}
        w, h, n = (_resolve(workflow, inp.get(k)) for k in ("width", "height", "length"))
        entry = {"nodeId": nid, "classType": node["class_type"], "width": w, "height": h, "length": n}
        gen.append(entry)
        try:
            if w is not None and h is not None and int(w) * int(h) > MAX_PIXELS:
                violations.append(f"node {nid}: width*height={int(w)*int(h)} > {MAX_PIXELS} (max 720p-equivalent)")
            if n is not None and int(n) > MAX_FRAMES:
                violations.append(f"node {nid}: length={n} > {MAX_FRAMES}")
        except (TypeError, ValueError):
            pass  # 링크 입력([node, idx]) 등 비상수 값은 검사 생략
    total = sum(int(g["length"]) for g in gen if isinstance(g["length"], (int, float)))
    if total > MAX_TOTAL_FRAMES:
        violations.append(f"total length={total} over {len(gen)} node(s) > {MAX_TOTAL_FRAMES}")
    return gen, violations


def _resolve_inputs(images):
    """s3Uri 항목을 다운로드해 base64 로 변환. 기존 항목은 그대로 통과."""
    if not images:
        return images, []
    resolved, meta = [], []
    for img in images:
        if "s3Uri" in img:
            bucket, key = _parse_s3_uri(img["s3Uri"])
            # ComfyUI 내 파일명은 반드시 images[].name 사용 (s3Uri basename 으로 대체하지 않음)
            name = img.get("name")
            if not name or "/" in name:
                raise ValueError(f"images[].name is required (and must be a plain filename) for s3Uri {img['s3Uri']}")
            obj = _s3().get_object(Bucket=bucket, Key=key)
            data = obj["Body"].read()
            resolved.append({"name": name, "image": base64.b64encode(data).decode()})
            meta.append({"assetId": img.get("assetId"), "s3Uri": img["s3Uri"], "name": name, "sizeBytes": len(data)})
            print(f"s3-handler - downloaded {img['s3Uri']} -> {name} ({len(data)} bytes)")
        else:
            resolved.append(img)
            meta.append({"assetId": img.get("assetId"), "name": img.get("name")})
    return resolved, meta


def _upload_outputs(result, out_cfg):
    """base handler 결과의 images[] 를 <prefix>/<assetId>/<filename> 으로 업로드. 반환: outputs 메타, errors"""
    bucket = out_cfg["bucket"]
    prefix = (out_cfg.get("prefix") or "").strip("/")
    override = out_cfg.get("filename") or "final"
    asset_prefix = out_cfg.get("assetIdPrefix") or "asset_output_"
    outputs, errors = [], []
    items = result.get("images") or []
    for i, item in enumerate(items):
        try:
            orig = item.get("filename") or f"output_{i}"
            stem, ext = os.path.splitext(override)
            if not ext:
                ext = os.path.splitext(orig)[1] or ".mp4"
            fname = f"{stem}{ext}"
            asset_id = f"{asset_prefix}{i+1:03d}"
            key = "/".join(p for p in (prefix, asset_id, fname) if p)
            ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
            otype = ctype.split("/")[0] if ctype.split("/")[0] in ("video", "image", "audio") else "file"

            if item.get("type") == "base64":
                body = base64.b64decode(item["data"])
            else:
                raise ValueError(f"unsupported output type {item.get('type')} (BUCKET_ENDPOINT_URL 는 비워두세요)")

            _s3().put_object(Bucket=bucket, Key=key, Body=body, ContentType=ctype)
            outputs.append({
                "type": otype, "assetId": asset_id, "bucket": bucket, "key": key,
                "filename": fname, "contentType": ctype, "sizeBytes": len(body),
                "s3Uri": f"s3://{bucket}/{key}",
            })
            print(f"s3-handler - uploaded s3://{bucket}/{key} ({len(body)} bytes)")
        except Exception as e:  # noqa: BLE001
            msg = f"upload failed for output {i}: {e}"
            print(f"s3-handler - {msg}")
            errors.append(msg)
    return outputs, errors


def _write_manifest(out_cfg, manifest):
    key = out_cfg.get("manifestKey")
    if not key:
        return None
    _s3().put_object(
        Bucket=out_cfg["bucket"], Key=key,
        Body=json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        ContentType="application/json",
    )
    print(f"s3-handler - manifest written s3://{out_cfg['bucket']}/{key}")
    return key


def handler(job):
    t0 = time.time()
    job_input = job.get("input") or {}
    out_cfg = job_input.get("output")
    if out_cfg and str(out_cfg.get("mode", "s3")).lower() != "s3":
        out_cfg = None
    has_s3_in = any("s3Uri" in (im or {}) for im in (job_input.get("images") or []))

    # 0) 워크플로 사전 검사 (해상도/프레임 한도) — GPU 실행 전 즉시 실패
    generation, violations = _inspect_workflow(job_input.get("workflow"))
    print(f"s3-handler - generation params: {json.dumps(generation)}")
    if violations:
        print(f"s3-handler - REJECTED: {violations}")

    # S3 관련 필드가 전혀 없으면 원본 핸들러 그대로 (기존 호환)
    if not out_cfg and not has_s3_in:
        if violations:
            return {"error": "workflow rejected: " + "; ".join(violations), "generation": generation}
        return base.handler(job)

    timings, errors, inputs_meta, outputs = {}, [], [], []
    status = "error"
    result = {}
    try:
        if violations:
            raise ValueError("workflow rejected: " + "; ".join(violations))

        # 1) 입력 다운로드
        t = time.time()
        images, inputs_meta = _resolve_inputs(job_input.get("images"))
        timings["downloadSec"] = round(time.time() - t, 2)

        # 2) ComfyUI 실행 (원본 핸들러)
        inner = dict(job_input)
        inner["images"] = images
        inner.pop("output", None)
        t = time.time()
        result = base.handler({"id": job["id"], "input": inner})
        timings["generateSec"] = round(time.time() - t, 2)
        if result.get("error"):
            errors.append(str(result["error"]))
            if result.get("details"):
                errors.extend(map(str, result["details"]))
        errors.extend(map(str, result.get("errors") or []))

        # 3) 결과 업로드
        if out_cfg and result.get("images"):
            t = time.time()
            outputs, up_err = _upload_outputs(result, out_cfg)
            errors.extend(up_err)
            timings["uploadSec"] = round(time.time() - t, 2)

        status = "success" if outputs and not result.get("error") else "error"
        if not out_cfg:  # S3 입력만 쓰고 출력은 기존 방식으로 반환
            return result
    except Exception as e:  # noqa: BLE001
        if not str(e).startswith("workflow rejected"):
            print(traceback.format_exc())
        errors.append(f"s3-handler: {e}")
        status = "error"

    timings["totalSec"] = round(time.time() - t0, 2)
    manifest = {
        "schemaVersion": 1,
        "jobId": job.get("id"),                          # RunPod job id
        "appJobId": (out_cfg or {}).get("appJobId"),     # ECS 앱 job id (output.appJobId)
        "status": status,
        "createdAt": _now(),
        "inputs": inputs_meta,
        "outputs": outputs,
        "generation": generation,                        # 실제 실행된 width/height/length
        "errors": errors,
        "timings": timings,
        "worker": {
            "id": os.environ.get("RUNPOD_POD_ID"),
            "endpointId": os.environ.get("RUNPOD_ENDPOINT_ID"),
            "imageRev": os.environ.get("IMAGE_REV"),
        },
    }
    manifest_key = None
    try:
        manifest_key = _write_manifest(out_cfg, manifest)
    except Exception as e:  # noqa: BLE001
        errors.append(f"manifest write failed: {e}")
        print(f"s3-handler - manifest write failed: {e}")

    resp = {"status": status, "outputs": outputs, "manifestKey": manifest_key, "timings": timings,
            "generation": generation}
    if errors:
        resp["errors"] = errors
    if status == "error":
        resp["error"] = errors[0] if errors else "unknown error"  # RunPod 이 FAILED 로 표기하도록
    return resp


if __name__ == "__main__":
    print("s3-handler - Starting handler (S3 wrapper over worker-comfyui)...")
    runpod.serverless.start({"handler": handler})
