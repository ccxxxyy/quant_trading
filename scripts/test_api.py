"""测试 Web API 接口。"""

import json
import urllib.request

BASE = "http://127.0.0.1:8888"

def get(path):
    r = urllib.request.urlopen(BASE + path)
    return json.loads(r.read())

print("=== Health Check ===")
print(get("/api/health"))

print("\n=== Strategies ===")
data = get("/api/strategies")
for s in data["strategies"]:
    print(f"  {s['id']:12s} - {s['name']}")

print("\n=== System Info ===")
info = get("/api/system/info")
print(f"  Name: {info['name']}")
print(f"  Version: {info['version']}")
print(f"  Strategies: {len(info['strategies'])}")

print("\n=== Run Backtest via API ===")
req = json.dumps({
    "strategy": "dual_ma",
    "symbol": "600519.SSE",
    "start": "2023-01-01",
    "capital": 1000000,
    "use_demo_data": True,
}).encode()
r = urllib.request.urlopen(
    urllib.request.Request(BASE + "/api/backtest/run", data=req, headers={"Content-Type": "application/json"})
)
result = json.loads(r.read())
m = result["metrics"]
print(f"  Total Return: {m['total_return']*100:+.2f}%")
print(f"  Sharpe: {m['sharpe_ratio']:.3f}")
print(f"  Max DD: {m['max_drawdown']*100:.2f}%")
print(f"  Trades: {m['total_trades']}")
print(f"  Equity points: {len(result['equity_curve'])}")

print("\nAll API tests passed!")
