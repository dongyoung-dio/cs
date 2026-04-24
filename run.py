"""
CS 대시보드 실행 스크립트 (원클릭)
====================================
수집 → 가공 → 대시보드 열기를 한 번에 실행합니다.

사용법:
    python run.py                     # 어제 데이터 수집 + 대시보드 업데이트
    python run.py --month 2026-03     # 3월 전체 수집 + 대시보드 업데이트
    python run.py --dashboard-only    # 대시보드만 열기 (이미 수집된 데이터 사용)
"""

import subprocess
import sys
import os
import webbrowser
from pathlib import Path


def run_command(cmd, desc):
    print(f"\n{'='*50}")
    print(f"🚀 {desc}")
    print(f"{'='*50}")
    result = subprocess.run([sys.executable] + cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    if result.returncode != 0:
        print(f"❌ {desc} 실패")
        return False
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CS 대시보드 실행")
    parser.add_argument("--month", help="수집할 월 (YYYY-MM)")
    parser.add_argument("--date", help="수집할 날짜 (YYYY-MM-DD)")
    parser.add_argument("--dashboard-only", action="store_true", help="대시보드만 열기")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))

    if not args.dashboard_only:
        # 1. 데이터 수집
        collect_cmd = ["collector.py"]
        if args.month:
            collect_cmd += ["--month", args.month]
        elif args.date:
            collect_cmd += ["--date", args.date]

        if not run_command(collect_cmd, "채널톡 데이터 수집"):
            sys.exit(1)

        # 2. 데이터 가공
        process_cmd = ["processor.py"]
        if args.month:
            process_cmd += ["--month", args.month]

        if not run_command(process_cmd, "데이터 가공/집계"):
            sys.exit(1)

    # 3. 대시보드 열기
    dashboard_path = os.path.join(base_dir, "dashboard.html")
    if os.path.exists(dashboard_path):
        print(f"\n🌐 대시보드 열기: {dashboard_path}")
        webbrowser.open(f"file://{os.path.abspath(dashboard_path)}")
    else:
        print("⚠️ dashboard.html 파일이 없습니다.")

    print("\n✅ 완료!")


if __name__ == "__main__":
    main()
