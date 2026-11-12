"""生成落地 Demo 的手机端界面（HTML → Edge 无头渲染成 PNG）。

参照行内"掌银助手"实机截图：薄荷渐变底、柔光白卡、青色渐变气泡、账单富卡、胶囊输入框。
共 6 屏，覆盖：首页 / 费率问答 / 余额与账单 / 安全拦截 / 账单详情 / 挂失办理。

渲染：对每张 *.html 调 Edge headless，2 倍图输出到同名 png（见 render.py）。
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent

# ---------------- 图形资源 ----------------

MASCOT = """<svg width="54" height="54" viewBox="0 0 54 54" fill="none">
<path d="M15 21c0-8 5-13 12-13s12 5 12 13" fill="#F6C64F"/>
<path d="M11 20l3-8 3 8 4-11 3 11 4-10 2 10 4-8 2 9 3-5 1 7" fill="#F2A33C"/>
<circle cx="27" cy="28" r="13" fill="#FFF1DC"/>
<circle cx="22.5" cy="27" r="1.8" fill="#4E3D2C"/>
<circle cx="31.5" cy="27" r="1.8" fill="#4E3D2C"/>
<path d="M24 32c2 1.7 4.4 1.7 6.4 0" stroke="#4E3D2C" stroke-width="1.8" stroke-linecap="round"/>
<path d="M17 42c0-5 4.4-7.5 10-7.5s10 2.5 10 7.5v5H17v-5z" fill="#7FCCA9"/>
<path d="M27 35v12" stroke="#5FAF8E" stroke-width="1.4"/>
</svg>"""

ICON_BACK = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M15 4.5L7.5 12 15 19.5" stroke="#232B2A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
ICON_SOUND = """<svg width="23" height="23" viewBox="0 0 24 24" fill="none"><path d="M4.5 9.5h3.6l4.6-3.4v11.8L8.1 14.5H4.5V9.5z" stroke="#6E7C79" stroke-width="1.5" stroke-linejoin="round"/><path d="M16.2 9c1.2 1.3 1.2 4.7 0 6M18.8 7.2c2.2 2.2 2.2 7.4 0 9.6" stroke="#6E7C79" stroke-width="1.4" stroke-linecap="round"/></svg>"""
ICON_GEAR = """<svg width="23" height="23" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="7.4" stroke="#6E7C79" stroke-width="1.5"/><circle cx="12" cy="12" r="2.7" stroke="#6E7C79" stroke-width="1.5"/><path d="M12 2.8v1.7M12 19.5v1.7M21.2 12h-1.7M4.5 12H2.8M18.5 5.5l-1.2 1.2M6.7 17.3l-1.2 1.2M18.5 18.5l-1.2-1.2M6.7 6.7L5.5 5.5" stroke="#6E7C79" stroke-width="1.5" stroke-linecap="round"/></svg>"""
ICON_MIC = """<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="7.2" y="2.4" width="5.6" height="9" rx="2.8" stroke="#2F9C86" stroke-width="1.5"/><path d="M4.2 9.6c0 3.2 2.6 5.7 5.8 5.7s5.8-2.5 5.8-5.7M10 15.3v2" stroke="#2F9C86" stroke-width="1.5" stroke-linecap="round"/></svg>"""
ICON_GRID = """<svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="7.4" cy="7.4" r="2.9" stroke="#2F9C86" stroke-width="1.5"/><circle cx="14.6" cy="7.4" r="2.9" stroke="#2F9C86" stroke-width="1.5"/><circle cx="7.4" cy="14.6" r="2.9" stroke="#2F9C86" stroke-width="1.5"/><circle cx="14.6" cy="14.6" r="2.9" fill="#2F9C86" fill-opacity=".18" stroke="#2F9C86" stroke-width="1.5"/></svg>"""
ICON_CAL = """<svg width="17" height="17" viewBox="0 0 16 16" fill="none"><rect x="2.2" y="3.4" width="11.6" height="10.4" rx="2.2" stroke="#B79B6A" stroke-width="1.3"/><path d="M2.2 6.6h11.6M5.5 2.1v2.6M10.5 2.1v2.6" stroke="#B79B6A" stroke-width="1.3" stroke-linecap="round"/></svg>"""
ICON_BOX = """<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 2.6l5.8 3.2v7.6L10 16.6 4.2 13.4V5.8L10 2.6z" stroke="#4C9BE8" stroke-width="1.4" stroke-linejoin="round"/><path d="M4.3 5.9L10 9.1l5.7-3.2M10 9.1v7.3" stroke="#4C9BE8" stroke-width="1.4" stroke-linejoin="round"/></svg>"""
ICON_BASKET = """<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M3.2 7.2h13.6l-1.4 8c-.1.8-.8 1.3-1.6 1.3H6.2c-.8 0-1.5-.5-1.6-1.3l-1.4-8z" fill="#F0A85C" fill-opacity=".22" stroke="#E08A3C" stroke-width="1.3" stroke-linejoin="round"/><path d="M7 7.1c0-2.3 1.4-3.9 3-3.9s3 1.6 3 3.9" stroke="#E08A3C" stroke-width="1.3" stroke-linecap="round"/></svg>"""
ICON_SHIELD = """<svg width="19" height="19" viewBox="0 0 18 18" fill="none"><path d="M9 2.2l5.4 1.9v4.3c0 3.3-2.3 6-5.4 7.3-3.1-1.3-5.4-4-5.4-7.3V4.1L9 2.2z" stroke="#2F9C86" stroke-width="1.35" stroke-linejoin="round"/><path d="M6.7 8.9l1.7 1.7 3.1-3.2" stroke="#2F9C86" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
ICON_CHEV = """<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3.4 5.4L7 9l3.6-3.6" stroke="#B79B6A" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
ICON_WALLET = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><rect x="3.2" y="6.2" width="17.6" height="12" rx="3" stroke="#2F9C86" stroke-width="1.5"/><path d="M3.2 10.2h17.6" stroke="#2F9C86" stroke-width="1.5"/><circle cx="17" cy="14.4" r="1.3" fill="#2F9C86"/></svg>"""
ICON_SWAP = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M4 9h13M13.6 5.6L17 9l-3.4 3.4" stroke="#2F9C86" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M20 15H7M10.4 11.6L7 15l3.4 3.4" stroke="#2F9C86" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
ICON_PIN = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 21c4-4.6 6-7.6 6-10a6 6 0 10-12 0c0 2.4 2 5.4 6 10z" stroke="#2F9C86" stroke-width="1.5" stroke-linejoin="round"/><circle cx="12" cy="11" r="2.2" stroke="#2F9C86" stroke-width="1.5"/></svg>"""
ICON_LOCK = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><rect x="5.2" y="10.4" width="13.6" height="9.4" rx="2.6" stroke="#2F9C86" stroke-width="1.5"/><path d="M8.6 10.2V8a3.4 3.4 0 016.8 0v2.2" stroke="#2F9C86" stroke-width="1.5" stroke-linecap="round"/></svg>"""

# ---------------- 样式 ----------------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 390px; height: 844px; }
body {
  font-family: "HarmonyOS Sans SC", "MiSans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  color: #222B2A; -webkit-font-smoothing: antialiased; overflow: hidden;
  background: linear-gradient(177deg, #C8E9DD 0%, #D8F1E9 16%, #E9F8F3 38%, #F6FCFA 62%, #FFFFFF 82%);
}
.screen { width: 390px; height: 844px; position: relative; display: flex; flex-direction: column; }

.status { height: 38px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px 0 22px; color: #1C2321; }
.status .time { font-size: 15px; font-weight: 600; letter-spacing: 0.2px; }
.status .r { display: flex; align-items: center; gap: 7px; }
.speed { font-size: 9.5px; color: #3B4442; }
.sig { display: flex; align-items: flex-end; gap: 1.5px; }
.sig i { width: 2.6px; background: #1C2321; border-radius: 1px; display: block; }
.sig span { font-size: 8.5px; font-weight: 600; margin-left: 1.5px; }
.batt { width: 22px; height: 11px; border: 1.3px solid #1C2321; border-radius: 3px; position: relative;
  display: flex; align-items: center; }
.batt::before { content: ""; position: absolute; right: -3.4px; top: 3px; width: 2px; height: 4px;
  background: #1C2321; border-radius: 0 1px 1px 0; }
.batt i { display: block; height: 5px; margin-left: 1.5px; background: #1C2321; border-radius: 1px; }
.pct { font-size: 10px; font-weight: 600; margin-left: 2px; }

.header { display: flex; align-items: center; gap: 8px; padding: 2px 16px 16px 12px; }
.hd-title { font-size: 21px; font-weight: 600; letter-spacing: 0.6px;
  background: linear-gradient(92deg, #3E9FD8 0%, #33B9C4 48%, #2FC0A2 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.hd-simple { font-size: 18px; font-weight: 500; color: #222B2A; }
.hd-actions { margin-left: auto; display: flex; gap: 16px; align-items: center; }

.body { flex: 1; padding: 0 16px; overflow: hidden; }
.say { font-size: 13px; color: #5A756E; margin: 2px 2px 10px; }
.saycard { background: #FFFFFF; border-radius: 16px; padding: 14px; border: 1px solid #E9F3EF;
  box-shadow: 0 3px 14px rgba(38, 92, 78, 0.05); }
.saycard .say { margin: 0 2px 11px; }
.chip { border: 1px solid #E6F0EC; border-radius: 10px; padding: 12px 14px;
  display: flex; align-items: center; gap: 11px; font-size: 15px; color: #2A3532; }
.chip + .chip { margin-top: 10px; }
.chip .ico { width: 26px; height: 26px; border-radius: 8px; display: flex; align-items: center;
  justify-content: center; background: #F0F7FB; flex: none; }
.chip .ico.warm { background: #FDF4E9; }

.quick-title { font-size: 13px; color: #5A756E; margin: 20px 2px 10px; }
.quick { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.quick .q { background: #FFFFFF; border: 1px solid #E9F3EF; border-radius: 14px;
  padding: 15px 4px 13px; text-align: center; font-size: 12.5px; color: #2A3532;
  box-shadow: 0 2px 10px rgba(38, 92, 78, 0.04); }
.quick .q .qi { width: 28px; height: 28px; margin: 0 auto 8px; border-radius: 9px; background: #EDF8F4;
  display: flex; align-items: center; justify-content: center; }

.privacy { margin-top: 18px; background: rgba(255,255,255,0.94); border: 1px solid #E4F0EB;
  border-radius: 16px; padding: 14px; display: flex; gap: 10px; align-items: flex-start;
  box-shadow: 0 3px 14px rgba(38, 92, 78, 0.05); }
.privacy .t { font-size: 13.5px; color: #2A6659; line-height: 1.6; font-weight: 600; }
.privacy .b { font-size: 12px; color: #7C9C95; margin-top: 5px; line-height: 1.65; }

.recent { background: #FFFFFF; border: 1px solid #E9F3EF; border-radius: 16px;
  padding: 14px; margin-top: 14px; box-shadow: 0 2px 12px rgba(38, 92, 78, 0.04); }
.recent .rt { font-size: 12px; color: #9DB6B0; margin-bottom: 8px; }
.recent .rq { font-size: 14px; color: #222B2A; }
.recent .ra { font-size: 12.5px; color: #7C9C95; margin-top: 6px; line-height: 1.6; }
.runinfo { margin-top: 14px; padding: 0 4px; font-size: 11px; color: #93B0A9; line-height: 1.95; }
.runinfo div { white-space: nowrap; }

.messages { flex: 1; padding: 6px 16px 4px; display: flex; flex-direction: column;
  justify-content: flex-start; gap: 11px; overflow: hidden; }
.row { display: flex; }
.row.r { justify-content: flex-end; }
.bubble { max-width: 80%; font-size: 15px; line-height: 1.62; }
.bubble.u { background: linear-gradient(96deg, #3ACDB4 0%, #2FB7A5 100%); color: #FFFFFF;
  padding: 11px 15px; border-radius: 12px 12px 3px 12px; position: relative;
 }
.bubble.u::after { content: ""; position: absolute; right: -5px; bottom: 7px; width: 11px; height: 11px;
  background: #2FB7A5; transform: rotate(45deg); border-radius: 2px; }
.bubble.a { background: #FFFFFF; color: #222B2A; padding: 13px 15px; border-radius: 12px;
  border-bottom-left-radius: 3px; border: 1px solid #EDF6F2; box-shadow: 0 3px 12px rgba(38, 92, 78, 0.05); }
.src { font-size: 11.5px; color: #98B4AE; margin-top: 8px; }
.mtag { display: inline-block; background: #E1F5EE; color: #0F6E56; border-radius: 5px;
  padding: 1px 6px; font-size: 10.5px; font-weight: 500; margin-right: 7px; }
.ts { align-self: center; font-size: 11px; color: #A6BEB8; letter-spacing: 0.2px;
  margin: 2px 0 4px; }
.bubble.u { box-shadow: inset 0 1px 0 rgba(255,255,255,0.18), 0 4px 12px rgba(47, 183, 165, 0.22); }
.bill .num .v, .bill .tr .amt, .detail .hd .big, .detail .tr .amt, .cat .vv {
  font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }
.bill .tr, .detail .tr { font-variant-numeric: tabular-nums; }
.hint { font-size: 11.5px; color: #7C9C95; text-align: right; padding-right: 2px; }

.bill { background: linear-gradient(180deg, #FFFDF6 0%, #FBF3E0 100%); border-radius: 14px;
  border: 1px solid #F2E6CD; position: relative; box-shadow: 0 4px 16px rgba(150, 120, 60, 0.08); }
.bill .top { padding: 15px 16px 13px; }
.bill .h { display: flex; align-items: center; gap: 7px; font-size: 12px; color: #B79B6A; margin-bottom: 11px; }
.bill .nums { display: flex; gap: 18px; }
.bill .num { flex: 1; min-width: 0; }
.bill .num:last-child { text-align: right; }
.bill .num .v { font-size: 21px; font-weight: 600; letter-spacing: -0.4px; white-space: nowrap; }
.bill .num .l { font-size: 11.5px; color: #B79B6A; margin-top: 4px; }
.bill .rows { background: #FFFFFF; border-radius: 0 0 13px 13px; padding: 2px 16px; }
.bill .tr { display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 12px 0; border-bottom: 1px solid #F5F0E5; font-size: 13.5px; }
.bill .tr:last-child { border-bottom: none; }
.bill .tr .l { flex: 1; min-width: 0; padding-right: 10px; }
.bill .tr .n { font-weight: 500; }
.bill .tr .s { font-size: 11.5px; color: #A9B7B3; margin-top: 4px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.bill .tr .amt { font-weight: 500; flex: none; white-space: nowrap; }
.bill .tr .amt.pos { color: #E8892B; }
.more { position: absolute; right: 14px; bottom: -14px; width: 30px; height: 30px; border-radius: 50%;
  background: #FFFFFF; border: 1px solid #F0E7D2; display: flex; align-items: center;
  justify-content: center; box-shadow: 0 2px 8px rgba(150, 120, 60, 0.12); }

.warn { background: #FFF5F2; border: 1px solid #FADCD5; border-radius: 12px; padding: 13px 15px;
  font-size: 14.5px; line-height: 1.62; color: #A03A2A; max-width: 84%;
  box-shadow: 0 3px 12px rgba(160, 58, 42, 0.06); }
.warn .t { font-size: 11.5px; color: #BE6C5B; margin-top: 7px; }

.dock { padding: 8px 16px 10px; }
.input { height: 48px; background: #FFFFFF; border: 1.6px solid #8FDCCB; border-radius: 24px;
  display: flex; align-items: center; gap: 11px; padding: 0 15px;
  box-shadow: 0 3px 14px rgba(47, 155, 134, 0.10); }
.input .ph { flex: 1; font-size: 13.5px; color: #A6BCB7; }
.foot { text-align: center; font-size: 10px; color: #A3BCB6; padding-bottom: 6px; }
.gesture { width: 134px; height: 4.5px; border-radius: 3px; background: rgba(34,43,42,0.28);
  margin: 0 auto 9px; }

.detail { background: #FFFFFF; border-radius: 16px; padding: 0; overflow: hidden;
  border: 1px solid #E9F3EF; box-shadow: 0 4px 18px rgba(38, 92, 78, 0.06); }
.detail .hd { padding: 16px; background: linear-gradient(180deg, #FFFDF6 0%, #FBF3E0 100%);
  border-bottom: 1px solid #F2E6CD; }
.detail .hd .cap { font-size: 12px; color: #B79B6A; }
.detail .hd .big { font-size: 30px; font-weight: 600; letter-spacing: -0.6px; margin-top: 6px; }
.detail .hd .sub { font-size: 12px; color: #A8916A; margin-top: 4px; }
.detail .list { padding: 4px 16px 6px; }
.detail .tr { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 13px 0; border-bottom: 1px solid #F5F0E5; font-size: 14px; }
.detail .tr:last-child { border-bottom: none; }
.detail .tr .l { flex: 1; min-width: 0; padding-right: 10px; }
.detail .tr .av { width: 34px; height: 34px; border-radius: 50%; flex: none;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 500; color: #FFFFFF; margin-right: 11px; }
.fb { display: flex; gap: 16px; font-size: 11.5px; color: #9DB6B0; margin-top: 10px;
  padding-top: 9px; border-top: 1px solid #F1F6F4; }
.recent .rt { display: flex; justify-content: space-between; }
.detail .tr .n { font-weight: 500; }
.detail .tr .s { font-size: 11.5px; color: #A9B7B3; margin-top: 4px; }
.detail .tr .amt { font-weight: 500; white-space: nowrap; }
.detail .tr .amt.pos { color: #E8892B; }
.detail .foot-row { padding: 12px 16px 16px; text-align: center; font-size: 12.5px; color: #2F9C86; }
.cats { margin-top: 14px; background: #FFFFFF; border-radius: 16px; padding: 16px;
  border: 1px solid #E9F3EF; box-shadow: 0 3px 14px rgba(38, 92, 78, 0.05); }
.cats h4 { font-size: 13px; color: #5A756E; font-weight: 500; margin-bottom: 14px; }
.cat { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; font-size: 12.5px; }
.cat .nm { width: 64px; color: #4A625C; flex: none; }
.cat .bar { flex: 1; height: 8px; border-radius: 4px; background: #EEF6F2; overflow: hidden; }
.cat .bar i { display: block; height: 100%; border-radius: 4px; }
.cat .vv { width: 62px; text-align: right; color: #223330; font-weight: 500; flex: none; }
"""

