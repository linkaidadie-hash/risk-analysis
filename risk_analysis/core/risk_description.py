"""
风险描述生成器 - 将数字评分转换为中文说明
"""

def generate_risk_description(risk_result, cash_flow_behavior, liability_result, 
                               loan_result, cashing_result, abnormal_result, 
                               limit, rate, decision):
    """生成详细的风险描述"""
    
    risk_level = risk_result['risk_level']
    total_score = risk_result['total_score']
    
    # 风险等级图标
    risk_icons = {'high': '🔴', 'medium': '🟡', 'low': '🟢', 'very_low': '🟢'}
    risk_names = {'high': '高风险', 'medium': '中风险', 'low': '低风险', 'very_low': '极低风险'}
    
    # 1. 综合结论
    conclusion = f"""
### {risk_icons.get(risk_level, '🟡')} {risk_names.get(risk_level, '中风险')}客户 - {decision}

**综合风险评分：{total_score:.2f}/1.00**
"""
    
    # 2. 风险因素详情
    risk_factors = []
    
    # 贷款风险
    if loan_result['loan_ratio'] > 0.5:
        risk_factors.append(f"  • 贷款占比过高（{loan_result['loan_ratio']:.0%}）：您的收入中超过一半被识别为借款/贷款，缺乏稳定的经营性收入")
    elif loan_result['loan_ratio'] > 0.3:
        risk_factors.append(f"  • 贷款占比较高（{loan_result['loan_ratio']:.0%}）：收入中有较大比例来自借款")
    
    if loan_result['large_loan_count'] > 0:
        risk_factors.append(f"  • 存在大额贷款（{loan_result['large_loan_count']}笔，合计¥{loan_result['large_loan_amount']:,.0f}）：需关注还款压力")
    
    # 资金行为风险
    retention_hours = cash_flow_behavior['avg_retention_hours']
    if retention_hours < 24:
        risk_factors.append(f"  • 资金快进快出（留存仅{retention_hours:.0f}小时）：资金到账后迅速转出，缺乏沉淀，资金链紧张")
    elif retention_hours < 72:
        risk_factors.append(f"  • 资金留存较短（{retention_hours:.0f}小时）：资金在账户停留时间较短")
    
    if cash_flow_behavior['stability_score'] > 0.6:
        risk_factors.append(f"  • 收入波动较大：月收入不稳定，抗风险能力较弱")
    
    if cash_flow_behavior['pressure_score'] > 0.5:
        risk_factors.append(f"  • 资金压力较大：存在频繁的大额支出")
    
    # 隐性负债风险
    if liability_result['has_implicit_liabilities']:
        risk_factors.append(f"  • 检测到隐性负债（{liability_result['repayment_count']}笔还款记录）：存在未披露的借款或分期还款")
        if liability_result['regular_payments']:
            for p in liability_result['regular_payments'][:2]:
                risk_factors.append(f"    - 规律性还款：每{p['interval_days']:.0f}天还款¥{p['amount']:,.0f}，疑似分期负债")
    
    # 套现风险
    if cashing_result['score'] > 0.5:
        risk_factors.append(f"  • 套现风险较高（评分{cashing_result['score']:.2f}）：存在疑似套现交易行为")
    elif cashing_result['score'] > 0.3:
        risk_factors.append(f"  • 存在套现嫌疑：部分交易模式与套现特征吻合")
    
    # 异常流动风险
    if abnormal_result['score'] > 0.6:
        risk_factors.append(f"  • 资金流动异常：存在快进快出、高频交易等异常模式")
    
    # 如果没有风险因素
    if not risk_factors:
        risk_factors.append("  • 未发现明显风险因素，财务状况良好")
    
    risk_section = """
### ⚠️ 风险因素分析
""" + "\n".join(risk_factors)
    
    # 3. 财务数据摘要
    total_income = loan_result['total_income']
    total_expense = loan_result['total_expense']
    net_flow = loan_result['net_flow']
    
    financial_section = f"""
### 📊 财务数据摘要
| 指标 | 数值 | 说明 |
|------|------|------|
| 总收入 | ¥{total_income:,.2f} | 统计周期内所有收入 |
| 总支出 | ¥{total_expense:,.2f} | 统计周期内所有支出 |
| 净现金流 | ¥{net_flow:,.2f} | 收入 - 支出 |
| 贷款占比 | {loan_result['loan_ratio']:.1%} | 借款/贷款占总收入比例 |
| 大额贷款笔数 | {loan_result['large_loan_count']} | 单笔超过阈值的大额借款 |
"""
    
    # 4. 资金行为摘要
    behavior_section = f"""
### 💰 资金行为分析
| 指标 | 数值 | 评价 |
|------|------|------|
| 资金留存时间 | {retention_hours:.0f}小时 | {'⚠️ 快进快出' if retention_hours < 24 else '✅ 留存正常' if retention_hours < 168 else '✅ 沉淀良好'} |
| 资金周转率 | {cash_flow_behavior['turnover_rate']:.2f} | {'⚠️ 入不敷出' if cash_flow_behavior['turnover_rate'] > 0.9 else '✅ 收支平衡'} |
| 收入稳定性 | {1-cash_flow_behavior['stability_score']:.0%} | {'⚠️ 波动较大' if cash_flow_behavior['stability_score'] > 0.6 else '✅ 相对稳定'} |
| 资金压力 | {cash_flow_behavior['pressure_score']:.0%} | {'⚠️ 压力较大' if cash_flow_behavior['pressure_score'] > 0.5 else '✅ 压力可控'} |
"""
    
    # 5. 授信建议
    advice_section = f"""
### 💡 授信建议
**建议额度：¥{limit:,.0f}**
**参考利率：{rate*100:.1f}%**
**放款决策：{decision}**

"""
    
    if risk_level == 'high':
        advice_section += """
**建议措施：**
1. 暂不授信，或要求提供更多经营流水证明
2. 建议增加担保措施（抵押、保证人等）
3. 补充近6个月银行流水及纳税证明
4. 建议先从小额短期产品开始合作
"""
    elif risk_level == 'medium':
        advice_section += """
**建议措施：**
1. 额度降低至标准的50-70%
2. 利率适当上浮
3. 建议增加共同借款人或担保
4. 缩短借款期限，密切监控资金用途
"""
    elif risk_level == 'low':
        advice_section += """
**建议措施：**
1. 可按标准额度授信
2. 提供优惠利率
3. 建议建立长期合作关系
"""
    else:
        advice_section += """
**建议措施：**
1. 可给予较高额度
2. 享受最优惠利率
3. 优质客户，建议提供VIP服务
"""
    
    # 组合所有部分
    full_description = conclusion + risk_section + financial_section + behavior_section + advice_section
    
    return full_description
