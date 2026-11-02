"""L3 编排层：脱敏 → 意图分类 → 路由状态机（重试一次 + 确定性兜底）。

无设备联调：
  python -m harness.pipeline --dry-run --input "帮偶查哈子余额"
真机（W1-D5 之后）：
  python -m harness.pipeline --model qwen3-1.7b --device <serial> --input "查下余额"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "registry"
PROMPTS = ROOT / "harness" / "prompts"

CONF_MIN = 0.5          # 低于此置信度 → 兜底转云（阈值先定标准再测）
MAX_JSON_RETRY = 1      # JSON 解析失败重试上限（硬性，防端侧死循环）

CLOUD_FALLBACK_REPLY = "这个问题我需要帮您转接在线客服，请稍候。"
RETRY_PROMPT_SUFFIX = "你上次的输出不符合格式：{err}。请重新输出，只输出一个 JSON 对象。"

# ---- T5：主体与外泄安全策略（代码层，不依赖模型自觉）----
OTHER_PERSON_PAT = re.compile(r"别人|他人|我妈|我爸|我朋友|我同事|家里人|老婆|老公|孩子|儿子|女儿|张三|李四")
EXFIL_PAT = re.compile(r"截图|截屏|拍照|发送到|发到|邮件|邮箱|转发|导出|打印")
PLACEHOLDER_PAT = re.compile(r"\[(?:姓名|卡号|证件|手机)_\d+\]|(?:姓名|卡号|证件|手机)_\d+")
PERSONAL_DATA_TOOLS = {"get_balance", "get_recent_transactions",
                       "get_deposit_holding", "get_quota"}

# ---- T1b：参数值级校验（不合法视作缺参 → 走注册表追问）----
CITY_STOP = {"附近", "周边", "这里", "那儿", "本地", "外地", "未知", "未提供", "最近", "哪个"}
TERM_ENUM = {"三个月", "半年", "一年", "两年", "三年", "五年"}
CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


@dataclass
class RouteResult:
    action: str                    # faq | tool | ask_slot | cloud | cloud_fallback | masked
    intent: str = "out_of_scope"
    confidence: float = 0.0
    slots: dict = field(default_factory=dict)
    masked_text: str = ""
    reply: str = ""
    tool_calls: list = field(default_factory=list)   # [{name, arguments, result}]
    entities: list = field(default_factory=list)     # 脱敏步骤解析出的实体
    fallback_reason: str = ""       # 非空时表示走了兜底路径（审计字段）
    trace: list = field(default_factory=list)        # [{step, ms, detail}]


class Harness:
    def __init__(self, adapter):
        self.adapter = adapter
        self.env = Environment(loader=FileSystemLoader(str(PROMPTS)),
                               undefined=StrictUndefined, trim_blocks=True)
        self.intents = yaml.safe_load((REGISTRY / "intents.yaml").read_text(encoding="utf-8"))
        self.tools_reg = yaml.safe_load((REGISTRY / "tools.yaml").read_text(encoding="utf-8"))
        self.intent_map = {it["id"]: it for it in self.intents["intents"]}
        from harness.tools_mock import ToolExecutor          # 延迟导入便于单测替换
        self.executor = ToolExecutor(self.tools_reg["tools"])

    # ---------- 通用：生成 + JSON 解析 + 重试一次 ----------
    def _gen_json(self, prompt: str, step: str) -> tuple[dict, list]:
        trace, last_err = [], ""
        for attempt in range(MAX_JSON_RETRY + 1):
            raw, t = self.adapter.generate(prompt + (f"\n\n{RETRY_PROMPT_SUFFIX.format(err=last_err)}" if last_err else ""))
            trace.append({"step": f"{step}#gen{attempt}", "wall_ms": (t.t_return - t.t_submit) * 1000})
            obj = extract_json(raw)
            if obj is not None:
                return obj, trace
            last_err = "无法解析为 JSON"
        return {}, trace + [{"step": f"{step}#fail", "detail": "json_parse_failed_after_retry"}]

    # ---------- ① 脱敏 ----------
    def mask(self, text: str) -> RouteResult:
        prompt = self.env.get_template("mask.j2").render()
        obj, trace = self._gen_json(prompt + "\n\n输入：" + text, "mask")
        if not obj or "text" not in obj:
            # 脱敏失败的安全兜底：不脱敏则不放行原文，直接转云（合规优先）
            return RouteResult(action="cloud_fallback", masked_text="",
                               fallback_reason="mask_failed", trace=trace)
        ents = obj.get("entities") or []
        valid = [e for e in ents if isinstance(e, dict) and e.get("type")
                 and e.get("original")]
        return RouteResult(action="masked", masked_text=obj.get("text", ""),
                            entities=valid, trace=trace)

    # ---------- ② 意图分类 ----------
    def classify(self, text: str) -> tuple[dict, list]:
        tpl = self.env.get_template("intent.j2")
        prompt = tpl.render(intents=self.intents["intents"]) + "\n\n输入：" + text
        return self._gen_json(prompt, "intent")

    # ---------- ③ 路由状态机 ----------
    def route(self, user_text: str) -> RouteResult:
        # Step1 脱敏（PII 不出设备）
        m = self.mask(user_text)
        if m.action == "cloud_fallback":
            m.reply = CLOUD_FALLBACK_REPLY
            return m
        text = m.masked_text
        trace = list(m.trace)

        # Step2 意图分类
        cls, tr = self.classify(text)
        trace += tr
        if not cls:
            return RouteResult(action="cloud_fallback", masked_text=text,
                               reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason="intent_json_failed", trace=trace)
        intent_id = str(cls.get("intent", ""))
        conf = float(cls.get("confidence", 0))
        if intent_id not in self.intent_map and intent_id != "out_of_scope":
            return RouteResult(action="cloud_fallback", masked_text=text,
                               reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason=f"intent_not_in_registry:{intent_id}", trace=trace)
        if intent_id == "out_of_scope" or conf < CONF_MIN:
            return RouteResult(action="cloud_fallback", intent=intent_id,
                               confidence=conf, masked_text=text,
                               reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason="oos_or_low_confidence", trace=trace)

        reg = self.intent_map[intent_id]
        base = dict(intent=intent_id, confidence=conf, masked_text=text,
                    slots=cls.get("slots", {}) or {})

        # Step3 分支
        route = reg.get("route")
        if route == "cloud":
            # ★ 高风险动作：注册表硬编码转云，模型意见仅供参考
            return RouteResult(action="cloud",
                               reply=f"好的，{reg['name']}需要为您转接服务，请稍候。",
                               trace=trace, **base)
        if route == "faq":
            card = (REGISTRY / reg["knowledge"]).read_text(encoding="utf-8")
            prompt = self.env.get_template("faq.j2").render(
                knowledge_card=card, question=text)
            raw, t = self.adapter.generate(prompt)
            trace.append({"step": "faq#gen", "wall_ms": (t.t_return - t.t_submit) * 1000})
            return RouteResult(action="faq", reply=raw.strip(), trace=trace, **base)
        if route == "tool":
            return self._route_tool(reg, text, base, trace, raw_text=user_text)
        return RouteResult(action="cloud_fallback", fallback_reason="unknown_route",
                           reply=CLOUD_FALLBACK_REPLY, trace=trace, **base)

    @staticmethod
    def policy_violation(tool_name: str, args: dict, masked_text: str, raw_text: str) -> str | None:
        """T5：调用前的确定性安全校验。返回违规类型（用于审计），None 表示放行。

        规则：
        - 外泄动作（截图/发送到/邮件/转发…）：任何工具都不执行，直接转云
        - 他人主体（别人/我妈/张三… 或脱敏后的 [姓名_x]）：仅限"读取本人数据"类工具
          （get_balance / get_recent_transactions / get_deposit_holding / get_quota）
        - 参数值含脱敏占位符（姓名_x / 卡号_x）：一律拒绝，防"用占位符查他人"
        """
        if EXFIL_PAT.search(raw_text):
            return "exfil"
        if tool_name in PERSONAL_DATA_TOOLS:
            if OTHER_PERSON_PAT.search(raw_text) or re.search(r"\[姓名_\d+\]", masked_text):
                return "other_person"
        for v in (args or {}).values():
            if isinstance(v, str) and PLACEHOLDER_PAT.search(v):
                return "placeholder_arg"
        return None

    @staticmethod
    def _cn_numeral(s: str) -> float | None:
        """解析中文数字：十万→100000，三万五→35000，五千→5000，十五→15。"""
        total = 0.0
        section = 0.0
        num = 0
        units = {"十": 10, "百": 100, "千": 1000}
        for ch in s:
            if ch in CN_DIGITS:
                num = CN_DIGITS[ch]
            elif ch in units:
                section += (num or 1) * units[ch]
                num = 0
            elif ch == "万":
                total += (section + num) * 10000
                section, num = 0, 0
            else:
                return None
        if total > 0 and num > 0 and "万" in s:      # 口语"三万五"=35000
            return total + num * 1000
        return total + section + num

    @staticmethod
    def _number_tokens(text: str) -> list[float]:
        """从原话抽取数字并换算单位（5万→50000，3千→3000，十万→100000）。"""
        out = []
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(万|千|w|k)?", text):
            v = float(m.group(1))
            unit = m.group(2)
            if unit in ("万", "w"):
                v *= 10000
            elif unit in ("千", "k"):
                v *= 1000
            out.append(v)
        for m in re.finditer(r"[零一二两三四五六七八九十百千万]+", text):
            v = Harness._cn_numeral(m.group(0))
            if v:
                out.append(float(v))
        return out

    @classmethod
    def invalid_args(cls, tool: dict, args: dict, raw_text: str) -> list[str]:
        """T1b：参数值级校验（值必须能在用户原话中找到依据）。

        返回非法参数名列表；调用方把这些键剔除后按"缺参"走注册表追问，
        从而挡住模型编造（city="附近"、amount 凭空给出、term 臆测）。
        """
        bad = []
        for name, rule in (tool.get("arg_rules") or {}).items():
            if name not in args:
                continue
            v = args.get(name)
            kind = (rule or {}).get("kind")
            if kind == "city":
                s = v.strip() if isinstance(v, str) else ""
                if (not s or s in CITY_STOP or not (2 <= len(s) <= 6) or s not in raw_text):
                    bad.append(name)
            elif kind == "amount":
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    bad.append(name)
                    continue
                if fv <= 0 or not any(abs(fv - n) < 0.5 for n in cls._number_tokens(raw_text)):
                    bad.append(name)
            elif kind == "term":
                if v not in TERM_ENUM or v not in raw_text:
                    bad.append(name)
        return bad

    def _route_tool(self, reg, text, base, trace, raw_text: str = ""):
        """T1：intent→tool 一一映射，工具名由注册表直给，模型只负责填参数。

        基线（旧逻辑）让模型自行选择工具并输出 <tool_call>，1.7B 基本不吐该格式（A 类 0.1~0.2）。
        改为"参数提取器"后：工具名、schema 由代码注入；模型只输出 arguments JSON；
        必填槽缺失 → 用注册表话术追问；参数错误 → 回灌错误重试一次。
        未映射/多工具时回退旧逻辑（_route_tool_legacy）。
        """
        tool_name = reg.get("tool")
        matched = [t for t in self.tools_reg["tools"] if t["name"] == tool_name]
        if len(matched) != 1:
            return self._route_tool_legacy(reg, text, base, trace)
        tool = matched[0]

        schema_json = json.dumps({"name": tool["name"], "description": tool["description"],
                                  "parameters": tool["parameters"]}, ensure_ascii=False)
        prompt = self.env.get_template("tool_call_direct.j2").render(
            tool=tool, schema_json=schema_json, text=text)
        slots = dict(base["slots"])

        args, attempt_prompt = None, prompt
        for attempt in range(2):                       # 含一次 JSON 纠错
            raw, t = self.adapter.generate(attempt_prompt)
            trace.append({"step": f"tool#args{attempt}",
                          "wall_ms": (t.t_return - t.t_submit) * 1000})
            obj = extract_json(raw)
            if isinstance(obj, dict):
                args = obj
                break
            attempt_prompt = prompt + "\n\n" + RETRY_PROMPT_SUFFIX.format(
                err="上一次输出不是合法 JSON 对象")

        if args is None:
            return RouteResult(action="cloud_fallback", fallback_reason="tool_args_json_failed",
                               reply=CLOUD_FALLBACK_REPLY, trace=trace,
                               **{**base, "slots": slots})

        # T5：调用前安全校验（主体/外泄/占位符），命中即不执行并转云，记录审计原因
        violated = self.policy_violation(tool_name, args, text, raw_text)
        if violated:
            return RouteResult(action="cloud_fallback",
                               fallback_reason=f"policy_block:{violated}",
                               reply=CLOUD_FALLBACK_REPLY, trace=trace,
                               **{**base, "slots": slots})

        # T1b：值级校验——不合法参数剔除后按缺参处理（挡住编造的城市/本金/期限）
        for k in self.invalid_args(tool, args, raw_text):
            args.pop(k, None)

        # 必填槽缺失 → 追问（代码触发，话术来自注册表，不让模型自由发挥）
        missing = [s for s in reg.get("slots", [])
                   if s.get("required") and s["name"] not in args]
        if missing:
            return RouteResult(action="ask_slot", trace=trace, reply=missing[0]["ask"],
                               **{**base, "slots": {**slots, **args}})

        result = self.executor.execute(tool_name, args, call_count=0)
        calls = [{"name": tool_name, "arguments": args, "result": result}]

        if result.get("error"):                        # 参数错误 → 回灌错误重试一次
            raw, t = self.adapter.generate(
                prompt + f"\n\n上一次调用 {tool_name} 返回错误：{result['error']}。"
                         f"请修正参数，只输出 JSON。")
            trace.append({"step": "tool#argfix",
                          "wall_ms": (t.t_return - t.t_submit) * 1000})
            obj = extract_json(raw)
            if isinstance(obj, dict):
                args = obj
                result = self.executor.execute(tool_name, args, call_count=1)
                calls.append({"name": tool_name, "arguments": args, "result": result})

        if result.get("error"):
            return RouteResult(action="cloud_fallback", fallback_reason="tool_failed",
                               tool_calls=calls, reply=CLOUD_FALLBACK_REPLY, trace=trace,
                               **{**base, "slots": {**slots, **args}})

        answer_prompt = (f"用一两句话向用户播报以下查询结果，数字要准确，"
                         f"开头带[MOCK]标记：{json.dumps(result, ensure_ascii=False)}\n用户原话：{text}")
        reply, t2 = self.adapter.generate(answer_prompt)
        trace.append({"step": "tool#summarize", "wall_ms": (t2.t_return - t2.t_submit) * 1000})
        return RouteResult(action="tool", reply=reply.strip(), tool_calls=calls,
                           trace=trace, **{**base, "slots": {**slots, **args}})

    def _route_tool_legacy(self, reg, text, base, trace):
        """旧逻辑（模型自选工具 + <tool_call> 格式）。仅作未映射/多工具时的兜底。"""
        from harness.tools_mock import render_tool_args_json
        tools_json = [{"schema_json": json.dumps(
            {"name": t["name"], "description": t["description"],
             "parameters": t["parameters"]}, ensure_ascii=False)}
            for t in self.tools_reg["tools"]]
        prompt = self.env.get_template("tool_call.j2").render(tools=tools_json, text=text)

        slots = dict(base["slots"])
        # 缺槽位：先追问（代码触发，用注册表 ask 话术，不让模型自由发挥）
        missing = [s for s in reg.get("slots", []) if s.get("required") and s["name"] not in slots]
        if missing:
            return RouteResult(action="ask_slot", trace=trace,
                               reply=missing[0]["ask"], **{**base, "slots": slots})

        calls = []
        for attempt in range(2):  # 含一次参数纠错重试
            raw, t = self.adapter.generate(prompt)
            trace.append({"step": f"tool#gen{attempt}", "wall_ms": (t.t_return - t.t_submit) * 1000})
            parsed = render_tool_args_json(raw)
            if parsed is None:
                # 模型没调工具而是直接回答：视为完成（FAQ 化回答）
                return RouteResult(action="tool", reply=raw.strip(),
                                   tool_calls=calls, trace=trace, **{**base, "slots": slots})
            name, arguments = parsed
            result = self.executor.execute(name, arguments, call_count=attempt)
            calls.append({"name": name, "arguments": arguments, "result": result})
            if result.get("error"):
                prompt += f"\n工具 {name} 返回错误：{result['error']}，请修正后重试。"
                continue
            # 工具结果回填 → 生成自然语言回复
            answer_prompt = (f"用一两句话向用户播报以下查询结果，数字要准确，"
                             f"开头带[MOCK]标记：{json.dumps(result, ensure_ascii=False)}\n用户原话：{text}")
            reply, t2 = self.adapter.generate(answer_prompt)
            trace.append({"step": "tool#summarize", "wall_ms": (t2.t_return - t2.t_submit) * 1000})
            return RouteResult(action="tool", reply=reply.strip(),
                               tool_calls=calls, trace=trace, **{**base, "slots": slots})
        return RouteResult(action="cloud_fallback", tool_calls=calls,
                           fallback_reason="tool_failed_twice",
                           reply=CLOUD_FALLBACK_REPLY, trace=trace, **{**base, "slots": slots})


def extract_json(raw: str) -> dict | None:
    """从模型输出提取首个 JSON 对象；grammar 约束正常时 raw 本身就是 JSON。"""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="qwen3-1.7b")
    ap.add_argument("--device", default=None)
    a = ap.parse_args()

    if a.dry_run:
        from harness.adapter_mnn import DryAdapter
        adapter = DryAdapter()
    else:
        from harness.adapter_mnn import MNNAdapter
        adapter = MNNAdapter(a.model, a.device)

    result = Harness(adapter).route(a.input)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
