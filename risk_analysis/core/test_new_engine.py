"""
改进版模拟器 - 生成更真实的交易行为
按客户类型模拟，匹配真实业务特征
"""
import pandas as pd
import numpy as np
import random
import sys
sys.path.insert(0, '/root/risk_system')
from core.new_engine import analyze


def set_seed(seed=42):
    np.random.seed(seed)
    random.seed(seed)


def gen_dates(start="2025-10-01", end="2026-04-10"):
    return pd.date_range(start=start, end=end, freq="D")


# =============================================================================
# 工薪族模拟器（真实特征）
# =============================================================================
def build_salary_worker(dates):
    """
    真实工薪族特征：
    - 每月1-5号发工资，整数或带少量零头（不会是10000.0这样整）
    - 日常消费：金额随机带零头，周末略多
    - 网购：偶尔大额支出
    - 无夜间交易（22:00-次日8:00无交易）
    - 无镜像进出
    - 收入来源单一
    """
    records = []
    for d in dates:
        hour = random.randint(9, 17)  # 交易发生在白天
        txn_time = d.replace(hour=hour, minute=random.randint(0, 59))

        # 工资：每月1-3号，金额带零头
        if d.day in [1, 2, 3]:
            records.append({
                "date": txn_time,
                "direction": "收入",
                "amount": round(random.uniform(8200, 9500), 2),  # 带零头
                "counterparty": "XX科技有限公司",
                "description": "工资",
            })

        # 日常消费：超市/餐饮，金额小且零散
        if random.random() > 0.35:
            amount = round(random.uniform(15, 180), 2)
            cps = ["超市", "便利店", "餐饮店", "外卖平台"]
            dsc = ["日常消费", "购物", "餐饮"]
            records.append({
                "date": txn_time,
                "direction": "支出",
                "amount": amount,
                "counterparty": random.choice(cps),
                "description": random.choice(dsc),
            })

        # 网购大件：偶尔（每月2-3次）
        if random.random() > 0.92:
            records.append({
                "date": txn_time,
                "direction": "支出",
                "amount": round(random.uniform(200, 800), 2),
                "counterparty": "某电商平台",
                "description": "网购",
            })

        # 交通出行
        if random.random() > 0.85:
            records.append({
                "date": txn_time,
                "direction": "支出",
                "amount": round(random.uniform(3, 30), 2),
                "counterparty": "公交/地铁",
                "description": "交通",
            })

    return records


# =============================================================================
# 个体经营模拟器（真实特征）
# =============================================================================
def build_merchant(dates):
    """
    真实个体经营特征：
    - 收入不固定，金额波动大，日期不规律
    - 有收入零头（小数点后有值）
    - 支出包含供应商采购、成本
    - 偶尔有花呗/信用卡还款（关键词命中但强度低）
    - 收入来源相对集中（主要几个客户）
    - 日间交易为主，晚上偶尔
    """
    clients = ["客户李", "客户王", "客户陈", "客户刘", "散客"]
    suppliers = ["原材料供应商", "物流费", "仓库租金", "水电费"]
    records = []
    for d in dates:
        hour = random.choices(
            [random.randint(8, 12), random.randint(14, 18), random.randint(20, 22)],
            weights=[0.5, 0.4, 0.1]
        )[0]
        txn_time = d.replace(hour=hour, minute=random.randint(0, 59))

        # 收入：每5-10天一笔，金额较大且随机
        if random.random() > 0.85:
            records.append({
                "date": txn_time,
                "direction": "收入",
                "amount": round(random.uniform(1500, 12000), 2),  # 带零头
                "counterparty": random.choice(clients),
                "description": "货款",
            })

        # 支出：成本、进货，日常开销
        if random.random() > 0.4:
            amount = round(random.uniform(80, 600), 2)
            records.append({
                "date": txn_time,
                "direction": "支出",
                "amount": amount,
                "counterparty": random.choice(suppliers),
                "description": "采购/成本",
            })

        # 花呗/信用卡还款（低频，还款金额固定）
        if d.day == 10 or d.day == 25:
            if random.random() > 0.6:
                records.append({
                    "date": txn_time,
                    "direction": "支出",
                    "amount": round(random.uniform(500, 2000), 2),
                    "counterparty": "花呗",
                    "description": "花呗还款",
                })

    return records


