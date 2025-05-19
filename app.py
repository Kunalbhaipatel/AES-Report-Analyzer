
import streamlit as st
import fitz
import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

def safe_search(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else "0"

def extract_baku_format(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()

    data = {}
    data['Well Name'] = safe_search(r"Well Name\s*:?[\s\n]*(.*?)\s", text)
    data['Date'] = safe_search(r"Report\s+#\d+\s+([0-9]{2}/[0-9]{2}/[0-9]{2})", text)
    data['Mud Weight'] = safe_search(r"MUD WT\s*([0-9.]+)", text)
    data['PV'] = safe_search(r"PV\s*=\s*([0-9.]+)", text)
    data['YP'] = safe_search(r"YP\s*=\s*([0-9.]+)", text)
    data['Ave Temp'] = safe_search(r"Flowline Temperature.*?([0-9]{2,3})\s*°F", text)

    gpm_vals = re.findall(r"PUMP\s+#\d+\s*([0-9.]+)\s*gpm", text, re.IGNORECASE)
    data['Pump 1 GPM'] = gpm_vals[0] if len(gpm_vals) > 0 else "0"
    data['Pump 2 GPM'] = gpm_vals[1] if len(gpm_vals) > 1 else "0"
    data['Pump 3 GPM'] = gpm_vals[2] if len(gpm_vals) > 2 else "0"

    data['API Screen'] = safe_search(r"Screens.*?([0-9]{2,3})\s*ppb", text)
    data['Screen Count'] = str(len(re.findall(r"Shaker\s+\d+", text)))
    return data

def to_float(val, default=0.0):
    try:
        return float(val)
    except:
        return default

st.title("🛢️ BAKU State Daily Mud Report Dashboard")

uploaded_files = st.file_uploader("Upload BAKU Reports (PDF)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    records = []
    for file in uploaded_files:
        try:
            records.append(extract_baku_format(file))
        except Exception as e:
            st.error(f"Failed to parse {file.name}: {e}")

    if records:
        df = pd.DataFrame(records)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df.sort_values('Date', inplace=True)

        for col in ['Mud Weight', 'PV', 'YP', 'Ave Temp', 'Pump 1 GPM', 'Pump 2 GPM', 'Pump 3 GPM', 'API Screen']:
            df[col] = df[col].apply(to_float)

        df['GPM Total'] = df[['Pump 1 GPM', 'Pump 2 GPM', 'Pump 3 GPM']].sum(axis=1)
        df['Screen Count'] = df['Screen Count'].apply(to_float)
        df['GPM/Screen'] = df['GPM Total'] / df['Screen Count'].replace(0, 1)
        df['Top Deck Wear'] = df['GPM Total'] * df['YP'] / df['API Screen'].replace(0, 100)
        df['Bottom Deck Wear'] = (df['GPM/Screen'] * 0.8).clip(upper=100)

        st.dataframe(df)

        st.subheader("📊 PV, YP, and GPM (Combo Chart)")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df['Date'], y=df['GPM Total'], name='GPM Total', marker_color='indianred'))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['PV'], name='PV', mode='lines+markers', line=dict(color='blue')))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['YP'], name='YP', mode='lines+markers', line=dict(color='green')))
        fig.update_layout(title='PV, YP and GPM Total (Combo View)', yaxis_title='Value', barmode='overlay')
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📌 Screen Wear Indicators")
        flags = df[['Date', 'Well Name', 'Top Deck Wear', 'Bottom Deck Wear', 'API Screen', 'Screen Count']].copy()
        flags['Top Deck Status'] = pd.cut(flags['Top Deck Wear'], [-1, 2.5, 4.0, 999], labels=["✅ Good", "⚠️ Caution", "🚨 Critical"])
        flags['Bottom Deck Status'] = pd.cut(flags['Bottom Deck Wear'], [-1, 2.0, 3.5, 999], labels=["✅ Good", "⚠️ Caution", "🚨 Critical"])
        st.dataframe(flags)

        st.subheader("📋 Statistical Summary")
        st.dataframe(df[['PV', 'YP', 'Mud Weight', 'Ave Temp', 'GPM Total', 'GPM/Screen', 'Top Deck Wear']].describe().T.round(2))
