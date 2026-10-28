import json, csv, os

BASE = r"C:/Users/Boss/.workbuddy/projects/c-Users-Boss-WorkBuddy-2026-10-15-17-08-15/fa50773e-f0c8-4220-be4a-fbd19d19e5aa/tool-results"
OUT = r"C:/Users/Boss/WorkBuddy/2026-10-15-17-08-15/data"
os.makedirs(OUT, exist_ok=True)

YEAR_FILES = [
    "mcp-westock-mcp-data_kline-1792056124173-a93d9f.txt",
    "mcp-westock-mcp-data_kline-1792056134798-e8dcb9.txt",
    "mcp-westock-mcp-data_kline-1792056134689-28df20.txt",
    "mcp-westock-mcp-data_kline-1792056143213-1bf135.txt",
    "mcp-westock-mcp-data_kline-1792056143276-beead4.txt",
    "mcp-westock-mcp-data_kline-1792056150961-c50d87.txt",
    "mcp-westock-mcp-data_kline-1792056151224-42126e.txt",
    "mcp-westock-mcp-data_kline-1792056158274-367bdd.txt",
]
INDEX_FILES = {
    "cs931152": [
        "mcp-westock-mcp-data_kline-1792055821427-9019fd.txt",
    ],
    "sh000300": [
        "mcp-westock-mcp-data_kline-1792055863723-06b944.txt",
        "mcp-westock-mcp-data_kline-1792056194338-9c03c2.txt",
    ],
}

store = {}


def collect(sym, nodes):
    d = store.setdefault(sym, {})
    for n in nodes:
        d[n["date"]] = (n.get("last"), n.get("volume"), n.get("amount"))


for fn in YEAR_FILES:
    with open(os.path.join(BASE, fn), "r", encoding="utf-8") as f:
        j = json.load(f)
    for item in j["data"]["data"]:
        collect(item["symbol"], item["data"]["nodes"])
    print("loaded", fn, len(j["data"]["data"]), "symbols")

for name, fns in INDEX_FILES.items():
    for fn in fns:
        with open(os.path.join(BASE, fn), "r", encoding="utf-8") as f:
            j = json.load(f)
        collect(name, j["data"]["nodes"])

for sym, d in sorted(store.items()):
    path = os.path.join(OUT, sym + ".csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "close", "volume", "amount"])
        for date in sorted(d):
            c, v, a = d[date]
            if c and c > 0:
                w.writerow([date, c, v, a])
    print(sym, len(d), min(d), max(d))
