"""
채널톡 상담 데이터 수집 스크립트
====================================
채널톡 Open API v5를 통해 상담 데이터를 수집하고 JSON으로 저장합니다.

사용법:
    python collector.py                    # 어제 데이터 수집
    python collector.py --date 2026-04-10  # 특정 날짜 수집
    python collector.py --range 2026-04-01 2026-04-10  # 기간 수집
    python collector.py --month 2026-03    # 월 단위 수집
"""

import requests
import json
import os
import sys
import time
import base64
from datetime import datetime, timedelta
from pathlib import Path

# 설정 불러오기
try:
    from config import (
        CHANNEL_ACCESS_KEY, CHANNEL_ACCESS_SECRET,
        BASE_URL, API_VERSION, PAGE_SIZE, CHAT_STATES,
        RAW_DIR, TAG_PREFIX_MAP, AGENT_NAME_MAP
    )
except ImportError:
    print("❌ config.py를 찾을 수 없습니다. config.py 파일을 확인하세요.")
    sys.exit(1)


class ChannelTalkCollector:
    """채널톡 Open API v5 데이터 수집기"""

    def __init__(self):
        self.base_url = f"{BASE_URL}/open/{API_VERSION}"
        self.session = requests.Session()

        # 채널톡 Open API v5 인증 (x-access-key / x-access-secret 헤더)
        self.session.headers.update({
            "x-access-key": CHANNEL_ACCESS_KEY,
            "x-access-secret": CHANNEL_ACCESS_SECRET,
            "Content-Type": "application/json",
        })

        # 저장 디렉토리 생성
        Path(RAW_DIR).mkdir(parents=True, exist_ok=True)

    def _request(self, endpoint, params=None, max_retries=3):
        """API 요청 (재시도 + Rate Limit 처리)"""
        url = f"{self.base_url}{endpoint}"

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # Rate Limit - 잠시 대기 후 재시도
                    wait = int(response.headers.get("Retry-After", 5))
                    print(f"  ⏳ Rate limit 도달, {wait}초 대기...")
                    time.sleep(wait)
                    continue
                elif response.status_code == 401:
                    print("❌ 인증 실패. config.py의 API Key를 확인하세요.")
                    sys.exit(1)
                else:
                    print(f"  ⚠️ API 오류 ({response.status_code}): {response.text[:200]}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None

            except requests.exceptions.Timeout:
                print(f"  ⏱ 타임아웃 (시도 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2)
            except requests.exceptions.ConnectionError:
                print(f"  🔌 연결 실패 (시도 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(5)

        return None

    # ============================================================
    # 모드 1: 과거 데이터 수집 (전체 상태, firstOpenedAt 기준)
    # ============================================================
    def fetch_chats_for_period(self, start_date, end_date):
        """과거 기간 전체 상담 수집 (opened+snoozed+closed, firstOpenedAt 기준)"""
        start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
        end_ts = int(datetime.combine(end_date + timedelta(days=1), datetime.min.time()).timestamp() * 1000)

        print(f"\n📥 {start_date} ~ {end_date} 전체 상태 상담 수집 중...")

        self.manager_cache = {}
        all_chats = []

        for state in CHAT_STATES:
            if state in ("opened", "snoozed"):
                chats = self._fetch_by_state_filtered(
                    state, start_ts, end_ts, date_field="firstOpenedAt",
                    max_pages=500, miss_tolerance=999, sort_order="desc"
                )
            else:
                chats = self._fetch_by_state_filtered(
                    state, start_ts, end_ts, date_field="firstOpenedAt",
                    sort_order="desc", miss_tolerance=10, max_pages=9999
                )
            all_chats.extend(chats)
            print(f"  ✅ {state}: {len(chats)}건")

        print(f"  📊 총 {len(all_chats)}건 수집 완료")
        return all_chats

    # ============================================================
    # 모드 2: 오늘 실시간 수집 (전체 상태, createdAt 기준) - 인입 기준
    # ============================================================
    def fetch_today_realtime(self):
        """오늘 인입된 상담 전체 수집 (opened+snoozed+closed, createdAt 기준)"""
        today = datetime.now().date()
        start_ts = int(datetime.combine(today, datetime.min.time()).timestamp() * 1000)
        end_ts = int(datetime.combine(today + timedelta(days=1), datetime.min.time()).timestamp() * 1000)

        print(f"\n📥 오늘({today}) 실시간 인입 상담 수집 중...")

        self.manager_cache = {}
        all_chats = []

        for state in CHAT_STATES:
            if state in ("opened", "snoozed"):
                # opened/snoozed는 정렬이 firstOpenedAt 순이 아니므로 전체 스캔 (max 100페이지)
                chats = self._fetch_by_state_filtered(
                    state, start_ts, end_ts, date_field="firstOpenedAt", max_pages=100, miss_tolerance=999
                )
            else:
                # closed는 최신순 정렬이 잘 되므로 조기 중단 가능
                chats = self._fetch_by_state_filtered(
                    state, start_ts, end_ts, date_field="firstOpenedAt"
                )
            all_chats.extend(chats)
            print(f"  ✅ {state}: {len(chats)}건")

        print(f"  📊 오늘 총 인입: {len(all_chats)}건")
        return all_chats

    # ============================================================
    # 공통: 상태별 커서 페이징 + 날짜 필터
    # ============================================================
    def _fetch_by_state_filtered(self, state, start_ts, end_ts, date_field="closedAt", max_pages=500, miss_tolerance=3, sort_order="desc"):
        """상태별 상담 수집, date_field 기준 필터
        - max_pages: 최대 페이지 수
        - miss_tolerance: 연속 미매칭 허용 횟수
        - sort_order: 'asc'(과거→최신) 또는 'desc'(최신→과거)
        """
        chats = []
        after = None
        page = 0
        consecutive_miss = 0

        while page < max_pages:
            params = {
                "state": state,
                "limit": PAGE_SIZE,
                "sortOrder": sort_order,
            }
            if after:
                params["since"] = after

            data = self._request("/user-chats", params=params)
            if not data or "userChats" not in data:
                break

            # 매니저 정보 캐시
            for mgr in data.get("managers", []):
                mgr_id = mgr.get("id")
                mgr_name = mgr.get("name", "Unknown")
                if mgr_id:
                    self.manager_cache[mgr_id] = mgr_name

            batch = data["userChats"]
            if not batch:
                break

            page += 1
            matched_in_batch = 0

            for chat in batch:
                ts = chat.get(date_field, 0) or chat.get("createdAt", 0)
                if not ts:
                    continue
                if start_ts <= ts < end_ts:
                    chats.append(chat)
                    matched_in_batch += 1

            # 연속 미매칭 추적
            if matched_in_batch == 0:
                consecutive_miss += 1
            else:
                consecutive_miss = 0

            # 조기 중단: 연속 miss_tolerance 배치 기간 밖
            if consecutive_miss >= miss_tolerance:
                break

            # 날짜 기반 조기 중단
            if sort_order == "asc":
                # asc: 최신 항목이 end_ts를 넘으면 더 이상 볼 필요 없음
                newest = max(
                    (c.get(date_field, 0) or c.get("createdAt", 0) for c in batch),
                    default=0
                )
                if newest and newest >= end_ts:
                    break
            elif miss_tolerance <= 3:
                # desc: 가장 오래된 항목이 start_ts 이전이면 중단
                oldest = min(
                    (c.get(date_field, 0) or c.get("createdAt", 0) for c in batch),
                    default=0
                )
                if oldest and oldest < start_ts:
                    break

            # 다음 페이지
            if data.get("next"):
                after = data["next"]
            else:
                break

            time.sleep(0.2)

            if page % 20 == 0:
                print(f"    ... {state} {len(chats)}건 수집 중 (page {page})")

        return chats

    def parse_chat(self, chat):
        """개별 상담 데이터에서 필요한 정보 추출"""
        # 태그 추출
        tags = chat.get("tags", []) or []

        # 태그 분류
        parsed_tags = []
        for tag in tags:
            tag_info = self._parse_tag(tag)
            parsed_tags.append(tag_info)

        # 상담원 정보 (매니저 캐시에서 이름 조회)
        assignee_id = chat.get("assigneeId")
        assignee_name = None
        if assignee_id:
            assignee_name = self.manager_cache.get(assignee_id, "Unknown")

        # 매핑된 이름 적용
        display_name = AGENT_NAME_MAP.get(assignee_name, assignee_name)

        return {
            "chat_id": chat.get("id"),
            "state": chat.get("state"),
            "created_at": chat.get("createdAt"),
            "first_opened_at": chat.get("firstOpenedAt"),
            "opened_at": chat.get("openedAt"),
            "closed_at": chat.get("closedAt"),
            "tags": tags,
            "parsed_tags": parsed_tags,
            "assignee": display_name,
            "assignee_id": chat.get("assigneeId"),
            "channel_id": chat.get("channelId"),
            # 복합태그 조합 생성
            "tag_combinations": self._generate_combinations(parsed_tags),
        }

    def _parse_tag(self, tag_name):
        """태그명에서 카테고리/코드 분리
        예: '문의/Q6_환불요청' → {'raw': '문의/Q6_환불요청', 'category': '문의', 'code': 'Q6', 'name': '환불요청'}
        """
        parts = tag_name.split("/")
        if len(parts) >= 2:
            category = parts[0]
            code_name = parts[1]
            # 코드와 이름 분리 (Q6_환불요청 → Q6, 환불요청)
            code_parts = code_name.split("_", 1)
            code = code_parts[0]
            name = code_parts[1] if len(code_parts) > 1 else ""
            return {
                "raw": tag_name,
                "category": category,
                "code": code,
                "name": name,
                "prefix": code[0] if code else "",
            }
        return {
            "raw": tag_name,
            "category": "기타",
            "code": tag_name,
            "name": "",
            "prefix": "",
        }

    def _generate_combinations(self, parsed_tags):
        """복합태그 조합 생성 (현재 시트의 RAW_complextag와 동일 로직)"""
        combos = []
        if len(parsed_tags) < 2:
            return combos

        for i in range(len(parsed_tags)):
            for j in range(i + 1, len(parsed_tags)):
                combo = f"{parsed_tags[i]['raw']} & {parsed_tags[j]['raw']}"
                combos.append(combo)
        return combos

    def save_raw(self, date_str, chats):
        """Raw 데이터 JSON 저장"""
        filepath = os.path.join(RAW_DIR, f"chats_{date_str}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(chats, f, ensure_ascii=False, indent=2)
        print(f"  💾 저장: {filepath}")
        return filepath

    def collect(self, start_date, end_date=None):
        """기간별 데이터 수집 (전체 상태, firstOpenedAt 기준)"""
        if end_date is None:
            end_date = start_date

        today = datetime.now().date()
        if end_date > today:
            end_date = today

        all_chats = self.fetch_chats_for_period(start_date, end_date)

        # 일별로 분류 (firstOpenedAt 기준 = 인입일)
        from collections import defaultdict
        daily_chats = defaultdict(list)

        for chat in all_chats:
            ts = chat.get("firstOpenedAt") or chat.get("createdAt", 0)
            if not ts:
                continue
            chat_date = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            parsed = self.parse_chat(chat)
            daily_chats[chat_date].append(parsed)

        # 일별 저장
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            chats = daily_chats.get(date_str, [])
            self.save_raw(date_str, chats)
            print(f"  📅 {date_str}: {len(chats)}건")
            current += timedelta(days=1)

        total = sum(len(v) for v in daily_chats.values())
        print(f"\n📊 총 {total}건, {len(daily_chats)}일치 데이터 저장 완료")
        return daily_chats

    def collect_today(self):
        """오늘 실시간 수집 (전체 상태, createdAt 인입 기준)"""
        all_chats = self.fetch_today_realtime()

        today_str = datetime.now().strftime("%Y-%m-%d")
        parsed = [self.parse_chat(chat) for chat in all_chats]
        self.save_raw(today_str, parsed)
        print(f"  📅 {today_str}: {len(parsed)}건 (인입 기준, 실시간)")
        return {today_str: parsed}


def main():
    """CLI 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="채널톡 상담 데이터 수집")
    parser.add_argument("--date", help="수집할 날짜 (YYYY-MM-DD)")
    parser.add_argument("--range", nargs=2, metavar=("START", "END"), help="수집 기간")
    parser.add_argument("--month", help="수집할 월 (YYYY-MM)")
    parser.add_argument("--today", action="store_true", help="오늘 실시간 인입 수집 (전체 상태)")
    args = parser.parse_args()

    # API Key 확인
    if "여기에" in CHANNEL_ACCESS_KEY:
        print("❌ config.py에 채널톡 API Key를 입력해주세요.")
        print("   경로: 채널톡 > 설정 > 보안 및 개발 > API 관리")
        sys.exit(1)

    collector = ChannelTalkCollector()

    if args.today:
        print(f"⚡ 오늘 실시간 인입 수집 (opened+snoozed+closed, createdAt 기준)")
        collector.collect_today()

    elif args.month:
        year, month = map(int, args.month.split("-"))
        start = datetime(year, month, 1).date()
        if month == 12:
            end = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            end = datetime(year, month + 1, 1).date() - timedelta(days=1)
        print(f"📅 {args.month} 월간 수집 - 전체 상태 기준 ({start} ~ {end})")
        collector.collect(start, end)

    elif args.range:
        start = datetime.strptime(args.range[0], "%Y-%m-%d").date()
        end = datetime.strptime(args.range[1], "%Y-%m-%d").date()
        print(f"📅 기간 수집 - 전체 상태 기준 ({start} ~ {end})")
        collector.collect(start, end)

    elif args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
        print(f"📅 {target} 단일 수집 - 전체 상태 기준")
        collector.collect(target)

    else:
        # 기본: 어제(closed) + 오늘(실시간)
        yesterday = (datetime.now() - timedelta(days=1)).date()
        print(f"📅 어제({yesterday}) 전체 상태 수집 + 오늘 실시간 인입 수집")
        collector.collect(yesterday)
        collector.collect_today()

    print("\n✅ 수집 완료!")


if __name__ == "__main__":
    main()
