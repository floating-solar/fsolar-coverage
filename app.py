import logging
import os

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import config
import dem_utils

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=".")
CORS(app)


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/dem_types")
def dem_types():
    return jsonify(config.DEM_TYPES)


@app.route("/api/test_key", methods=["POST"])
def test_key():
    body = request.get_json(force=True) or {}
    api_key = (body.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "API 키가 비어있습니다."}), 400
    logger.info("API 키 테스트 요청 (길이: %d)", len(api_key))
    try:
        result = dem_utils.test_api_key(api_key)
        return jsonify(result)
    except Exception as e:
        logger.exception("API 키 테스트 오류")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        body = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "JSON 파싱 오류"}), 400

    bbox = body.get("bbox")
    elevation = body.get("elevation")
    dem_type = body.get("dem_type", "COP30")
    api_key = body.get("api_key") or config.OPENTOPO_API_KEY

    # ── 입력 검증 ────────────────────────────────────────────────
    if not bbox or not all(
        k in bbox for k in ("south", "north", "west", "east")
    ):
        return jsonify({"error": "분석 영역(bbox)이 필요합니다."}), 400

    if elevation is None:
        return jsonify({"error": "기준 고도 값이 필요합니다."}), 400

    try:
        elevation = float(elevation)
    except (TypeError, ValueError):
        return jsonify({"error": "고도 값이 유효하지 않습니다."}), 400

    if dem_type not in config.DEM_TYPES:
        return jsonify({"error": f"지원하지 않는 DEM 유형: {dem_type}"}), 400

    lat_span = float(bbox["north"]) - float(bbox["south"])
    lon_span = float(bbox["east"]) - float(bbox["west"])
    if lat_span <= 0 or lon_span <= 0:
        return jsonify({"error": "bbox 좌표가 올바르지 않습니다."}), 400
    if lat_span > config.MAX_BBOX_DEGREES or lon_span > config.MAX_BBOX_DEGREES:
        return jsonify(
            {
                "error": (
                    f"선택 영역이 너무 큽니다. "
                    f"최대 {config.MAX_BBOX_DEGREES}° × {config.MAX_BBOX_DEGREES}° 이하로 줄여주세요."
                )
            }
        ), 400

    # ── DEM 다운로드 ─────────────────────────────────────────────
    source = config.DEM_TYPES[dem_type].get("source", "opentopo")
    try:
        if source == "aws":
            tif_path = dem_utils.download_dem_aws(bbox, dem_type, config.CACHE_DIR)
        else:
            if not api_key:
                return jsonify(
                    {"error": "OpenTopography API 키가 필요합니다. 우측 상단 [🔑 API Key] 버튼으로 입력하세요."}
                ), 400
            tif_path = dem_utils.download_dem(bbox, dem_type, api_key, config.CACHE_DIR)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("DEM 다운로드 오류")
        return jsonify({"error": f"DEM 다운로드 실패: {e}"}), 500

    # ── 고도 분석 ────────────────────────────────────────────────
    try:
        result = dem_utils.analyze_dem(tif_path, elevation)
    except Exception as e:
        logger.exception("DEM 분석 오류")
        return jsonify({"error": f"분석 오류: {e}"}), 500

    result.update(
        {
            "dem_type": dem_type,
            "dem_name": config.DEM_TYPES[dem_type]["name"],
            "elevation_threshold": elevation,
            "bbox": bbox,
        }
    )
    return jsonify(result)


if __name__ == "__main__":
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
