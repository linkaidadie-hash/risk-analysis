"""
流水风控最终版策略 - 核心引擎 v2
基于《流水风控最终版策略文档》实现
总风险分 = 现金流行为风险分 × 0.6 + 异常交易模式风险分 × 0.4
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List
from dataclasses import dataclass, field


# =============================================================================
# 客户分型
# =============================================================================
def classify_customer(df: pd.DataFrame) -> str:
    income_df = df[df['direction'] == '收入']
    if income_df.empty:
        return "混合型"
    monthly_cnt = income_df.groupby(income_df['date'].dt.to_period('M'))['amount'].count().mean()
    cp_income = income_df.groupby('counterparty')['amount'].sum()
    total_income = cp_income.sum()
    concentration = (cp_income.max() / total_income) if total_income > 0 else 0
    amt_counts = income_df['amount'].round(0).value_counts()
    fixed_ratio = (amt_counts.iloc[0] / len(income_df)) if len(income_df) > 0 and len(amt_counts) > 0 else 0
    source_count = income_df['counterparty'].nunique()
    if source_count >= 8 and concentration < 0.35 and monthly_cnt >= 15:
        return "电商/商户型"
    elif concentration > 0.75 and monthly_cnt <= 5:
        return "工薪族"
    elif fixed_ratio > 0.35 and concentration > 0.55:
        return "资金中转型"
    elif source_count >= 3 and concentration >= 0.20:
        return "个体经营"
    return "混合型"


# =============================================================================
# 样本有效性校验
# =============================================================================
@dataclass
class SampleValidation:
    valid: bool
    reason: str
    suggestions: List[str] = field(default_factory=list)
    score: float = 1.0

    def to_dict(self) -> dict:
        return {"valid": self.valid, "reason": self.reason, "suggestions": self.suggestions, "score": self.score}


def validate_sample(df: pd.DataFrame, min_days: int = 60) -> SampleValidation:
    if df.empty:
        return SampleValidation(False, "无交易数据", ["请上传有效流水"], 0.0)
    df_income = df[df['direction'] == '收入']
    total_days = (df['date'].max() - df['date'].min()).days + 1 if len(df) > 1 else 0
    total_txns = len(df)
    income_txns = len(df_income)
    total_income = df_income['amount'].sum()
    reasons, suggestions, invalid_count = [], [], 0
    if total_days < min_days:
        invalid_count += 1
        reasons.append(f"流水天数仅{total_days}天，低于最低要求{min_days}天")
        suggestions.append(f"请补充至少{min_days}天的完整流水")
    if total_txns < 10:
        invalid_count += 1
        reasons.append(f"总交易笔数仅{total_txns}笔，过少")
        suggestions.append("交易笔数不足，请上传完整流水")
    if income_txns < 5:
        invalid_count += 1
        reasons.append(f"收入笔数仅{income_txns}笔，无法识别主要收入行为")
        suggestions.append("请上传包含完整收入记录的流水")
    if total_income < 3000:
        invalid_count += 1
        reasons.append(f"总收入仅{total_income:.2f}元，低于最低准入阈值")
        suggestions.append("收入过低，建议更换主用账户或补充其他收入证明")
    if invalid_count == 0:
        vs = 1.0 - (total_days < 90) * 0.1 - (total_txns < 30) * 0.1
        return SampleValidation(True, "样本有效", [], max(0.5, vs))
    return SampleValidation(False, "; ".join(reasons), suggestions, max(0.0, 1.0 - invalid_count * 0.2))


# =============================================================================
# A. 现金流行为风险分（60%）
# =============================================================================

def calc_surplus_ratio(df: pd.DataFrame):
    income_df = df[df['direction'] == '收入']
    expense_df = df[df['direction'] == '支出']
    total_income = income_df['amount'].sum()
    total_expense = expense_df['amount'].sum()
    if total_income <= 0:
        return 0.0, 0.90, "无收入", 0.0
    surplus = (total_income - total_expense) / total_income
    if surplus > 0.15:
        score, label = 0.10, f"结余良好({surplus:.1%})"
    elif surplus >= 0.05:
        score, label = 0.30, f"结余正常({surplus:.1%})"
    elif surplus >= 0.0:
        score, label = 0.60, f"结余偏低({surplus:.1%})"
    else:
        score, label = 0.90, f"入不敷出({surplus:.1%})"
    return surplus, score, label, total_income - total_expense


def calc_fast_outflow(df: pd.DataFrame):
    income_df = df[df['direction'] == '收入'].sort_values('date')
    expense_df = df[df['direction'] == '支出'].sort_values('date')
    if income_df.empty or expense_df.empty:
        return 0.0, 0.10, "无流出记录", 0.0, 0.0
    total_income = income_df['amount'].sum()
    median_income = income_df['amount'].median()
    large_threshold = max(median_income * 2, 3000)
    normal_outflow = 0.0
    for _, income in income_df.iterrows():
        cutoff = income['date'] + pd.Timedelta(hours=24)
        out = expense_df[(expense_df['date'] > income['date']) & (expense_df['date'] <= cutoff)]['amount'].sum()
        normal_outflow += min(out, income['amount'])
    normal_ratio = normal_outflow / total_income if total_income > 0 else 0.0
    large_income = income_df[income_df['amount'] >= large_threshold]
    large_outflow = 0.0
    large_total = large_income['amount'].sum()
    for _, income in large_income.iterrows():
        cutoff = income['date'] + pd.Timedelta(hours=24)
        out = expense_df[(expense_df['date'] > income['date']) & (expense_df['date'] <= cutoff)]['amount'].sum()
        large_outflow += min(out, income['amount'])
    large_ratio = large_outflow / large_total if large_total > 0 else 0.0
    combined = normal_ratio * 0.4 + large_ratio * 0.6
    if combined < 0.30:
        score, label = 0.10, f"沉淀良好({combined:.1%})"
    elif combined < 0.50:
        score, label = 0.35, f"留存偏短({combined:.1%})"
    elif combined < 0.70:
        score, label = 0.65, f"快进快出({combined:.1%})"
    else:
        score, label = 0.90, f"高度中转({combined:.1%})"
    return combined, score, label, normal_ratio, large_ratio


def calc_income_stability(df: pd.DataFrame):
    income_df = df[df['direction'] == '收入']
    if income_df.empty:
        return 0.0, 0.90, {"coverage_months": 0, "cv": 0, "concentration": 0}, "无收入"
    now = income_df['date'].max()
    recent = income_df[income_df['date'] >= now - pd.DateOffset(months=6)]
    months_covered = recent['date'].dt.to_period('M').nunique()
    coverage_ratio = months_covered / 6.0
    coverage_score = 0.10 if coverage_ratio >= 5 / 6 else 0.35 if coverage_ratio >= 4 / 6 else 0.65 if coverage_ratio >= 3 / 6 else 0.90
    monthly = recent.groupby(recent['date'].dt.to_period('M'))['amount'].sum()
    cv = (monthly.std() / monthly.mean()) if len(monthly) > 1 and monthly.mean() > 0 else 0.0
    cv_score = 0.10 if cv < 0.30 else 0.35 if cv < 0.60 else 0.65 if cv < 1.00 else 0.90
    cp_sum = income_df.groupby('counterparty')['amount'].sum()
    total = cp_sum.sum()
    concentration = (cp_sum.max() / total) if total > 0 else 0.0
    conc_score = 0.15 if 0.30 <= concentration <= 0.70 else 0.35 if 0.15 <= concentration < 0.30 or 0.70 < concentration <= 0.85 else 0.70
    score = coverage_score * 0.40 + cv_score * 0.40 + conc_score * 0.20
    label = "稳定" if score < 0.25 else "有波动" if score < 0.50 else "波动较大" if score < 0.75 else "极不稳定"
    detail = {"coverage_months": int(months_covered), "coverage_score": coverage_score, "cv": round(cv, 3), "cv_score": cv_score, "concentration": round(concentration, 3), "conc_score": conc_score}
    return score, score, label, detail


def calc_balance_pressure(df: pd.DataFrame, threshold: float = 1000):
    if df.empty or 'balance' not in df.columns:
        df_w = df.copy().sort_values('date')
        df_w['ci'] = df_w.apply(lambda r: r['amount'] if r['direction'] == '收入' else 0, axis=1).cumsum()
        df_w['ce'] = df_w.apply(lambda r: r['amount'] if r['direction'] == '支出' else 0, axis=1).cumsum()
        bal = df_w['ci'] - df_w['ce']
    else:
        bal = df['balance'].dropna()
    if len(bal) == 0:
        return 0.0, 0.50, "数据不足", 0
    low_days = (bal < threshold).sum()
    low_ratio = low_days / len(bal)
    if low_ratio < 0.10:
        score, label = 0.10, f"安全垫充足({low_ratio:.1%})"
    elif low_ratio < 0.25:
        score, label = 0.35, f"偶有压力({low_ratio:.1%})"
    elif low_ratio < 0.50:
        score, label = 0.65, f"压力明显({low_ratio:.1%})"
    else:
        score, label = 0.90, f"经常性不足({low_ratio:.1%})"
    return low_ratio, score, label, int(low_days)


def calc_cashflow_risk(df: pd.DataFrame) -> Dict[str, Any]:
    s1_ratio, s1_score, s1_label, net_cashflow = calc_surplus_ratio(df)
    fo_ratio, s2_score, s2_label, n24, l24 = calc_fast_outflow(df)
    s3_score, _, s3_label, s3_detail = calc_income_stability(df)
    lb_ratio, s4_score, s4_label, lb_days = calc_balance_pressure(df)
    cashflow_score = s1_score * 0.333 + s2_score * 0.250 + s3_score * 0.250 + s4_score * 0.167
    return {
        "cashflow_score": round(cashflow_score, 4),
        "surplus_ratio": round(s1_ratio, 4),
        "surplus_label": s1_label,
        "fast_outflow_ratio": round(fo_ratio, 4),
        "fast_outflow_label": s2_label,
        "normal_24h_ratio": round(n24, 4),
        "large_24h_ratio": round(l24, 4),
        "stability_score": round(s3_score, 4),
        "stability_label": s3_label,
        "stability_detail": s3_detail,
        "low_balance_ratio": round(lb_ratio, 4),
        "low_balance_label": s4_label,
        "net_cashflow": round(net_cashflow, 2),
        "sub_scores": {
            "A1_surplus": {"score": round(s1_score, 4), "label": s1_label},
            "A2_fast_outflow": {"score": round(s2_score, 4), "label": s2_label},
            "A3_stability": {"score": round(s3_score, 4), "label": s3_label},
            "A4_balance_pressure": {"score": round(s4_score, 4), "label": s4_label},
        }
    }


# =============================================================================
# B. 异常交易模式风险分（40%）
# =============================================================================
HIGH_KW = ["套现", "垫还", "代还", "过桥", "走账", "刷单", "下款", "贷款", "借款"]
MED_KW = ["pos", "POS", "刷卡", "银联", "商户结算", "信用卡还款", "花呗", "借呗", "微粒贷"]


def _kw_score(text: str):
    h = sum(1 for kw in HIGH_KW if kw in text)
    m = sum(1 for kw in MED_KW if kw in text)
    return (1.0, h, "high") if h > 0 else (0.5, m, "medium") if m > 0 else (0.0, 0, "none")


def calc_fixed_amount(df: pd.DataFrame):
    all_txns = pd.concat([df[df['direction'] == '收入'], df[df['direction'] == '支出']]).sort_values('date')
    if len(all_txns) < 5:
        return 0.0, 0.10, "交易不足", {}
    cnt = all_txns['amount'].round(0).value_counts()
    repeat_cnt = int(cnt.iloc[0]) if len(cnt) > 0 else 0
    repeat_ratio = repeat_cnt / len(all_txns)
    short_repeat = 0
    for i in range(len(all_txns)):
        for j in range(i + 1, min(i + 10, len(all_txns))):
            delta = (all_txns.iloc[j]['date'] - all_txns.iloc[i]['date']).days
            if 0 < delta <= 7 and abs(all_txns.iloc[i]['amount'] - all_txns.iloc[j]['amount']) < 1:
                short_repeat += 1
    abnormal = min(repeat_ratio * 2 + (short_repeat / len(all_txns)), 1.0)
    score = 0.10 if abnormal < 0.25 else 0.35 if abnormal < 0.40 else 0.65 if abnormal < 0.60 else 0.90
    label = "正常" if abnormal < 0.25 else "轻度异常" if abnormal < 0.40 else "中度异常" if abnormal < 0.60 else "高度异常"
    return abnormal, score, label, {"max_repeat_count": repeat_cnt, "repeat_ratio": round(repeat_ratio, 3), "short_repeat_count": short_repeat}


def calc_mirror_flow(df: pd.DataFrame, threshold: float = 0.05, hours: int = 24):
    income_df = df[df['direction'] == '收入'].sort_values('date')
    expense_df = df[df['direction'] == '支出'].sort_values('date')
    if len(income_df) == 0:
        return 0.0, 0.10, "无收入", 0
    mirror = 0
    for _, inc in income_df.iterrows():
        cutoff = inc['date'] + pd.Timedelta(hours=hours)
        cands = expense_df[(expense_df['date'] > inc['date']) & (expense_df['date'] <= cutoff)]
        for _, exp in cands.iterrows():
            if abs(exp['amount'] - inc['amount']) / inc['amount'] <= threshold:
                mirror += 1
                break
    ratio = mirror / len(income_df)
    score = 0.10 if ratio < 0.05 else 0.35 if ratio < 0.10 else 0.65 if ratio < 0.20 else 0.90
    label = "无镜像" if ratio < 0.05 else "偶有镜像" if ratio < 0.10 else "镜像明显" if ratio < 0.20 else "高度镜像"
    return ratio, score, label, mirror


def calc_keyword_risk(df: pd.DataFrame):
    all_txns = pd.concat([df[df['direction'] == '收入'], df[df['direction'] == '支出']])
    n = len(all_txns)
    if n == 0:
        return 0.0, 0.10, "无敏感词", {"high_hits": 0, "medium_hits": 0}
    h_cnt, m_cnt = 0, 0
    for _, row in all_txns.iterrows():
        text = str(row.get('description', '')) + str(row.get('counterparty', ''))
        _, hits, lvl = _kw_score(text)
        if lvl == "high":
            h_cnt += hits
        elif lvl == "medium":
            m_cnt += hits
    risk = min((h_cnt * 1.0 + m_cnt * 0.5) / n * 3, 1.0)
    score = 0.10 if risk < 0.08 else 0.35 if risk < 0.20 else 0.65 if risk < 0.45 else 0.90
    label = "无敏感词" if risk < 0.08 else "轻度命中" if risk < 0.20 else "中度命中" if risk < 0.45 else "高度命中"
    return risk, score, label, {"high_hits": h_cnt, "medium_hits": m_cnt}


def calc_loan_chain(df: pd.DataFrame):
    kw_list = ["还款", "分期", "借款", "贷款", "还借", "利息", "花呗", "借呗", "微粒贷", "京东金条", "美团生活费"]
    all_txns = pd.concat([df[df['direction'] == '收入'], df[df['direction'] == '支出']])
    n = len(all_txns)
    hits = 0
    for _, row in all_txns.iterrows():
        text = str(row.get('description', '')) + str(row.get('counterparty', ''))
        for kw in kw_list:
            if kw in text:
                hits += 1
                break
    ratio = hits / n if n > 0 else 0
    score = 0.10 if ratio < 0.03 else 0.35 if ratio < 0.08 else 0.65 if ratio < 0.15 else 0.90
    label = "无借贷链" if ratio < 0.03 else "轻度疑似" if ratio < 0.08 else "中度疑似" if ratio < 0.15 else "高度疑似"
    return ratio, score, label, hits


def calc_night_txn(df: pd.DataFrame):
    all_txns = pd.concat([df[df['direction'] == '收入'], df[df['direction'] == '支出']]).copy()
    n = len(all_txns)
    if n == 0:
        return 0.0, 0.10, "时段正常", 0
    if 'hour' not in all_txns.columns:
        all_txns['hour'] = all_txns['date'].dt.hour
    night = all_txns[(all_txns['hour'] >= 23) | (all_txns['hour'] <= 5)]
    ratio = len(night) / n
    score = 0.10 if ratio < 0.05 else 0.35 if ratio < 0.15 else 0.65 if ratio < 0.30 else 0.90
    label = "时段正常" if ratio < 0.05 else "偶有夜交易" if ratio < 0.15 else "夜交易偏多" if ratio < 0.30 else "高度异常时段"
    return ratio, score, label, len(night)


def calc_abnormal_risk(df: pd.DataFrame) -> Dict[str, Any]:
    b1, _, l1, d1 = calc_fixed_amount(df)
    b2, _, l2, c2 = calc_mirror_flow(df)
    b3, _, l3, d3 = calc_keyword_risk(df)
    b4, _, l4, c4 = calc_loan_chain(df)
    b5, _, l5, c5 = calc_night_txn(df)
    abnormal_score = b1 * 0.25 + b2 * 0.25 + b3 * 0.20 + b4 * 0.20 + b5 * 0.10
    return {
        "abnormal_score": round(abnormal_score, 4),
        "sub_scores": {
            "B1_fixed_amount": {"score": round(b1, 4), "label": l1, "detail": d1},
            "B2_mirror_flow": {"score": round(b2, 4), "label": l2, "mirror_count": c2},
            "B3_keyword": {"score": round(b3, 4), "label": l3, "detail": d3},
            "B4_loan_chain": {"score": round(b4, 4), "label": l4, "hit_count": c4},
            "B5_night_txn": {"score": round(b5, 4), "label": l5, "night_count": c5},
        }
    }


# =============================================================================
# 风险等级 & 额度
# =============================================================================
RISK_LEVELS = [(0.75, "极高风险"), (0.50, "高风险"), (0.25, "中风险"), (0.0, "低风险")]

def get_risk_level(score: float) -> str:
    for t, l in RISK_LEVELS:
        if score >= t:
            return l
    return "低风险"

RISK_DISC = {"低风险": 1.0, "中风险": 0.7, "高风险": 0.3, "极高风险": 0.0}
STAB_DISC = {"稳定": 1.1, "有波动": 1.0, "波动较大": 0.8, "极不稳定": 0.7}
INC_COEFF = {"工薪族": 0.35, "个体经营": 0.25, "电商/商户型": 0.20, "资金中转型": 0.15, "混合型": 0.25}


def calc_limit(monthly_avg: float, cust_type: str, risk_lvl: str, stab_label: str) -> float:
    coef = INC_COEFF.get(cust_type, 0.25)
    rdisc = RISK_DISC.get(risk_lvl, 0.0)
    sdisc = STAB_DISC.get(stab_label, 1.0)
    if rdisc == 0:
        return 0
    return max(0, round(monthly_avg * coef * rdisc * sdisc, 0))


# =============================================================================
# 硬拒绝 & 人工复核
# =============================================================================
def check_reject(df: pd.DataFrame, cf: Dict, ab: Dict) -> Dict[str, Any]:
    three_ago = df['date'].max() - pd.DateOffset(months=3)
    recent_inc = df[(df['direction'] == '收入') & (df['date'] >= three_ago)]['amount'].sum()
    reasons = []
    if recent_inc < 3000:
        reasons.append("近3个月总收入过低，低于最低准入阈值")
    df_w = df.copy()
    df_w['month'] = df_w['date'].dt.to_period('M')
    monthly_net = df_w.groupby('month').apply(
        lambda g: g[g['direction'] == '收入']['amount'].sum() - g[g['direction'] == '支出']['amount'].sum(), include_groups=False)
    neg_months = (monthly_net < 0).sum()
    if neg_months >= 3:
        reasons.append(f"连续{neg_months}个月净现金流为负")
    if ab['sub_scores']['B2_mirror_flow']['score'] > 0.35:
        reasons.append("高强度镜像进出特征明显")
    if ab['sub_scores']['B4_loan_chain']['score'] > 0.4:
        reasons.append("多头借贷/借新还旧特征显著")
    if ab['sub_scores']['B3_keyword']['score'] > 0.7:
        reasons.append("存在大量疑似套现/走账/刷流水行为")
    return {"rejected": len(reasons) > 0, "reasons": reasons}


def check_manual_review(df: pd.DataFrame, cf: Dict, ab: Dict, cust_type: str) -> Dict[str, Any]:
    cf_score = cf.get('cashflow_score', 0)
    ab_score = ab.get('abnormal_score', 0)
    mirror = ab['sub_scores']['B2_mirror_flow']['score']
    loan = ab['sub_scores']['B4_loan_chain']['score']
    signals = []
    if cust_type in ["个体经营", "电商/商户型"]:
        signals.append("客户类型疑似商户/经营者")
    if ab_score < 0.3 and cf_score > 0.5:
        signals.append("收入波动大但总体结余良好")
    if mirror > 0.15 and ab_score < 0.5:
        signals.append("固定额交易多，但对手方正常")
    if loan > 0.1 and loan < 0.3:
        signals.append("存在贷款相关交易，但强度一般，建议人工核实")
    if cf_score > 0.6 and ab_score < 0.3:
        signals.append("高风险分主要由单一维度拉高，建议人工确认")
    return {"needs_review": len(signals) > 0, "signals": signals}


# =============================================================================
# 风险标签 & 解释生成
# =============================================================================
def generate_tags(cf: Dict, ab: Dict, risk_lvl: str) -> List[str]:
    tags = []
    s = cf.get('surplus_ratio', 0)
    fo = cf.get('fast_outflow_ratio', 0)
    lb = cf.get('low_balance_ratio', 0)
    stab = cf.get('stability_label', '')
    mirror = ab['sub_scores']['B2_mirror_flow']['score']
    loan = ab['sub_scores']['B4_loan_chain']['score']
    kw = ab['sub_scores']['B3_keyword']['score']
    fixed = ab['sub_scores']['B1_fixed_amount']['score']
    if s < 0:
        tags.append("🚨 入不敷出")
    elif s < 0.05:
        tags.append("⚠️ 结余偏低")
    if fo > 0.5:
        tags.append("🚨 资金快进快出")
    elif fo > 0.3:
        tags.append("⚠️ 留存偏短")
    if "不稳定" in stab or "波动大" in stab:
        tags.append("⚠️ 收入不稳定")
    elif "稳定" in stab:
        tags.append("✅ 收入稳定")
    if lb > 0.5:
        tags.append("🚨 余额经常不足")
    elif lb > 0.25:
        tags.append("⚠️ 偶有资金压力")
    if mirror > 0.2:
        tags.append("🚨 疑似资金中转")
    elif mirror > 0.1:
        tags.append("⚠️ 偶有镜像进出")
    if loan > 0.4:
        tags.append("🚨 疑似多头借贷")
    elif loan > 0.1:
        tags.append("⚠️ 存在贷款相关交易")
    if kw > 0.6:
        tags.append("🚨 敏感关键词高命中")
    elif kw > 0.3:
        tags.append("⚠️ 敏感关键词轻度命中")
    if fixed > 0.5:
        tags.append("🚨 固定额交易异常")
    elif fixed > 0.25:
        tags.append("⚠️ 固定额交易偏多")
    if risk_lvl == "低风险" and not tags:
        tags.append("✅ 风险指标均正常")
    return tags


def generate_explanation(cf: Dict, ab: Dict, cust_type: str, risk_lvl: str, total: float) -> str:
    parts = []
    fo = cf.get('fast_outflow_ratio', 0)
    stab = cf.get('stability_label', '')
    ml = ab['sub_scores']['B2_mirror_flow']['label']
    ll = ab['sub_scores']['B4_loan_chain']['label']
    kl = ab['sub_scores']['B3_keyword']['label']
    if risk_lvl in ("极高风险", "高风险"):
        parts.append(f"综合风险评分{total:.2f}，属于{risk_lvl}客户。")
    else:
        parts.append(f"综合风险评分{total:.2f}，风险在可控范围内。")
    if fo > 0.5:
        parts.append("近6个月资金快速流出特征明显，多笔入账后在24小时内快速转出，存在资金中转嫌疑。")
    elif fo > 0.3:
        parts.append("资金留存偏短，部分入账资金未充分沉淀即转出。")
    if "不稳定" in stab or "波动大" in stab:
        parts.append("收入连续性和稳定性偏差，月度收入波动较大。")
    elif "稳定" in stab:
        parts.append("收入稳定性良好。")
    if "镜像" in ml and "无" not in ml:
        parts.append("检测到短期镜像进出交易，建议关注资金真实用途。")
    if "疑似" in ll or "多头" in ll:
        parts.append("存在疑似借贷链行为，可能涉及多头借贷或借新还旧。")
    if "命中" in kl and "无" not in kl:
        parts.append("交易备注/对手方中检测到敏感关键词，建议人工核实交易背景。")
    if len(parts) == 1:
        parts.append("各维度未发现明显异常信号，财务状况基本正常。")
    return " ".join(parts)


# =============================================================================
# 主分析入口
# =============================================================================
def analyze(df: pd.DataFrame) -> Dict[str, Any]:
    sample = validate_sample(df)
    if not sample.valid:
        return {
            "total_risk_score": None,
            "risk_level": "样本无效",
            "suggested_limit": 0,
            "manual_review": False,
            "reject_flag": True,
            "risk_tags": ["🚨 样本无效"],
            "explanation": f"样本校验未通过：{sample.reason}。建议：{'；'.join(sample.suggestions)}",
            "sub_scores": {},
            "sample_validation": sample.to_dict(),
            "customer_type": None,
        }
    cust_type = classify_customer(df)
    cf = calc_cashflow_risk(df)
    ab = calc_abnormal_risk(df)
    total = round(cf['cashflow_score'] * 0.6 + ab['abnormal_score'] * 0.4, 4)
    risk_lvl = get_risk_level(total)
    inc_df = df[df['direction'] == '收入']
    six_ago = df['date'].max() - pd.DateOffset(months=6)
    recent = inc_df[inc_df['date'] >= six_ago]
    monthly_incs = recent.groupby(recent['date'].dt.to_period('M'))['amount'].sum()
    monthly_avg = float(monthly_incs.mean()) if len(monthly_incs) > 0 else float(inc_df['amount'].sum())
    limit = calc_limit(monthly_avg, cust_type, risk_lvl, cf['stability_label'])
    reject = check_reject(df, cf, ab)
    manual = check_manual_review(df, cf, ab, cust_type)
    tags = generate_tags(cf, ab, risk_lvl)
    explanation = generate_explanation(cf, ab, cust_type, risk_lvl, total)
    return {
        "total_risk_score": total,
        "risk_level": risk_lvl,
        "suggested_limit": limit,
        "manual_review": manual['needs_review'],
        "reject_flag": reject['rejected'],
        "risk_tags": tags,
        "explanation": explanation,
        "customer_type": cust_type,
        "monthly_avg_income": round(monthly_avg, 2),
        "sample_validation": sample.to_dict(),
        "reject_rules": reject,
        "manual_review_signals": manual,
        "cashflow_score": cf['cashflow_score'],
        "abnormal_score": ab['abnormal_score'],
        "sub_scores": {"cashflow": cf['sub_scores'], "abnormal": ab['sub_scores']},
        "cashflow_behavior": cf,
        "abnormal_trading": ab,
    }
