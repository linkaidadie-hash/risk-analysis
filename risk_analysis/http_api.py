from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "risk_system.db"
for p in [DATA_DIR, UPLOAD_DIR]:
    p.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"csv", "xls", "xlsx"}
MAX_CONTENT_LENGTH = 30 * 1024 * 1024
MAX_REPORTS_PER_USER = 200
RATE_LIMIT = {"window": 60, "requests": 80}
rate_limit_store: dict[str, list[datetime]] = {}

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["JSON_AS_ASCII"] = False


def w(v: float) -> float:
    """元 → 万元，保留2位小数"""
    return round(float(v) / 10000.0, 2)


@dataclass
class RiskResult:
    status: str
    summary: dict[str, Any]
    indicators: dict[str, Any]
    risk_flags: list[dict[str, Any]]
    risk_score: float
    risk_level: str
    recommendation: dict[str, Any]
    monthly: list[dict[str, Any]]
    distributions: dict[str, Any]
    top_income: list[dict[str, Any]]
    top_expense: list[dict[str, Any]]
    counterparties: list[dict[str, Any]]
    transactions: list[dict[str, Any]]
    night_transactions: list[dict[str, Any]]
    loan_transactions: list[dict[str, Any]]
    repeated_transactions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "indicators": self.indicators,
            "risk_flags": self.risk_flags,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "recommendation": self.recommendation,
            "monthly": self.monthly,
            "distributions": self.distributions,
            "top_income": self.top_income,
            "top_expense": self.top_expense,
            "counterparties": self.counterparties,
            "transactions": self.transactions,
            "night_transactions": self.night_transactions,
            "loan_transactions": self.loan_transactions,
            "repeated_transactions": self.repeated_transactions,
        }


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    if "$" not in stored:
        return False
    salt, _ = stored.split("$", 1)
    return hash_password(password, salt) == stored


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            token TEXT,
            created_at TEXT NOT NULL,
            last_login_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reports_user_id ON reports(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_token ON users(token)")


init_db()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def rate_limit_check(ip: str) -> bool:
    now = datetime.utcnow()
    bucket = rate_limit_store.setdefault(ip, [])
    window_start = now - timedelta(seconds=RATE_LIMIT["window"])
    bucket[:] = [t for t in bucket if t > window_start]
    if len(bucket) >= RATE_LIMIT["requests"]:
        return False
    bucket.append(now)
    return True


def auth_user() -> sqlite3.Row | None:
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not token:
        return None
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()


def json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


# ---- 列名映射（扩展）----
COLUMN_MAP = {
    "date": ["交易时间", "交易日期", "时间", "日期", "入账时间", "记账时间", "交易发生时间", "付款时间", "流水时间"],
    "amount": ["金额", "交易金额", "收入金额", "支出金额", "发生额", "变动金额", "实际金额", "收/支金额"],
    "balance": ["余额", "账户余额", "可用余额", "本次余额"],
    "direction": ["收/支", "收支方向", "交易方向", "借贷标志", "收入/支出", "收支类型"],
    "counterparty": ["交易对方", "对方户名", "对方名称", "收/付款方", "对象", "交易对象", "对手方", "商户名称"],
    "description": ["摘要", "备注", "附言", "用途", "交易摘要", "说明", "商品说明", "备注说明", "业务摘要"],
    "channel": ["交易渠道", "渠道", "支付方式", "交易类型", "交易场景", "业务类型"],
}

INCOME_WORDS = ["收入", "入账", "贷", "收款", "转入", "退款", "工资", "薪资", "奖金"]
EXPENSE_WORDS = ["支出", "出账", "借", "付款", "转出", "消费", "还款", "提现", "支付"]
DIRECTION_MAP = {"支": "支出", "收": "收入", "收入": "收入", "支出": "支出"}

# 贷款关键词
LOAN_KEYWORDS = [
    "借呗", "微粒贷", "网商贷", "花呗", "借呗分期", "消费金融", "现金贷",
    "分期乐", "拍拍贷", "你我贷", "宜人贷", "平安普惠", "助学贷", "捷信",
    "京东金条", "京东白条", "抖音月付", "微贷", "小赢", "洋钱罐",
    "贷款", "借款", "还借款", "还贷", "偿还贷款", "信用贷", "经营贷",
]

SUSPICIOUS_KEYWORDS = {
    "gambling": ["博彩", "娱乐城", "棋牌", "德州", "赌", "casino"],
    "collection": ["法院", "仲裁", "执行", "催收", "逾期", "诉讼", "保全"],
    "gray": ["跑分", "代付", "刷单", "返利", "收款码", "兼职返现"],
}


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_amount(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("¥", "").replace("￥", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {"-", ".", "-."}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


EXPENSE_TRANSFER_KEYWORDS = ["零钱通转出", "零钱提现", "信用卡还款", "零钱充值", "转账-转出", "转到"]
INCOME_TRANSFER_KEYWORDS = ["转入零钱通", "转账-转入", "转入"]


EXPENSE_TRANSFER_KEYWORDS = ["零钱通转出", "零钱提现", "信用卡还款", "零钱充值", "转账-转出", "转到"]


def detect_duplicate_transactions(work_df: pd.DataFrame) -> list[dict[str, Any]]:
    """找出金额+对手方完全相同的重复交易（至少2次），过滤无效对手方"""
    if len(work_df) < 2:
        return []
    valid = work_df[(work_df["counterparty"].str.strip() != "") & (work_df["counterparty"] != "/")].copy()
    mask = valid.duplicated(subset=["amount", "counterparty"], keep=False)
    dup = valid[mask].copy().sort_values(["counterparty", "amount", "date"])
    if dup.empty:
        return []
    rows = dup[["date", "direction", "amount", "counterparty", "channel", "description"]].to_dict("records")
    for r in rows:
        if hasattr(r["date"], "strftime"):
            r["date"] = r["date"].strftime("%Y-%m-%d %H:%M:%S")
        else:
            r["date"] = str(r["date"])
        r["amount"] = round(float(r["amount"]), 2)
    return rows


def detect_direction(raw_direction: str, amount: float, description: str, trade_type: str = "") -> str:
    rd = str(raw_direction).strip()
    if rd in DIRECTION_MAP:
        return DIRECTION_MAP[rd]
    # 收/支="/" 时，用交易类型辅助判断
    if rd == "/" and trade_type:
        tt = str(trade_type).lower()
        for kw in EXPENSE_TRANSFER_KEYWORDS:
            if kw.lower() in tt:
                return "支出"
        for kw in INCOME_TRANSFER_KEYWORDS:
            if kw.lower() in tt:
                return "收入"
        # 仍无法判断，默认支出（更保守）
        return "支出"
    text = f"{rd} {description}".lower()
    for kw in INCOME_WORDS:
        if kw.lower() in text:
            return "收入"
    for kw in EXPENSE_WORDS:
        if kw.lower() in text:
            return "支出"
    return "收入" if amount >= 0 else "支出"


def is_loan_related(counterparty: str, description: str, channel: str) -> bool:
    text = f"{counterparty} {description} {channel}".lower()
    for kw in LOAN_KEYWORDS:
        if kw.lower() in text:
            return True
    return False


class DataAdapter:
    def _find_column(self, df: pd.DataFrame, candidates: list[str]) -> str | None:
        lowered = {str(c).strip().lower(): c for c in df.columns}
        for name in candidates:
            if name.lower() in lowered:
                return lowered[name.lower()]
        for col in df.columns:
            col_text = str(col).strip().lower()
            if any(name.lower() in col_text for name in candidates):
                return col
        return None

    def standardize(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        df = raw_df.copy()
        df.columns = [str(c).strip() for c in df.columns]

        mapped: dict[str, str | None] = {key: self._find_column(df, aliases) for key, aliases in COLUMN_MAP.items()}
        if not mapped["date"] or not mapped["amount"]:
            raise ValueError("无法识别日期列或金额列")

        out = pd.DataFrame()
        out["date"] = pd.to_datetime(df[mapped["date"]], errors="coerce")
        out["amount_raw"] = df[mapped["amount"]].apply(parse_amount)
        out["description"] = df[mapped["description"]].apply(normalize_text) if mapped["description"] else ""
        out["counterparty"] = df[mapped["counterparty"]].apply(normalize_text) if mapped["counterparty"] else "未识别"
        out["channel"] = df[mapped["channel"]].apply(normalize_text) if mapped["channel"] else "未知"
        out["balance"] = df[mapped["balance"]].apply(parse_amount) if mapped["balance"] else np.nan
        raw_direction = df[mapped["direction"]].apply(normalize_text) if mapped["direction"] else ""
        trade_type_col = df["交易类型"].apply(normalize_text) if "交易类型" in df.columns else [""] * len(df)
        out["direction"] = [detect_direction(rd, amt, desc, tt) for rd, amt, desc, tt in zip(raw_direction, out["amount_raw"], out["description"], trade_type_col)]
        out["amount"] = out["amount_raw"].abs()
        out = out.dropna(subset=["date"])
        out = out[out["amount"] > 0]
        out = out.sort_values("date").reset_index(drop=True)
        return out[["date", "amount", "direction", "counterparty", "description", "channel", "balance"]]


class RiskEngine:
    def analyze(self, df: pd.DataFrame) -> RiskResult:
        work = df.copy().sort_values("date").reset_index(drop=True)
        work["month"] = work["date"].dt.to_period("M").astype(str)
        income = work[work["direction"] == "收入"].copy()
        expense = work[work["direction"] == "支出"].copy()
        if work.empty or income.empty:
            raise ValueError("有效收入数据不足，无法生成风控报告")

        # ---- 月度统计 ----
        monthly_income = income.groupby("month")["amount"].sum()
        monthly_expense = expense.groupby("month")["amount"].sum()
        monthly_net = monthly_income.sub(monthly_expense, fill_value=0)

        avg_income = float(monthly_income.mean()) if not monthly_income.empty else 0.0
        avg_expense = float(monthly_expense.mean()) if not monthly_expense.empty else 0.0
        avg_net = float(monthly_net.mean()) if len(monthly_net) else 0.0
        income_std = float(monthly_income.std(ddof=0)) if len(monthly_income) > 1 else 0.0
        income_cv = (income_std / avg_income) if avg_income > 0 else 1.0
        negative_month_ratio = float((monthly_net < 0).mean()) if len(monthly_net) else 0.0

        # ---- 近30天 / 近90天 ----
        max_date = work["date"].max()
        cutoff_30d = max_date - timedelta(days=30)
        cutoff_90d = max_date - timedelta(days=90)
        rec30 = work[work["date"] >= cutoff_30d]
        rec90 = work[work["date"] >= cutoff_90d]
        rec30_income = float(rec30[rec30["direction"] == "收入"]["amount"].sum())
        rec30_expense = float(rec30[rec30["direction"] == "支出"]["amount"].sum())
        rec30_net = rec30_income - rec30_expense
        rec90_net = float(rec90[rec90["direction"] == "收入"]["amount"].sum() - rec90[rec90["direction"] == "支出"]["amount"].sum())

        # ---- 资金留存时长 ----
        in_times = sorted(income["date"].tolist())
        out_times = sorted(expense["date"].tolist())
        retention_hours = 0.0
        if in_times and out_times:
            total_gap, gap_count = 0.0, 0
            for it in in_times:
                next_out = next((t for t in out_times if t > it), None)
                if next_out:
                    total_gap += (next_out - it).total_seconds() / 3600
                    gap_count += 1
            retention_hours = round(total_gap / gap_count, 2) if gap_count > 0 else 0.0

        # ---- 同日快进快出 ----
        sdi = income.groupby(income["date"].dt.date)["amount"].sum()
        sdo = expense.groupby(expense["date"].dt.date)["amount"].sum()
        overlap = sdi.index.intersection(sdo.index)
        same_day_ratio = 0.0
        if len(overlap):
            same_day_ratio = float(sdo.loc[overlap].sum() / sdi.loc[overlap].sum()) if sdi.loc[overlap].sum() > 0 else 0.0

        # ---- 夜间交易（0-5点）----
        night_mask = work["date"].dt.hour.isin([0, 1, 2, 3, 4, 5])
        night_tx = work[night_mask]

        # ---- 贷款相关 ----
        loan_mask = work.apply(lambda r: is_loan_related(r["counterparty"], r["description"], r["channel"]), axis=1)
        loan_tx = work[loan_mask]

        # ---- 收入集中度 ----
        counterparty_income_share = 0.0
        top_counterparty = "无"
        if not income.empty:
            cp_inc = income.groupby("counterparty")["amount"].sum().sort_values(ascending=False)
            top_counterparty = str(cp_inc.index[0])
            counterparty_income_share = float(cp_inc.iloc[0] / cp_inc.sum())

        # ---- 工资性收入 ----
        salary_like_ratio = float(
            income["description"].str.contains("工资|薪资|代发|薪金|salary", case=False, regex=True, na=False).mean()
        ) if len(income) else 0.0

        # ---- 可疑关键词 ----
        keyword_hits = {k: 0 for k in SUSPICIOUS_KEYWORDS}
        merged = work["counterparty"].fillna("") + " " + work["description"].fillna("") + " " + work["channel"].fillna("")
        for tag, words in SUSPICIOUS_KEYWORDS.items():
            keyword_hits[tag] = int(merged.str.contains("|".join(map(re.escape, words)), case=False, regex=True).sum())

        # ---- 低余额 ----
        balance_min = float(work["balance"].dropna().min()) if work["balance"].notna().any() else np.nan
        low_balance_ratio = 0.0
        if work["balance"].notna().any():
            daily_bal = work.dropna(subset=["balance"]).groupby(work["date"].dt.date)["balance"].last()
            if len(daily_bal):
                thr = max(avg_expense * 0.1, 1000)
                low_balance_ratio = float((daily_bal < thr).mean())

        # ---- 大额支出比 ----
        large_expense_ratio = 0.0
        if not expense.empty and expense["amount"].sum() > 0:
            large_exp = expense[expense["amount"] >= avg_expense * 2]
            large_expense_ratio = float(large_exp["amount"].sum() / expense["amount"].sum())

        # ---- 整额比 ----
        round_ratio = float((work["amount"] % 100 == 0).mean()) if len(work) else 0.0

        # =============================================
        # 风险评分
        # =============================================
        risk_flags: list[dict[str, Any]] = []
        score = 0.0

        def add_flag(code, title, severity, value, weight, detail):
            nonlocal score
            risk_flags.append({"code": code, "title": title, "severity": severity, "value": value, "weight": weight, "detail": detail})
            score += weight

        if income_cv >= 0.65:
            add_flag("INCOME_VOLATILE", "收入波动大", "high", round(income_cv, 3), 12, "月收入波动系数偏高，稳定性不足。")
        elif income_cv >= 0.35:
            add_flag("INCOME_FLUCTUATE", "收入存在波动", "medium", round(income_cv, 3), 6, "月收入有一定波动。")

        if negative_month_ratio >= 0.5:
            add_flag("NET_NEGATIVE", "入不敷出月份偏多", "high", round(negative_month_ratio, 3), 15, "超过一半月份净现金流为负。")
        elif negative_month_ratio >= 0.25:
            add_flag("NET_PRESSURE", "部分月份现金流承压", "medium", round(negative_month_ratio, 3), 7, "存在周期性资金压力。")

        if same_day_ratio >= 0.75:
            add_flag("TURNOVER_FAST", "快进快出明显", "high", round(same_day_ratio, 3), 14, "同日流入流出占比高，疑似通道型资金。")
        elif same_day_ratio >= 0.45:
            add_flag("TURNOVER_MEDIUM", "资金留存偏短", "medium", round(same_day_ratio, 3), 7, "资金沉淀偏弱。")

        if retention_hours < 6:
            add_flag("RETENTION_VERY_LOW", "资金极快转出", "high", f"{retention_hours}h", 16, f"平均留存仅{retention_hours}小时，资金沉淀极弱。")
        elif retention_hours < 24:
            add_flag("RETENTION_LOW", "资金留存偏短", "medium", f"{retention_hours}h", 8, f"平均留存{retention_hours}小时，缓冲能力不足。")

        if counterparty_income_share >= 0.75:
            add_flag("CP_CONCENTRATION", "收入依赖单一对手方", "high", round(counterparty_income_share, 3), 12, f"主要收入集中于 {top_counterparty}。")
        elif counterparty_income_share >= 0.5:
            add_flag("CP_CONCENTRATION_MEDIUM", "收入集中度较高", "medium", round(counterparty_income_share, 3), 6, f"主要收入来源偏集中：{top_counterparty}。")

        if len(night_tx) > 0:
            nr = round(float(len(night_tx) / len(work)), 3)
            if nr >= 0.15:
                add_flag("NIGHT_TXN", "夜间交易占比偏高", "medium", nr, 7, f"夜间(0-5点)交易{len(night_tx)}笔，占比{nr}。")

        if len(loan_tx) > 0:
            linc = float(loan_tx[loan_tx["direction"] == "收入"]["amount"].sum())
            lexp = float(loan_tx[loan_tx["direction"] == "支出"]["amount"].sum())
            add_flag("LOAN_ACTIVITY", "存在贷款相关交易", "medium", len(loan_tx), 8, f"检测到{len(loan_tx)}笔贷款相关交易（收{linc:.0f}元/支{lexp:.0f}元），疑似多头借贷或还款行为。")

        if round_ratio >= 0.7 and len(work) >= 20:
            add_flag("ROUND_TXN", "整额交易占比偏高", "medium", round(round_ratio, 3), 5, "大量整百整千交易。")

        if large_expense_ratio >= 0.6:
            add_flag("LARGE_EXPENSE", "大额支出占比高", "medium", round(large_expense_ratio, 3), 6, "大额支出较多，影响还款稳定性。")

        if not np.isnan(balance_min) and balance_min < 0:
            add_flag("BALANCE_NEGATIVE", "账户曾出现负余额", "high", round(balance_min, 2), 15, "流水显示账户存在透支或垫资迹象。")
        elif low_balance_ratio >= 0.45:
            add_flag("LOW_BALANCE", "低余额日占比较高", "medium", round(low_balance_ratio, 3), 7, "账户缓冲资金偏弱。")

        for tag, hits in keyword_hits.items():
            if hits <= 0:
                continue
            if tag == "collection":
                add_flag("LEGAL_COLLECTION", "疑似催收/司法关键词", "high", hits, min(18, 6 + hits * 2), "出现逾期、执行、仲裁等敏感关键词。")
            elif tag == "gambling":
                add_flag("GAMBLING", "疑似博彩相关关键词", "high", hits, min(18, 6 + hits * 2), "交易对手或摘要疑似博彩相关。")
            elif tag == "gray":
                add_flag("GRAY_ACTIVITY", "疑似异常资金中介痕迹", "high", hits, min(18, 6 + hits * 2), "存在跑分、代付、刷单等可疑关键词。")

        # 综合调节
        if salary_like_ratio >= 0.5 and income_cv < 0.3 and negative_month_ratio < 0.2:
            score -= 8
        elif salary_like_ratio >= 0.25 and income_cv < 0.4:
            score -= 4
        if rec30_net > avg_net * 0.8 and avg_net > 0:
            score -= 3
        if retention_hours < 6 and negative_month_ratio > 0.3:
            score += 5  # 快进快出+入不敷出叠加

        score = float(max(0.0, min(100.0, score)))
        if score >= 60:
            risk_level = "高风险"
        elif score >= 30:
            risk_level = "中风险"
        else:
            risk_level = "低风险"

        # =============================================
        # 借款金额（近30天为基准，期限1个月）
        # =============================================
        base = max(rec30_net, 0.0)
        if risk_level == "低风险" and retention_hours >= 24 and income_cv < 0.3:
            factor = 1.5
        elif risk_level == "中风险":
            factor = 1.0
        else:
            factor = 0.5
        recommended_amount = base * factor
        recommended_amount = float(int(max(0.0, recommended_amount) / 1000) * 1000)
        recommended_term = 1
        monthly_payment = max(0.0, rec30_net)

        reasons = []
        if rec30_net > 0:
            reasons.append(f"近30天净流入约 {w(rec30_net):.2f} 万元")
        else:
            reasons.append("近30天净流入不足，授信需保守")
        reasons.append(f"综合风险{risk_level}（{score:.0f}分）")
        if retention_hours < 24:
            reasons.append(f"资金留存{retention_hours}h，偿债能力弱")
        if salary_like_ratio >= 0.3:
            reasons.append("收入具备一定工资化特征")
        if len(loan_tx) > 0:
            reasons.append(f"存在{len(loan_tx)}笔贷款相关交易")

        # =============================================
        # 构造返回数据
        # =============================================
        months = sorted(set(work["month"]))
        monthly_table = []
        for m in months:
            mi = float(monthly_income.get(m, 0.0))
            me = float(monthly_expense.get(m, 0.0))
            monthly_table.append({"month": m, "income": w(mi), "expense": w(me), "net": w(mi - me)})

        # 流水明细（全部，只保留5列）
        tx = work[["date", "direction", "amount", "counterparty", "channel"]].copy()
        tx["date"] = tx["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
        tx["amount"] = tx["amount"].round(2)
        transactions = tx.to_dict("records")

        # 大额收入（4列）
        ti = income.nlargest(30, "amount")[["date", "amount", "counterparty", "channel"]].copy()
        if not ti.empty:
            ti["date"] = ti["date"].dt.strftime("%Y-%m-%d")
            ti["amount"] = ti["amount"].round(2)
        top_income_list = ti.to_dict("records")

        # 大额支出（4列）
        te = expense.nlargest(30, "amount")[["date", "amount", "counterparty", "channel"]].copy()
        if not te.empty:
            te["date"] = te["date"].dt.strftime("%Y-%m-%d")
            te["amount"] = te["amount"].round(2)
        top_expense_list = te.to_dict("records")

        # 对手方汇总
        cp_all = work.groupby("counterparty")["amount"].agg(["sum", "count"]).reset_index().sort_values("sum", ascending=False).head(30)
        counterparties = [{"counterparty": str(r["counterparty"]), "total_amount": w(float(r["sum"])), "count": int(r["count"])} for _, r in cp_all.iterrows()]

        # 夜间明细
        nl = night_tx[["date", "direction", "amount", "counterparty", "channel"]].copy()
        if not nl.empty:
            nl["date"] = nl["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
            nl["amount"] = nl["amount"].round(2)
        night_list = nl.to_dict("records")

        # 贷款明细
        ll = loan_tx[["date", "direction", "amount", "counterparty", "channel", "description"]].copy()
        if not ll.empty:
            ll["date"] = ll["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
            ll["amount"] = ll["amount"].round(2)
        loan_list = ll.to_dict("records")

        # 重复交易（金额+对手方完全相同，至少2次）
        repeated_list = detect_duplicate_transactions(work)

        # 概览（万元）
        summary = {
            "date_range": f"{work['date'].min():%Y-%m-%d} 至 {work['date'].max():%Y-%m-%d}",
            "transaction_count": int(len(work)),
            "income_total": w(float(income["amount"].sum())),
            "expense_total": w(float(expense["amount"].sum())),
            "avg_monthly_income": w(avg_income),
            "avg_monthly_expense": w(avg_expense),
            "avg_monthly_net": w(avg_net),
            "recent_30d_net": w(rec30_net),
            "recent_90d_net": w(rec90_net),
            "salary_like_ratio": round(salary_like_ratio, 3),
            "months": len(months),
            "retention_hours": round(retention_hours, 2),
        }

        night_ratio_val = round(float(len(night_tx) / len(work)), 3) if len(work) else 0.0
        indicators = {
            "income_cv": round(income_cv, 3),
            "negative_month_ratio": round(negative_month_ratio, 3),
            "same_day_turnover_ratio": round(same_day_ratio, 3),
            "retention_hours": round(retention_hours, 2),
            "counterparty_income_share": round(counterparty_income_share, 3),
            "night_ratio": night_ratio_val,
            "night_count": len(night_tx),
            "loan_count": len(loan_tx),
            "loan_income": w(float(loan_tx[loan_tx["direction"] == "收入"]["amount"].sum())) if len(loan_tx) > 0 else 0.0,
            "loan_expense": w(float(loan_tx[loan_tx["direction"] == "支出"]["amount"].sum())) if len(loan_tx) > 0 else 0.0,
            "round_number_ratio": round(round_ratio, 3),
            "large_expense_ratio": round(large_expense_ratio, 3),
            "low_balance_days_ratio": round(low_balance_ratio, 3),
            "keyword_hits": keyword_hits,
        }

        distributions = {
            "channel_breakdown": {k: w(float(v)) for k, v in work.groupby("channel")["amount"].sum().sort_values(ascending=False).head(10).to_dict().items()},
            "direction_breakdown": {"income_count": int(len(income)), "expense_count": int(len(expense))},
        }

        recommendation = {
            "recommended_amount": w(recommended_amount),
            "recommended_term_months": recommended_term,
            "monthly_payment_limit": w(monthly_payment),
            "decision": "建议通过" if risk_level == "低风险" else "建议审慎通过" if risk_level == "中风险" else "建议拒绝或降额",
            "reason": "；".join(reasons),
        }

        return RiskResult(
            status="ok",
            summary=summary,
            indicators=indicators,
            risk_flags=sorted(risk_flags, key=lambda x: x["weight"], reverse=True),
            risk_score=round(score, 2),
            risk_level=risk_level,
            recommendation=recommendation,
            monthly=monthly_table,
            distributions=distributions,
            top_income=top_income_list,
            top_expense=top_expense_list,
            counterparties=counterparties,
            transactions=transactions,
            night_transactions=night_list,
            loan_transactions=loan_list,
            repeated_transactions=repeated_list,
        )


adapter = DataAdapter()
engine = RiskEngine()


def read_raw_file(path: Path, original_filename: str) -> pd.DataFrame:
    ext = original_filename.rsplit(".", 1)[1].lower()
    wechat_like = "微信" in original_filename
    if ext in {"xls", "xlsx"}:
        if wechat_like:
            try:
                return pd.read_excel(path, header=16)
            except Exception:
                return pd.read_excel(path)
        return pd.read_excel(path)
    for enc in ["utf-8-sig", "utf-8", "gb18030", "gbk", "gb2312"]:
        try:
            if wechat_like:
                return pd.read_csv(path, encoding=enc, skiprows=16)
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    raise ValueError("无法读取文件，请确认编码和格式是否正确")


# ---- 路由 ----
@app.get("/")
def index(): return render_template("login.html")
@app.get("/dashboard.html")
def dashboard_page(): return render_template("dashboard.html")
@app.get("/report.html")
def report_page(): return render_template("report.html")


@app.post("/api/register")
def register():
    if not rate_limit_check(request.remote_addr or "unknown"):
        return json_error("请求过于频繁，请稍后再试", 429)
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
        return json_error("用户名需为 3-20 位字母、数字或下划线")
    if len(password) < 6:
        return json_error("密码至少 6 位")
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            return json_error("用户名已存在")
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO users(username,password_hash,token,created_at,last_login_at) VALUES(?,?,?,?,?)",
            (username, hash_password(password), token, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    return jsonify({"success": True, "token": token, "username": username})


@app.post("/api/login")
def login():
    if not rate_limit_check(request.remote_addr or "unknown"):
        return json_error("请求过于频繁，请稍后再试", 429)
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return json_error("用户名或密码错误", 401)
        token = secrets.token_urlsafe(32)
        conn.execute("UPDATE users SET token=?, last_login_at=? WHERE id=?", (token, datetime.utcnow().isoformat(), user["id"]))
    return jsonify({"success": True, "token": token, "username": username})


@app.post("/api/logout")
def logout():
    user = auth_user()
    if not user:
        return json_error("未登录", 401)
    with get_db() as conn:
        conn.execute("UPDATE users SET token=NULL WHERE id=?", (user["id"],))
    return jsonify({"success": True})


@app.get("/api/me")
def me():
    user = auth_user()
    if not user:
        return json_error("未登录", 401)
    return jsonify({"id": user["id"], "username": user["username"]})


@app.post("/api/upload")
def upload():
    user = auth_user()
    if not user:
        return json_error("未登录", 401)
    if not rate_limit_check(request.remote_addr or "unknown"):
        return json_error("请求过于频繁，请稍后再试", 429)
    if "file" not in request.files:
        return json_error("请选择要上传的流水文件")
    file = request.files["file"]
    if not file or not file.filename:
        return json_error("文件为空")
    if not allowed_file(file.filename):
        return json_error("仅支持 csv / xls / xlsx 文件")

    with get_db() as conn:
        if conn.execute("SELECT COUNT(*) FROM reports WHERE user_id=?", (user["id"],)).fetchone()[0] >= MAX_REPORTS_PER_USER:
            return json_error(f"报告数量已达上限 {MAX_REPORTS_PER_USER} 份")
    report_id = uuid.uuid4().hex[:12]
    safe_name = secure_filename(file.filename)
    stored_name = f"{report_id}_{safe_name}"
    save_path = UPLOAD_DIR / stored_name
    file.save(save_path)
    try:
        raw = read_raw_file(save_path, file.filename)
        standardized = adapter.standardize(raw)
        result = engine.analyze(standardized).to_dict()
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
    with get_db() as conn:
        conn.execute("INSERT INTO reports(id,user_id,original_filename,stored_filename,status,result_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (report_id, user["id"], file.filename, stored_name, result.get("status", "error"), json.dumps(result, ensure_ascii=False), datetime.utcnow().isoformat()))
    return jsonify({"report_id": report_id, "result": result})


@app.get("/api/reports")
def list_reports():
    user = auth_user()
    if not user:
        return json_error("未登录", 401)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 10)), 1), 50)
    offset = (page - 1) * page_size
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM reports WHERE user_id=?", (user["id"],)).fetchone()[0]
        rows = conn.execute("SELECT id, original_filename, status, created_at FROM reports WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user["id"], page_size, offset)).fetchall()
    return jsonify({"reports": [dict(r) for r in rows], "page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size})


@app.get("/api/report/<report_id>")
def get_report(report_id: str):
    user = auth_user()
    if not user:
        return json_error("未登录", 401)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id=? AND user_id=?", (report_id, user["id"])).fetchone()
    if not row:
        return json_error("报告不存在", 404)
    return jsonify({"id": row["id"], "filename": row["original_filename"], "status": row["status"], "created_at": row["created_at"], "result": json.loads(row["result_json"])})


@app.delete("/api/report/<report_id>")
def delete_report(report_id: str):
    user = auth_user()
    if not user:
        return json_error("未登录", 401)
    with get_db() as conn:
        row = conn.execute("SELECT stored_filename FROM reports WHERE id=? AND user_id=?", (report_id, user["id"])).fetchone()
        if not row:
            return json_error("报告不存在", 404)
        conn.execute("DELETE FROM reports WHERE id=? AND user_id=?", (report_id, user["id"]))
    try:
        (UPLOAD_DIR / row["stored_filename"]).unlink(missing_ok=True)
    except Exception:
        pass
    return jsonify({"success": True})


@app.get("/api/stats")
def stats():
    user = auth_user()
    if not user:
        return json_error("未登录", 401)
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM reports WHERE user_id=?", (user["id"],)).fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM reports WHERE user_id=? AND status='ok'", (user["id"],)).fetchone()[0]
        latest = conn.execute("SELECT created_at FROM reports WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (user["id"],)).fetchone()
    return jsonify({"total_reports": total, "success_reports": success, "last_activity": latest["created_at"] if latest else None})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", conditional=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