# ---------------- 公共组件 ----------------

STATUS = """<div class="status"><span class="time">18:07</span>
<span class="r">
  <span class="speed">80.0 KB/s</span>
  <span class="sig"><i style="height:4px"></i><i style="height:6px"></i><i style="height:8px"></i><i style="height:10px"></i><span>5G</span></span>
  <span class="sig"><i style="height:4px"></i><i style="height:6px"></i><i style="height:8px"></i><i style="height:10px"></i><span>5G</span></span>
  <span class="batt"><i style="width:15px"></i></span>
  <span class="pct">88</span>
</span></div>"""


def header(title: str = "我是您的掌银助手", actions: bool = True, mascot: bool = True) -> str:
    if title == "我是您的掌银助手":
        body = f'<span class="hd-title">{title}</span>'
    else:
        body = f'<span class="hd-simple">{title}</span>'
    acts = f'<span class="hd-actions">{ICON_SOUND}{ICON_GEAR}</span>' if actions else ""
    mas = MASCOT if mascot else ""
    return f'<div class="header"><span>{ICON_BACK}</span>{mas}{body}{acts}</div>'


DOCK = f"""<div class="dock"><div class="input">{ICON_MIC}
<span class="ph">发消息或长按说话</span>{ICON_GRID}</div></div>
<div class="foot">演示环境 · 数据为示例</div><div class="gesture"></div>"""