# =============================================================================
# 资金中转型模拟器（真实特征）
# =============================================================================
def build_transferring(dates):
    """
    真实资金中转特征：
    - 大额进，大额出，金额接近，间隔短（1-4小时）
    - 金额多为整数或大额
    - 交易对手经常变
    - 快速流出，无沉淀
    - 日间操作
    - 结余极低或为负
    """
    records = []
    for d in dates:
        # 上午大额进
        in_hour = random.randint(9, 11)
        amount = float(random.choice([3000, 5000, 8000, 10000, 15000]))
        records.append({
            "date": d.replace(hour=in_hour, minute=random.randint(0, 59)),
            "direction": "收入",
            "amount": amount,
            "counterparty": f"对方{random.randint(100,999)}",
            "description": "转账",
        })

        # 1-4小时后出去，金额略小（扣手续费或留一点余额）
        out_amount = round(amount * random.uniform(0.95, 0.995), 2)
        out_hour = min(in_hour + random.randint(1, 4), 22)
        records.append({
            "date": d.replace(hour=out_hour, minute=random.randint(0, 59)),
            "direction": "支出",
            "amount": out_amount,
            "counterparty": f"对方{random.randint(100,999)}",
            "description": "转出",
        })

        # 少量日常消费（维持日常假象）
        if random.random() > 0.7:
            records.append({
                "date": d.replace(hour=random.randint(12, 20), minute=random.randint(0, 59)),
                "direction": "支出",
                "amount": round(random.uniform(20, 100), 2),
                "counterparty": "日常",
                "description": "消费",
            })

    return records


# =============================================================================
# 多头借贷模拟器（真实特征）
# =============================================================================
def build_multi_loan(dates):
    """
    多头借贷特征：
    - 收入中有多笔"贷款下款"（微粒贷/花呗/借呗/京东金条）
    - 还款日固定（5号/15号/25号），反复出现
    - 收入不稳定，有时有小额兼职补充
    - 关键词命中明显
    - 有一定结余但靠借贷维持
    """
    records = []
    loan_products = [
        ("微粒贷", "贷款下款"),
        ("花呗", "花呗购物"),
        ("借呗", "借呗借款"),
        ("京东金条", "京东金条借款"),
        ("美团生活费", "生活费借款"),
    ]
    for d in dates:
        hour = random.randint(9, 20)
        txn_time = d.replace(hour=hour, minute=random.randint(0, 59))

        # 贷款下款：固定日期（如5号、15号、25号）从不同平台进
        if d.day in [5, 15, 25]:
            product, desc = random.choice(loan_products)
            records.append({
                "date": txn_time,
                "direction": "收入",
                "amount": round(random.uniform(2000, 8000), 2),
                "counterparty": product,
                "description": desc,
            })

        # 还款日：同一天还掉（小额）
        if d.day in [5, 15, 25]:
            for _ in range(random.randint(1, 2)):
                product, _ = random.choice(loan_products)
                records.append({
                    "date": txn_time + pd.Timedelta(hours=random.randint(1, 3)),
                    "direction": "支出",
                    "amount": round(random.uniform(200, 1000), 2),
                    "counterparty": product,
                    "description": random.choice(["还款", "分期还款"]),
                })

        # 偶尔有真实收入（兼职/劳务）
        if random.random() > 0.88:
            records.append({
                "date": txn_time,
                "direction": "收入",
                "amount": round(random.uniform(100, 800), 2),
                "counterparty": "雇主/客户",
                "description": "劳务费",
            })

        # 日常支出
        if random.random() > 0.5:
            records.append({
                "date": txn_time,
                "direction": "支出",
                "amount": round(random.uniform(20, 150), 2),
                "counterparty": "日常",
                "description": "消费",
            })

    return records


