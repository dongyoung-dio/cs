# 병원비환급 CS 대시보드 자동화 시스템

## 파일 구조

```
cs-dashboard/
├── config.py          ← 채널톡 API Key 설정 (여기만 수정하면 됨)
├── collector.py       ← 채널톡에서 상담 데이터 수집
├── processor.py       ← 수집된 데이터 가공/집계
├── run.py             ← 원클릭 실행 (수집 → 가공 → 대시보드 열기)
├── dashboard.html     ← 대시보드 (브라우저에서 바로 열기 가능)
└── data/              ← 수집/가공 데이터 저장 (자동 생성)
    ├── raw/           ← 일별 Raw JSON
    ├── processed/     ← 가공된 데이터
    └── dashboard.json ← 대시보드용 통합 데이터
```

## 시작하기

### Step 1: API Key 발급
1. 채널톡 관리자 로그인
2. **설정 > 보안 및 개발 > API 관리** 이동
3. **새 API Key 생성** 클릭
4. Access Key와 Access Secret 복사

### Step 2: config.py 수정
```python
CHANNEL_ACCESS_KEY = "발급받은_Access_Key"
CHANNEL_ACCESS_SECRET = "발급받은_Access_Secret"
```

### Step 3: 실행
```bash
# 어제 데이터 수집 + 대시보드 업데이트
python run.py

# 특정 월 전체 수집
python run.py --month 2026-03

# 대시보드만 열기 (이미 수집된 데이터 사용)
python run.py --dashboard-only
```

## 대시보드 미리보기
API Key 없이도 `dashboard.html`을 브라우저에서 열면 프로토타입을 볼 수 있습니다.
(현재 구글 시트의 실제 데이터가 샘플로 들어가 있음)

## 주의사항
- Python 3.8+ 필요
- `pip install requests` 실행 필요
- 채널톡 API Rate Limit: 스크립트에서 자동 처리됨
