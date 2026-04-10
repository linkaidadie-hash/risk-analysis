#!/usr/bin/env python3
"""
流水风控分析脚本 - OpenClaw Skill 调用
用法: python3 analyze.py <文件路径> [文件类型: csv|excel|wechat]
"""

import sys
import os
import json
import pandas as pd
from datetime import datetime

# 添加 risk_system 路径
sys.path.insert(0, '/root/risk_system')

from core.data_adapter import DataAdapter
from core.risk_engine import RiskEngine

def analyze_file(filepath, source_type=None):
    """分析交易流水文件"""
    
    if not os.path.exists(filepath):
        return {"error": f"文件不存在: {filepath}"}
    
    # 读取文件
    filename = os.path.basename(filepath)
    is_wechat = '微信' in filename
    
    try:
        if filepath.endswith('.xlsx') or filepath.endswith('.xls'):
            if is_wechat:
                df_raw = pd.read_excel(filepath, header=16)
            else:
                df_raw = pd.read_excel(filepath)
        else:
            if is_wechat:
                df_raw = pd.read_csv(filepath, encoding='gbk', skiprows=16)
            else:
                try:
                    df_raw = pd.read_csv(filepath, encoding='gbk')
                except:
                    df_raw = pd.read_csv(filepath, encoding='utf-8')
    except Exception as e:
        return {"error": f"读取文件失败: {str(e)}"}
    
    if df_raw is None or len(df_raw) == 0:
        return {"error": "文件为空"}
    
    # 标准化数据
    adapter = DataAdapter()
    df = adapter.standardize(df_raw)
    
    if len(df) == 0:
        return {"error": "未识别到有效交易"}
    
    # 基础统计
    income_df = df[df['direction'] == '收入']
    expense_df = df[df['direction'] == '支出']
    income_sum = income_df['amount'].sum()
    expense_sum = expense_df['amount'].sum()
    
    # 大额交易
    top_income = income_df.nlargest(10, 'amount')[['date', 'amount', 'counterparty', 'description']].copy()
    top_expense = expense_df.nlargest(10, 'amount')[['date', 'amount', 'counterparty', 'description']].copy()
    
    # 资金行为分析
    engine = RiskEngine()
    behavior = engine.analyze_cash_flow_behavior(df)
    
    # 风险评分（假设贷款占比 0，后续用户需要手工审核确认）
    risk_score = engine.calculate_risk_score(0, behavior['behavior_risk_score'])
    
    if risk_score >= 0.5:
        risk_level = "🔴 高风险"
    elif risk_score >= 0.3:
        risk_level = "🟡 中风险"
    else:
        risk_level = "🟢 低风险"
    
    # 统计天数
    days = max((df['date'].max() - df['date'].min()).days, 1)
    
    # 格式化输出
    result = {
        "summary": {
            "source_type": adapter.source_type,
            "total_income_count": len(income_df),
            "total_income_amount": f"¥{income_sum:,.2f}",
            "total_expense_count": len(expense_df),
            "total_expense_amount": f"¥{expense_sum:,.2f}",
            "net_cashflow": f"¥{behavior['net_cashflow']:,.2f}",
            "days": days,
        },
        "cash_flow_behavior": {
            "avg_retention_hours": f"{behavior['avg_retention_hours']:.0f}小时",
            "retention_status": behavior['retention_status'],
            "turnover_rate": f"{behavior['turnover_rate']:.2f}",
            "turnover_status": behavior['turnover_status'],
            "stability_status": behavior['stability_status'],
            "pressure_status": behavior['pressure_status'],
        },
        "top_income": [],
        "top_expense": [],
        "risk_assessment": {
            "risk_score": f"{risk_score:.2f}/1.00",
            "risk_level": risk_level,
            "note": "风险评分基于贷款占比=0的假设，大额收入手工审核后需重新计算"
        }
    }
    
    # 大额收入
    for idx, row in top_income.iterrows():
        result["top_income"].append({
            "date": row['date'].strftime('%Y-%m-%d') if pd.notna(row['date']) else "未知",
            "amount": f"¥{row['amount']:,.2f}",
            "counterparty": str(row['counterparty'])[:30],
            "description": str(row['description'])[:50] if pd.notna(row['description']) else ""
        })
    
    # 大额支出
    for idx, row in top_expense.iterrows():
        result["top_expense"].append({
            "date": row['date'].strftime('%Y-%m-%d') if pd.notna(row['date']) else "未知",
            "amount": f"¥{row['amount']:,.2f}",
            "counterparty": str(row['counterparty'])[:30],
            "description": str(row['description'])[:50] if pd.notna(row['description']) else ""
        })
    
    return result

def format_text(result):
    """格式化为友好文本"""
    if "error" in result:
        return f"❌ 错误: {result['error']}"
    
    lines = []
    lines.append("=" * 50)
    lines.append("📊 流水风控分析报告")
    lines.append("=" * 50)
    
    # 基础统计
    s = result["summary"]
    lines.append(f"\n💰 收支概况（来源: {s['source_type']}）")
    lines.append(f"   收入: {s['total_income_count']}笔, {s['total_income_amount']}")
    lines.append(f"   支出: {s['total_expense_count']}笔, {s['total_expense_amount']}")
    lines.append(f"   净现金流: {s['net_cashflow']}")
    lines.append(f"   统计天数: {s['days']}天")
    
    # 资金行为
    b = result["cash_flow_behavior"]
    lines.append(f"\n💵 资金行为分析")
    lines.append(f"   资金留存: {b['avg_retention_hours']} ({b['retention_status']})")
    lines.append(f"   资金周转率: {b['turnover_rate']} ({b['turnover_status']})")
    lines.append(f"   收入稳定性: {b['stability_status']}")
    lines.append(f"   资金压力: {b['pressure_status']}")
    
    # 大额收入
    lines.append(f"\n🔴 大额收入 TOP10:")
    for i, item in enumerate(result["top_income"][:10], 1):
        lines.append(f"   {i}. {item['date']} {item['amount']} - {item['counterparty']}")
        if item['description']:
            lines.append(f"      备注: {item['description']}")
    
    # 大额支出
    lines.append(f"\n📤 大额支出 TOP10:")
    for i, item in enumerate(result["top_expense"][:10], 1):
        lines.append(f"   {i}. {item['date']} {item['amount']} - {item['counterparty']}")
        if item['description']:
            lines.append(f"      备注: {item['description']}")
    
    # 风险评估
    r = result["risk_assessment"]
    lines.append(f"\n⚠️ 风险评估")
    lines.append(f"   综合风险评分: {r['risk_score']}")
    lines.append(f"   风险等级: {r['risk_level']}")
    lines.append(f"   备注: {r['note']}")
    
    lines.append("\n" + "=" * 50)
    lines.append("📝 下一步: 请确认大额收入的性质（经营收入/借款）以获得准确风险评分")
    lines.append("=" * 50)
    
    return "\n".join(lines)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 analyze.py <文件路径>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    source_type = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = analyze_file(filepath, source_type)
    
    # 输出格式: JSON 或文本
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))
