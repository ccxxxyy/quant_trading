"""测试策略对比 API。"""

import json
import urllib.request

BASE = "http://127.0.0.1:8888"

print("=== Strategy Compare API ===")
req = json.dumps({
    "strategy": "dual_ma",
    "symbol": "600519.SSE",
    "start": "2023-01-01",
    "capital": 1000000,
    "use_demo_data": True,
}).encode()

r = urllib.request.urlopen(
    urllib.request.Request(
        BASE + "/api/backtest/compare",
        data=req,
        headers={"Content-Type": "application/json"},
    )
)
data = json.loads(r.read())

print(f"Compared {len(data['results'])} strategies:")
for sid, result in data["results"].items():
    m = result["metrics"]
    print(f"  {sid:12s} | return={m['total_return']*100:+.2f}% | sharpe={m['sharpe_ratio']:.3f} | trades={m['total_trades']}")

print("\nCompare API OK!")
