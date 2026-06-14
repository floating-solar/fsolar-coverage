# DEM Elevation Coverage 분석 도구 - 상세 설계 계획

## 1. 프로젝트 개요

사용자가 지도에서 원하는 영역을 선택하고 기준 고도(Elevation)를 입력하면,
해당 영역 내에서 기준 고도 이하인 면적을 계산하여 시각화하는 웹 애플리케이션.

- **목적**: 특정 고도 이하 침수 가능 면적, 태양광 입지 분석, 홍수 위험 평가 등
- **방식**: Python 백엔드 + 단일 HTML 프론트엔드
- **데이터**: 무료 공개 글로벌 DEM (Cloud Optimized GeoTIFF)

---

## 2. 활용 가능한 무료 글로벌 DEM 목록

| DEM 이름 | 해상도 | 제공기관 | 접근 방식 | 비고 |
|---|---|---|---|---|
| **Copernicus GLO-30** | 30m | ESA/Copernicus | OpenTopography API, AWS S3 COG | 최신, 전 지구 |
| **SRTM GL1** | 30m | NASA/USGS | OpenTopography API | 위도 ±60° |
| **NASADEM** | 30m | NASA | OpenTopography API, AWS COG | SRTM 개선판 |
| **ASTER GDEM v3** | 30m | NASA/METI | OpenTopography API | 전 지구 |
| **AW3D30 v3.2** | 30m | JAXA | OpenTopography API | 전 지구 |
| **Copernicus GLO-90** | 90m | ESA/Copernicus | AWS S3 COG (퍼블릭) | 대역폭 절감용 |

### OpenTopography API
- 무료 API 키 발급: https://portal.opentopography.org/requestApiKey
- 요청 URL 예시:
  ```
  https://portal.opentopography.org/API/globaldem
    ?demtype=COP30
    &south={south}&north={north}&west={west}&east={east}
    &outputFormat=GTiff
    &API_key={key}
  ```
- 지원 demtype: `COP30`, `SRTMGL1`, `NASADEM`, `AW3D30`, `SRTMGL3`

### AWS S3 직접 접근 (COG)
- Copernicus GLO-30: `s3://copernicus-dem-30m/` (퍼블릭)
- NASADEM: `s3://nasadem/` (퍼블릭)
- 타일 단위로 다운로드 가능 (1°×1° 격자)

---

## 3. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                   Browser (단일 HTML)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Leaflet 지도 │  │  영역 선택   │  │ 결과 시각화   │  │
│  │  (OSM 타일)  │  │ (Leaflet.draw)│  │(Chart + 레이어)│  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘  │
│         └─────────────────┴──────────────────┘          │
│                           │ REST API 호출                │
└───────────────────────────┼─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│              Python Flask 백엔드 (app.py)                │
│  ┌────────────────────────────────────────────────────┐  │
│  │  /api/analyze  엔드포인트                          │  │
│  │  - bbox + elevation + dem_type 수신                │  │
│  │  - OpenTopography API 또는 AWS S3에서 DEM 다운로드 │  │
│  │  - rasterio로 GeoTIFF 파싱                        │  │
│  │  - numpy 마스킹으로 고도 이하 면적 계산            │  │
│  │  - 결과 GeoJSON + 면적 통계 반환                   │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  /api/preview  엔드포인트                          │  │
│  │  - 선택 영역의 DEM 히스토그램 데이터 반환          │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│              외부 DEM 데이터 소스                        │
│  OpenTopography API  /  AWS S3 COG  /  로컬 캐시        │
└─────────────────────────────────────────────────────────┘
```

---

## 4. 기술 스택

### 프론트엔드 (단일 HTML 파일)
| 라이브러리 | 버전 | 용도 |
|---|---|---|
| Leaflet.js | 1.9.x | 인터랙티브 지도 |
| Leaflet.draw | 1.0.x | 박스/폴리곤 영역 선택 |
| Chart.js | 4.x | 고도 분포 히스토그램 |
| Leaflet.GeotiffLayer | - | DEM 레이어 오버레이 |

### 백엔드 (Python)
| 패키지 | 용도 |
|---|---|
| Flask | REST API 서버 |
| rasterio | GeoTIFF 읽기 / 공간 연산 |
| numpy | 배열 마스킹, 면적 계산 |
| pyproj | 좌표 변환, 면적 단위 환산 |
| requests | OpenTopography API 호출 |
| boto3 | AWS S3 COG 접근 (선택) |
| flask-cors | 브라우저 CORS 허용 |

---

## 5. 기능 명세

### 5.1 지도 인터페이스
- OpenStreetMap 기본 타일 표시
- 위성 영상 레이어 토글 (Esri World Imagery)
- 줌 및 패닝
- 현재 마우스 위치의 위경도 표시

### 5.2 영역 선택
- **사각형 선택** (기본): 드래그로 bbox 지정
- **폴리곤 선택**: 자유형 다각형 영역
- 선택 영역 면적 실시간 표시
- 최대 선택 면적 제한 (API 부하 방지, 기본 5°×5°)

### 5.3 DEM 선택
```
[ Copernicus GLO-30 ▼ ]
  ├ Copernicus GLO-30  (30m, 전지구)
  ├ NASADEM            (30m, ±60°)
  ├ SRTM GL1           (30m, ±60°)
  ├ ASTER GDEM v3      (30m, 전지구)
  └ AW3D30 v3.2        (30m, 전지구)
