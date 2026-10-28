"""创新药—CRO 板块轮动策略回测（纯标准库实现，不使用任何未来信息）。

数据：
  cs931152  中证创新药产业指数（价格指数）
  CRO 组合  6 家 CRO/CDMO 龙头等权组合（前复权收盘价）
  sh000300  沪深300指数（市场基准）

执行约定：
  信号在第 t 个交易日收盘后计算，仓位在第 t+1 个交易日收盘价执行，
  交易成本在换仓时按换手市值扣减。
"""

import csv, json, math, os, statistics

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OUTDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
os.makedirs(OUTDIR, exist_ok=True)

INNOV_MEMBERS = ["sh600276", "sz300558", "sz002422", "sh600196", "sz002294", "sz002653"]
CRO_MEMBERS = ["sh603259", "sz300347", "sz300759", "sz002821", "sh603127", "sz300725"]
NAMES = {
    "sh600276": "恒瑞医药", "sz300558": "贝达药业", "sz002422": "科伦药业",
    "sh600196": "复星医药", "sz002294": "信立泰", "sz002653": "海思科",
    "sh603259": "药明康德", "sz300347": "泰格医药", "sz300759": "康龙化成",
    "sz002821": "凯莱英", "sh603127": "昭衍新药", "sz300725": "药石科技",
}
TRADING_DAYS = 252
RF_ANNUAL = 0.02


