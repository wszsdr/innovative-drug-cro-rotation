# -*- coding: utf-8 -*-
"""创新药—CRO 板块轮动策略回测 v2（纯标准库实现，严格无未来信息）。

相对 v1 的改进：
  1. 板块组合改为「月末再平衡」并内扣再平衡换手成本（v1 为无成本日度再平衡）；
  2. 新增 S5 可辨识度自适应轮动：用动量差的 t 统计量衡量轮动信号是否可辨识，
     不可辨识时转为静态 50/50，而非强行轮动；
  3. 新增 S6 机器学习方向预测：逻辑回归逐月滚动训练（expanding window），
     仅用已实现标签训练，用作下月板块方向预测；
  4. 新增 S3-WF：参数按年滚动校准（walk-forward），消除参数选择上的前视；
  5. 新增 bootstrap 随机择时基准与月度 Newey-West 显著性检验。
"""

import csv, json, math, os, random, statistics

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
IDLE_ANNUAL = 0.02
COST = 0.001
WARMUP = 120
SPLIT = "2023-01-01"


# ------------------------------------------------------------------ 数据
def read_csv(name):
    rows = {}
    with open(os.path.join(BASE, name + ".csv"), "r", encoding="utf-8") as f:
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


def build_portfolio(member_prices, members, cost=COST):
    """等权组合：月末恢复等权并内扣换手成本，月内权重自然漂移。"""
    common = None
    for s in members:
        d = set(member_prices[s])
        common = d if common is None else (common & d)
    dates = sorted(common)
    n = len(members)
    w = [1.0 / n] * n
    nav, rets = [1.0], []
    cur = 1.0
    for i in range(1, len(dates)):
        rs = [member_prices[s][dates[i]] / member_prices[s][dates[i - 1]] - 1.0 for s in members]
        r = sum(w[j] * rs[j] for j in range(n))
        vals = [w[j] * (1 + rs[j]) for j in range(n)]
        tot = sum(vals)
        w = [v / tot for v in vals]
        if i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7]:
            turn = sum(abs(w[j] - 1.0 / n) for j in range(n))
            r -= turn * cost
            w = [1.0 / n] * n
        cur *= (1 + r)
        nav.append(cur)
        rets.append(r)
    return dates, nav, rets


def align(dates_a, val_a, dates_b, val_b):
    mb = dict(zip(dates_b, val_b))
    common = [d for d in dates_a if d in mb]
    return common, [dict(zip(dates_a, val_a))[d] for d in common], [mb[d] for d in common]


# ------------------------------------------------------------------ 统计工具
def ma(vals, n, i):
    if i + 1 < n:
        return None
    return sum(vals[i + 1 - n:i + 1]) / n


def roll_std(seq, n, i):
    if i + 1 < n:
        return None
    return statistics.pstdev(seq[i + 1 - n:i + 1])


def pearson(x, y):
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx = math.sqrt(sum((v - mx) ** 2 for v in x))
    dy = math.sqrt(sum((v - my) ** 2 for v in y))
    return num / (dx * dy) if dx and dy else 0.0


def max_drawdown(nav):
    peak, mdd = nav[0], 0.0
    for v in nav:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


def monthly_returns(nav, dates):
    out, start = [], nav[0]
    for i in range(1, len(dates)):
        if dates[i][:7] != dates[i - 1][:7]:
            out.append(nav[i - 1] / start - 1.0)
            start = nav[i - 1]
    out.append(nav[-1] / start - 1.0)
    return out


def nw_t_stat(x, lag=3):
    """月频收益均值的 Newey-West t 检验（H0: 均值=0）。"""
    n = len(x)
    if n < 8:
        return 0.0, 1.0
    m = sum(x) / n
    d = [v - m for v in x]
    g0 = sum(v * v for v in d) / n
    var = g0
    for l in range(1, lag + 1):
        gl = sum(d[i] * d[i - l] for i in range(l, n)) / n
        var += 2 * (1 - l / (lag + 1)) * gl
    var = max(var, 1e-12)
    se = math.sqrt(var / n)
    t = m / se if se else 0.0
    return t, math.erfc(abs(t) / math.sqrt(2))


def t_test_simple(x):
    n = len(x)
    if n < 2:
        return 0.0, 1.0
    m = sum(x) / n
    se = statistics.stdev(x) / math.sqrt(n)
    t = m / se if se else 0.0
    return t, math.erfc(abs(t) / math.sqrt(2))


