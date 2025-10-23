import streamlit as st
import pandas as pd
import re

# 全角数字と全角プラスを半角に変換するマップ
FW_TO_ASCII = str.maketrans({
    '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
    '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
    '＋': '+'
})

def normalize_digits(s: str) -> str:
    """全角文字を半角にし、不要な空白をトリムする"""
    if s is None:
        return ''
    s = str(s).translate(FW_TO_ASCII).strip()
    return s

def normalize_candidate(candidate: str) -> str:
    """
    候補文字列から数字と先頭の+だけを残し、国際表記(+81)を国内表記(0...)に変換する。
    ハイフンやスペース、長短ダッシュなども除去する。
    """
    if not candidate:
        return ''
    # 全角→半角、トリム
    s = normalize_digits(candidate)
    # remove common dash-like chars and spaces
    s = re.sub(r'[\s\u2010-\u2015\-\u2212]', '', s)
    # convert +81... -> 0...
    if s.startswith('+81'):
        s = '0' + s[3:]
    # Ensure only digits now
    s = re.sub(r'[^\d]', '', s)
    return s

def is_valid_jp_mobile(num: str) -> bool:
    """
    日本国内の携帯電話番号として有効かを判定。
    典型的には 070/080/090 + 8桁 の 11桁（ハイフンなし）を期待する。
    """
    return bool(re.fullmatch(r'^(070|080|090)\d{8}$', num))

def extract_mobile_numbers_from_multiple_columns(df: pd.DataFrame, column_priority_list: list) -> pd.DataFrame:
    """
    指定された複数の列から優先順位に基づいて携帯電話番号を抽出し、
    新しい列 'extracted_mobile_numbers' を追加した DataFrame を返す。
    抽出はセル内の複数候補にも対応します。
    """
    results = []
    candidate_re = re.compile(r'\+?\d[\d\-\s\u2010-\u2015\u2212]*\d')

    for idx, row in df.iterrows():
        found_mobile_numbers = []
        
        # 優先順位リストに従って各列をチェック
        for col_name in column_priority_list:
            if col_name in row and pd.notna(row[col_name]):
                text = str(row[col_name])
                candidates = candidate_re.findall(text)
                
                extracted_from_col = []
                for cand in candidates:
                    norm = normalize_candidate(cand)
                    if is_valid_jp_mobile(norm):
                        extracted_from_col.append(norm)
                
                # この列で携帯番号が見つかったら、それを採用し、次の列はチェックしない
                if extracted_from_col:
                    found_mobile_numbers = extracted_from_col
                    break # 優先順位の高い列で見つかったので、次の列はスキップ
        
        # 重複を除去し、順序を保持
        seen = set()
        deduped = []
        for n in found_mobile_numbers:
            if n not in seen:
                seen.add(n)
                deduped.append(n)
        
        # 携帯番号が見つかった行のみを結果に含める
        if deduped:
            new_row = row.copy()
            new_row['extracted_mobile_numbers'] = ','.join(deduped)
            results.append(new_row)
            
    if results:
        return pd.DataFrame(results)
    else:
        # 携帯番号が見つからなかった場合、元のカラムと新しいカラムを持つ空のDataFrameを返す
        cols = list(df.columns) + ['extracted_mobile_numbers']
        return pd.DataFrame(columns=cols)

st.title('CSVから携帯電話番号を抽出アプリ（複数列対応・優先順位付き）')

st.write('CSVファイルをアップロードしてください。')
uploaded_file = st.file_uploader("CSVファイルをここにドラッグ＆ドロップ、またはクリックして選択", type="csv")

if uploaded_file is not None:
    df = None
    encodings = ['utf-8', 'shift_jis', 'cp932', 'euc_jp']
    for enc in encodings:
        try:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, encoding=enc)
            st.success(f"CSVファイルを '{enc}' エンコーディングで正常に読み込みました。")
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            st.error(f"CSVファイルの読み込み中に予期せぬエラーが発生しました: {e} (エンコーディング: {enc})")
            st.stop()
    
    if df is None:
        st.error("CSVファイルをサポートされているいずれのエンコーディングでも読み込めませんでした。ファイルを確認してください。")
        st.stop()

    st.write("### アップロードされたCSVデータ（プレビュー）")
    st.dataframe(df.head())

    column_options = df.columns.tolist()
    if not column_options:
        st.warning("CSVに列が見つかりません。")
        st.stop()

    st.write("### 携帯電話番号が含まれる可能性がある列を選択してください (優先順位順)")
    st.write("Ctrl/Cmdを押しながら複数選択できます。")
    # ユーザーが列を複数選択できるようにする
    selected_columns_for_extraction = st.multiselect(
        "列名", 
        column_options, 
        default=["請求先電話番号", "電話"] # デフォルトでこれらを選択
    )

    if st.button('携帯電話番号を抽出'):
        if selected_columns_for_extraction:
            with st.spinner('携帯電話番号を抽出中...'):
                # 複数列に対応する関数を呼び出す
                extracted_df = extract_mobile_numbers_from_multiple_columns(df, selected_columns_for_extraction)

            if not extracted_df.empty:
                st.success(f"{len(extracted_df)} 行で携帯番号が見つかりました。")
                st.dataframe(extracted_df)

                csv = extracted_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig') # BOM付きUTF-8
                st.download_button(
                    label="抽出結果をCSVでダウンロード",
                    data=csv,
                    file_name="extracted_mobile_numbers.csv",
                    mime="text/csv",
                )
            else:
                st.warning("指定された列から携帯電話番号は見つかりませんでした。")
        else:
            st.warning("携帯電話番号が含まれる列を一つ以上選択してください。")

st.write("---")
st.write("### 使用上の注意とヒント")
st.write("・セルにハイフンやスペース、全角数字、+81 のような国際表記が含まれていても抽出できます。")
st.write("・**複数列を選択した場合、リストの上にある列の番号が優先されます。**")
st.write("・セル内に複数の番号がある場合、すべて抽出して 'extracted_mobile_numbers' 列にカンマ区切りで表示します。")
st.write("・このアプリは 'utf-8', 'shift_jis', 'cp932', 'euc_jp' のエンコーディングを自動的に試します。")
st.write("・より厳密なバリデーションや別キャリアの番号対応が必要ならルールを調整してください。")
