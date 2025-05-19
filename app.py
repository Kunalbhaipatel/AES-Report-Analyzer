
import streamlit as st
import fitz
import re
import pandas as pd
import plotly.graph_objects as go

def safe_search(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else "0"

def extract_volume_format(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    text = "".join([page.get_text() for page in doc])

    data = {}
    data['Well Name'] = safe_search(r"Well Name.*?:?\s*(.*?)\n", text)
    data['Rig Name'] = safe_search(r"Rig Name.*?:?\s*(.*?)\n", text)
    data['Bit Size'] = safe_search(r"Bit Data.*?Size\s*\n\s*(.*?)\s", text)
    data['Depth'] = safe_search(r"Drilled Depth\s*\n\s*([\d,]+)", text).replace(',', '')
    data['Drilling Hrs'] = safe_search(r"Hours\s*\n\s*([\d.]+)", text)

    data['Base Oil'] = safe_search(r"Oil Added \(\+\)\s+([\d.]+)", text)
    data['Water'] = safe_search(r"Water Added \(\+\)\s+([\d.]+)", text)
    data['Barite'] = safe_search(r"Barite Added \(\+\)\s+([\d.]+)", text)
    data['Chemical'] = safe_search(r"Other Product Usage \(\+\)\s+([\d.]+)", text)
    data['Losses'] = safe_search(r"Left on Cuttings \(\-\)\s+([\d.\-]+)", text)

    data['In Pits'] = safe_search(r"In Pits\s+([\d.]+)\s*bbl", text)
    data['In Hole'] = safe_search(r"In Hole\s+([\d.]+)\s*bbl", text)
    data['Total Circ'] = str(float(data['In Pits']) + float(data['In Hole']))

    data['Mud Weight'] = safe_search(r"MUD WT\s*([\d.]+)", text)
    data['PV'] = safe_search(r"Plastic Viscosity.*?@\s*\d+\s*°F\s*(\d+)", text)
    data['YP'] = safe_search(r"Yield Point.*?=\s*(\d+)", text)
    data['Ave Temp'] = safe_search(r"Flowline Temperature\s*°F\s*([\d.]+)", text)

    return data

def to_float(val, default=0.0):
    try:
        return float(val)
    except:
        return default

st.title("📘 BAKU State: Full Mud + Volume Analysis Dashboard")

uploaded_files = st.file_uploader("Upload Mud Reports", type="pdf", accept_multiple_files=True)

if uploaded_files:
    records = []
    for file in uploaded_files:
        try:
            records.append(extract_volume_format(file))
        except Exception as e:
            st.error(f"Failed to parse {file.name}: {e}")

    if records:
        df = pd.DataFrame(records)
        df['Date'] = pd.to_datetime(df.index, errors='coerce')
        df['Well Name'] = df['Well Name'].fillna('UNKNOWN')

        for col in ['Depth', 'Drilling Hrs', 'Base Oil', 'Water', 'Barite', 'Chemical', 'Losses', 'Total Circ',
                    'PV', 'YP', 'Mud Weight', 'Ave Temp']:
            df[col] = df[col].apply(to_float)

        df['Total Dilution'] = df[['Base Oil', 'Water', 'Chemical']].sum(axis=1)
        df['Discard Ratio'] = df['Losses'] / df['Total Circ'].replace(0, 1)
        df['DSRE%'] = (df['Total Dilution'] / (df['Total Dilution'] + df['Losses'].replace(0, 1))) * 100
        df['ROP'] = df['Depth'] / df['Drilling Hrs'].replace(0, 1)
        df['Mud Cutting Ratio'] = df['Losses'] / df['Total Circ'].replace(0, 1) * 100
        df['Top Deck SCE'] = df['Losses'] * 0.6
        df['Bottom Deck SCE'] = df['Losses'] * 0.4

        st.dataframe(df)

        st.subheader("📊 ROP and Dilution Ratio")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['ROP'], name='ROP', mode='lines+markers'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Discard Ratio'], name='Discard Ratio', mode='lines+markers'))
        fig.update_layout(title='ROP and Discard Ratio', yaxis_title='Value')
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📈 Statistical Summary")

        st.subheader("📊 Trend Plots by Well")
        selected = st.multiselect("Select Wells", df['Well Name'].unique().tolist(), default=df['Well Name'].unique().tolist())
        trend_df = df[df['Well Name'].isin(selected)]

        st.plotly_chart(
            go.Figure([
                go.Scatter(x=trend_df['Date'], y=trend_df['ROP'], mode='lines+markers', name='ROP'),
                go.Scatter(x=trend_df['Date'], y=trend_df['DSRE%'], mode='lines+markers', name='DSRE%'),
                go.Scatter(x=trend_df['Date'], y=trend_df['Mud Cutting Ratio'], mode='lines+markers', name='Mud Cutting Ratio')
            ]).update_layout(title='Performance Trends by Date', yaxis_title='Value'),
            use_container_width=True
        )

        st.subheader("🪛 Deck-level SCE Loss Summary")
        deck_summary = trend_df.groupby(['Well Name']).agg({
            'Top Deck SCE': 'sum',
            'Bottom Deck SCE': 'sum',
            'Losses': 'sum'
        }).round(2)
        st.dataframe(deck_summary)

        st.subheader("📊 Compare Wells or Rigs")
        compare_mode = st.radio("Compare by", ["Well Name", "Rig Name"], horizontal=True)
        comp_df = df.groupby(compare_mode).agg({
            'ROP': 'mean',
            'DSRE%': 'mean',
            'Discard Ratio': 'mean',
            'Top Deck SCE': 'sum',
            'Bottom Deck SCE': 'sum'
        }).round(2).reset_index()

        st.dataframe(comp_df)

        st.plotly_chart(
            go.Figure([
                go.Bar(x=comp_df[compare_mode], y=comp_df['ROP'], name='ROP'),
                go.Bar(x=comp_df[compare_mode], y=comp_df['DSRE%'], name='DSRE%'),
                go.Bar(x=comp_df[compare_mode], y=comp_df['Top Deck SCE'], name='Top Deck SCE'),
                go.Bar(x=comp_df[compare_mode], y=comp_df['Bottom Deck SCE'], name='Bottom Deck SCE')
            ]).update_layout(barmode='group', title=f'Comparison by {compare_mode}', yaxis_title='Value'),
            use_container_width=True
        )
        comp_df['ROP Rank'] = comp_df['ROP'].rank(ascending=False).astype(int)
        comp_df['Delta DSRE%'] = comp_df['DSRE%'] - comp_df['DSRE%'].mean()

        st.markdown("### 📥 Export Comparison Table")
        csv = comp_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Comparison CSV", csv, f"{compare_mode}_comparison.csv", "text/csv")
        # Color scale logic could be added here for visual ranks
        st.dataframe(df[['ROP', 'Discard Ratio', 'DSRE%', 'Mud Cutting Ratio']].describe().T.round(2))
