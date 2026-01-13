import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json

# ---------------------------------------------------------
# 1. 設定・データ処理クラス (Backend Logic)
# ---------------------------------------------------------
class AssetManager:
    def __init__(self):
        # 本来はCSVやデータベースから読み込みますが、デモ用に初期値を設定
        if 'portfolio' not in st.session_state:
            # サンプルデータ: 証券会社のCSVを読み込んだ想定のデータフレーム
            data = {
                'Ticker': [
                    # 米国株・ETF (コア資産)
                    'VTI', 'VYM', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'KO', 'MCD',
                    # 日本株 (高配当・優待)
                    '7203.T', '8306.T', '9433.T', '8001.T', '7974.T', '2914.T', 
                    # その他 (コモディティ・暗号資産)
                    'GLD', 'BTC-USD', 'ETH-USD'
                ],
                'Name': [
                    # 米国株
                    'Vanguard Total Stock', 'High Dividend Yield', 'Invesco QQQ', 'Apple', 'Microsoft', 'NVIDIA', 'Coca-Cola', 'McDonalds',
                    # 日本株
                    'トヨタ自動車', '三菱UFJ FG', 'KDDI', '伊藤忠商事', '任天堂', 'JT (日本たばこ)', 
                    # その他
                    'SPDR Gold Shares', 'Bitcoin', 'Ethereum'
                ],
                'Category': [
                    '米国株ETF', '米国株ETF', '米国株ETF', '米国個別株', '米国個別株', '米国個別株', '米国個別株', '米国個別株',
                    '日本株', '日本株', '日本株', '日本株', '日本株', '日本株',
                    'コモディティ', '暗号資産', '暗号資産'
                ],
                'Quantity': [
                    # 数量 (口数・株数)
                    30, 45, 10, 15, 10, 8, 30, 10,  # 米国
                    100, 400, 200, 100, 100, 200,   # 日本 (単元株ベース)
                    5, 0.05, 1.5                    # その他
                ],
                'Target_Ratio': [
                    # 目標ポートフォリオ比率 (合計が1.0になるように設定)
                    0.25, 0.15, 0.10, 0.05, 0.05, 0.03, 0.02, 0.02, # 米国重視
                    0.05, 0.05, 0.05, 0.05, 0.04, 0.04,             # 日本安定
                    0.03, 0.01, 0.01                                # サテライト
                ]
            }
            st.session_state['portfolio'] = pd.DataFrame(data)
        
        if 'cash_balance' not in st.session_state:
            st.session_state['cash_balance'] = 1000000  # 現金残高 (円)
            
        if 'transactions' not in st.session_state:
            # サンプルデータ（給与予定とカード引き落とし予定）
            tx_data = {
                'Date': ['2025-11-27', '2025-11-27', '2025-12-10', '2025-12-25', '2026-01-27'],
                'Type': ['収入', '支出', '支出', '収入', '支出'],
                'Category': ['アルバイト先A', '三井住友カード', 'JCBカード', 'アルバイト先A', '三井住友カード'],
                'Amount': [73985, 45584, 5070, 86680, 110011],
                'Status': ['完了', '完了', '完了', '完了', '予定'] # 予定か完了か
            }
            df_tx = pd.DataFrame(tx_data)
            df_tx['Date'] = pd.to_datetime(df_tx['Date']) # 日付型に変換
            st.session_state['transactions'] = df_tx
            
        if 'notifications' not in st.session_state:
            # 過去の通知履歴サンプル
            st.session_state['notifications'] = [
                {'Date': '2025-11-28', 'Type': 'Alert', 'Message': 'ポートフォリオの変動率が閾値を超えました。'},
                {'Date': '2025-11-25', 'Type': 'Info', 'Message': '配当金が入金されました: $25.00'},
            ]

    def get_market_prices(self, df):
        """Yahoo Financeから現在価格を取得して結合する"""
        tickers = df['Ticker'].tolist()
        if not tickers:
            return df
        
        try:
            # yfinanceで一括取得 (週末の空白を埋めるため、少し長めに過去5日分取る)
            prices_data = yf.download(tickers, period="5d", progress=False)['Close']
            
            # 「前の日のデータ」で穴埋め(ffill)してから、最新行を取得する
            current_prices = prices_data.ffill().iloc[-1]
            
            # ドル円レート取得 (簡易的に150円とするか、APIで取るか。今回はAPIで取得)
            usd_jpy = yf.Ticker("JPY=X").history(period="1d")['Close'].iloc[-1]

            # データフレームに価格情報をマージ
            def calculate_value(row):
                ticker = row['Ticker']
                price = current_prices.get(ticker, 0)
                # 日本株以外（.Tがつかない）はドル建てと簡易判定して円換算
                if ".T" not in ticker and "-USD" not in ticker and ticker != "JPY=X":
                    price_jen = price * usd_jpy
                elif "-USD" in ticker: # 暗号資産
                     price_jen = price * usd_jpy
                else:
                    price_jen = price
                
                return price_jen

            df['Current_Price_JPY'] = df.apply(calculate_value, axis=1)
            df['Market_Value'] = df['Quantity'] * df['Current_Price_JPY']
            return df
            
        except Exception as e:
            st.error(f"データ取得エラー: {e}")
            df['Current_Price_JPY'] = 0
            df['Market_Value'] = 0
            return df

