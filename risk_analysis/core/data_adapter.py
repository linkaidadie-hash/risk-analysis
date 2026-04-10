import pandas as pd
import numpy as np
import re
from typing import Optional


def _parse_amount(raw) -> float:
    """解析金额字符串，返回绝对值。"""
    s = str(raw).replace('¥', '').replace(',', '').strip()
    s = re.sub(r'[^\d.-]', '', s)
    try:
        return abs(float(s))
    except (ValueError, TypeError):
        return 0.0


def _find_column(df: pd.DataFrame, *keywords: str) -> Optional[str]:
    """在 df.columns 中查找包含任意 keyword 的列名。"""
    for col in df.columns:
        col_str = str(col).strip()
        if any(kw in col_str for kw in keywords):
            return col
    return None


class DataAdapter:
    def __init__(self):
        self.source_type: Optional[str] = None

    def _standardize_wechat(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理微信格式流水。"""
        self.source_type = '微信'
        col_map = {}
        for col in df.columns:
            col_str = str(col).strip()
            if '交易时间' in col_str:
                col_map[col] = 'date'
            elif '交易对方' in col_str:
                col_map[col] = 'counterparty'
            elif '收/支' in col_str:
                col_map[col] = 'direction'
            elif '金额' in col_str:
                col_map[col] = 'amount'
            elif '备注' in col_str:
                col_map[col] = 'description'

        df = df.rename(columns=col_map)
        result = pd.DataFrame()

        result['date'] = pd.to_datetime(df['date'], errors='coerce') if 'date' in df.columns else pd.NaT
        result['amount'] = df['amount'].apply(_parse_amount) if 'amount' in df.columns else 0.0

        dir_col = 'direction' if 'direction' in df.columns else None
        if dir_col:
            dirs = df[dir_col].astype(str).str.strip()
            result['direction'] = '不计收支'
            result.loc[dirs.str.contains('收入'), 'direction'] = '收入'
            result.loc[dirs.str.contains('支出'), 'direction'] = '支出'
        else:
            result['direction'] = '不计收支'

        result['counterparty'] = df['counterparty'].fillna('').astype(str) if 'counterparty' in df.columns else ''
        result['description'] = df['description'].fillna('').astype(str) if 'description' in df.columns else ''
        result['category'] = ''  # 微信格式无分类字段

        return result

    def _standardize_generic(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理支付宝/银行通用格式流水。"""
        result = pd.DataFrame()

        # 日期
        date_col = _find_column(df, '时间', '日期')
        result['date'] = pd.to_datetime(df[date_col], errors='coerce') if date_col else pd.NaT

        # 金额 + 方向
        amount_col = _find_column(df, '金额')
        if amount_col:
            raw_amounts = df[amount_col].apply(_parse_amount)
            amounts_num = pd.to_numeric(df[amount_col].astype(str).str.replace(',', '').str.strip().apply(
                lambda x: re.sub(r'[^\d.-]', '', x)), errors='coerce')
            result['amount'] = amounts_num.abs()
            result['direction'] = amounts_num.apply(
                lambda x: '支出' if x < 0 else ('收入' if x > 0 else '不计收支'))
        else:
            result['amount'] = 0.0
            result['direction'] = '不计收支'

        # 收支列（优先按字符判断）
        dir_col = _find_column(df, '收/支')
        if dir_col:
            dirs = df[dir_col].astype(str).str.strip()
            result['direction'] = '不计收支'
            result.loc[dirs.str.contains('收入'), 'direction'] = '收入'
            result.loc[dirs.str.contains('支出'), 'direction'] = '支出'

        # 对方户名
        cp_col = _find_column(df, '对方', '户名')
        result['counterparty'] = df[cp_col].fillna('').astype(str) if cp_col else ''

        # 备注/摘要
        desc_col = _find_column(df, '备注', '摘要', '商品说明')
        result['description'] = df[desc_col].fillna('').astype(str) if desc_col else ''

        # 分类
        cat_col = _find_column(df, '分类', '类别')
        result['category'] = df[cat_col].fillna('').astype(str) if cat_col else ''

        self.source_type = '支付宝' if dir_col else '银行'
        return result

    def standardize(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化任意格式的交易流水。"""
        columns = [str(col).strip() for col in df.columns]

        is_wechat = (
            any('交易时间' in c for c in columns) and
            any('交易对方' in c for c in columns) and
            any('收/支' in c for c in columns)
        )

        if is_wechat:
            result_df = self._standardize_wechat(df)
        else:
            result_df = self._standardize_generic(df)

        # 过滤无效记录
        result_df = result_df[result_df['direction'].isin(['收入', '支出'])]
        result_df = result_df[result_df['amount'] > 0]
        result_df = result_df[result_df['date'].notna()]

        print(f"[DEBUG] 最终有效交易: {len(result_df)} 笔")
        print(f"[DEBUG] 收入: {(result_df['direction'] == '收入').sum()} 笔")
        print(f"[DEBUG] 支出: {(result_df['direction'] == '支出').sum()} 笔")

        result_df['source'] = self.source_type
        return result_df.reset_index(drop=True)
