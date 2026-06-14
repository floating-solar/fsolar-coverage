import io
import math
import os
import base64
import hashlib
import logging

import numpy as np
import requests
import rasterio
from rasterio.merge import merge as rio_merge
from PIL import Image

logger = logging.getLogger(__name__)

OPENTOPO_URL = "https://portal.opentopography.org/API/globaldem"


AWS_COP30_BASE = "https://copernicus-dem-30m.s3.amazonaws.com"
AWS_COP90_BASE = "https://copernicus-dem-90m.s3.amazonaws.com"


def _cop_tile_url(lat, lon, base):
    """Copernicus 1°×1° 타일 URL 생성."""
    lat_h = "N" if lat >= 0 else "S"
    lon_h = "E" if lon >= 0 else "W"
    la, lo = abs(lat), abs(lon)
    name = f"Copernicus_DSM_COG_10_{lat_h}{la:02d}_00_{lon_h}{lo:03d}_00_DEM"
    return f"{base}/{name}/{name}.tif"


def download_dem_aws(bbox, dem_type, cache_dir):
    """API 키 없이 AWS S3 COG에서 Copernicus DEM 다운로드 (COP30 / COP90)."""
    cache_path = get_cache_path(bbox, dem_type, cache_dir)
    if os.path.exists(cache_path):
        logger.info("캐시 DEM 로드: %s", cache_path)
        return cache_path

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    base = AWS_COP30_BASE if dem_type == "COP30" else AWS_COP90_BASE

    lat_lo = int(math.floor(bbox["south"]))
    lat_hi = int(math.floor(bbox["north"]))
    lon_lo = int(math.floor(bbox["west"]))
    lon_hi = int(math.floor(bbox["east"]))

    urls = [
        _cop_tile_url(lat, lon, base)
        for lat in range(lat_lo, lat_hi + 1)
        for lon in range(lon_lo, lon_hi + 1)
    ]
    logger.info("AWS COG 타일 %d개: %s", len(urls), [u.split("/")[-1] for u in urls])

    datasets = []
    try:
        for url in urls:
            try:
                datasets.append(rasterio.open(url))
            except Exception as e:
                logger.warning("타일 건너뜀 (%s): %s", url.split("/")[-1], e)

        if not datasets:
            raise ValueError("접근 가능한 COG 타일이 없습니다. 네트워크 상태를 확인하세요.")

        bounds = (bbox["west"], bbox["south"], bbox["east"], bbox["north"])
        merged, transform = rio_merge(datasets, bounds=bounds)
        data = merged[0]

        profile = datasets[0].profile.copy()
        profile.update(
            height=data.shape[0], width=data.shape[1],
            transform=transform, driver="GTiff", compress="lzw", count=1,
        )
        tmp = cache_path + ".tmp"
        try:
            with rasterio.open(tmp, "w", **profile) as dst:
                dst.write(data, 1)
            os.replace(tmp, cache_path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

        logger.info("AWS DEM 저장 완료: %s %s", cache_path, data.shape)
        return cache_path
    finally:
        for ds in datasets:
            try:
                ds.close()
            except Exception:
                pass


def get_cache_path(bbox, dem_type, cache_dir):
    key = (
        f"{bbox['south']:.4f}_{bbox['north']:.4f}"
        f"_{bbox['west']:.4f}_{bbox['east']:.4f}"
    )
    short = hashlib.md5(key.encode()).hexdigest()[:12]
    return os.path.join(cache_dir, dem_type.lower(), f"{short}.tif")


def test_api_key(api_key):
    """
    두 단계로 API 키를 진단한다.
    1) 공개 데모 키(demoapikeyot2022)로 엔드포인트 자체가 동작하는지 확인
    2) 사용자 키를 'API_key' → 'apikey' 순으로 시도
    """
    api_key = api_key.strip()
    BASE = {
        "demtype": "SRTMGL3",
        "south": 37.0, "north": 37.02,
        "west": 127.0, "east": 127.02,
        "outputFormat": "GTiff",
    }

    def _get(params):
        prepared = requests.Request("GET", OPENTOPO_URL, params=params).prepare()
        safe = prepared.url
        for secret in (api_key,):
            if secret and len(secret) > 4:
                safe = safe.replace(secret, secret[:4] + "****")
        logger.info("요청 URL: %s", safe)
        return requests.get(OPENTOPO_URL, params=params, timeout=30)

    def _is_tiff(resp):
        ct = resp.headers.get("Content-Type", "")
        return resp.status_code == 200 and ("tiff" in ct.lower() or "octet" in ct.lower())

    # ── Step 1: 데모 키로 엔드포인트 연결 확인 ──────────────────
    try:
        demo_resp = _get({**BASE, "API_key": "demoapikeyot2022"})
        logger.info("데모 키 응답: HTTP %d", demo_resp.status_code)
    except requests.RequestException as e:
        return {"ok": False, "error": f"OpenTopography 서버 연결 실패: {e}"}

    if not _is_tiff(demo_resp):
        return {
            "ok": False,
            "error": (
                f"OpenTopography 엔드포인트 이상 (HTTP {demo_resp.status_code}).\n"
                "잠시 후 다시 시도하거나 portal.opentopography.org 상태를 확인하세요.\n"
                f"응답: {demo_resp.text[:200]}"
            ),
        }

    # ── Step 2: 사용자 키, 파라미터 이름 두 가지 시도 ────────────
    logger.info("엔드포인트 정상. 사용자 키 테스트 (길이: %d자)", len(api_key))
    for key_param in ("API_key", "apikey"):
        try:
            resp = _get({**BASE, key_param: api_key})
        except requests.RequestException as e:
            continue
        logger.info("[%s] HTTP %d", key_param, resp.status_code)
        if _is_tiff(resp):
            return {"ok": True, "message": f"API 키 유효 ✓  (파라미터: {key_param})", "key_param": key_param}

    # 두 형식 모두 실패
    last_body = resp.text[:300] if "resp" in dir() else ""
    return {
        "ok": False,
        "error": (
            "API 키 인증 실패 (HTTP 401) — 엔드포인트는 정상입니다.\n\n"
            "💡 가능한 원인 및 해결:\n"
            "  ① 가입 이메일의 인증 링크를 클릭했는지 확인\n"
            "  ② portal.opentopography.org 로그인 → My Account → API Key 상태 확인\n"
            "  ③ 키 전체를 다시 복사해 붙여넣기 (공백·줄바꿈 주의)\n"
            "  ④ 새 키를 재발급(Regenerate) 후 재시도\n\n"
            f"전송된 키 길이: {len(api_key)}자\n"
            f"서버 응답: {last_body}"
        ),
    }


def download_dem(bbox, dem_type, api_key, cache_dir):
    api_key = api_key.strip()
    cache_path = get_cache_path(bbox, dem_type, cache_dir)

    if os.path.exists(cache_path):
        logger.info("캐시에서 DEM 로드: %s", cache_path)
        return cache_path

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    params = {
        "demtype": dem_type,
        "south": bbox["south"],
        "north": bbox["north"],
        "west": bbox["west"],
        "east": bbox["east"],
        "outputFormat": "GTiff",
        "API_key": api_key,
    }

    logger.info("API 키 길이: %d자", len(api_key))

    # API_key → apikey 순으로 시도 (OpenTopography 파라미터 이름 혼용 대응)
    resp = None
    for key_param in ("API_key", "apikey"):
        p = {**params, key_param: api_key}
        prepared = requests.Request("GET", OPENTOPO_URL, params=p).prepare()
        masked = prepared.url.replace(api_key, api_key[:4] + "****") if len(api_key) > 4 else prepared.url
        logger.info("DEM 요청 URL (%s): %s", key_param, masked)

        resp = requests.get(OPENTOPO_URL, params=p, timeout=180, stream=True)
        ct = resp.headers.get("Content-Type", "")
        logger.info("응답: HTTP %d  Content-Type: %s", resp.status_code, ct)

        if resp.status_code == 200 and ("tiff" in ct.lower() or "octet" in ct.lower()):
            break  # 성공
        if resp.status_code != 401:
            break  # 401 이외의 오류는 재시도해도 무의미

    if resp.status_code != 200:
        raise ValueError(
            f"OpenTopography API 오류 (HTTP {resp.status_code}): {resp.text[:300]}"
        )

    content_type = resp.headers.get("Content-Type", "")
    if "tiff" not in content_type.lower() and "octet-stream" not in content_type.lower():
        snippet = resp.text[:400]
        raise ValueError(f"DEM 다운로드 실패 – 서버 응답:\n{snippet}")

    tmp_path = cache_path + ".tmp"
    try:
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        os.replace(tmp_path, cache_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    logger.info("DEM 다운로드 완료: %s", cache_path)
    return cache_path


def analyze_dem(tif_path, elevation_threshold):
    with rasterio.open(tif_path) as src:
        data = src.read(1).astype(np.float32)
        nodata = src.nodata
        transform = src.transform
        height, width = data.shape

    # ── 유효 데이터 마스크 ──────────────────────────────────────
    valid_mask = np.ones((height, width), dtype=bool)
    if nodata is not None:
        valid_mask &= ~np.isclose(data, nodata)
    valid_mask &= np.isfinite(data)

    # ── 고도 이하 마스크 ────────────────────────────────────────
    below_mask = valid_mask & (data <= elevation_threshold)

    # ── 위도별 픽셀 면적 계산 (m²) ──────────────────────────────
    # transform.f : 북쪽 끝 위도, transform.e : 음수 (남향)
    lats = transform.f + (np.arange(height) + 0.5) * transform.e
    lat_rad = np.radians(lats)
    pixel_w_m = abs(transform.a) * 111_320.0 * np.cos(lat_rad)  # (H,)
    pixel_h_m = abs(transform.e) * 110_540.0

    pixel_area_m2 = pixel_w_m * pixel_h_m  # (H,)

    total_area_m2 = float(np.dot(valid_mask.sum(axis=1), pixel_area_m2))
    below_area_m2 = float(np.dot(below_mask.sum(axis=1), pixel_area_m2))

    below_ratio = (below_area_m2 / total_area_m2 * 100.0) if total_area_m2 > 0 else 0.0

    # ── 고도 통계 ────────────────────────────────────────────────
    valid_data = data[valid_mask]
    stats = {
        "min_elev": round(float(valid_data.min()), 2),
        "max_elev": round(float(valid_data.max()), 2),
        "mean_elev": round(float(valid_data.mean()), 2),
        "std_elev": round(float(valid_data.std()), 2),
    }

    # ── 히스토그램 (50 bins) ─────────────────────────────────────
    counts, bin_edges = np.histogram(valid_data, bins=50)
    histogram = {
        "bins": [round(float(v), 2) for v in bin_edges.tolist()],
        "counts": counts.tolist(),
    }

    # ── PNG 오버레이 생성 ────────────────────────────────────────
    overlay_png = _create_mask_png(below_mask, height, width)

    # ── 마우스 호버용 고도 격자 (300×300 이하) ───────────────────
    elev_grid = _build_elev_grid(data, valid_mask, max_size=300)

    return {
        "total_area_km2": round(total_area_m2 / 1e6, 4),
        "below_area_km2": round(below_area_m2 / 1e6, 4),
        "below_ratio_pct": round(below_ratio, 2),
        "stats": stats,
        "histogram": histogram,
        "overlay_png": overlay_png,
        "elev_grid": elev_grid,
    }


def _build_elev_grid(data, valid_mask, max_size=300):
    """고도 배열을 max_size×max_size 이하로 균일 샘플링해 JSON 전송용 격자 반환."""
    height, width = data.shape
    step_h = max(1, (height + max_size - 1) // max_size)  # ceiling division
    step_w = max(1, (width  + max_size - 1) // max_size)

    sub_data  = data[::step_h, ::step_w]
    sub_valid = valid_mask[::step_h, ::step_w]

    rows, cols = sub_data.shape
    flat = [
        round(float(sub_data[i, j])) if sub_valid[i, j] else None
        for i in range(rows)
        for j in range(cols)
    ]
    return {"rows": rows, "cols": cols, "data": flat}


def _create_mask_png(below_mask, height, width, max_px=2048):
    """below_mask를 반투명 파란색 RGBA PNG (base64)로 변환."""
    # 해상도가 크면 축소
    scale = min(1.0, max_px / max(height, width))
    if scale < 1.0:
        new_h = max(1, int(height * scale))
        new_w = max(1, int(width * scale))
        src_img = Image.fromarray(below_mask.astype(np.uint8) * 255, mode="L")
        src_img = src_img.resize((new_w, new_h), Image.NEAREST)
        mask = np.array(src_img) > 127
    else:
        mask = below_mask

    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[mask, 0] = 30
    rgba[mask, 1] = 100
    rgba[mask, 2] = 220
    rgba[mask, 3] = 160  # ~63% 투명도

    img = Image.fromarray(rgba, "RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"