def u(text: str) -> str:
    return f'<div class="row r"><div class="bubble u">{text}</div></div>'


def a(text: str, src: str = "", feedback: bool = False) -> str:
    s = f'<div class="src">{src}</div>' if src else ""
    fb = ('<div class="fb"><span>有帮助</span><span>没帮上</span><span>复制</span></div>'
          if feedback else "")
    return f'<div class="row"><div class="bubble a">{text}{s}{fb}</div></div>'


def bill_card() -> str:
    return f"""
<div class="row"><div style="max-width:88%">
  <div class="bill">
    <div class="top">
      <div class="h">{ICON_CAL}本月收支概览</div>
      <div class="nums">
        <div class="num"><div class="v">12,345.67</div><div class="l">可用余额（元）</div></div>
        <div class="num"><div class="v">2,180.00</div><div class="l">本月收入（元）</div></div>
      </div>
    </div>
    <div class="rows">
      <div class="tr"><div class="l"><div class="n">转账-熊*杰</div><div class="s">尾号 8474 · 11-10</div></div>
        <div class="amt">- ¥ 1,500.00</div></div>
      <div class="tr"><div class="l"><div class="n">工资发放</div><div class="s">11-08 09:12</div></div>
        <div class="amt pos">+ ¥ 2,180.00</div></div>
    </div>
    <div class="more">{ICON_CHEV}</div>
  </div>
  <div class="src" style="padding:0 4px; margin-top:16px"><span class="mtag">已脱敏</span>工具调用 get_balance · 手机号未上送</div>
</div></div>"""


