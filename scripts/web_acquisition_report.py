from __future__ import annotations

import argparse
import json

from app_services.analytics.acquisition_service import AcquisitionService


def _format_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


async def _main(days: int) -> int:
    service = AcquisitionService()
    report = await service.build_report(days=days)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print()
    print(
        "source / medium / campaign | visitors | logins | checkout_started | checkout_paid | jobs_launched | login_cr | paid_cr | launch_cr"
    )
    print("-" * 140)
    for item in report["sources"]:
        visitors = int(item["visitors"])
        logins = int(item["logins"])
        paid = int(item["checkout_paid"])
        launches = int(item["jobs_launched"])
        label = " / ".join(
            [
                str(item["utm_source"]),
                str(item["utm_medium"]),
                str(item["utm_campaign"]),
            ]
        )
        print(
            f"{label} | {visitors} | {logins} | {item['checkout_started']} | {paid} | {launches} | "
            f"{_format_percent(logins, visitors)} | {_format_percent(paid, visitors)} | {_format_percent(launches, visitors)}"
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print web acquisition funnel summary from Postgres.")
    parser.add_argument("--days", type=int, default=30, help="Trailing number of days to include.")
    args = parser.parse_args()

    import asyncio

    raise SystemExit(asyncio.run(_main(max(int(args.days or 30), 1))))
