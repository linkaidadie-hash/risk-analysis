"""
额度 & 利率决策模块
"""
from config import (
    RISK_COEFS, MAX_LIMIT, MIN_LIMIT,
    INTEREST_RATES, CREDIT_ADVICE,
    LIMIT_B_DAYS, LIMIT_B_FACTOR,
    RISK_THRESHOLDS,
)


class CreditLimitManager:
    def __init__(self):
        self.limit_coefs = RISK_COEFS
        self.max_limit = MAX_LIMIT
        self.min_limit = MIN_LIMIT
        self.rates = INTEREST_RATES

    def risk_level(self, score: float) -> str:
        """根据综合评分返回风险等级。"""
        if score >= RISK_THRESHOLDS["high"]:
            return "high"
        if score >= RISK_THRESHOLDS["medium"]:
            return "medium"
        if score < 0.15:
            return "very_low"
        return "low"

    def calculate_limit(self, net_income: float, risk_level: str, cashing_ratio: float = 0) -> float:
        """方案A：月均收入 × 风险系数 × 贷款占比调整。"""
        if net_income < self.min_limit:
            return 0
        coef = self.limit_coefs.get(risk_level, 0.5)
        limit = net_income * coef * 6
        if cashing_ratio > 0.3:
            limit *= 0.5
        return min(limit, self.max_limit)

    def calculate_limit_b(self, net_cashflow: float, days: int) -> float:
        """方案B：日均净现金流 × 25 × 0.65（更保守）。"""
        if net_cashflow <= 0:
            return 0
        daily_net = net_cashflow / max(days, 1)
        limit = daily_net * LIMIT_B_DAYS * LIMIT_B_FACTOR
        return min(max(limit, self.min_limit), self.max_limit)

    def get_rate(self, risk_level: str) -> float:
        return self.rates.get(risk_level.lower(), 0.15)

    def get_advice(self, risk_level: str) -> dict:
        return CREDIT_ADVICE.get(risk_level.lower(), CREDIT_ADVICE["medium"])

    def make_decision(self, risk_level: str, limit: float) -> str:
        if risk_level == "high" or limit < 10000:
            return "拒绝放款"
        if risk_level == "medium":
            return "谨慎放款"
        return "可放款"