def read_csv(name):
    path = os.path.join(BASE, name + ".csv")
    rows = {}
    with open(path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                c = float(r["close"])
            except (TypeError, ValueError):
                continue
            if c and c > 0:
                rows[r["date"]] = c
    return rows


def to_series(rows):
    dates = sorted(rows)
    return dates, [rows[d] for d in dates]


def build_cro_index(member_series, members):
    """等权组合：每日对可得成分股的日收益率取算术平均，累乘为净值指数。"""
    common = None
    for sym in members:
        d = set(member_series[sym][0])
        common = d if common is None else (common & d)
    dates = sorted(common)
    rets, nav, base = [], [], 1.0
    prev = {s: member_series[s][1][member_series[s][0].index(dates[0])] for s in members}
    nav.append(base)
    for i in range(1, len(dates)):
        day_rets = []
        for s in members:
            idx = member_series[s][0].index(dates[i])
            cur = member_series[s][1][idx] if member_series[s][0][idx] == dates[i] else prev[s]
            day_rets.append(cur / prev[s] - 1.0)
            prev[s] = cur
        r = sum(day_rets) / len(day_rets)
        rets.append(r)
        base *= (1 + r)
        nav.append(base)
    return dates[1:], rets, nav[1:]


def align(*series):
    """按日期交集对齐多个 (dates, values) 序列。"""
    sets = [set(s[0]) for s in series]
    common = set.intersection(*sets)
    dates = sorted(common)
    out = []
    for dates_, values in series:
        m = dict(zip(dates_, values))
        out.append([m[d] for d in dates])
    return dates, out


def ma(values, n, i):
    if i + 1 < n:
        return None
    return sum(values[i + 1 - n:i + 1]) / n


def rolling_std(rets, n, i):
    if i + 1 < n:
        return None
    window = rets[i + 1 - n:i + 1]
    return statistics.pstdev(window)


def month_end_flags(dates):
    flags = [False] * len(dates)
    for i in range(len(dates) - 1):
        if dates[i][:7] != dates[i + 1][:7]:
            flags[i] = True
    flags[-1] = True
    return flags


def max_drawdown(nav):
    peak, mdd = nav[0], 0.0
    for v in nav:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


def perf(nav, dates, rets=None, turnover_cost_total=None):
    n = len(nav)
    years = n / TRADING_DAYS
    total = nav[-1] / nav[0] - 1.0
    ann = (nav[-1] / nav[0]) ** (1 / years) - 1.0 if years > 0 else 0.0
    rr = []
    for i in range(1, n):
        rr.append(nav[i] / nav[i - 1] - 1.0)
    vol = statistics.pstdev(rr) * math.sqrt(TRADING_DAYS) if len(rr) > 1 else 0.0
    sharpe = (ann - RF_ANNUAL) / vol if vol > 0 else 0.0
    mdd = max_drawdown(nav)
    calmar = ann / abs(mdd) if mdd < 0 else 0.0
    monthly = monthly_returns(nav, dates)
    win = sum(1 for x in monthly if x > 0) / len(monthly) if monthly else 0.0
    srt = sorted(rr)
    var95 = srt[int(0.05 * len(srt))] if srt else 0.0
    cvar = sum(srt[:max(1, int(0.05 * len(srt)))]) / max(1, int(0.05 * len(srt))) if srt else 0.0
    return {
        "total_return": total, "annual_return": ann, "volatility": vol,
        "sharpe": sharpe, "max_drawdown": mdd, "calmar": calmar,
        "monthly_win": win, "var95": var95, "cvar95": cvar,
        "final_nav": nav[-1], "n_days": n,
    }


def monthly_returns(nav, dates):
    out = []
    start_nav = nav[0]
    for i in range(1, len(dates)):
        if dates[i][:7] != dates[i - 1][:7]:
            out.append(nav[i - 1] / start_nav - 1.0)
            start_nav = nav[i - 1]
    out.append(nav[-1] / start_nav - 1.0)
    return out


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx = math.sqrt(sum((v - mx) ** 2 for v in x))
    dy = math.sqrt(sum((v - my) ** 2 for v in y))
    return num / (dx * dy) if dx and dy else 0.0


def alpha_beta(strat_rets, bench_rets):
    n = len(strat_rets)
    ms, mb = sum(strat_rets) / n, sum(bench_rets) / n
    cov = sum((strat_rets[i] - ms) * (bench_rets[i] - mb) for i in range(n)) / n
    var_b = sum((bench_rets[i] - mb) ** 2 for i in range(n)) / n
    beta = cov / var_b if var_b else 0.0
    alpha_daily = ms - beta * mb
    return alpha_daily * TRADING_DAYS, beta


def t_test(diff):
    n = len(diff)
    if n < 2:
        return 0.0, 1.0
    m = sum(diff) / n
    sd = statistics.stdev(diff)
    se = sd / math.sqrt(n)
    t = m / se if se else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    return t, p


def backtest(dates, px_a, px_b, *, mom_win=120, ma_win=180, vol_win=20,
             target_vol=0.15, use_trend=True, use_vol=True, cost=0.001,
             start=None, end=None, idle_annual=0.02):
    """返回 (nav, dates, rets, turnover_list, holding_log)"""
    idxs = range(len(dates))
    if start or end:
        idxs = [i for i in idxs if (not start or dates[i] >= start) and (not end or dates[i] <= end)]
    idxs = list(idxs)
    rets_a = [None] + [px_a[i] / px_a[i - 1] - 1 for i in range(1, len(px_a))]
    rets_b = [None] + [px_b[i] / px_b[i - 1] - 1 for i in range(1, len(px_b))]
    nav, nav_dates, nav_rets = [1.0], [dates[idxs[0]]], []
    holdings, turnovers = [], []
    cur = None  # None / 'A' / 'B'
    w = 1.0
    prev_w = 0.0
    w_series = []
    for k in range(1, len(idxs)):
        i = idxs[k]
        sig_i = idxs[k - 1]  # 信号在前一交易日收盘后生成
        mom_a = px_a[sig_i] / px_a[sig_i - mom_win] - 1 if sig_i - mom_win >= 0 else None
        mom_b = px_b[sig_i] / px_b[sig_i - mom_win] - 1 if sig_i - mom_win >= 0 else None
        ma_a = ma(px_a, ma_win, sig_i)
        ma_b = ma(px_b, ma_win, sig_i)
        vol_a = rolling_std([r for r in rets_a[1:sig_i + 1] if r is not None], vol_win, sig_i - 1)
        vol_b = rolling_std([r for r in rets_b[1:sig_i + 1] if r is not None], vol_win, sig_i - 1)
        # 月度调仓：仅在月份切换处重新决策，其余交易日沿用上一持仓
        if dates[i][:7] != dates[sig_i][:7] or cur is None:
            if mom_a is None or mom_b is None:
                target, w = None, 0.0
            else:
                target = "A" if mom_a >= mom_b else "B"
                ok_a = (not use_trend) or (ma_a is not None and px_a[sig_i] > ma_a)
                ok_b = (not use_trend) or (ma_b is not None and px_b[sig_i] > ma_b)
                if target == "A" and not ok_a:
                    target = "B" if ok_b else None
                elif target == "B" and not ok_b:
                    target = "A" if ok_a else None
                sigma = (vol_a if target == "A" else vol_b) if target else None
                if target and sigma:
                    sigma_ann = sigma * math.sqrt(TRADING_DAYS)
                    w = min(1.0, target_vol / sigma_ann) if use_vol else 1.0
                else:
                    w = 1.0 if target else 0.0
            turnover = 0.0
            if cur != target:
                turnover = (w if target else 0.0)
                if cur:
                    turnover += 1.0
            elif cur is not None and target is not None:
                turnover = abs(w - prev_w)
            prev_w = w
            cur = target
        else:
            turnover = 0.0
        # 收益按 T 日（执行日的下一日，即 i 日）资产收益结算：此处用 i-1 -> i 的收益
        if cur == "A":
            r = rets_a[i]
        elif cur == "B":
            r = rets_b[i]
        else:
            r = idle_annual / TRADING_DAYS
        cost_rate = turnover * cost
        nav_ret = (w if cur else 0.0) * r - cost_rate
        nav.append(nav[-1] * (1 + nav_ret))
        nav_dates.append(dates[i])
        nav_rets.append(nav_ret)
        holdings.append(cur)
        turnovers.append(turnover)
        w_series.append(w if cur else 0.0)
    return nav, nav_dates, nav_rets, turnovers, holdings, w_series


def buy_hold(px, dates, start=None, end=None):
    idxs = [i for i in range(len(dates)) if (not start or dates[i] >= start) and (not end or dates[i] <= end)]
    base = px[idxs[0]]
    return [px[i] / base for i in idxs], [dates[i] for i in idxs]


def static_5050(px_a, px_b, dates, start=None, end=None, rebalance_monthly=True):
    idxs = [i for i in range(len(dates)) if (not start or dates[i] >= start) and (not end or dates[i] <= end)]
    # 月度再平衡的 50/50 组合
    nav, nav_dates = [1.0], [dates[idxs[0]]]
    wa = wb = 0.5
    for k in range(1, len(idxs)):
        i = idxs[k]
        prev = idxs[k - 1]
        ra = px_a[i] / px_a[prev] - 1
        rb = px_b[i] / px_b[prev] - 1
        val_a = wa * (1 + ra)
        val_b = wb * (1 + rb)
        total = val_a + val_b
        wa, wb = val_a / total, val_b / total
        nav.append(nav[-1] * total)
        nav_dates.append(dates[i])
        if rebalance_monthly and dates[i][:7] != dates[prev][:7]:
            wa = wb = 0.5
    return nav, nav_dates


def main():
    px_innov_raw = read_csv("cs931152")
    px_hs300_raw = read_csv("sh000300")
    all_members = INNOV_MEMBERS + CRO_MEMBERS
    member_series = {s: to_series(read_csv(s)) for s in all_members}

    inn_dates, inn_rets, inn_nav = build_cro_index(member_series, INNOV_MEMBERS)
    cro_dates, cro_rets, cro_nav = build_cro_index(member_series, CRO_MEMBERS)
    px_innov = dict(zip(inn_dates, inn_nav))
    px_cro = dict(zip(cro_dates, cro_nav))

    # 效度检验：自建创新药组合与中证创新药产业指数(931152)重叠期日收益相关性
    idx_dates, idx_px = to_series(px_innov_raw)
    idx_ret = {idx_dates[i]: idx_px[i] / idx_px[i - 1] - 1 for i in range(1, len(idx_dates))}
    inn_ret_map = dict(zip(inn_dates, inn_rets))
    common_dates = sorted(set(idx_ret) & set(inn_ret_map))
    va = [inn_ret_map[d] for d in common_dates]
    vb = [idx_ret[d] for d in common_dates]
    validity = {
        "window": [common_dates[0], common_dates[-1]] if common_dates else [],
        "n": len(common_dates),
        "corr": pearson(va, vb) if common_dates else None,
    }

    dates, (px_a, px_b, px_m) = align(
        to_series(px_innov), to_series(px_cro), to_series(px_hs300_raw)
    )
    WARMUP = 120
    start_date = dates[WARMUP]
    meta = {
        "start": start_date, "end": dates[-1], "n_days": len(dates) - WARMUP,
        "raw_start": dates[0], "warmup_days": WARMUP,
        "innov_members": [NAMES[s] for s in INNOV_MEMBERS],
        "cro_members": [NAMES[s] for s in CRO_MEMBERS],
        "validity_vs_cs931152": validity,
    }

    WARMUP = 120
    start_date = dates[WARMUP]

    results = {}

    # S1 纯动量轮动（无趋势过滤、无波动率控制、满仓）
    nav, d, r, turn, hold, ws = backtest(dates, px_a, px_b, use_trend=False, use_vol=False, start=start_date)
    results["S1_动量轮动"] = {"perf": perf(nav, d), "nav": nav, "dates": d, "rets": r, "turnover": turn, "w": ws}

    # S2 动量 + 趋势过滤（满仓或空仓）
    nav, d, r, turn, hold, ws = backtest(dates, px_a, px_b, use_trend=True, use_vol=False, start=start_date)
    results["S2_动量+趋势"] = {"perf": perf(nav, d), "nav": nav, "dates": d, "rets": r, "turnover": turn, "w": ws}

    # S3 主策略：动量 + 趋势过滤 + 15% 波动率目标
    nav, d, r, turn, hold, ws = backtest(dates, px_a, px_b, use_trend=True, use_vol=True, start=start_date)
    results["S3_主策略"] = {"perf": perf(nav, d), "nav": nav, "dates": d, "rets": r, "turnover": turn, "w": ws}

    # S4 波动率目标放宽至 25%
    nav, d, r, turn, hold, ws = backtest(dates, px_a, px_b, use_trend=True, use_vol=True, target_vol=0.25, start=start_date)
    results["S4_波动率目标25%"] = {"perf": perf(nav, d), "nav": nav, "dates": d, "rets": r, "turnover": turn, "w": ws}

    nav, d = buy_hold(px_a, dates, start=start_date)
    results["B1_创新药买入持有"] = {"perf": perf(nav, d), "nav": nav, "dates": d}

    nav, d = buy_hold(px_b, dates, start=start_date)
    results["B2_CRO买入持有"] = {"perf": perf(nav, d), "nav": nav, "dates": d}

    nav, d = static_5050(px_a, px_b, dates, start=start_date)
    results["B3_静态50/50"] = {"perf": perf(nav, d), "nav": nav, "dates": d}

    nav, d = buy_hold(px_m, dates, start=start_date)
    results["B4_沪深300"] = {"perf": perf(nav, d), "nav": nav, "dates": d, "rets": [nav[i] / nav[i - 1] - 1 for i in range(1, len(nav))]}

    # Alpha / Beta（相对沪深300）与显著性检验
    bench_rets = results["B4_沪深300"]["rets"]
    for k, v in results.items():
        if "rets" not in v:
            v["rets"] = [v["nav"][i] / v["nav"][i - 1] - 1 for i in range(1, len(v["nav"]))]
        rr = v["rets"]
        m = min(len(rr), len(bench_rets))
        v["perf"]["alpha"], v["perf"]["beta"] = alpha_beta(rr[:m], bench_rets[:m])
        diff = [rr[i] - bench_rets[i] for i in range(m)]
        t, p = t_test(diff)
        v["perf"]["t_vs_hs300"] = t
        v["perf"]["p_vs_hs300"] = p

    # 分年度收益
    yearly = {}
    for k, v in results.items():
        nav, d = v["nav"], v["dates"]
        by_year = {}
        start_nav, start_year = nav[0], d[0][:4]
        for i in range(1, len(d)):
            if d[i][:4] != d[i - 1][:4]:
                by_year[start_year] = nav[i - 1] / start_nav - 1
                start_nav, start_year = nav[i - 1], d[i][:4]
        by_year[start_year] = nav[-1] / start_nav - 1
        yearly[k] = by_year

    # 参数稳健性（S3）
    grid = []
    for mom in (40, 60, 80, 120):
        for maw in (60, 120, 180):
            nav, d, r, turn, hold, ws = backtest(dates, px_a, px_b, mom_win=mom, ma_win=maw, start=start_date)
            p = perf(nav, d)
            grid.append({"mom": mom, "ma": maw, "ann": p["annual_return"],
                         "sharpe": p["sharpe"], "mdd": p["max_drawdown"]})

    # 交易成本敏感性（S3）
    cost_grid = []
    for c in (0.0005, 0.001, 0.002, 0.003):
        nav, d, r, turn, hold, ws = backtest(dates, px_a, px_b, cost=c, start=start_date)
        p = perf(nav, d)
        cost_grid.append({"cost": c, "ann": p["annual_return"], "sharpe": p["sharpe"], "mdd": p["max_drawdown"]})

    # 样本内 / 样本外
    split = "2023-01-01"
    oos = {}
    for k in ["S1_动量轮动", "S3_主策略", "S4_波动率目标25%", "B1_创新药买入持有", "B2_CRO买入持有", "B3_静态50/50", "B4_沪深300"]:
        res = {}
        for label, s, e in [("样本内", start_date, split), ("样本外", split, None)]:
            if k.startswith("S"):
                kw = {}
                if k == "S1_动量轮动":
                    kw = {"use_trend": False, "use_vol": False}
                elif k == "S4_波动率目标25%":
                    kw = {"target_vol": 0.25}
                n2, d2, r2, t2, h2, ws2 = backtest(dates, px_a, px_b, start=s, end=e, **kw)
            elif k == "B3_静态50/50":
                n2, d2 = static_5050(px_a, px_b, dates, start=s, end=e)
            elif k == "B1_创新药买入持有":
                n2, d2 = buy_hold(px_a, dates, start=s, end=e)
            elif k == "B2_CRO买入持有":
                n2, d2 = buy_hold(px_b, dates, start=s, end=e)
            else:
                n2, d2 = buy_hold(px_m, dates, start=s, end=e)
            res[label] = perf(n2, d2)
        oos[k] = res

    # 持仓分布
    nav, d, r, turn, hold, ws = backtest(dates, px_a, px_b, start=start_date)
    hold_stat = {
        "A_创新药": sum(1 for h in hold if h == "A") / len(hold),
        "B_CRO": sum(1 for h in hold if h == "B") / len(hold),
        "空仓": sum(1 for h in hold if h is None) / len(hold),
        "换仓次数": sum(1 for t in turn if t > 0),
        "平均仓位": sum(ws) / len(ws),
        "年双边换手率": sum(turn) / (len(turn) / TRADING_DAYS),
    }
    nav1, d1, r1, turn1, hold1, ws1 = backtest(dates, px_a, px_b, use_trend=False, use_vol=False, start=start_date)
    hold_stat_s1 = {
        "A_创新药": sum(1 for h in hold1 if h == "A") / len(hold1),
        "B_CRO": sum(1 for h in hold1 if h == "B") / len(hold1),
        "换仓次数": sum(1 for t in turn1 if t > 0),
        "年双边换手率": sum(turn1) / (len(turn1) / TRADING_DAYS),
    }

    # 两板块日收益相关性与分年相关性
    ra_all = [px_a[i] / px_a[i - 1] - 1 for i in range(1, len(px_a))]
    rb_all = [px_b[i] / px_b[i - 1] - 1 for i in range(1, len(px_b))]
    corr_all = pearson(ra_all, rb_all)
    corr_year = {}
    for y in sorted(set(x[:4] for x in dates)):
        idx = [i for i in range(1, len(dates)) if dates[i][:4] == y]
        if len(idx) > 30:
            corr_year[y] = pearson([ra_all[i - 1] for i in idx], [rb_all[i - 1] for i in idx])
    corr_stat = {"全样本": corr_all, "分年": corr_year}

    out = {
        "meta": meta,
        "summary": {k: v["perf"] for k, v in results.items()},
        "yearly": yearly,
        "grid": grid,
        "cost_grid": cost_grid,
        "oos": oos,
        "hold_stat": hold_stat,
        "hold_stat_s1": hold_stat_s1,
        "corr_stat": corr_stat,
    }
    with open(os.path.join(OUTDIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 导出净值曲线
    with open(os.path.join(OUTDIR, "nav_curves.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "S1", "S2", "S3", "S4", "B1", "B2", "B3", "B4"])
        series = {k: dict(zip(v["dates"], v["nav"])) for k, v in results.items()}
        keys = ["S1_动量轮动", "S2_动量+趋势", "S3_主策略", "S4_波动率目标25%",
                "B1_创新药买入持有", "B2_CRO买入持有", "B3_静态50/50", "B4_沪深300"]
        for dd in sorted(set(dates)):
            w.writerow([dd] + [round(series[k].get(dd, ""), 4) if dd in series[k] else "" for k in keys])

    print(json.dumps(out["meta"], ensure_ascii=False))
    for k, v in out["summary"].items():
        print(f"{k:24s} 年化{v['annual_return']*100:7.2f}%  波动{v['volatility']*100:6.2f}%  "
              f"夏普{v['sharpe']:5.2f}  回撤{v['max_drawdown']*100:7.2f}%  Calmar{v['calmar']:5.2f}  "
              f"月胜率{v['monthly_win']*100:5.1f}%  alpha{v['alpha']*100:6.2f}%  beta{v['beta']:4.2f}  t={v['t_vs_hs300']:5.2f}")
    print("\n持仓分布S3:", json.dumps(hold_stat, ensure_ascii=False))
    print("持仓分布S1:", json.dumps(hold_stat_s1, ensure_ascii=False))
    print("相关性:", json.dumps(corr_stat, ensure_ascii=False))
    print("\n年度收益:")
    for k, v in yearly.items():
        print(k, {y: f"{x*100:.1f}%" for y, x in v.items()})
    print("\n参数网格:")
    for g in grid:
        print(g["mom"], g["ma"], f"{g['ann']*100:.2f}%", f"{g['sharpe']:.2f}", f"{g['mdd']*100:.2f}%")
    print("\n成本敏感性:")
    for g in cost_grid:
        print(g["cost"], f"{g['ann']*100:.2f}%", f"{g['sharpe']:.2f}", f"{g['mdd']*100:.2f}%")
    print("\n样本内外:")
    for k, v in oos.items():
        print(k, {lab: f"{x['annual_return']*100:.2f}%/{x['sharpe']:.2f}/{x['max_drawdown']*100:.2f}%" for lab, x in v.items()})


if __name__ == "__main__":
    main()