# =============================================================================
# 电商/商户模拟器（真实特征）
# =============================================================================
def build_ecommerce(dates):
    """
    电商/商户特征：
    - 收入频率高（每天多笔）
    - 大量不同对手方（随机客户名）
    - 金额随机，批次特征（进货-出货模式）
    - 有时凌晨有订单（电商特性）
    - 收入集中度低（不依赖单一来源）
    - 有平台服务费支出（关键词）
    """
    records = []
    customer_pool = [f"买家{i}" for i in range(1, 50)]
    for d in dates:
        # 日间：正常销售
        for _ in range(random.randint(2, 8)):
            hour = random.randint(9, 22)
            records.append({
                "date": d.replace(hour=hour, minute=random.randint(0, 59)),
                "direction": "收入",
                "amount": round(random.uniform(30, 800), 2),
                "counterparty": random.choice(customer_pool),
                "description": "线上订单",
            })

        # 平台服务费/推广费（关键词）
        if random.random() > 0.7:
            records.append({
                "date": d.replace(hour=random.randint(10, 16), minute=random.randint(0, 59)),
                "direction": "支出",
                "amount": round(random.uniform(50, 500), 2),
                "counterparty": "电商平台",
                "description": "平台服务费",
            })

        # 偶尔凌晨订单（电商特性，区分工薪族）
        if random.random() > 0.85:
            records.append({
                "date": d.replace(hour=random.randint(0, 5), minute=random.randint(0, 59)),
                "direction": "收入",
                "amount": round(random.uniform(50, 300), 2),
                "counterparty": random.choice(customer_pool),
                "description": "线上订单",
            })

        # 货源采购
        if random.random() > 0.75:
            records.append({
                "date": d.replace(hour=random.randint(8, 14), minute=random.randint(0, 59)),
                "direction": "支出",
                "amount": round(random.uniform(200, 2000), 2),
                "counterparty": "供应商",
                "description": "采购",
            })

    return records


# =============================================================================
# 运行测试
# =============================================================================
def run_test(name, builder, seed=42):
    print(f"\n{'='*68}")
    print(f"  {name}")
    print(f"{'='*68}")
    set_seed(seed)
    dates = gen_dates()
    records = builder(dates)
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    result = analyze(df)
    print(f"  风险等级     : {result['risk_level']}  |  总风险分: {result['total_risk_score']}")
    print(f"  现金流分     : {result['cashflow_score']} (60%)  |  异常分: {result['abnormal_score']} (40%)")
    print(f"  建议额度     : ¥{result['suggested_limit']:,.0f}")
    print(f"  客户分型     : {result['customer_type']}")
    print(f"  月均收入     : ¥{result['monthly_avg_income']:,.2f}")
    print(f"  风险标签     : {result['risk_tags']}")
    print(f"  硬拒         : {result['reject_flag']}  {result['reject_rules']['reasons']}")
    print(f"  人工复核     : {result['manual_review']}  {result['manual_review_signals']['signals']}")
    print(f"  解释         : {result['explanation']}")
    print(f"  --- 现金流子项 ---")
    for k, v in result['cashflow_behavior']['sub_scores'].items():
        print(f"    {k}: score={v['score']}  label={v['label']}")
    print(f"  --- 异常交易子项 ---")
    for k, v in result['abnormal_trading']['sub_scores'].items():
        print(f"    {k}: score={v['score']}  label={v['label']}")


if __name__ == "__main__":
    print("=" * 68)
    print("  流水风控策略 - 改进版模拟测试（真实行为特征）")
    print("=" * 68)

    run_test("【1】工薪族 - 正常稳定", build_salary_worker, seed=42)
    run_test("【2】个体经营 - 波动有贷款", build_merchant, seed=123)
    run_test("【3】资金中转型 - 高风险", build_transferring, seed=777)
    run_test("【4】多头借贷 - 还款频繁", build_multi_loan, seed=999)
    run_test("【5】电商/商户 - 高频零散", build_ecommerce, seed=555)