# ---------------------------------------------------------
# 新規追加: データの保存・復元クラス (CSV機能なし版)
# ---------------------------------------------------------
class DataManager:
    @staticmethod
    def export_data():
        """現在のセッション状態をJSON文字列として書き出す"""
        export_dict = {
            'cash_balance': st.session_state.get('cash_balance', 1000000),
            'notifications': st.session_state.get('notifications', []),
            # DataFrameをJSON文字列に変換して保存
            'portfolio_json': st.session_state['portfolio'].to_json(orient='records', date_format='iso'),
            'transactions_json': st.session_state['transactions'].to_json(orient='records', date_format='iso')
        }
        return json.dumps(export_dict, ensure_ascii=False, indent=2)

    @staticmethod
    def import_data(uploaded_file):
        """アップロードされたJSONファイルを読み込んでセッションに反映"""
        try:
            data = json.load(uploaded_file)
            
            # 1. 現金残高の復元
            if 'cash_balance' in data:
                st.session_state['cash_balance'] = data['cash_balance']
            
            # 2. 通知履歴の復元
            if 'notifications' in data:
                st.session_state['notifications'] = data['notifications']
            
            # 3. ポートフォリオの復元
            if 'portfolio_json' in data:
                st.session_state['portfolio'] = pd.read_json(data['portfolio_json'], orient='records')
                
            # 4. 家計簿の復元 (日付型を認識させる)
            if 'transactions_json' in data:
                df_tx = pd.read_json(data['transactions_json'], orient='records')
                if not df_tx.empty and 'Date' in df_tx.columns:
                    df_tx['Date'] = pd.to_datetime(df_tx['Date'])
                st.session_state['transactions'] = df_tx
                
            return True
        except Exception as e:
            st.error(f"データの読み込みに失敗しました: {e}")
            return False

