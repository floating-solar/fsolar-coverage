import os

OPENTOPO_API_KEY = os.environ.get("OPENTOPO_API_KEY", "")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
MAX_BBOX_DEGREES = 4.0
PORT = int(os.environ.get("PORT", 5000))
DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

DEM_TYPES = {
    # ── API 키 불필요 (AWS S3 COG 직접 접근) ────────────────────
    "COP30": {
        "name": "Copernicus GLO-30 (AWS)",
        "resolution": "30m",
        "coverage": "전 지구",
        "provider": "ESA / AWS Open Data",
        "source": "aws",
    },
    "COP90": {
        "name": "Copernicus GLO-90 (AWS)",
        "resolution": "90m",
        "coverage": "전 지구",
        "provider": "ESA / AWS Open Data",
        "source": "aws",
    },
    # ── OpenTopography API 키 필요 ───────────────────────────────
    "SRTMGL1": {
        "name": "SRTM GL1",
        "resolution": "30m",
        "coverage": "위도 ±60°",
        "provider": "NASA / USGS",
        "source": "opentopo",
    },
    "NASADEM": {
        "name": "NASADEM",
        "resolution": "30m",
        "coverage": "위도 ±60°",
        "provider": "NASA",
        "source": "opentopo",
    },
    "AW3D30": {
        "name": "AW3D30 v3.2",
        "resolution": "30m",
        "coverage": "전 지구",
        "provider": "JAXA",
        "source": "opentopo",
    },
    "SRTMGL3": {
        "name": "SRTM GL3",
        "resolution": "90m",
        "coverage": "위도 ±60°",
        "provider": "NASA / USGS",
        "source": "opentopo",
    },
}
