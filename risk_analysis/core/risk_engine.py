import pandas as pd
import numpy as np
from config import (
    BEHAVIOR_RETENTION_HOURS, BEHAVIOR_RETENTION_SCORES,
    BEHAVIOR_TURNOVER, BEHAVIOR_TURNOVER_SCORES,
    STABILITY_RATIO, STABILITY_SCORES,
    PRESSURE_RATIO, PRESSURE_SCORES,
    RISK_WEIGHT,
    LOAN_RATIO_WEIGHT, BEHAVIOR_WEIGHT,
    RISK_THRESHOLDS,
)


def _retention_status(hours: float) -> tuple:
    if hours < BEHAVIOR_RETENTION_HOURS["fast"]:
        return "快进快出", BEHAVIOR_RETENTION_SCORES["fast"]
    if hours < BEHAVIOR_RETENTION_HOURS["short"]:
        return "留存较短", BEHAVIOR_RETENTION_SCORES["short"]
    if hours < BEHAVIOR_RETENTION_HOURS["normal"]:
        return "留存正常", BEHAVIOR_RETENTION_SCORES["normal"]
    return "沉淀良好", BEHAVIOR_RETENTION_SCORES["good"]


def _turnover_status(rate: float) -> tuple:
    if rate >= BEHAVIOR_TURNOVER["deficit"]:
        return "入不敷出", BEHAVIOR_TURNOVER_SCORES["deficit"]
    if rate >= BEHAVIOR_TURNOVER["balanced"]:
        return "收支平衡", BEHAVIOR_TURNOVER_SCORES["balanced"]
    return "有盈余", BEHAVIOR_TURNOVER_SCORES["surplus"]


def _stability_status(ratio: float) -> tuple:
    if ratio < STABILITY_RATIO["volatile"]:
        return "波动大", STABILITY_SCORES["volatile"]
    if ratio < STABILITY_RATIO["fluctuate"]:
        return "有一定波动", STABILITY_SCORES["fluctuate"]
    return "稳定", STABILITY_SCORES["stable"]


def _pressure_status(net: float, income: float) -> tuple:
    if net < 0:
        return "压力很大（入不敷出）", PRESSURE_SCORES["deficit"]
    if net < income * PRESSURE_RATIO:
        return "有一定压力", PRESSURE_SCORES["some"]
    return "压力可控", PRESSURE_SCORES["ok"]


class RiskEngine:
    def analyze_cash_flow_behavior(self, df: pd.DataFrame) -> dict:
        """资金行为分析（不修改原 DataFrame）。"""
        if df.empty:
            return {
                'avg_retention_hours': 0,
                'retention_status': '无数据',
                'turnover_rate': 0,
                'turnover_status': '无数据',
                'stability_status': '无数据',
                'pressure_status': '无数据',
                'behavior_risk_score': 0.5,
                'total_income': 0.0,
                'total_expense': 0.0,
                'net_cashflow': 0.0,
            }

        income_df = df[df['direction'] == '收入'].sort_values('date')
        expense_df = df[df['direction'] == '支出'].sort_values('date')

        # 资金留存时间
        retention_times = []
        for _, income in income_df.iterrows():
            later = expense_df[expense_df['date'] > income['date']]
            if len(later) > 0:
                hours = (later.iloc[0]['date'] - income['date']).total_seconds() / 3600
                if 0 < hours < 720:
                    retention_times.append(hours)

        avg_retention = float(np.mean(retention_times)) if retention_times else 72.0
        retention_label, retention_score = _retention_status(avg_retention)

        # 资金周转率
        total_income = float(df[df['direction'] == '收入']['amount'].sum())
        total_expense = float(df[df['direction'] == '支出']['amount'].sum())

        if total_income > 0:
            turnover = total_expense / total_income
            turnover_label, turnover_score = _turnover_status(turnover)
        else:
            turnover = 0.0
            turnover_label, turnover_score = "无收入", 0.5

        # 收入稳定性（月度收入变异系数）
        df_work = df.copy()
        df_work['month'] = df_work['date'].dt.to_period('M')
        monthly_income = df_work[df_work['direction'] == '收入'].groupby('month')['amount'].sum()

        if len(monthly_income) > 1:
            mean_inc = monthly_income.mean()
            median_inc = monthly_income.median()
            ratio = median_inc / mean_inc if mean_inc > 0 else 1.0
            stability_label, stability_score = _stability_status(float(ratio))
        else:
            stability_label, stability_score = "数据不足", 0.4

        # 资金压力
        net_cashflow = total_income - total_expense
        pressure_label, pressure_score = _pressure_status(net_cashflow, total_income)

        # 综合行为风险
        behavior_risk = (
            retention_score * RISK_WEIGHT["retention"] +
            turnover_score * RISK_WEIGHT["turnover"] +
            stability_score * RISK_WEIGHT["stability"] +
            pressure_score * RISK_WEIGHT["pressure"]
        )

        return {
            'avg_retention_hours': avg_retention,
            'retention_status': retention_label,
            'turnover_rate': turnover,
            'turnover_status': turnover_label,
            'stability_status': stability_label,
            'pressure_status': pressure_label,
            'behavior_risk_score': behavior_risk,
            'total_income': total_income,
            'total_expense': total_expense,
            'net_cashflow': net_cashflow,
        }

    def calculate_risk_score(self, loan_ratio: float, behavior_risk: float) -> float:
        return loan_ratio * LOAN_RATIO_WEIGHT + behavior_risk * BEHAVIOR_WEIGHT

    def risk_level(self, score: float) -> str:
        if score >= RISK_THRESHOLDS["high"]:
            return "high"
        if score >= RISK_THRESHOLDS["medium"]:
            return "medium"
        if score < 0.15:   # 极低阈值（可调）
            return "very_low"
        return "low"

    def calculate_limit_a(self, monthly_income: float, loan_ratio: float, risk_level: str) -> float:
        from config import RISK_COEFS, MAX_LIMIT, MIN_LIMIT
        if monthly_income < 5000:
            return 0
        coef = RISK_COEFS.get(risk_level, 0.5)
        limit = monthly_income * coef * (1 - loan_ratio * 0.5)
        return min(max(limit, MIN_LIMIT), MAX_LIMIT)

    def calculate_limit_b(self, net_cashflow: float, days: int) -> float:
        from config import MAX_LIMIT, MIN_LIMIT, LIMIT_B_DAYS, LIMIT_B_FACTOR
        if net_cashflow <= 0:
            return 0
        daily_net = net_cashflow / max(days, 1)
        limit = daily_net * LIMIT_B_DAYS * LIMIT_B_FACTOR
        return min(max(limit, MIN_LIMIT), MAX_LIMIT)
