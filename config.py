"""
채널톡 API 설정 파일
====================================
아래 값을 채널톡 관리자 화면에서 발급받은 API Key로 교체하세요.
경로: 채널톡 > 설정 > 보안 및 개발 > API 관리
"""

# ===== 채널톡 API 인증 =====
CHANNEL_ACCESS_KEY = "69dcad774fcaa3de57af"
CHANNEL_ACCESS_SECRET = "56cc8ddd7a87b28b1cd84dfd32ad8c05"

# ===== 수집 설정 =====
BASE_URL = "https://api.channel.io"
API_VERSION = "v5"

# 한 번에 조회할 상담 수 (최대 500)
PAGE_SIZE = 500

# 수집 대상 상담 상태
CHAT_STATES = ["opened", "snoozed", "closed"]

# ===== 데이터 저장 경로 =====
DATA_DIR = "./data"
RAW_DIR = f"{DATA_DIR}/raw"
PROCESSED_DIR = f"{DATA_DIR}/processed"
DASHBOARD_DATA = f"{DATA_DIR}/dashboard.json"

# ===== 태그 분류 체계 =====
TAG_CATEGORIES = {
    "문의": "Q",    # Q1~Q19
    "처리": "M",    # M1, M6, M8, M10
    "안내": "A",    # A3, A4, A6, A8
    "환불": "R",    # R3, R8, R10, R11, RP, RT
    "특성": "E",    # E3
}

# 태그 → 카테고리 역매핑 (prefix 기반)
TAG_PREFIX_MAP = {
    "Q": "문의",
    "M": "처리",
    "A": "안내",
    "R": "환불",
    "E": "특성",
}

# ===== 상담원 매핑 =====
# 채널톡 매니저 이름 → 대시보드 표시 이름
AGENT_NAME_MAP = {
    "Randy": "Randy",
    "Summer": "Summer",
    "lily": "Lily",
    "Lily": "Lily",
    "allie": "Allie",
    "Allie": "Allie",
    "Jiu": "Jiu",
    "jiu": "Jiu",
}

# 대시보드에 표시할 상담원 순서 & 색상
AGENT_DISPLAY = ["Randy", "Summer", "Lily", "Allie", "Jiu"]
