"""
简化手工审核 - 按单笔交易标记（适合小额高频场景）
"""
import streamlit as st
import pandas as pd
from core.manual_review import _recommend


class SimpleReview:
    def show(self, df: pd.DataFrame):
        """
        显示大额收入审核界面（按单笔展示）。
        返回 (business_total, loan_total)，未确认时返回 (None, None)。
        """
        st.markdown("---")
        st.markdown("## ✏️ 大额收入审核")
        st.info("请确认以下大额收入（前20笔）哪些是经营收入，哪些是借款")

        income_df = df[df['direction'] == '收入'].copy()
        if len(income_df) == 0:
            st.warning("无收入交易")
            return None, None

        top_income = income_df.nlargest(20, 'amount')

        if 'income_types' not in st.session_state:
            st.session_state.income_types = {}

        for idx, row in top_income.iterrows():
            cp = str(row.get('counterparty', '未知'))
            desc = str(row.get('description', ''))
            cat = str(row.get('category', ''))
            amount = float(row['amount'])
            date = row['date']

            recommended = _recommend(cp, desc, cat)
            current = st.session_state.income_types.get(idx, recommended)

            cols = st.columns([2, 1.5, 2, 2, 1.5])
            with cols[0]:
                st.write(date.strftime('%Y-%m-%d') if pd.notna(date) else '未知')
            with cols[1]:
                st.write(f"¥{amount:,.2f}")
            with cols[2]:
                st.write(cp[:30])
            with cols[3]:
                st.write(desc[:30])
            with cols[4]:
                sel = st.selectbox(
                    "类型",
                    options=['经营收入', '借款'],
                    index=0 if current == '经营收入' else 1,
                    key=f"income_{idx}",
                    label_visibility="collapsed",
                )
                st.session_state.income_types[idx] = sel

        if st.button("✅ 确认并计算", type="primary"):
            business_total = 0.0
            loan_total = 0.0
            business_count = 0
            loan_count = 0

            for idx, row in top_income.iterrows():
                amount = float(row['amount'])
                selected = st.session_state.income_types.get(idx, '借款')
                if selected == '经营收入':
                    business_total += amount
                    business_count += 1
                else:
                    loan_total += amount
                    loan_count += 1

            # 其余未在 top20 的收入全部归为借款
            other = income_df[~income_df.index.isin(top_income.index)]
            loan_total += float(other['amount'].sum())
            loan_count += len(other)

            st.session_state.business_total = business_total
            st.session_state.loan_total = loan_total
            st.session_state.business_count = business_count
            st.session_state.loan_count = loan_count
            st.session_state.review_done = True

            total = business_total + loan_total
            st.success(f"""
            ✅ 已确认！
            - 经营收入: {business_count}笔，¥{business_total:,.2f}
            - 借款: {loan_count}笔，¥{loan_total:,.2f}
            - 贷款占比: {loan_total / total * 100:.1f}%（贷款总额 ¥{loan_total:,.2f}）
            """)
            st.rerun()

        if st.session_state.get('review_done', False):
            return st.session_state.business_total, st.session_state.loan_total

        return None, None
