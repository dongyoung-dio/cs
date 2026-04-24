"""
CS 데이터 가공/집계 스크립트
====================================
수집된 Raw 데이터를 대시보드용 JSON으로 집계합니다.
현재 구글 시트의 6개 탭 구조를 그대로 재현합니다.

사용법:
    python processor.py                   # 전체 Raw 데이터 집계
    python processor.py --month 2026-03   # 특정 월만 집계
"""

import json
import os
import sys
from datetime import datetime, date
from collections import defaultdict, Counter
from pathlib import Path

from config import RAW_DIR, PROCESSED_DIR, DASHBOARD_DATA, TAG_PREFIX_MAP


class DataProcessor:
    """수집된 Raw 데이터를 대시보드용으로 가공"""

    def __init__(self):
        Path(PROCESSED_DIR).mkdir(parents=True, exist_ok=True)
        self.raw_data = {}  # date_str → [parsed_chats]

    def load_raw_files(self, month_filter=None):
        """Raw JSON 파일 로드"""
        raw_path = Path(RAW_DIR)
        if not raw_path.exists():
            print("❌ Raw 데이터가 없습니다. collector.py를 먼저 실행하세요.")
            sys.exit(1)

        files = sorted(raw_path.glob("chats_*.json"))
        if month_filter:
            files = [f for f in files if month_filter in f.name]

        for filepath in files:
            date_str = filepath.stem.replace("chats_", "")
            with open(filepath, "r", encoding="utf-8") as f:
                self.raw_data[date_str] = json.load(f)

        print(f"📂 {len(self.raw_data)}일치 데이터 로드 완료")

    # ========================================
    # RAW_tag 시트 재현: 일별 단일태그 건수
    # ========================================
    def calc_daily_tag_counts(self):
        """일별 태그별 건수 집계 (RAW_tag 시트 대응)"""
        result = {}

        for date_str, chats in self.raw_data.items():
            tag_counter = Counter()
            for chat in chats:
                for tag_info in chat.get("parsed_tags", []):
                    tag_counter[tag_info["raw"]] += 1
            result[date_str] = dict(tag_counter.most_common())

        return result

    # ========================================
    # RAW_complextag 시트 재현: 일별 복합태그 건수
    # ========================================
    def calc_daily_complex_tag_counts(self):
        """일별 복합태그 조합 건수 집계 (RAW_complextag 시트 대응)"""
        result = {}

        for date_str, chats in self.raw_data.items():
            combo_counter = Counter()
            for chat in chats:
                for combo in chat.get("tag_combinations", []):
                    combo_counter[combo] += 1
            result[date_str] = dict(combo_counter.most_common())

        return result

    # ========================================
    # RAW_count 시트 재현: 일별 상담원별 처리량
    # ========================================
    def calc_daily_agent_counts(self):
        """일별 상담원별 처리 건수 (RAW_count 시트 대응)"""
        result = {}

        for date_str, chats in self.raw_data.items():
            agent_counter = Counter()
            for chat in chats:
                agent = chat.get("assignee") or "미배정"
                agent_counter[agent] += 1

            result[date_str] = {
                "agents": dict(agent_counter),
                "total": sum(agent_counter.values()),
            }

        return result

    # ========================================
    # 월별태그top 시트 재현: 월별 Top 태그
    # ========================================
    def calc_monthly_tag_top(self, top_n=50):
        """월별 Top N 태그 집계 (월별태그top 시트 대응)"""
        monthly_tags = defaultdict(Counter)
        monthly_totals = defaultdict(int)

        for date_str, chats in self.raw_data.items():
            month = date_str[:7]  # YYYY-MM
            for chat in chats:
                monthly_totals[month] += 1
                for tag_info in chat.get("parsed_tags", []):
                    monthly_tags[month][tag_info["raw"]] += 1

        result = {}
        for month in sorted(monthly_tags.keys()):
            total_inquiries = monthly_totals[month]
            total_tags = sum(monthly_tags[month].values())
            top_tags = monthly_tags[month].most_common(top_n)

            result[month] = {
                "total_inquiries": total_inquiries,
                "total_tags": total_tags,
                "top": [
                    {
                        "tag": tag,
                        "count": count,
                        "tag_pct": round(count / total_tags * 100, 2) if total_tags else 0,
                        "inquiry_pct": round(count / total_inquiries * 100, 2) if total_inquiries else 0,
                    }
                    for tag, count in top_tags
                ],
            }

        return result

    # ========================================
    # 복합태그비율 시트 재현: 월별 환불 분석
    # ========================================
    def calc_monthly_refund_analysis(self):
        """월별 환불 관련 분석 (복합태그비율 시트 대응)"""
        monthly_data = defaultdict(lambda: {
            "total": 0,
            "refund_request": 0,   # 환불 요청
            "refund_hold": 0,      # 환불 유예
            "refund_defense": 0,   # 환불 방어
            "refund_reasons": Counter(),
        })

        for date_str, chats in self.raw_data.items():
            month = date_str[:7]
            for chat in chats:
                monthly_data[month]["total"] += 1
                tags_raw = [t.get("raw", "") for t in chat.get("parsed_tags", [])]

                # 환불 요청 (Q6_환불요청 태그 포함)
                has_refund_request = any("Q6_환불요청" in t for t in tags_raw)
                if has_refund_request:
                    monthly_data[month]["refund_request"] += 1

                # 환불 유예 / 방어 판정
                has_hold = any("환불유예" in t or "환불 유예" in t for t in tags_raw)
                has_defense = any("환불방어" in t or "환불 방어" in t for t in tags_raw)

                if has_hold:
                    monthly_data[month]["refund_hold"] += 1
                if has_defense:
                    monthly_data[month]["refund_defense"] += 1

                # 환불사유 분류
                for tag_info in chat.get("parsed_tags", []):
                    if tag_info.get("prefix") == "R":
                        monthly_data[month]["refund_reasons"][tag_info["raw"]] += 1

        result = {}
        for month in sorted(monthly_data.keys()):
            d = monthly_data[month]
            total = d["total"]
            result[month] = {
                "total_inquiries": total,
                "refund_request": d["refund_request"],
                "refund_request_pct": round(d["refund_request"] / total * 100, 2) if total else 0,
                "refund_hold": d["refund_hold"],
                "refund_hold_pct": round(d["refund_hold"] / total * 100, 2) if total else 0,
                "refund_defense": d["refund_defense"],
                "refund_defense_pct": round(d["refund_defense"] / total * 100, 2) if total else 0,
                "refund_reasons": [
                    {"reason": reason, "count": count}
                    for reason, count in d["refund_reasons"].most_common(20)
                ],
            }

        return result

    # ========================================
    # 월별 요약 통계 (KPI 카드용)
    # ========================================
    def calc_monthly_summary(self):
        """월별 핵심 지표 요약"""
        monthly_counts = defaultdict(lambda: {"total": 0, "agents": Counter(), "days": set()})

        for date_str, chats in self.raw_data.items():
            month = date_str[:7]
            monthly_counts[month]["total"] += len(chats)
            monthly_counts[month]["days"].add(date_str)

            for chat in chats:
                agent = chat.get("assignee") or "미배정"
                monthly_counts[month]["agents"][agent] += 1

        result = {}
        for month in sorted(monthly_counts.keys()):
            d = monthly_counts[month]
            num_days = len(d["days"])
            result[month] = {
                "total_consultations": d["total"],
                "num_days": num_days,
                "daily_avg": round(d["total"] / num_days, 2) if num_days else 0,
                "agents": dict(d["agents"]),
            }

        return result

    # ========================================
    # 태그 카테고리 분포
    # ========================================
    def calc_tag_category_distribution(self):
        """월별 태그 카테고리 분포"""
        monthly = defaultdict(Counter)

        for date_str, chats in self.raw_data.items():
            month = date_str[:7]
            for chat in chats:
                for tag_info in chat.get("parsed_tags", []):
                    category = tag_info.get("category", "기타")
                    monthly[month][category] += 1

        return {month: dict(counts) for month, counts in sorted(monthly.items())}

    # ========================================
    # 전체 대시보드 데이터 생성
    # ========================================
    def build_dashboard_json(self):
        """대시보드에 필요한 모든 데이터를 하나의 JSON으로 통합"""
        print("\n🔧 데이터 가공 시작...")

        dashboard = {
            "generated_at": datetime.now().isoformat(),
            "daily_tag_counts": self.calc_daily_tag_counts(),
            "daily_complex_tag_counts": self.calc_daily_complex_tag_counts(),
            "daily_agent_counts": self.calc_daily_agent_counts(),
            "monthly_tag_top": self.calc_monthly_tag_top(),
            "monthly_refund": self.calc_monthly_refund_analysis(),
            "monthly_summary": self.calc_monthly_summary(),
            "tag_categories": self.calc_tag_category_distribution(),
            "monthly_applications": self._load_applications(),
        }

        # JSON 저장
        with open(DASHBOARD_DATA, "w", encoding="utf-8") as f:
            json.dump(dashboard, f, ensure_ascii=False, indent=2)

        print(f"✅ 대시보드 데이터 생성 완료: {DASHBOARD_DATA}")
        return dashboard

    def _load_applications(self):
        """병원비환급 월별 신청수 로드 (data/applications.json)"""
        app_path = os.path.join(os.path.dirname(DASHBOARD_DATA), "applications.json")
        try:
            with open(app_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"📋 신청수 데이터 로드: {app_path}")
            result = {
                "apps": data.get("monthly", {}),
                "refunds_db": data.get("monthly_refunds_db", {}),
                "cohort": data.get("cohort_refunds", {})
            }
            return result
        except FileNotFoundError:
            print("ℹ️ applications.json 없음, 신청수 데이터 생략")
            return {"apps": {}, "refunds_db": {}}

        # JSON 저장
        with open(DASHBOARD_DATA, "w", encoding="utf-8") as f:
            json.dump(dashboard, f, ensure_ascii=False, indent=2)

        print(f"✅ 대시보드 데이터 생성 완료: {DASHBOARD_DATA}")
        return dashboard


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CS 데이터 가공/집계")
    parser.add_argument("--month", help="특정 월만 집계 (YYYY-MM)")
    args = parser.parse_args()

    processor = DataProcessor()
    processor.load_raw_files(month_filter=args.month)
    processor.build_dashboard_json()


if __name__ == "__main__":
    main()
