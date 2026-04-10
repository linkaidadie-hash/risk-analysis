import os
from typing import Dict, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(BASE_DIR, "models/default_model.pkl")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ========== 通用阈值 ==========
FEATURE_LOOKBACK_DAYS = 180
MIN_TXNS_FOR_ANALYSIS = 5
MAX_LIMIT = 500000
MIN_LIMIT = 5000

# ========== 风险评分阈值 ==========
RISK_THRESHOLDS = {
    "high": 0.5,    # 综合评分 >= 0.5 → 高风险
    "medium": 0.3,  # 0.3 <= 综合评分 < 0.5 → 中风险
    "low": 0.0,     # 综合评分 < 0.3 → 低风险（极低单独判断）
}

# ========== 行为分析参数 ==========
BEHAVIOR_RETENTION_HOURS = {
    "fast": 24,     # < 24小时 快进快出
    "short": 72,    # < 72小时 留存较短
    "normal": 168,  # < 168小时（7天）留存正常
    # >= 168小时 沉淀良好
}

BEHAVIOR_RETENTION_SCORES = {
    "fast": 0.9,
    "short": 0.6,
    "normal": 0.3,
    "good": 0.1,
}

BEHAVIOR_TURNOVER = {
    "deficit": 1.2,   # >= 1.2 入不敷出
    "balanced": 0.9,  # >= 0.9 收支平衡
    # < 0.9 有盈余
}

BEHAVIOR_TURNOVER_SCORES = {
    "deficit": 0.8,
    "balanced": 0.5,
    "surplus": 0.2,
}

STABILITY_RATIO = {
    "volatile": 0.6,  # median/mean < 0.6 波动大
    "fluctuate": 0.8, # < 0.8 有一定波动
    # >= 0.8 稳定
}

STABILITY_SCORES = {
    "volatile": 0.7,
    "fluctuate": 0.5,
    "stable": 0.2,
}

PRESSURE_RATIO = 0.1  # 净现金流 < 收入*0.1 有压力

PRESSURE_SCORES = {
    "deficit": 0.9,
    "some": 0.5,
    "ok": 0.2,
}

# ========== 风险权重 ==========
RISK_WEIGHT = {
    "retention": 0.3,
    "turnover": 0.3,
    "stability": 0.2,
    "pressure": 0.2,
}

# ========== 贷款占比风险 ==========
LOAN_RATIO_WEIGHT = 0.6   # 贷款占比在综合评分中的权重
BEHAVIOR_WEIGHT = 0.4     # 行为风险在综合评分中的权重

# ========== 额度计算 ==========
RISK_COEFS = {
    "high": 0.3,
    "medium": 0.6,
    "low": 1.0,
    "very_low": 1.2,
}

LIMIT_B_DAYS = 25
LIMIT_B_FACTOR = 0.65

# ========== 利率 ==========
INTEREST_RATES = {
    "high": 0.24,
    "medium": 0.18,
    "low": 0.12,
    "very_low": 0.08,
}

# ========== 贷款配置 ==========
LOAN_CONFIG = {
    "large_loan_min": 10000,
    "small_accumulated_min": 30000,
    "inflow_outflow_ratio_range": [0.65, 1.35],
    "min_inflow_count": 1,
    "max_loan_days": 180,
    "min_loan_days": 30,
}

# ========== 套现检测 ==========
CASHING_CONFIG = {
    "min_txns": 2,
    "integer_ratio_threshold": 0.6,
    "common_amounts": [3000, 5000, 8000, 10000, 15000, 20000, 30000, 50000],
    "suspicious_keywords": [
        "支付", "科技", "信息", "网络", "电子",
        "pos", "刷卡", "收款", "扫码", "银联", "个体户"
    ],
}

# ========== 异常流动检测 ==========
ABNORMAL_FLOW_CONFIG = {
    "min_frequency": 5,
    "time_window_days": 30,
    "match_ratio_threshold": 0.7,
    "normal_keywords": ["信用卡", "房贷", "抵押", "车贷", "水电", "工资"],
}

# ========== 授信建议 ==========
CREDIT_ADVICE = {
    "high": {
        "advice": "❌ 不建议授信",
        "reason": "违约风险极高",
        "action": "拒绝授信或追加担保"
    },
    "medium": {
        "advice": "⚠️ 谨慎授信",
        "reason": "存在中度风险",
        "action": "额度降至50%或增加抵押"
    },
    "low": {
        "advice": "✅ 可正常授信",
        "reason": "风险可控",
        "action": "标准额度授信"
    },
    "very_low": {
        "advice": "✅✅ 优质客户",
        "reason": "经营状况良好",
        "action": "可提高额度"
    },
}

# ========== UI / 安全 ==========
UI_CONFIG = {
    "page_title": "民间借贷风控系统",
    "page_icon": "💰",
    "layout": "wide",
    "sidebar_state": "expanded",
}

SECURITY_CONFIG = {
    "session_timeout": 3600,
    "max_upload_size": 100,  # MB
    "allowed_extensions": [".xlsx", ".csv"],
}
