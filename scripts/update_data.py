import os
import sys
import json
import urllib.request
from datetime import datetime, timedelta, timezone

API_KEY = os.environ["ECOS_API_KEY"]
TODAY = datetime.utcnow().strftime("%Y%m%d")
START = (datetime.utcnow() - timedelta(days=60)).strftime("%Y%m%d")


def fetch(stat_code, item_code):
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{API_KEY}/json/kr/1/100/"
        f"{stat_code}/D/{START}/{TODAY}/{item_code}"
    )
    with urllib.request.urlopen(url, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    result = data.get("StatisticSearch")
    if not result:
        raise RuntimeError(f"ECOS error for {stat_code}/{item_code}: {data}")
    rows = result.get("row", [])
    rows.sort(key=lambda r: r["TIME"])
    return [(r["TIME"], float(r["DATA_VALUE"])) for r in rows]


series = {
    "ktb3": fetch("817Y002", "010200000"),
    "ktb10": fetch("817Y002", "010210000"),
    "corpAA": fetch("817Y002", "010300000"),
    "corpBBB": fetch("817Y002", "010320000"),
    "baseRate": fetch("722Y001", "0101000"),
    "usdkrw": fetch("731Y001", "0000001"),
    "kospi": fetch("802Y001", "0001000"),
}

# Align on dates common to every series that must be perfectly in sync.
# (baseRate is handled separately below since it rarely changes and can lag.)
core_keys = ["ktb3", "ktb10", "corpAA", "corpBBB", "usdkrw", "kospi"]
date_sets = [set(t for t, _ in series[k]) for k in core_keys]
common_dates = sorted(set.intersection(*date_sets))

if not common_dates:
    print("No common trading dates found across series", file=sys.stderr)
    sys.exit(1)

common_dates = common_dates[-30:]  # keep the most recent 30 aligned business days


def values_for(key):
    lookup = dict(series[key])
    return [lookup[t] for t in common_dates]


as_of_raw = common_dates[-1]
as_of = f"{as_of_raw[0:4]}-{as_of_raw[4:6]}-{as_of_raw[6:8]}"

# Base rate only changes on MPC decision dates, so take the latest value
# on or before today's asOfDate rather than requiring an exact date match.
base_rate = series["baseRate"][-1][1]
for t, v in series["baseRate"]:
    if t <= as_of_raw:
        base_rate = v

ktb3_hist = values_for("ktb3")
ktb10_hist = values_for("ktb10")
corpAA_hist = values_for("corpAA")
corpBBB_hist = values_for("corpBBB")
usdkrw_hist = values_for("usdkrw")
kospi_hist = values_for("kospi")

y3 = ktb3_hist[-1]
y10 = ktb10_hist[-1]
spread_aa = round(corpAA_hist[-1] - y3, 3)
spread_bbb = round(corpBBB_hist[-1] - y3, 3)

out = {
    "asOfDate": as_of,
    "baseRate": base_rate,
    "curves": {"y3": y3, "y10": y10},
    "spreads": {"corpAA": spread_aa, "corpBBB": spread_bbb},
    "history": {
        "ktb3": ktb3_hist,
        "ktb10": ktb10_hist,
        "corpAA": corpAA_hist,
        "corpBBB": corpBBB_hist,
        "usdkrw": usdkrw_hist,
        "kospi": kospi_hist,
    },
    "updatedAt": datetime.now(timezone.utc).isoformat(),
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(f"Updated data.json — asOfDate={as_of}, baseRate={base_rate}, y3={y3}, y10={y10}")
