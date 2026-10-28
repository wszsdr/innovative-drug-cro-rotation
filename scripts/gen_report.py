import json

NAV = json.load(open("results/nav_sampled.json", encoding="utf-8"))
T = json.load(open("results/tables.json", encoding="utf-8"))
R = json.load(open("results/results.json", encoding="utf-8"))

summary = R["summary"]
order = ["S1_动量轮动", "S2_动量+趋势", "S3_主策略", "S4_波动率目标25%",
         "B1_创新药买入持有", "B2_CRO买入持有", "B3_静态50/50", "B4_沪深300"]
labels = {"S1_动量轮动": "S1 动量轮动", "S2_动量+趋势": "S2 动量+趋势",
          "S3_主策略": "S3 主策略(波动率目标15%)", "S4_波动率目标25%": "S4 波动率目标25%",
          "B1_创新药买入持有": "B1 创新药买入持有", "B2_CRO买入持有": "B2 CRO买入持有",
          "B3_静态50/50": "B3 静态50/50", "B4_沪深300": "B4 沪深300"}


def pct(x, d=2):
    return f"{x*100:.{d}f}%"


rows = []
for k in order:
    v = summary[k]
    cls = "pos" if v["annual_return"] > 0 else "neg"
    rows.append(
        f"<tr><td class='nm'>{labels[k]}</td>"
        f"<td class='{cls}'>{pct(v['total_return'])}</td>"
        f"<td class='{cls}'>{pct(v['annual_return'])}</td>"
        f"<td>{pct(v['volatility'])}</td>"
        f"<td>{v['sharpe']:.3f}</td>"
        f"<td class='neg'>{pct(v['max_drawdown'])}</td>"
        f"<td>{v['calmar']:.3f}</td>"
        f"<td>{pct(v['monthly_win'],1)}</td>"
        f"<td>{v['beta']:.2f}</td>"
        f"<td>{pct(v['var95'])}</td>"
        f"<td>{pct(v['cvar95'])}</td></tr>"
    )
rows = "\n".join(rows)

years = T["years"]
series_names = [labels[k] for k in T["yearly"].keys()]
yearly_series = [{"name": labels[k], "type": "bar", "data": v} for k, v in T["yearly"].items()]

grid_rows = "\n".join(
    f"<tr><td>{g[0]}</td><td>{g[1]}</td><td>{g[2]:.2f}%</td><td>{g[3]:.2f}</td><td class='neg'>{g[4]:.2f}%</td></tr>"
    for g in T["grid"]
)
cost_rows = "\n".join(
    f"<tr><td>{c[0]*100:.2f}%</td><td>{c[1]:.2f}%</td><td>{c[2]:.2f}</td></tr>"
    for c in T["cost"]
)
corr_rows = "\n".join(
    f"<tr><td>{y}</td><td>{v}</td></tr>" for y, v in sorted(T["corr_year"].items())
)

oos = R["oos"]
oos_rows = "\n".join(
    f"<tr><td class='nm'>{labels[k]}</td>"
    f"<td>{pct(v['样本内']['annual_return'])}</td><td>{v['样本内']['sharpe']:.2f}</td>"
    f"<td class='neg'>{pct(v['样本内']['max_drawdown'])}</td>"
    f"<td>{pct(v['样本外']['annual_return'])}</td><td>{v['样本外']['sharpe']:.2f}</td>"
    f"<td class='neg'>{pct(v['样本外']['max_drawdown'])}</td></tr>"
    for k, v in oos.items() if k in labels
)