def binom_p_two_sided(k, n, p=0.5):
    """二项分布双侧 p 值（n<=200 直接计算）。"""
    if n == 0:
        return 1.0
    pmf = [math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    obs = pmf[k]
    return min(1.0, sum(v for v in pmf if v <= obs * (1 + 1e-9)))


def alpha_beta(sr, br):
    n = min(len(sr), len(br))
    ms, mb = sum(sr[:n]) / n, sum(br[:n]) / n
    cov = sum((sr[i] - ms) * (br[i] - mb) for i in range(n)) / n
    var_b = sum((br[i] - mb) ** 2 for i in range(n)) / n
    beta = cov / var_b if var_b else 0.0
    return (ms - beta * mb) * TRADING_DAYS, beta


def perf(nav, dates):
    n = len(nav)
    years = n / TRADING_DAYS
    ann = (nav[-1] / nav[0]) ** (1 / years) - 1.0 if years > 0 else 0.0
    rr = [nav[i] / nav[i - 1] - 1 for i in range(1, n)]
    vol = statistics.pstdev(rr) * math.sqrt(TRADING_DAYS) if len(rr) > 1 else 0.0
    sharpe = (ann - RF_ANNUAL) / vol if vol > 0 else 0.0
    mdd = max_drawdown(nav)
    mr = monthly_returns(nav, dates)
    srt = sorted(rr)
    k = max(1, int(0.05 * len(srt)))
    return {
        "total_return": nav[-1] / nav[0] - 1.0, "annual_return": ann, "volatility": vol,
        "sharpe": sharpe, "max_drawdown": mdd, "calmar": ann / abs(mdd) if mdd < 0 else 0.0,
        "monthly_win": sum(1 for x in mr if x > 0) / len(mr) if mr else 0.0,
        "var95": srt[k - 1] if srt else 0.0,
        "cvar95": sum(srt[:k]) / k if srt else 0.0,
    }


# ------------------------------------------------------------------ 回测引擎
class Ctx:
    pass


def make_ctx(dates, px_a, px_b, ra, rb):
    c = Ctx()
    c.dates, c.px_a, c.px_b, c.ra, c.rb = dates, px_a, px_b, ra, rb
    return c


def sigma_of(ctx, kind, sig, vol_win=20):
    if kind == "A":
        seq = ctx.ra
    elif kind == "B":
        seq = ctx.rb
    else:
        seq = [0.5 * (ctx.ra[i] + ctx.rb[i]) for i in range(len(ctx.ra))]
    s = roll_std(seq, vol_win, sig)
    return s * math.sqrt(TRADING_DAYS) if s else None


def run_engine(ctx, chooser, *, use_vol=True, target_vol=0.15, cost=COST,
               start=None, end=None, want_segments=False):
    dates = ctx.dates
    idxs = [i for i in range(len(dates))
            if (not start or dates[i] >= start) and (not end or dates[i] <= end)]
    idle = IDLE_ANNUAL / TRADING_DAYS
    e_a = e_b = 0.0
    kind = None
    nav, nav_dates, nav_rets = [1.0], [dates[idxs[0]]], []
    wlog, holdlog, turnovers = [], [], []
    segs, seg_len, seg_kind, seg_w, seg_turn = [], 0, None, 0.0, 0.0

    def close_seg():
        if seg_len:
            segs.append((seg_len, seg_kind, seg_w, seg_turn))

    for k in range(1, len(idxs)):
        i, sig = idxs[k], idxs[k - 1]
        turnover = 0.0
        if kind is None or dates[i][:7] != dates[sig][:7]:
            new_kind = chooser(sig)
            w = 1.0
            if new_kind and use_vol:
                s = sigma_of(ctx, new_kind, sig)
                if s and s > 0:
                    w = min(1.0, target_vol / s)
            ne = {"A": (w, 0.0), "B": (0.0, w), "AB": (0.5 * w, 0.5 * w), None: (0.0, 0.0)}[new_kind]
            turnover = abs(ne[0] - e_a) + abs(ne[1] - e_b)
            e_a, e_b = ne
            kind = new_kind
            close_seg()
            seg_len, seg_kind, seg_w, seg_turn = 0, new_kind, w, turnover
        W = e_a + e_b
        if W > 0:
            va, vb = e_a * (1 + ctx.ra[i]), e_b * (1 + ctx.rb[i])
            r_inv = (va + vb) / W - 1.0
            e_a, e_b = va / (va + vb) * W, vb / (va + vb) * W
        else:
            r_inv = 0.0
        nav_ret = W * r_inv + (1 - W) * idle - turnover * cost
        nav.append(nav[-1] * (1 + nav_ret))
        nav_dates.append(dates[i])
        nav_rets.append(nav_ret)
        wlog.append(W)
        holdlog.append(kind)
        turnovers.append(turnover)
        seg_len += 1
    close_seg()
    out = [nav, nav_dates, nav_rets, wlog, holdlog, turnovers]
    if want_segments:
        out.append(segs)
    return out


def replay_segments(ctx, segs, idxs, cost=COST):
    """按给定的持仓段序列重放收益（用于 bootstrap 置换检验）。"""
    dates, idle = ctx.dates, IDLE_ANNUAL / TRADING_DAYS
    nav, rets = [1.0], []
    e_a = e_b = 0.0
    j = 1
    for (nd, kind, w, turn) in segs:
        ne = {"A": (w, 0.0), "B": (0.0, w), "AB": (0.5 * w, 0.5 * w), None: (0.0, 0.0)}[kind]
        turnover = abs(ne[0] - e_a) + abs(ne[1] - e_b)
        e_a, e_b = ne
        for _ in range(nd):
            if j >= len(idxs):
                break
            i = idxs[j]
            j += 1
            W = e_a + e_b
            if W > 0:
                va, vb = e_a * (1 + ctx.ra[i]), e_b * (1 + ctx.rb[i])
                r_inv = (va + vb) / W - 1.0
                e_a, e_b = va / (va + vb) * W, vb / (va + vb) * W
            else:
                r_inv = 0.0
            r = W * r_inv + (1 - W) * idle - (turnover * cost if _ == 0 else 0.0)
            nav.append(nav[-1] * (1 + r))
            rets.append(r)
    return nav, rets


# ------------------------------------------------------------------ 决策器
def rule_chooser(ctx, mom_win=120, ma_win=180, use_trend=True):
    def f(sig):
        if sig - mom_win < 0:
            return None
        mom_a = ctx.px_a[sig] / ctx.px_a[sig - mom_win] - 1
        mom_b = ctx.px_b[sig] / ctx.px_b[sig - mom_win] - 1
        target = "A" if mom_a >= mom_b else "B"
        if use_trend:
            ma_a, ma_b = ma(ctx.px_a, ma_win, sig), ma(ctx.px_b, ma_win, sig)
            ok_a = ma_a is not None and ctx.px_a[sig] > ma_a
            ok_b = ma_b is not None and ctx.px_b[sig] > ma_b
            if target == "A" and not ok_a:
                target = "B" if ok_b else None
            elif target == "B" and not ok_b:
                target = "A" if ok_a else None
        return target
    return f


def adaptive_chooser(ctx, mom_win=120, vol_win=20, tau=1.0):
    """可辨识度自适应轮动：IR 为动量差的 t 统计量。"""
    def f(sig):
        if sig - mom_win < 0:
            return None
        diff = (ctx.px_a[sig] / ctx.px_a[sig - mom_win] - 1) - \
               (ctx.px_b[sig] / ctx.px_b[sig - mom_win] - 1)
        d = [ctx.ra[j] - ctx.rb[j] for j in range(sig - vol_win + 1, sig + 1)]
        sd = statistics.pstdev(d) if len(d) > 2 else 0.0
        denom = sd * math.sqrt(mom_win)
        ir = diff / denom if denom > 0 else 0.0
        if abs(ir) < tau:
            return "AB"
        return "A" if ir > 0 else "B"
    return f


def decision_points(dates, start=None, end=None):
    """返回 [(i, sig)]：i 为执行日（新月首个交易日），sig 为信号日（上月最后交易日）。"""
    idxs = [i for i in range(len(dates))
            if (not start or dates[i] >= start) and (not end or dates[i] <= end)]
    pts = []
    for k in range(1, len(idxs)):
        if k == 1 or dates[idxs[k]][:7] != dates[idxs[k - 1]][:7]:
            pts.append((idxs[k], idxs[k - 1]))
    return pts


# ------------------------------------------------------------------ 机器学习
def logistic_fit(X, y, n_iter=500, lr=0.3, l2=0.05):
    nf = len(X[0])
    w = [0.0] * nf
    b = 0.0
    n = len(X)
    for _ in range(n_iter):
        gw = [0.0] * nf
        gb = 0.0
        for xi, yi in zip(X, y):
            z = sum(w[j] * xi[j] for j in range(nf)) + b
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            e = p - yi
            for j in range(nf):
                gw[j] += e * xi[j]
            gb += e
        for j in range(nf):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
        b -= lr * gb / n
    return w, b


def ml_features(ctx, sig, mom_win=120, corr_win=60, vol_win=20):
    if sig - mom_win < 0:
        return None
    m120 = (ctx.px_a[sig] / ctx.px_a[sig - mom_win] - 1) - (ctx.px_b[sig] / ctx.px_b[sig - mom_win] - 1)
    m60 = (ctx.px_a[sig] / ctx.px_a[sig - 60] - 1) - (ctx.px_b[sig] / ctx.px_b[sig - 60] - 1)
    ra = ctx.ra[sig - corr_win + 1:sig + 1]
    rb = ctx.rb[sig - corr_win + 1:sig + 1]
    corr = pearson(ra, rb)
    disp = statistics.pstdev([ra[j] - rb[j] for j in range(len(ra))]) if len(ra) > 2 else 0.0
    va = roll_std(ctx.ra, vol_win, sig) or 0.0
    vb = roll_std(ctx.rb, vol_win, sig) or 0.0
    voldiff = (va - vb) * math.sqrt(TRADING_DAYS)
    ma_a, ma_b = ma(ctx.px_a, 180, sig), ma(ctx.px_b, 180, sig)
    trend = (1 if ma_a and ctx.px_a[sig] > ma_a else 0) - (1 if ma_b and ctx.px_b[sig] > ma_b else 0)
    return [m120, m60, corr, disp, voldiff, trend]


def build_ml(ctx, start=None, end=None, min_train=24):
    """逐月滚动训练逻辑回归，返回 (pred_by_date, eval_records)。"""
    dates = ctx.dates
    pts = decision_points(dates, start, end)
    feats = {}
    for (i, sig) in pts:
        f = ml_features(ctx, sig)
        if f:
            feats[sig] = f
    labels = {}
    for k in range(len(pts) - 1):
        sig, sig_next = pts[k][1], pts[k + 1][1]
        ra_ = ctx.px_a[sig_next] / ctx.px_a[sig] - 1
        rb_ = ctx.px_b[sig_next] / ctx.px_b[sig] - 1
        labels[sig] = 1 if ra_ >= rb_ else 0

    pred, evals = {}, []
    for k in range(len(pts)):
        i, sig = pts[k]
        train_sigs = [pts[j][1] for j in range(0, k) if pts[j][1] in feats and pts[j][1] in labels]
        if len(train_sigs) < min_train or sig not in feats:
            continue
        X = [feats[s] for s in train_sigs]
        y = [labels[s] for s in train_sigs]
        nf = len(X[0])
        mu = [sum(x[j] for x in X) / len(X) for j in range(nf)]
        sd = [max(statistics.pstdev([x[j] for x in X]), 1e-9) for j in range(nf)]
        Xs = [[(x[j] - mu[j]) / sd[j] for j in range(nf)] for x in X]
        w, b = logistic_fit(Xs, y)
        xs = [(feats[sig][j] - mu[j]) / sd[j] for j in range(nf)]
        z = sum(w[j] * xs[j] for j in range(nf)) + b
        p = 1.0 / (1.0 + math.exp(-z))
        pred[sig] = "A" if p >= 0.5 else "B"
        if sig in labels:
            evals.append({"date": dates[sig], "pred": pred[sig], "y": labels[sig], "p": p})
    return pred, evals


def ml_chooser(pred, ctx, fallback_mom=120):
    base = rule_chooser(ctx, mom_win=fallback_mom, use_trend=False)

    def f(sig):
        if sig in pred:
            return pred[sig]
        return base(sig)
    return f


# ------------------------------------------------------------------ 主流程
def main():
    random.seed(20261028)
    member_px = {s: read_csv(s) for s in INNOV_MEMBERS + CRO_MEMBERS}
    hs_rows = read_csv("sh000300")
    idx_rows = read_csv("cs931152")

    d_a, nav_a, ret_a = build_portfolio(member_px, INNOV_MEMBERS)
    d_b, nav_b, ret_b = build_portfolio(member_px, CRO_MEMBERS)

    hs_dates, hs_px = to_series(hs_rows)
    map_a, map_b, map_m = dict(zip(d_a, nav_a)), dict(zip(d_b, nav_b)), dict(zip(hs_dates, hs_px))
    dates = sorted(set(map_a) & set(map_b) & set(map_m))
    px_a = [map_a[d] for d in dates]
    px_b = [map_b[d] for d in dates]
    px_m = [map_m[d] for d in dates]

    ra = [0.0] + [px_a[i] / px_a[i - 1] - 1 for i in range(1, len(dates))]
    rb = [0.0] + [px_b[i] / px_b[i - 1] - 1 for i in range(1, len(dates))]
    rm = [0.0] + [px_m[i] / px_m[i - 1] - 1 for i in range(1, len(dates))]

    ctx = make_ctx(dates, px_a, px_b, ra, rb)
    start_date = dates[WARMUP]

    # 效度检验
    idx_d, idx_p = to_series(idx_rows)
    idx_ret = {idx_d[i]: idx_p[i] / idx_p[i - 1] - 1 for i in range(1, len(idx_d))}
    a_ret = {dates[i]: ra[i] for i in range(1, len(dates))}
    common = sorted(set(idx_ret) & set(a_ret))
    validity = {"window": [common[0], common[-1]], "n": len(common),
                "corr": pearson([a_ret[d] for d in common], [idx_ret[d] for d in common])}

    results = {}

    def add(name, nav, nd, rets=None, wlog=None):
        p = perf(nav, nd)
        results[name] = {"perf": p, "nav": nav, "dates": nd,
                         "rets": rets if rets is not None else [nav[i] / nav[i - 1] - 1 for i in range(1, len(nav))],
                         "w": wlog or []}
        return results[name]

    # ---- 策略
    specs = [
        ("S1_动量轮动", rule_chooser(ctx, 120, 180, False), dict(use_vol=False)),
        ("S2_动量+趋势", rule_chooser(ctx, 120, 180, True), dict(use_vol=False)),
        ("S3_动量+趋势+波动率", rule_chooser(ctx, 120, 180, True), dict(use_vol=True, target_vol=0.15)),
        ("S4_波动率目标25%", rule_chooser(ctx, 120, 180, True), dict(use_vol=True, target_vol=0.25)),
        ("S5_自适应轮动", adaptive_chooser(ctx, 120, 20, 1.0), dict(use_vol=True, target_vol=0.15)),
    ]
    for name, ch, kw in specs:
        nav, nd, rets, wl, hl, tl = run_engine(ctx, ch, start=start_date, **kw)
        add(name, nav, nd, rets, wl)

    # S6 机器学习（逐月滚动训练，仅在其有效区间内评价）
    pred, evals = build_ml(ctx, start=start_date)
    ml_dates = sorted(evals and [e["date"] for e in evals] or [])
    ml_start = ml_dates[0] if ml_dates else start_date
    nav, nd, rets, wl, hl, tl = run_engine(ctx, ml_chooser(pred, ctx), start=ml_start,
                                       use_vol=True, target_vol=0.15)
    add("S6_机器学习方向预测", nav, nd, rets, wl)
    # 同窗口对照
    for name, ch, kw in specs[:4]:
        nav2, nd2, rets2, wl2, hl2, tl2 = run_engine(ctx, ch, start=ml_start, **kw)
        results[name]["same_window"] = perf(nav2, nd2)
    bench_ml = {}

    # ---- 基准
    def buy_hold(px, start=start_date, end=None):
        idxs = [i for i in range(len(dates)) if dates[i] >= start and (not end or dates[i] <= end)]
        base = px[idxs[0]]
        return [px[i] / base for i in idxs], [dates[i] for i in idxs]

    nav, nd = buy_hold(px_a); add("B1_创新药买入持有", nav, nd)
    nav, nd = buy_hold(px_b); add("B2_CRO买入持有", nav, nd)
    nav, nd = buy_hold(px_m); add("B4_沪深300", nav, nd)
    # 静态 50/50（月末再平衡）
    idxs = [i for i in range(len(dates)) if dates[i] >= start_date]
    nav, nd = [1.0], [dates[idxs[0]]]
    wa = wb = 0.5
    cur = 1.0
    for k in range(1, len(idxs)):
        i, prev = idxs[k], idxs[k - 1]
        va, vb = wa * (1 + ra[i]), wb * (1 + rb[i])
        tot = va + vb
        r = tot - 1
        wa, wb = va / tot, vb / tot
        if dates[i][:7] != dates[prev][:7]:
            turn = abs(wa - 0.5) + abs(wb - 0.5)
            r -= turn * COST
            wa = wb = 0.5
        cur *= (1 + r)
        nav.append(cur); nd.append(dates[i])
    add("B3_静态50/50", nav, nd)

    # ---- alpha/beta 与显著性
    bench = results["B4_沪深300"]["rets"]
    for k, v in results.items():
        m = min(len(v["rets"]), len(bench))
        v["perf"]["alpha"], v["perf"]["beta"] = alpha_beta(v["rets"][:m], bench[:m])
        diff = [v["rets"][i] - bench[i] for i in range(m)]
        v["perf"]["t_daily"], v["perf"]["p_daily"] = t_test_simple(diff)
        mr_s = monthly_returns(v["nav"], v["dates"])
        mr_b = monthly_returns(results["B4_沪深300"]["nav"], results["B4_沪深300"]["dates"])
        diff_m = [mr_s[i] - mr_b[i] for i in range(min(len(mr_s), len(mr_b)))]
        v["perf"]["t_monthly_nw"], v["perf"]["p_monthly_nw"] = nw_t_stat(diff_m)

    # ---- 分年度
    yearly = {}
    for k, v in results.items():
        nav, d = v["nav"], v["dates"]
        by_year, start_nav, sy = {}, nav[0], d[0][:4]
        for i in range(1, len(d)):
            if d[i][:4] != d[i - 1][:4]:
                by_year[sy] = nav[i - 1] / start_nav - 1
                start_nav, sy = nav[i - 1], d[i][:4]
        by_year[sy] = nav[-1] / start_nav - 1
        yearly[k] = by_year

    # ---- 参数网格（S3）
    grid = []
    for mom in (40, 60, 80, 120):
        for maw in (60, 120, 180):
            nav, nd, *_ = run_engine(ctx, rule_chooser(ctx, mom, maw, True), start=start_date,
                                     use_vol=True, target_vol=0.15)
            p = perf(nav, nd)
            grid.append({"mom": mom, "ma": maw, "ann": p["annual_return"],
                         "sharpe": p["sharpe"], "mdd": p["max_drawdown"]})

    # ---- 阈值敏感性（S5）
    tau_grid = []
    for tau in (0.5, 1.0, 1.5, 2.0):
        nav, nd, *_ = run_engine(ctx, adaptive_chooser(ctx, 120, 20, tau), start=start_date,
                                 use_vol=True, target_vol=0.15)
        p = perf(nav, nd)
        tau_grid.append({"tau": tau, "ann": p["annual_return"], "sharpe": p["sharpe"],
                         "mdd": p["max_drawdown"]})

    # ---- 成本敏感性（S3 / S5）
    cost_grid = []
    for c in (0.0005, 0.001, 0.002, 0.003):
        nav, nd, *_ = run_engine(ctx, rule_chooser(ctx, 120, 180, True), start=start_date,
                                 use_vol=True, target_vol=0.15, cost=c)
        p3 = perf(nav, nd)
        nav, nd, *_ = run_engine(ctx, adaptive_chooser(ctx, 120, 20, 1.0), start=start_date,
                                 use_vol=True, target_vol=0.15, cost=c)
        p5 = perf(nav, nd)
        cost_grid.append({"cost": c, "ann_s3": p3["annual_return"], "sharpe_s3": p3["sharpe"],
                          "ann_s5": p5["annual_return"], "sharpe_s5": p5["sharpe"]})

    # ---- 样本内 / 样本外
    oos = {}
    for k, (ch, kw) in {n: (c, k_) for n, c, k_ in specs}.items():
        res = {}
        for label, s, e in [("样本内", start_date, SPLIT), ("样本外", SPLIT, None)]:
            nav, nd, *_ = run_engine(ctx, ch, start=s, end=e, **kw)
            res[label] = perf(nav, nd)
        oos[k] = res
    for k in ["B1_创新药买入持有", "B2_CRO买入持有", "B3_静态50/50", "B4_沪深300"]:
        px = {"B1_创新药买入持有": px_a, "B2_CRO买入持有": px_b, "B4_沪深300": px_m}[k] if k != "B3_静态50/50" else None
        res = {}
        for label, s, e in [("样本内", start_date, SPLIT), ("样本外", SPLIT, None)]:
            if k == "B3_静态50/50":
                idxs = [i for i in range(len(dates)) if dates[i] >= s and (not e or dates[i] <= e)]
                nav, cur, wa, wb = [1.0], 1.0, 0.5, 0.5
                for kk in range(1, len(idxs)):
                    i, prev = idxs[kk], idxs[kk - 1]
                    va, vb = wa * (1 + ra[i]), wb * (1 + rb[i])
                    tot = va + vb
                    r = tot - 1
                    wa, wb = va / tot, vb / tot
                    if dates[i][:7] != dates[prev][:7]:
                        r -= (abs(wa - 0.5) + abs(wb - 0.5)) * COST
                        wa = wb = 0.5
                    cur *= (1 + r)
                    nav.append(cur)
                res[label] = perf(nav, [dates[i] for i in idxs])
            else:
                nav, nd = buy_hold(px, s, e)
                res[label] = perf(nav, nd)
        oos[k] = res

    # ---- walk-forward 参数校准（每年用截至上年末的网格最优）
    wf_years = {}
    years = sorted(set(d[:4] for d in dates if d >= dates[WARMUP]))
    wf_params = {}
    for y in years:
        if y <= years[0]:
            wf_params[y] = (120, 180)
            continue
        best, best_s = (120, 180), -9e9
        for mom in (40, 60, 80, 120):
            for maw in (60, 120, 180):
                nav, nd, *_ = run_engine(ctx, rule_chooser(ctx, mom, maw, True),
                                         start=start_date, end=str(int(y) - 1) + "-12-31",
                                         use_vol=True, target_vol=0.15)
                s = perf(nav, nd)["sharpe"]
                if s > best_s:
                    best_s, best = s, (mom, maw)
        wf_params[y] = best
    idxs_all = [i for i in range(len(dates)) if dates[i] >= start_date]
    nav, nd, rets_wf, wl, hl, = [1.0], [dates[idxs_all[0]]], [], [], []
    # 逐年拼接
    for y in years:
        s, e = y + "-01-01", y + "-12-31"
        mom, maw = wf_params[y]
        n2, d2, r2, w2, h2, t2 = run_engine(ctx, rule_chooser(ctx, mom, maw, True), start=s, end=e,
                                        use_vol=True, target_vol=0.15)
        scale = nav[-1]
        for j in range(1, len(n2)):
            nav.append(scale * n2[j]); nd.append(d2[j]); rets_wf.append(r2[j - 1]); wl.append(w2[j - 1])
    add("S7_滚动参数校准", nav, nd, rets_wf, wl)
    m = min(len(rets_wf), len(bench))
    results["S7_滚动参数校准"]["perf"]["alpha"], results["S7_滚动参数校准"]["perf"]["beta"] = alpha_beta(rets_wf, bench[:m])
    diff = [rets_wf[i] - bench[i] for i in range(m)]
    results["S7_滚动参数校准"]["perf"]["t_daily"], results["S7_滚动参数校准"]["perf"]["p_daily"] = t_test_simple(diff)
    mr_s = monthly_returns(nav, nd)
    mr_b = monthly_returns(results["B4_沪深300"]["nav"], results["B4_沪深300"]["dates"])
    dm = [mr_s[i] - mr_b[i] for i in range(min(len(mr_s), len(mr_b)))]
    results["S7_滚动参数校准"]["perf"]["t_monthly_nw"], results["S7_滚动参数校准"]["perf"]["p_monthly_nw"] = nw_t_stat(dm)
    by_year, start_nav, sy = {}, nav[0], nd[0][:4]
    for i in range(1, len(nd)):
        if nd[i][:4] != nd[i - 1][:4]:
            by_year[sy] = nav[i - 1] / start_nav - 1
            start_nav, sy = nav[i - 1], nd[i][:4]
    by_year[sy] = nav[-1] / start_nav - 1
    yearly["S7_滚动参数校准"] = by_year

    # ---- bootstrap 随机择时基准
    boot = {}
    for name, ch, kw in [("S1_动量轮动", rule_chooser(ctx, 120, 180, False), dict(use_vol=False)),
                         ("S3_动量+趋势+波动率", rule_chooser(ctx, 120, 180, True), dict(use_vol=True, target_vol=0.15)),
                         ("S5_自适应轮动", adaptive_chooser(ctx, 120, 20, 1.0), dict(use_vol=True, target_vol=0.15))]:
        nav, nd, rets, wl, hl, tl, segs = run_engine(ctx, ch, start=start_date, want_segments=True, **kw)
        idxs = [i for i in range(len(dates)) if dates[i] >= start_date]
        real = perf(nav, nd)
        sims = []
        for _ in range(1000):
            ss = segs[:]
            random.shuffle(ss)
            n2, r2 = replay_segments(ctx, ss, idxs)
            if len(n2) > 10:
                sims.append(perf(n2, nd[:len(n2)]))
        anns = sorted(s["annual_return"] for s in sims)
        shps = sorted(s["sharpe"] for s in sims)
        boot[name] = {
            "real_ann": real["annual_return"], "real_sharpe": real["sharpe"],
            "sim_ann_median": anns[len(anns) // 2], "sim_sharpe_median": shps[len(shps) // 2],
            "pct_ann": sum(1 for x in anns if x < real["annual_return"]) / len(anns),
            "pct_sharpe": sum(1 for x in shps if x < real["sharpe"]) / len(shps),
            "sim_ann_p95": anns[int(0.95 * len(anns))], "sim_sharpe_p95": shps[int(0.95 * len(shps))],
        }

    # ---- 条件分析：按可辨识度 IR 分组看轮动相对 50/50 的月超额
    pts = decision_points(dates, start_date)
    groups = {"低(|IR|<1)": [], "中(1~2)": [], "高(>2)": []}
    corr_groups = {"低(<0.6)": [], "中(0.6~0.7)": [], "高(>0.7)": []}
    disp_pairs = []
    for k in range(len(pts) - 1):
        i, sig = pts[k]
        i_next, sig_next = pts[k + 1]
        f = ml_features(ctx, sig)
        if not f:
            continue
        diff = f[0]
        d = [ra[j] - rb[j] for j in range(sig - 19 + 1, sig + 1)]
        sd = statistics.pstdev(d) if len(d) > 2 else 0.0
        ir = diff / (sd * math.sqrt(120)) if sd > 0 else 0.0
        # 轮动（持强者）相对 50/50 的月收益差
        ra_p = px_a[sig_next] / px_a[sig] - 1
        rb_p = px_b[sig_next] / px_b[sig] - 1
        rot = ra_p if ir >= 0 else rb_p
        exc = rot - 0.5 * (ra_p + rb_p)
        key = "低(|IR|<1)" if abs(ir) < 1 else ("中(1~2)" if abs(ir) < 2 else "高(>2)")
        groups[key].append(exc)
        c = pearson(ra[sig - 59:sig + 1], rb[sig - 59:sig + 1])
        ck = "低(<0.6)" if c < 0.6 else ("中(0.6~0.7)" if c < 0.7 else "高(>0.7)")
        corr_groups[ck].append(exc)
        dsp = statistics.pstdev([ra[j] - rb[j] for j in range(sig - 59, sig + 1)]) * math.sqrt(TRADING_DAYS)
        disp_pairs.append((dsp, exc))
    cond = {}
    for gname, g in list(groups.items()) + list(corr_groups.items()):
        if g:
            t, p = t_test_simple(g)
            cond[gname] = {"n": len(g), "mean_excess": sum(g) / len(g),
                           "win_rate": sum(1 for x in g if x > 0) / len(g), "t": t, "p": p}
    if disp_pairs:
        ds = sorted(x[0] for x in disp_pairs)
        lo, hi = ds[len(ds) // 3], ds[2 * len(ds) // 3]
        for gname, sel in [("低离散度(下1/3)", [e for d_, e in disp_pairs if d_ <= lo]),
                           ("中离散度", [e for d_, e in disp_pairs if lo < d_ <= hi]),
                           ("高离散度(上1/3)", [e for d_, e in disp_pairs if d_ > hi])]:
            if sel:
                t, p = t_test_simple(sel)
                cond[gname] = {"n": len(sel), "mean_excess": sum(sel) / len(sel),
                               "win_rate": sum(1 for x in sel if x > 0) / len(sel), "t": t, "p": p}

    # ---- 稳健性：用公开指数替代自建创新药组合
    idx_dates, idx_px = to_series(idx_rows)
    dates2 = [d for d in dates if d in set(idx_dates)]
    mp = dict(zip(idx_dates, idx_px))
    px_i = [mp[d] for d in dates2]
    px_c = dict(zip(dates, px_b))
    px_c2 = [px_c[d] for d in dates2]
    ra2 = [0.0] + [px_i[i] / px_i[i - 1] - 1 for i in range(1, len(dates2))]
    rb2 = [0.0] + [px_c2[i] / px_c2[i - 1] - 1 for i in range(1, len(dates2))]
    ctx2 = make_ctx(dates2, px_i, px_c2, ra2, rb2)
    start2 = dates2[WARMUP]
    alt = {}
    for name, ch, kw in [("S1_动量轮动", rule_chooser(ctx2, 120, 180, False), dict(use_vol=False)),
                         ("S3_动量+趋势+波动率", rule_chooser(ctx2, 120, 180, True), dict(use_vol=True, target_vol=0.15)),
                         ("S5_自适应轮动", adaptive_chooser(ctx2, 120, 20, 1.0), dict(use_vol=True, target_vol=0.15))]:
        nav, nd, *_ = run_engine(ctx2, ch, start=start2, **kw)
        alt[name] = perf(nav, nd)
        alt[name]["window"] = [nd[0], nd[-1]]

    # ---- 持仓统计
    hold_stat = {}
    for name, ch, kw in specs + [("S6_机器学习方向预测", ml_chooser(pred, ctx), dict(use_vol=True, target_vol=0.15))]:
        st = start_date if name != "S6_机器学习方向预测" else ml_start
        nav, nd, rets, wl, hl, tl = run_engine(ctx, ch, start=st, **kw)
        hold_stat[name] = {
            "A_创新药": sum(1 for h in hl if h == "A") / len(hl),
            "B_CRO": sum(1 for h in hl if h == "B") / len(hl),
            "AB_静态50/50": sum(1 for h in hl if h == "AB") / len(hl),
            "空仓": sum(1 for h in hl if h is None) / len(hl),
            "平均仓位": sum(wl) / len(wl),
            "调仓次数": sum(1 for t in tl if t > 0),
            "年双边换手率": sum(tl) / (len(tl) / TRADING_DAYS),
        }

    # ---- 相关性
    corr_year = {}
    for y in sorted(set(d[:4] for d in dates)):
        idx = [i for i in range(1, len(dates)) if dates[i][:4] == y]
        if len(idx) > 30:
            corr_year[y] = pearson([ra[i] for i in idx], [rb[i] for i in idx])
    corr_stat = {"全样本": pearson(ra[1:], rb[1:]), "分年": corr_year}

    # ---- 机器学习评价
    ml_eval = {}
    if evals:
        hit = [1 if e["pred"] == ("A" if e["y"] == 1 else "B") else 0 for e in evals]
        oos_h = [1 if e["pred"] == ("A" if e["y"] == 1 else "B") else 0
                 for e in evals if e["date"] >= SPLIT]
        ml_eval = {
            "n_total": len(hit), "acc_total": sum(hit) / len(hit),
            "p_total": binom_p_two_sided(sum(hit), len(hit)),
            "n_oos": len(oos_h), "acc_oos": (sum(oos_h) / len(oos_h)) if oos_h else None,
            "p_oos": binom_p_two_sided(sum(oos_h), len(oos_h)) if oos_h else None,
            "start": evals[0]["date"], "end": evals[-1]["date"],
        }

    out = {
        "meta": {
            "start": start_date, "end": dates[-1], "n_days": len(dates) - WARMUP,
            "warmup_days": WARMUP, "split": SPLIT,
            "innov_members": [NAMES[s] for s in INNOV_MEMBERS],
            "cro_members": [NAMES[s] for s in CRO_MEMBERS],
            "validity_vs_cs931152": validity,
            "portfolio_rebalance": "月末等权再平衡，换手按单边0.1%内扣",
            "ml_window": [ml_eval.get("start"), ml_eval.get("end")] if ml_eval else None,
        },
        "summary": {k: v["perf"] for k, v in results.items()},
        "yearly": yearly,
        "grid": grid, "tau_grid": tau_grid, "cost_grid": cost_grid,
        "oos": oos, "bootstrap": boot, "cond": cond, "alt_index": alt,
        "hold_stat": hold_stat, "corr_stat": corr_stat, "ml_eval": ml_eval,
        "ml_compare": {k: results[k].get("same_window") for k in
                       ["S1_动量轮动", "S2_动量+趋势", "S3_动量+趋势+波动率", "S4_波动率目标25%"]},
    }
    with open(os.path.join(OUTDIR, "results_v2.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    keys = ["S1_动量轮动", "S2_动量+趋势", "S3_动量+趋势+波动率", "S4_波动率目标25%",
            "S5_自适应轮动", "S6_机器学习方向预测", "S7_滚动参数校准",
            "B1_创新药买入持有", "B2_CRO买入持有", "B3_静态50/50", "B4_沪深300"]
    with open(os.path.join(OUTDIR, "nav_curves_v2.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date"] + keys)
        ser = {k: dict(zip(v["dates"], v["nav"])) for k, v in results.items()}
        for dd in sorted(set(dates)):
            w.writerow([dd] + [round(ser[k][dd], 4) if dd in ser[k] else "" for k in keys])

    print("META", json.dumps(out["meta"], ensure_ascii=False))
    for k in keys:
        p = results[k]["perf"]
        print(f"{k:22s} 年化{p['annual_return']*100:7.2f}% 波动{p['volatility']*100:6.2f}% 夏普{p['sharpe']:5.2f} "
              f"回撤{p['max_drawdown']*100:7.2f}% Calmar{p['calmar']:5.2f} 月胜{p['monthly_win']*100:5.1f}% "
              f"a{p['alpha']*100:6.2f}% b{p['beta']:4.2f} t日{p['t_daily']:5.2f} t月NW{p.get('t_monthly_nw',0):5.2f}")
    print("\nML", json.dumps(ml_eval, ensure_ascii=False))
    print("\nBOOT", json.dumps(boot, ensure_ascii=False, indent=1))
    print("\nCOND", json.dumps(cond, ensure_ascii=False))
    print("\nALT(指数替代)", json.dumps({k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in alt.items()}, ensure_ascii=False))
    print("\nTAU", json.dumps(tau_grid, ensure_ascii=False))
    print("\nGRID", json.dumps(grid, ensure_ascii=False))
    print("\nCOST", json.dumps(cost_grid, ensure_ascii=False))
    print("\nOOS")
    for k, v in oos.items():
        print(" ", k, {lab: f"{x['annual_return']*100:.2f}%/{x['sharpe']:.2f}/{x['max_drawdown']*100:.2f}%" for lab, x in v.items()})
    print("\nHOLD", json.dumps(hold_stat, ensure_ascii=False))
    print("\nYEARLY")
    for k in keys:
        print(" ", k, {y: f"{x*100:.1f}" for y, x in yearly.get(k, {}).items()})
    print("\nCORR", json.dumps(corr_stat, ensure_ascii=False))


if __name__ == "__main__":
    main()