```

### 5.4 고도 입력 및 분석
- 고도 입력 슬라이더 + 숫자 입력 (m 단위)
- **[분석 실행]** 버튼 클릭 시 백엔드 API 호출
- 진행 상태 표시 (로딩 스피너)
- 분석 결과:
  - 선택 영역 총 면적 (km²)
  - 기준 고도 이하 면적 (km²)
  - 비율 (%)
  - 최소/최대/평균 고도 (m)

### 5.5 결과 시각화
- **지도 오버레이**: 기준 고도 이하 영역을 반투명 파란색으로 표시
- **고도 분포 히스토그램**: 전체 영역의 고도 분포 + 기준선 표시
- **범례**: 고도 색상 스케일
- **결과 패널**: 면적 통계 수치 표시

### 5.6 추가 기능
- 분석 결과 PNG 이미지 저장
- 분석 결과 GeoJSON 내보내기
- API 키 설정 모달 (OpenTopography)
- 로컬 캐시 (이미 다운로드한 DEM 타일 재사용)

---

## 6. 파일 구조

```
/home/hydro/research/solar/elev/
├── dem_cover.md          # 이 계획 문서
├── app.py                # Flask 백엔드 서버
├── dem_utils.py          # DEM 다운로드 및 처리 유틸리티
├── index.html            # 단일 프론트엔드 HTML
├── requirements.txt      # Python 의존성
├── config.py             # API 키, 설정값
└── cache/                # 다운로드된 DEM 타일 캐시
    └── cop30/
        └── {lat}_{lon}.tif
```

---

## 7. 백엔드 API 설계

### POST /api/analyze
**Request**
```json
{
  "bbox": {
    "south": 37.4,
    "north": 37.6,
    "west": 126.8,
    "east": 127.0
  },
  "elevation": 50.0,
  "dem_type": "COP30",
  "api_key": "your_opentopography_key"
}
```

**Response**
```json
{
  "total_area_km2": 312.5,
  "below_area_km2": 78.3,
  "below_ratio_pct": 25.1,
  "stats": {
    "min_elev": -5.2,
    "max_elev": 847.3,
    "mean_elev": 134.7
  },
  "geojson": {
    "type": "FeatureCollection",
    "features": [...]
  },
  "histogram": {
    "bins": [0, 10, 20, ...],
    "counts": [1200, 3400, ...]
  }
}
```

### GET /api/dem_types
지원 DEM 목록 및 메타데이터 반환

### GET /api/health
서버 상태 확인

---

## 8. 주요 알고리즘

### 8.1 면적 계산
```python
# 위도에 따라 픽셀 실제 면적이 달라지므로 보정 필요
# rasterio transform을 이용해 각 픽셀 위도 계산 후 cos(lat) 보정
pixel_area_m2 = (resolution * cos(lat_rad)) * resolution
total_below_area = count_below_pixels * pixel_area_m2
```

### 8.2 마스킹 처리
```python
with rasterio.open(dem_path) as src:
    data = src.read(1, masked=True)
    nodata = src.nodata
    mask = (data <= elevation_threshold) & (data != nodata)
    below_pixels = np.sum(mask)
```

### 8.3 결과 폴리곤 생성 (GeoJSON)
```python
from rasterio.features import shapes
from shapely.geometry import shape
# 마스크 → 폴리곤 벡터화
geometries = list(shapes(mask.astype('uint8'), transform=src.transform))
```

---

## 9. 구현 단계

| 단계 | 내용 | 예상 소요 |
|---|---|---|
| **1단계** | 환경 설정 및 의존성 설치 (`requirements.txt`) | 10분 |
| **2단계** | `dem_utils.py`: DEM 다운로드 + 캐시 + 면적 계산 | 30분 |
| **3단계** | `app.py`: Flask REST API 구현 | 20분 |
| **4단계** | `index.html`: Leaflet 지도 + 영역 선택 UI | 30분 |
| **5단계** | `index.html`: 결과 시각화 (오버레이 + 차트) | 20분 |
| **6단계** | 통합 테스트 + 오류 처리 보강 | 20분 |

---

## 10. OpenTopography API 키 발급 방법

1. https://portal.opentopography.org/requestApiKey 접속
2. 무료 계정 생성 후 API Key 발급
3. `config.py`에 입력하거나 HTML UI에서 직접 입력 가능
4. **무료 한도**: 일 1,000회 요청, 최대 4°×4° 영역

---

## 11. 주의 사항 및 제약

- **영역 크기 제한**: OpenTopography API는 최대 약 4°×4° (약 200,000 km²) 지원
- **노데이터 처리**: 해양 등 일부 지역 NoData 값 별도 처리 필요
- **좌표계**: WGS84 (EPSG:4326) 기준, 면적 계산 시 투영좌표계 변환
- **캐시 정책**: 동일 bbox+DEM 조합은 로컬 캐시에서 반환하여 API 호출 절감
- **CORS**: Flask-CORS로 로컬 개발 환경에서 브라우저 접근 허용

---

## 12. 향후 확장 가능성

- 시계열 비교 (GLO-30 vs 구버전 DEM 차이)
- 등고선 생성 및 표시
- 침수 시뮬레이션 (해수면 상승 시나리오)
- 태양광 패널 설치 가능 평지 면적 분석
- 배치 처리 (여러 고도값 동시 계산)