hold = R["hold_stat"]
meta = R["meta"]

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>创新药与CRO板块轮动策略回测报告</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
:root {{ --bg:#f7f8fa; --card:#ffffff; --line:#e3e6ea; --txt:#1f2328; --sub:#5b6470; --red:#c0392b; --green:#1e8e57; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:24px; background:var(--bg); color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; font-size:14px; line-height:1.7; }}
.wrap {{ max-width:1180px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 6px; font-weight:600; }}
h2 {{ font-size:16px; margin:28px 0 12px; font-weight:600; border-left:3px solid #2b6cb0; padding-left:8px; }}
.sub {{ color:var(--sub); font-size:13px; margin-bottom:18px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin-bottom:16px; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }}
.kpi .k {{ color:var(--sub); font-size:12px; }}
.kpi .v {{ font-size:22px; font-weight:600; margin-top:4px; }}
.kpi .n {{ color:var(--sub); font-size:12px; margin-top:2px; }}
.pos {{ color:var(--red); }} .neg {{ color:var(--green); }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ padding:7px 8px; border-bottom:1px solid var(--line); text-align:right; }}
th {{ background:#f1f3f5; color:var(--sub); font-weight:600; text-align:right; }}
td.nm, th.nm {{ text-align:left; }}
tr:hover td {{ background:#fafbfc; }}
.tabs {{ display:flex; gap:8px; margin-bottom:10px; }}
.tab {{ padding:5px 14px; border:1px solid var(--line); border-radius:6px; background:#fff; cursor:pointer; font-size:13px; }}
.tab.on {{ background:#2b6cb0; color:#fff; border-color:#2b6cb0; }}
.note {{ color:var(--sub); font-size:12px; margin-top:10px; }}
.grid2 {{ display:grid; grid-template-columns:1.4fr 1fr; gap:16px; }}
ul {{ margin:8px 0 0 18px; padding:0; }}
li {{ margin-bottom:4px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>创新药与 CRO 板块轮动交易策略回测报告</h1>
  <div class="sub">回测区间 {meta['start']} 至 {meta['end']}（{meta['n_days']} 个交易日）｜月度调仓｜信号滞后一日执行｜单边交易成本 0.1%｜数据导出时点 2026-10-15</div>

  <div class="kpis">
    <div class="kpi"><div class="k">动量轮动年化收益</div><div class="v pos">{pct(summary['S1_动量轮动']['annual_return'])}</div><div class="n">夏普 {summary['S1_动量轮动']['sharpe']:.2f}，t={summary['S1_动量轮动']['t_vs_hs300']:.2f}</div></div>
    <div class="kpi"><div class="k">主策略年化波动率</div><div class="v">{pct(summary['S3_主策略']['volatility'])}</div><div class="n">低于沪深300的 {pct(summary['B4_沪深300']['volatility'])}</div></div>
    <div class="kpi"><div class="k">主策略最大回撤</div><div class="v neg">{pct(summary['S3_主策略']['max_drawdown'])}</div><div class="n">CRO买入持有为 {pct(summary['B2_CRO买入持有']['max_drawdown'])}</div></div>
    <div class="kpi"><div class="k">沪深300年化收益</div><div class="v">{pct(summary['B4_沪深300']['annual_return'])}</div><div class="n">夏普 {summary['B4_沪深300']['sharpe']:.2f}</div></div>
  </div>

  <div class="card" style="margin-top:16px">
    <strong>核心结论：</strong>创新药与 CRO 两个子板块之间存在可利用的中期相对强弱差异，纯动量轮动（S1）在样本内取得年化 {pct(summary['S1_动量轮动']['annual_return'])}、夏普 {summary['S1_动量轮动']['sharpe']:.2f} 的表现，优于任一单一板块买入持有与静态 50/50 组合；加入 15% 波动率目标后（S3），年化收益降至 {pct(summary['S3_主策略']['annual_return'])}，但波动率与最大回撤分别降至 {pct(summary['S3_主策略']['volatility'])} 与 {pct(summary['S3_主策略']['max_drawdown'])}，β 降至 {summary['S3_主策略']['beta']:.2f}。样本外（2023 年后）超额收益显著衰减，策略优势不应被外推。
  </div>

  <h2>净值曲线（起点标准化为 1）</h2>
  <div class="card">
    <div class="tabs">
      <div class="tab on" id="tabChart">图</div>
      <div class="tab" id="tabTable">表</div>
    </div>
    <div id="navChart" style="width:100%;height:420px;"></div>
    <div id="navTable" style="display:none;max-height:420px;overflow:auto;">
      <table><thead><tr><th class="nm">日期</th><th>S1</th><th>S2</th><th>S3</th><th>S4</th><th>B1</th><th>B2</th><th>B3</th><th>B4</th></tr></thead>
      <tbody id="navBody"></tbody></table>
    </div>
    <div class="note">数据为周度抽样点（共 {len(NAV['dates'])} 点），完整日频序列见 results/nav_curves.csv。</div>
  </div>

  <h2>绩效指标汇总</h2>
  <div class="card">
    <table>
      <thead><tr><th class="nm">组合</th><th>累计收益</th><th>年化收益</th><th>年化波动</th><th>夏普</th><th>最大回撤</th><th>Calmar</th><th>月胜率</th><th>β</th><th>VaR95</th><th>CVaR95</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <div class="note">α、β 为相对沪深300日收益回归得到；VaR/CVaR 为日度 95% 置信水平；无风险利率 2%。</div>
  </div>

  <div class="grid2">
    <div>
      <h2>分年度收益率</h2>
      <div class="card"><div id="yearChart" style="width:100%;height:340px;"></div>
      <div class="note">2019 年为自 7 月 30 日起的半年收益，非完整年度。</div></div>
    </div>
    <div>
      <h2>板块相关性</h2>
      <div class="card">
        <div id="corrChart" style="width:100%;height:250px;"></div>
        <table style="margin-top:8px"><thead><tr><th class="nm">年份</th><th>日收益相关系数</th></tr></thead><tbody>{corr_rows}</tbody></table>
        <div class="note">全样本相关系数 0.643，两板块共享医药系统性风险，轮动可利用的是相对强弱而非独立走势。</div>
      </div>
    </div>
  </div>

  <h2>稳健性检验</h2>
  <div class="grid2">
    <div class="card">
      <strong>参数网格（S3）</strong>
      <table><thead><tr><th>动量窗口</th><th>均线窗口</th><th>年化</th><th>夏普</th><th>最大回撤</th></tr></thead><tbody>{grid_rows}</tbody></table>
    </div>
    <div class="card">
      <strong>交易成本敏感性（S3）</strong>
      <table><thead><tr><th>单边成本</th><th>年化</th><th>夏普</th></tr></thead><tbody>{cost_rows}</tbody></table>
      <div class="note">主策略换仓 {hold['换仓次数']} 次，平均仓位 {hold['平均仓位']:.2f}，年双边换手率约 {hold['年双边换手率']:.2f} 倍。</div>
    </div>
  </div>

  <h2>样本内 / 样本外对比（分界 2023-01-01）</h2>
  <div class="card">
    <table>
      <thead><tr><th class="nm">组合</th><th>样本内年化</th><th>样本内夏普</th><th>样本内回撤</th><th>样本外年化</th><th>样本外夏普</th><th>样本外回撤</th></tr></thead>
      <tbody>{oos_rows}</tbody>
    </table>
    <div class="note">样本外各策略夏普比率均大幅下降，S3 样本外夏普仅 {oos['S3_主策略']['样本外']['sharpe']:.2f}，与基准接近持平。这是本文最重要的负面结果：轮动收益高度依赖 2019—2021 年的强趋势环境。</div>
  </div>

  <h2>方法要点与局限</h2>
  <div class="card">
    <ul>
      <li><strong>防未来信息：</strong>信号于 t-1 日收盘后计算、t 日结算收益；成分股名单期初固定；前 120 个交易日为信号预热期不计入净值。</li>
      <li><strong>组合构建：</strong>两个板块各取 6 只龙头等权、日度再平衡；创新药组合与中证创新药产业指数（931152）重叠期日收益相关系数 0.869，建构效度可接受。</li>
      <li><strong>局限：</strong>成分股按事后可见的龙头名单选取，存在幸存者偏差；等权日度再平衡忽略冲击成本；未考虑涨跌停不可交易与流动性约束；样本仅覆盖单一行业的一个牛熊周期。</li>
      <li><strong>数据来源：</strong>日频前复权行情，导出时点 2026-10-15；基准为沪深300指数（000300）。</li>
    </ul>
  </div>

  <div class="note" style="margin-bottom:30px">本文为课程论文性质的历史回测研究，全部数据来自公开市场行情，不构成投资建议。回测收益不代表未来可实现收益。</div>
</div>

"""

SCRIPT = r"""<script>
var NAV = __NAV__;
var YEARS = __YEARS__;
var YS = __YS__;
var CORR = __CORR__;

var series = [
  {name:'S1 动量轮动', data:NAV.S1, color:'#c0392b'},
  {name:'S2 动量+趋势', data:NAV.S2, color:'#e08a2e'},
  {name:'S3 主策略', data:NAV.S3, color:'#2b6cb0'},
  {name:'S4 目标25%', data:NAV.S4, color:'#7d5fb2'},
  {name:'B1 创新药', data:NAV.B1, color:'#5b6470'},
  {name:'B2 CRO', data:NAV.B2, color:'#0f9b8e'},
  {name:'B3 静态50/50', data:NAV.B3, color:'#a0aec0'},
  {name:'B4 沪深300', data:NAV.B4, color:'#1f2328'}
];

echarts.init(document.getElementById('navChart')).setOption({{
  tooltip: {{ trigger: 'axis' }},
  legend: {{ data: series.map(function(s){{ return s.name; }}), bottom: 0, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: 55, right: 20, top: 20, bottom: 60 }},
  xAxis: {{ type: 'category', data: NAV.dates, axisLabel: {{ fontSize: 11 }} }},
  yAxis: {{ type: 'log', name: '净值(对数)', axisLabel: {{ fontSize: 11 }} }},
  series: series.map(function(s) {{
    return {{ name: s.name, type: 'line', showSymbol: false, smooth: false,
      lineStyle: {{ width: s.name === 'S3 主策略' ? 2.4 : 1.4, color: s.color }},
      itemStyle: {{ color: s.color }}, data: s.data }};
  }})
}});

echarts.init(document.getElementById('yearChart')).setOption({{
  tooltip: {{ trigger: 'axis' }},
  legend: {{ data: YS.map(function(s){{ return s.name; }}), bottom: 0, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: 50, right: 20, top: 20, bottom: 60 }},
  xAxis: {{ type: 'category', data: YEARS }},
  yAxis: {{ type: 'value', name: '%' }},
  series: YS
}});

echarts.init(document.getElementById('corrChart')).setOption({{
  tooltip: {{ trigger: 'axis' }},
  grid: {{ left: 45, right: 15, top: 20, bottom: 35 }},
  xAxis: {{ type: 'category', data: CORR.map(function(c){{ return c[0]; }}) }},
  yAxis: {{ type: 'value', min: 0.4, max: 0.9, name: '相关系数' }},
  series: [{{ type: 'bar', data: CORR.map(function(c){{ return c[1]; }}),
    itemStyle: {{ color: '#2b6cb0' }} }}]
}});

var body = document.getElementById('navBody');
var step = Math.max(1, Math.floor(NAV.dates.length / 60));
for (var i = 0; i < NAV.dates.length; i += step) {{
  body.insertAdjacentHTML('beforeend', '<tr><td class="nm">' + NAV.dates[i] + '</td><td>' +
    NAV.S1[i] + '</td><td>' + NAV.S2[i] + '</td><td>' + NAV.S3[i] + '</td><td>' + NAV.S4[i] +
    '</td><td>' + NAV.B1[i] + '</td><td>' + NAV.B2[i] + '</td><td>' + NAV.B3[i] + '</td><td>' + NAV.B4[i] + '</td></tr>');
}}

document.getElementById('tabChart').onclick = function() {{
  document.getElementById('navChart').style.display = 'block';
  document.getElementById('navTable').style.display = 'none';
  document.getElementById('tabChart').className = 'tab on';
  document.getElementById('tabTable').className = 'tab';
}};
document.getElementById('tabTable').onclick = function() {{
  document.getElementById('navChart').style.display = 'none';
  document.getElementById('navTable').style.display = 'block';
  document.getElementById('tabTable').className = 'tab on';
  document.getElementById('tabChart').className = 'tab';
}};
</script>
"""

SCRIPT = (SCRIPT
  .replace("{{", "{").replace("}}", "}")
  .replace("__NAV__", json.dumps(NAV, ensure_ascii=False))
  .replace("__YEARS__", json.dumps(years, ensure_ascii=False))
  .replace("__YS__", json.dumps(yearly_series, ensure_ascii=False))
  .replace("__CORR__", json.dumps(sorted(T["corr_year"].items()), ensure_ascii=False)))

html = html + SCRIPT + """
</body>
</html>
"""

open("创新药CRO轮动策略回测报告.html", "w", encoding="utf-8").write(html)
print("written", len(html))
