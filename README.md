# 流水风控分析系统

交易流水分析工具，支持微信/支付宝/银行格式，输出资金行为分析、风险评级、大额交易审核建议。

## 功能

- 📊 **多格式支持**：微信、支付宝、银行 CSV/Excel
- 💰 **收支统计**：收入/支出笔数、金额、净现金流
- 🔍 **大额交易**：自动标记收入/支出 TOP10
- ⏱️ **资金行为**：留存时间、周转率、稳定性、资金压力
- ⚠️ **风险评级**：综合风险评分 + 等级（高/中/低）
- 💡 **审核建议**：基于风险评分的授信建议

## 安装

```bash
pip install -r requirements.txt
```

## 使用

### 命令行

```bash
python scripts/analyze.py <文件路径> [csv|excel|wechat]
```

示例：

```bash
python scripts/analyze.py data/wechat.xlsx
python scripts/analyze.py data/alipay.csv
python scripts/analyze.py reports/bank_statement.xlsx wechat
```

### Python API

```python
import sys
sys.path.insert(0, 'path/to/risk_analysis')
from core.data_adapter import DataAdapter
from core.risk_engine import RiskEngine

# 标准化数据
adapter = DataAdapter()
df = adapter.standardize(df_raw)

# 资金行为分析
engine = RiskEngine()
behavior = engine.analyze_cash_flow_behavior(df)

# 风险评分
score = engine.calculate_risk_score(loan_ratio=0, behavior_risk=behavior['behavior_risk_score'])
```

## 项目结构

```
risk_analysis/
├── core/
│   ├── __init__.py
│   ├── config.py       # 阈值和配置参数
│   ├── data_adapter.py # 数据标准化（微信/支付宝/银行）
│   └── risk_engine.py  # 风控引擎
├── scripts/
│   └── analyze.py      # 命令行分析脚本
└── README.md
```

## 依赖

- Python 3.x
- pandas >= 2.0
- numpy >= 1.24
- openpyxl >= 3.1

## 风险评级说明

| 评分区间 | 等级 | 建议 |
|---------|------|------|
| ≥ 0.5 | 🔴 高风险 | 不建议授信 |
| 0.3 - 0.5 | 🟡 中风险 | 谨慎授信，额度降低 |
| < 0.3 | 🟢 低风险 | 可正常授信 |

## 配置

阈值参数集中在 `core/config.py`，包括：

- 资金留存时间阈值（快进快出/较短/正常/沉淀良好）
- 资金周转率阈值（入不敷出/收支平衡/有盈余）
- 收入稳定性阈值（波动大/有一定波动/稳定）
- 风险权重分配
- 额度计算系数

根据实际业务需求调整即可。
