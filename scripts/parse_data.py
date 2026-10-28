import json, csv, os, glob

BASE = r"C:/Users/Boss/.workbuddy/projects/c-Users-Boss-WorkBuddy-2026-10-15-17-08-15/fa50773e-f0c8-4220-be4a-fbd19d19e5aa/tool-results"
OUT = r"C:/Users/Boss/WorkBuddy/2026-10-15-17-08-15/data"
os.makedirs(OUT, exist_ok=True)

FILES = {
    "cs931152": "mcp-westock-mcp-data_kline-1792055821427-9019fd.txt",
    "cro_batch": "mcp-westock-mcp-data_kline-1792055856786-0acce9.txt",
    "sh000300": "mcp-westock-mcp-data_kline-1792055863723-06b944.txt",
}


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_csv(name, rows):
    path = os.path.join(OUT, name + ".csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "close", "high", "low", "volume", "amount"])
        for r in sorted(rows):
            w.writerow(r)
    print(name, len(rows), rows[0][0] if rows else "NA", rows[-1][0] if rows else "NA")


def node_to_row(n):
    return [n["date"], n.get("open"), n.get("last"), n.get("high"), n.get("low"),
            n.get("volume"), n.get("amount")]


d = load(os.path.join(BASE, FILES["cs931152"]))
write_csv("cs931152", [node_to_row(n) for n in d["data"]["nodes"]])

d = load(os.path.join(BASE, FILES["sh000300"]))
write_csv("sh000300", [node_to_row(n) for n in d["data"]["nodes"]])

d = load(os.path.join(BASE, FILES["cro_batch"]))
for item in d["data"]["data"]:
    sym = item["symbol"]
    write_csv(sym, [node_to_row(n) for n in item["data"]["nodes"]])
