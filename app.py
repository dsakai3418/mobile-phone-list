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

def extract_mobile_numbers(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    指定された列から携帯電話番号を抽出し、元の行を保ったまま
    新しい列 'extracted_mobile_numbers' を追加した DataFrame を返す。
    抽出はセル内の複数候補にも対応します。
    """
    results = []
    # permissive candidate pattern: starts with optional + and digits, may include dashes/spaces
    candidate_re = re.compile(r'\+?\d[\d\-\s\u2010-\u2015\u2212]*\d')

    for idx, row in df.iterrows():
        extracted = []
        if column_name in row and pd.notna(row[column_name]):
            text = str(row[column_name])
            # find candidate substrings
            candidates = candidate_re.findall(text)
            for cand in candidates:
                norm = normalize_candidate(cand)
                if is_valid_jp_mobile(norm):
                    extracted.append(norm)
        # dedupe while preserving order
        seen = set()
        deduped = []
        for n in extracted:
            if n not in seen:
                seen.add(n)
                deduped.append(n)
        # make a copy of the row and add new column
        new_row = row.copy()
        new_row['extracted_mobile_numbers'] = ','.join(deduped) if deduped else ''
        if deduped: # 携帯番号が見つかった行のみ結果に含める
            results.append(new_row)
    if results:
        return pd.DataFrame(results)
    else:
        # 携帯番号が見つからなかった場合、元のカラムと新しいカラムを持つ空のDataFrameを返す
        cols = list(df.columns) + ['extracted_mobile_numbers']
        return pd.DataFrame(columns=cols)

st.title('CSVから携帯電話番号を抽出アプリ（改良版）')

st.write('CSVファイルをアップロードしてください。')
uploaded_file = st.file_uploader("CSVファイルをここにドラッグ＆ドロップ、またはクリックして選択", type="csv")

if uploaded_file is not None:
    df = None
    # エンコーディングを複数試す
    encodings = ['utf-8', 'shift_jis', 'cp932', 'euc_jp']
    for enc in encodings:
        try:
            # uploaded_file は BytesIO オブジェクトなので、read() でバイト列を読み込み、StringIOでPandasに渡す
            uploaded_file.seek(0) # ファイルポインタを先頭に戻す
            df = pd.read_csv(uploaded_file, encoding=enc)
            st.success(f"CSVファイルを '{enc}' エンコーディングで正常に読み込みました。")
            break # 成功したらループを抜ける
        except UnicodeDecodeError:
            continue # 次のエンコーディングを試す
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

    st.write("### 携帯電話番号が含まれる列を選択してください")
    selected_column = st.selectbox("列名", column_options)

    if st.button('携帯電話番号を抽出'):
        if selected_column:
            with st.spinner('携帯電話番号を抽出中...'):
                extracted_df = extract_mobile_numbers(df, selected_column)

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
            st.warning("携帯電話番号が含まれる列を選択してください。")

st.write("---")
st.write("### 使用上の注意とヒント")
st.write("・セルにハイフンやスペース、全角数字、+81 のような国際表記が含まれていても抽出できます。")
st.write("・セル内に複数の番号がある場合、すべて抽出して 'extracted_mobile_numbers' 列にカンマ区切りで表示します。")
st.write("・このアプリは 'utf-8', 'shift_jis', 'cp932', 'euc_jp' のエンコーディングを自動的に試します。")
st.write("・より厳密なバリデーションや別キャリアの番号対応が必要ならルールを調整してください。")
