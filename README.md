# 流水风控分析系统

交易流水分析工具，支持微信/支付宝/银行格式，自动识别大额交易、评估资金行为和风险等级。

## 功能

- 📊 交易流水导入（CSV/Excel）
- 💰 收支统计与大额交易标记
- 📈 资金行为分析（留存时间、周转率、稳定性）
- ⚠️ 综合风险评分

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python3 scripts/analyze.py <文件路径>
```

## 目录结构

```
risk_analysis/
├── core/           # 核心引擎
│   ├── data_adapter.py    # 数据适配器
│   └── risk_engine.py     # 风控引擎
├── scripts/
│   └── analyze.py        # 分析入口
└── config.py
```

## API 服务

```bash
python3 risk_analysis/http_api.py
```