# ---------------------------------------------------------
# 2. UI コンポーネント (Frontend Views)
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="個人資産ダッシュボード", page_icon="💹", layout="wide")
    manager = AssetManager()
    
    # --- サイドバー（ナビゲーション） ---
    # --- サイドバー（メニューに家計簿を追加） ---
    st.sidebar.title("メニュー")
    page = st.sidebar.radio("移動先", ["概要 (Overview)", "詳細 (Detail)", "家計簿 (Budget)", "資産入力 (Input)", "通知履歴 (History)", "データ管理 (Data)"])
    # データを最新化
    df_portfolio = st.session_state['portfolio']
    df_valued = manager.get_market_prices(df_portfolio.copy())
    
    total_investments = df_valued['Market_Value'].sum()
    cash = st.session_state['cash_balance']
    total_assets = total_investments + cash

    # --- 1. 概要画面 (Overview) ---
    if page == "概要 (Overview)":
        st.title("📊 資産状況サマリー")
        
        # KPIカード
        col1, col2, col3 = st.columns(3)
        col1.metric("総資産額", f"¥{total_assets:,.0f}")
        col2.metric("評価損益 (前日比)", "+¥12,400", "0.8%") # ※本来は履歴データと比較計算
        col3.metric("現金比率", f"{cash/total_assets*100:.1f}%")

        # グラフエリア
        c1, c2 = st.columns([1, 1])
        
        with c1:
            st.subheader("アセットアロケーション (現在)")
            # 資産クラスごとの集計
            alloc_df = df_valued.groupby('Category')['Market_Value'].sum().reset_index()
            # 現金も追加してグラフ化
            alloc_df.loc[len(alloc_df)] = ['現金', cash]
            
            fig_pie = px.pie(alloc_df, values='Market_Value', names='Category', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        with c2:
            st.subheader("リバランス判断")
            # 目標と現在の乖離を表示
            target_amounts = total_investments * df_valued['Target_Ratio'] # 簡易計算（投資資産内での比率）
            diff = df_valued['Market_Value'] - target_amounts
            
            df_rebalance = pd.DataFrame({
                'Ticker': df_valued['Ticker'],
                '現在額': df_valued['Market_Value'],
                '乖離額': diff
            })
            
            fig_bar = px.bar(df_rebalance, x='Ticker', y='乖離額', 
                             color='乖離額', title="目標乖離 (プラスは売り、マイナスは買い推奨)")
            st.plotly_chart(fig_bar, use_container_width=True)

    # --- 2. 詳細画面 (Detail) ---
    elif page == "詳細 (Detail)":
        st.title("📋 保有資産詳細")
        
        st.dataframe(df_valued.style.format({
            "Quantity": "{:.4f}",
            "Current_Price_JPY": "¥{:.0f}",
            "Market_Value": "¥{:.0f}",
            "Target_Ratio": "{:.1%}"
        }), use_container_width=True)
        
        st.subheader("資産クラス別内訳")
        st.bar_chart(df_valued.groupby('Category')['Market_Value'].sum())

    # --- 3. 入力画面 (Input) ---
    elif page == "資産入力 (Input)":
        st.title("📝 データ入力・更新")
        st.subheader("🏦 残高の直接修正")
        with st.form("input_form"):
            # 現在の値をデフォルトに設定
            new_cash = st.number_input("現在の現金残高 (円)", value=int(st.session_state['cash_balance']))
            
            st.info("証券データ（保有数）の修正")
            edited_df = st.data_editor(st.session_state['portfolio'], num_rows="dynamic")
            
            if st.form_submit_button("全データを保存・更新"):
                st.session_state['cash_balance'] = new_cash
                st.session_state['portfolio'] = edited_df
                st.success("データが更新されました！")

    # --- 4. 通知履歴画面 (History) ---
    elif page == "通知履歴 (History)":
        st.title("🔔 通知・アラート履歴")
        st.write("市場の急変や、リバランスのタイミング、配当金の入金予定などを表示します。")
        
        history_df = pd.DataFrame(st.session_state['notifications'])
        
        # テーブル表示（重要度で色分けなどの装飾が可能）
        st.table(history_df)
        
        # デモ用のアラート生成ボタン
        if st.button("市場急変チェックを実行 (デモ)"):
            new_alert = {
                'Date': datetime.now().strftime('%Y-%m-%d'),
                'Type': 'Warning',
                'Message': 'USD/JPYが1日で2%以上変動しました。資産価値を確認してください。'
            }
            st.session_state['notifications'].insert(0, new_alert)
            st.rerun()
            
# --- 5. 家計簿画面 (Budget) ---
    elif page == "家計簿 (Budget)":
        st.title("💰 家計簿・資金繰り管理")
        
        df_tx = st.session_state['transactions']
        today = pd.Timestamp(datetime.now().date())
        current_year = datetime.now().year # 今年の年を取得
        current_cash = st.session_state['cash_balance']

        # --- A. 資金繰りサマリー (3列に変更) ---
        st.subheader("📊 資金繰り状況")
        
        # 1. 年収計算 (今年のデータの '収入' を合計)
        annual_income = df_tx[
            (df_tx['Date'].dt.year == current_year) & 
            (df_tx['Type'] == '収入')
        ]['Amount'].sum()

        # 2. 未来の支出計算
        future_expenses = df_tx[(df_tx['Date'] >= today) & (df_tx['Type'] == '支出')]['Amount'].sum()
        
        # 3. 余力計算
        capacity = current_cash - future_expenses
        
        # 指標を3つ並べて表示
        col1, col2, col3 = st.columns(3)
        
        col1.metric(
            label=f"{current_year}年の年収 (合計)", 
            value=f"¥{annual_income:,.0f}",
            help="今年の1月1日から今日までに登録された「収入」と、将来の「収入予定」の合計額です。"
        )
        
        col2.metric(
            label="予定されている引き落とし総額", 
            value=f"¥{future_expenses:,.0f}",
            help="今日以降に予定されている「支出」の合計額です。"
        )
            
        col3.metric(
            label="現在の支払余力", 
            value=f"¥{capacity:,.0f}",
            delta=f"{capacity:,.0f}",
            help="現在の現金残高から、予定支出を引いた金額です。"
        )

        st.divider()

        # ==========================================
        # ★ パート・アルバイト給与計算 (前回作成分)
        # ==========================================
        st.subheader("🧮 パート・アルバイト給与計算")
        with st.expander("詳細な給与計算パネルを開く", expanded=False): # デフォルトは閉じておく
            with st.form("part_time_form_advanced"):
                c_date, c_cat = st.columns(2)
                pay_date = c_date.date_input("給料日（予定）", value=datetime.now() + timedelta(days=30))
                job_options = ["アルバイト先A", "アルバイト先B", "単発バイト", "副業", "その他"]
                salary_category = c_cat.selectbox("勤務先 (カテゴリ)", job_options)
                
                # シフト入力
                c1, c2 = st.columns(2)
                rate1 = c1.number_input("時給1 (基本)", value=1141, step=10, key="r1")
                hours1 = c2.number_input("時間1", value=68.0, step=0.5, key="h1")
                
                c3, c4 = st.columns(2)
                rate2 = c3.number_input("時給2 (深夜等)", value=100, step=10, key="r2")
                hours2 = c4.number_input("時間2", value=18.0, step=0.5, key="h2")

                allowance = st.number_input("その他手当", value=0, step=1000)

                total_salary = int((rate1 * hours1) + (rate2 * hours2) + allowance)
                st.write(f"💰 給与見込み: **¥{total_salary:,.0f}**")
                
                if st.form_submit_button("収入予定に追加"):
                    if total_salary > 0:
                        new_row = {'Date': pd.Timestamp(pay_date), 'Type': '収入', 'Category': salary_category, 'Amount': total_salary, 'Status': '予定'}
                        st.session_state['transactions'] = pd.concat([st.session_state['transactions'], pd.DataFrame([new_row])], ignore_index=True)
                        st.balloons()
                        st.rerun()

        st.divider()

        # --- B. 入出金リスト (未来と過去をタブ分け) ---
        st.subheader("📅 入出金リスト")
        
        tab_future, tab_past = st.tabs(["🔮 今後の予定", "📜 過去の履歴"])
        
        # 色分け用関数
        def highlight_type(val):
            return 'color: red; font-weight: bold;' if val == '支出' else 'color: blue; font-weight: bold;'

        with tab_future:
            future_tx = df_tx[df_tx['Date'] >= today].sort_values('Date')
            if not future_tx.empty:
                st.dataframe(future_tx.style.applymap(highlight_type, subset=['Type']).format({"Date": "{:%Y-%m-%d}", "Amount": "¥{:,}"}), use_container_width=True)
            else:
                st.info("これからの予定はありません。")

        with tab_past:
            # 日付が今日より前のものを抽出
            past_tx = df_tx[df_tx['Date'] < today].sort_values('Date', ascending=False) # 新しい順
            
            if not past_tx.empty:
                st.dataframe(past_tx.style.applymap(highlight_type, subset=['Type']).format({"Date": "{:%Y-%m-%d}", "Amount": "¥{:,}"}), use_container_width=True)
            else:
                st.info("過去の履歴データはありません。")

        # --- C. その他の予定登録 ---
        st.divider()
        st.subheader("📝 その他 収支の登録")
        with st.form("budget_form"):
            c1, c2, c3 = st.columns(3)
            new_date = c1.date_input("日付", value=datetime.now())
            new_type = c2.selectbox("収支", ["支出", "収入"])
            new_cat = c3.selectbox("項目名", ["食費", "交通費", "交際費", "三井住友カード", "臨時収入"])
            new_amt = st.number_input("金額", value=1000, step=1000)
            
            if st.form_submit_button("追加する"):
                new_row = {'Date': pd.Timestamp(new_date), 'Type': new_type, 'Category': new_cat, 'Amount': new_amt, 'Status': '予定'}
                st.session_state['transactions'] = pd.concat([st.session_state['transactions'], pd.DataFrame([new_row])], ignore_index=True)
                st.success("追加しました！")
                st.rerun()

# --- 6. データ管理画面 (Data) ---
    elif page == "データ管理 (Data)":
        st.title("💾 データのバックアップ・復元")
        st.info("入力したデータをファイル(JSON)として保存、または復元します。")

        col1, col2 = st.columns(2)

        # --- 保存 (Download) ---
        with col1:
            st.subheader("📤 保存 (Download)")
            json_data = DataManager.export_data()
            date_str = datetime.now().strftime('%Y%m%d_%H%M')
            
            st.download_button(
                label="バックアップファイルを保存 (.json)",
                data=json_data,
                file_name=f"backup_{date_str}.json",
                mime="application/json"
            )

        # --- 復元 (Upload) ---
        with col2:
            st.subheader("📥 復元 (Upload)")
            uploaded_file = st.file_uploader("バックアップファイルをアップロード", type=["json"])
            
            if uploaded_file is not None:
                if st.button("データを復元する"):
                    success = DataManager.import_data(uploaded_file)
                    if success:
                        st.success("復元しました！画面を更新します。")
                        st.rerun()

if __name__ == "__main__":
    main()