def page(name: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{name}</title><style>{CSS}</style></head><body>{body}</body></html>"""


# ---------------- 六屏 ----------------

HOME = page("首页", f"""<div class="screen">{STATUS}{header()}
<div class="body">
  <div class="saycard">
    <div class="say">您可以对我说：</div>
    <div class="chip"><span class="ico">{ICON_BOX}</span>跨行转账收手续费吗</div>
    <div class="chip"><span class="ico warm">{ICON_BASKET}</span>查下我的账户余额</div>
    <div class="chip"><span class="ico">{ICON_BOX}</span>我要挂失银行卡</div>
  </div>

  <div class="quick-title">常用功能</div>
  <div class="quick">
    <div class="q"><div class="qi">{ICON_WALLET}</div>查余额</div>
    <div class="q"><div class="qi">{ICON_SWAP}</div>转账</div>
    <div class="q"><div class="qi">{ICON_PIN}</div>网点</div>
    <div class="q"><div class="qi">{ICON_LOCK}</div>挂失</div>
  </div>

  <div class="privacy">{ICON_SHIELD}
    <div><div class="t">敏感信息在本机完成脱敏</div>
    <div class="b">手机号、卡号、身份证不出设备，仅上送脱敏后文本；对话与账户数据不上传云端。</div></div>
  </div>

  <div class="recent">
    <div class="rt"><span>最近对话</span><span>18:02</span></div>
    <div class="rq">跨行转账收手续费吗</div>
    <div class="ra">行内转账免费；跨行 1 万元以下 0 元（优惠期内）</div>
  </div>

  <div class="runinfo">
    <div>一加 Ace 2 · Android 16 · Qwen3-1.7B Q8_0 1.8GB</div>
    <div>llama.cpp b11669 · 本机 CPU · 全程联网 0 次</div>
  </div>
</div>
{DOCK}
</div>""")

CHAT_FAQ = page("费率问答", f"""<div class="screen">{STATUS}{header()}
<div class="messages">
  <div class="ts">今天 18:07</div>
  {u("跨行转账收手续费吗")}
  {a("手机银行行内转账免费；跨行转账 1 万元以下（普通到账）手续费为 0 元，1 万元以上按行内公示费率收取。", "依据 费率说明 I2 · I3")}
  {u("那 ATM 取现呢")}
  {a("本行 ATM 取款免费；跨行 ATM 取款每笔按行内公示价目收费，具体以网点公告为准。", "依据 费率说明 I4", feedback=True)}
</div>
{DOCK}
</div>""")

CHAT_BILL = page("余额查询", f"""<div class="screen">{STATUS}{header()}
<div class="messages">
  <div class="ts">今天 18:07</div>
  {u("我手机 187****1430，顺便看下余额")}
  <div class="hint">已在本机脱敏 → 手机号替换为 [手机_1]</div>
  {a("手机号已为你隐藏，余额如下：")}
  {bill_card()}
</div>
{DOCK}
</div>""")

CHAT_BLOCK = page("安全拦截", f"""<div class="screen">{STATUS}{header()}
<div class="messages">
  <div class="ts">今天 18:07</div>
  {u("查一下张*三的账户余额")}
  <div class="row"><div class="warn">
    涉及他人账户，需账户本人授权，本次未执行。已为你转接人工客服。
    <div class="t">安全策略拦截 · 主体校验未通过</div>
  </div></div>
  {a("如需查询亲属账户，可由本人携带身份证到我行网点办理账户关联授权。", "安全策略 · 已记录本次请求")}
</div>
{DOCK}
</div>""")

BILL_DETAIL = page("收支明细", f"""<div class="screen">{STATUS}{header("收支明细", actions=False, mascot=False)}
<div class="body" style="padding-top:4px">
  <div class="detail">
    <div class="hd">
      <div class="cap">本月支出（元）</div>
      <div class="big">13,630.00</div>
      <div class="sub">共 6 笔 · 收入 13,814.30 元 · 共 4 笔 · 对方姓名已脱敏</div>
    </div>
    <div class="list">
      <div class="tr"><span class="av" style="background:#5EB8A6">转</span><div class="l"><div class="n">转账-熊*杰</div><div class="s">借记卡 8474 · 11-10 17:36</div></div>
        <div class="amt">- ¥ 13,500.00</div></div>
      <div class="tr"><span class="av" style="background:#E9A75C">薪</span><div class="l"><div class="n">工资发放</div><div class="s">11-08 09:12 · 代发</div></div>
        <div class="amt pos">+ ¥ 12,438.00</div></div>
      <div class="tr"><span class="av" style="background:#7FA9DE">消</span><div class="l"><div class="n">扫码支付-便利店</div><div class="s">11-07 21:05</div></div>
        <div class="amt">- ¥ 38.50</div></div>
      <div class="tr"><span class="av" style="background:#B08BD0">还</span><div class="l"><div class="n">信用卡还款</div><div class="s">11-05 10:22 · 自动还款</div></div>
        <div class="amt">- ¥ 2,000.00</div></div>
      <div class="tr"><span class="av" style="background:#6FC49B">理</span><div class="l"><div class="n">理财赎回</div><div class="s">11-03 15:40</div></div>
        <div class="amt pos">+ ¥ 1,376.30</div></div>
    </div>
    <div class="foot-row">查看全部 10 笔</div>
  </div>

  <div class="cats">
    <h4>支出分类</h4>
    <div class="cat"><span class="nm">转账</span><span class="bar"><i style="width:96%;background:#3ACDB4"></i></span><span class="vv">13,500.00</span></div>
    <div class="cat"><span class="nm">信用卡</span><span class="bar"><i style="width:15%;background:#7FD8C6"></i></span><span class="vv">2,000.00</span></div>
    <div class="cat"><span class="nm">消费</span><span class="bar"><i style="width:4%;background:#BFE9DF"></i></span><span class="vv">538.50</span></div>
  </div>
</div>
<div class="gesture" style="margin-top:auto"></div>
</div>""")

CHAT_LOSS = page("挂失办理", f"""<div class="screen">{STATUS}{header()}
<div class="messages">
  <div class="ts">今天 18:07</div>
  {u("我要挂失银行卡")}
  {a("请问是要挂失尾号 8474 的借记卡吗？挂失后该卡将立即停止支付，补卡需到网点办理。")}
  {u("对，就是这张")}
  {a("已为你提交挂失申请，卡号 8474 已于 18:32 冻结。补卡请携带身份证至任意网点。", "工具调用 report_loss · 参数校验通过")}
  <div class="hint">已在本机完成 · 数据未出设备</div>
</div>
{DOCK}
</div>""")

SCREENS = {
    "01-home": HOME,
    "02-chat-faq": CHAT_FAQ,
    "03-chat-bill": CHAT_BILL,
    "04-chat-block": CHAT_BLOCK,
    "05-bill-detail": BILL_DETAIL,
    "06-chat-loss": CHAT_LOSS,
}

GALLERY = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>Demo 预览</title>
<style>body{margin:0;padding:24px;background:#E9F2EF;font-family:"PingFang SC","Microsoft YaHei",system-ui;
display:flex;flex-wrap:wrap;gap:20px;justify-content:center}
.cell{width:210px}
.phone{background:#fff;border-radius:18px;padding:6px;border:1px solid #D8E6E1;overflow:hidden;height:462px}
iframe{width:390px;height:844px;border:0;transform:scale(0.5077);transform-origin:0 0}
p{font-size:12px;color:#5F7A73;text-align:center;margin:6px 0 0}</style></head><body>
""" + "".join(
    f'<div class="cell"><div class="phone"><iframe src="{k}.html"></iframe></div><p>{t}</p></div>'
    for k, t in [("01-home", "① 首页"), ("02-chat-faq", "② 费率问答"), ("03-chat-bill", "③ 余额与账单"),
                 ("04-chat-block", "④ 安全拦截"), ("05-bill-detail", "⑤ 收支明细"), ("06-chat-loss", "⑥ 挂失办理")]
) + "</body></html>"

for name, html in list(SCREENS.items()) + [("index", GALLERY)]:
    (OUT / f"{name}.html").write_text(html, encoding="utf-8")
    print("写出", f"{name}.html")
