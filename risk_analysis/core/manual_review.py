"""
手工审核模块 - 按交易对手汇总标记
"""
import streamlit as st
import pandas as pd


def _safe_mode(series: pd.Series) -> str:
    """取众数，失败则返回空字符串。"""
    if series.empty:
        return ''
    try:
        mode = series.mode()
        if len(mode) > 0:
            return str(mode.iloc[0])
    except Exception:
        pass
    return ''


# 智能推荐关键词（可配置化）
LOAN_KEYWORDS = ['借款', '贷款', '借贷', '还', '借', '债', '信用', '花呗', '借呗', '微粒贷', '网商贷', '京东金条']
BUSINESS_KEYWORDS = ['淘宝', '天猫', '京东', '拼多多', '美团', '饿了么', '商业服务', '收款', '销售',
                     '工资', '薪资', '奖金', '佣金', '返利', '退款', '报销', '支付宝', '微信']


def _recommend(cp: str, desc: str = '', category: str = '') -> str:
    """根据交易对手/备注/分类推荐收入类型。"""
    combined = f"{cp} {desc} {category}".lower()
    if any(kw in combined for kw in LOAN_KEYWORDS):
        return '贷款'
    if any(kw in combined for kw in BUSINESS_KEYWORDS):
        return '经营收入'
    return '经营收入'  # 默认


class ManualReview:
    def __init__(self):
        self.reviewed = False

    def show_review_interface(self, df: pd.DataFrame, loan_result: dict) -> dict:
        """显示手工审核界面，按交易对手聚合展示。"""
        st.markdown("---")
        st.markdown("## ✏️ 手工审核区")
        st.warning("系统识别可能不准确，请手动标记主要交易对手类型")

        income_df = df[df['direction'] == '收入'].copy()
        if len(income_df) == 0:
            st.info("无收入交易")
            return loan_result

        # 按交易对手聚合
        agg_df = income_df.groupby('counterparty').agg(
            total_amount=('amount', 'sum'),
            txn_count=('amount', 'count'),
            category=('category', _safe_mode),
            description=('description', _safe_mode),
        ).reset_index()
        agg_df.columns = ['交易对手', '总金额', '笔数', '主要分类', '主要备注']
        agg_df = agg_df.sort_values('总金额', ascending=False).reset_index(drop=True)

        st.markdown(f"### 📊 交易对手分析（前20，{len(agg_df)} 个对手）")

        if 'cp_types' not in st.session_state:
            st.session_state.cp_types = {}

        shown = agg_df.head(20)
        for _, row in shown.iterrows():
            cp = str(row['交易对手'])
            total = float(row['总金额'])
            count = int(row['笔数'])
            cat = str(row.get('主要分类', '')) or ''
            desc = str(row.get('主要备注', '')) or ''

            recommended = _recommend(cp, desc, cat)
            current = st.session_state.cp_types.get(cp, recommended)

            cols = st.columns([3, 1.5, 1, 2, 2, 2])
            with cols[0]:
                st.write(cp[:30] if cp else '(空)')
            with cols[1]:
                st.write(f"¥{total:,.0f}")
            with cols[2]:
                st.write(f"{count}笔")
            with cols[3]:
                st.write(cat[:20])
            with cols[4]:
                st.write(desc[:20])
            with cols[5]:
                sel = st.selectbox(
                    "类型",
                    options=['经营收入', '贷款', '不计入'],
                    index=['经营收入', '贷款', '不计入'].index(current),
                    key=f"cp_select_{hash(cp) & 0x7FFFFFFF}",
                    label_visibility="collapsed",
                )
                st.session_state.cp_types[cp] = sel

        st.markdown("---")

        col1, col2 = st.columns([1, 3])
        with col1:
            apply_btn = st.button("✅ 应用手工标记并重新计算", type="primary", use_container_width=True)

        # 应用逻辑（按钮触发，每次 rerun 只执行一次）
        if apply_btn and 'manual_apply_done' not in st.session_state:
            business_total = 0.0
            loan_total = 0.0
            business_count = 0
            loan_count = 0
            excluded_count = 0

            for _, row in income_df.iterrows():
                cp = str(row.get('counterparty', ''))
                amount = float(row['amount'])
                cp_type = st.session_state.cp_types.get(cp)

                if cp_type == '经营收入':
                    business_total += amount
                    business_count += 1
                elif cp_type == '贷款':
                    loan_total += amount
                    loan_count += 1
                else:
                    excluded_count += 1

            total_income = business_total + loan_total
            loan_ratio = loan_total / total_income if total_income > 0 else 1.0

            # 更新传入的 loan_result（修改引用本身）
            loan_result['business_income'] = business_total
            loan_result['business_count'] = business_count
            loan_result['total_loan_amount'] = loan_total
            loan_result['total_loan_count'] = loan_count
            loan_result['loan_ratio'] = loan_ratio

            st.session_state['manual_review_applied'] = True
            st.session_state['manual_loan_result'] = loan_result.copy()
            st.session_state['manual_apply_done'] = True
            st.rerun()

        # 重置
        if st.session_state.get('manual_review_applied', False):
            if st.button("🔄 重置手工审核", use_container_width=True):
                st.session_state.pop('manual_review_applied', None)
                st.session_state.pop('manual_loan_result', None)
                st.session_state.pop('manual_apply_done', None)
                st.session_state.cp_types = {}
                st.rerun()

        # 防止 apply 后重复执行
        if not apply_btn:
            st.session_state.pop('manual_apply_done', None)

        return loan_result

    def is_manual_applied(self) -> bool:
        return st.session_state.get('manual_review_applied', False)

    def get_manual_result(self) -> dict:
        return st.session_state.get('manual_loan_result', None)
