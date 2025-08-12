
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import gspread
import json
from google.oauth2.service_account import Credentials
from openai import OpenAI
from analizador import analizar_datos_taller

st.set_page_config(layout="wide", page_title="Controller Financiero IA")

# --- LOGIN ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def login():
    st.markdown("## 🔐 Iniciar sesión")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("Iniciar sesión"):
        if username == st.secrets["USER"] and password == st.secrets["PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Credenciales incorrectas")

if not st.session_state.authenticated:
    login()
    st.stop()

# --- MEMORIA DE CONVERSACIÓN ---
if "historial" not in st.session_state:
    st.session_state.historial = []
if "data" not in st.session_state:
    st.session_state.data = None
if "sheet_url" not in st.session_state:
    st.session_state.sheet_url = ""

# --- CARGA DE DATOS CON CACHE ---
@st.cache_data(show_spinner=False)
def load_excel(file):
    return pd.read_excel(file, sheet_name=None)

@st.cache_data(show_spinner=False)
def load_gsheet(json_keyfile, sheet_url):
    creds_dict = json.loads(json_keyfile)
    scope = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(sheet_url)
    return {ws.title: pd.DataFrame(ws.get_all_records()) for ws in sheet.worksheets()}

def ask_gpt(prompt):
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    messages = [{"role": "system", "content": "Eres un controller financiero experto de un taller de desabolladura y pintura."}]
    for h in st.session_state.historial:
        messages.append({"role": "user", "content": h["pregunta"]})
        messages.append({"role": "assistant", "content": h["respuesta"]})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3
    )
    return response.choices[0].message.content

def mostrar_grafico_torta(df, col_categoria, col_valor, titulo):
    resumen = df.groupby(col_categoria)[col_valor].sum()
    fig, ax = plt.subplots()
    ax.pie(resumen, labels=resumen.index, autopct='%1.1f%%', startangle=90)
    ax.set_title(titulo)
    st.pyplot(fig)

def mostrar_grafico_barras(df, col_categoria, col_valor, titulo):
    resumen = df.groupby(col_categoria)[col_valor].sum().sort_values()
    fig, ax = plt.subplots()
    resumen.plot(kind="barh", ax=ax)
    ax.set_title(titulo)
    ax.set_xlabel(col_valor)
    st.pyplot(fig)

def mostrar_tabla(df, col_categoria, col_valor):
    resumen = df.groupby(col_categoria)[col_valor].sum().reset_index()
    st.markdown("### 📊 Tabla Resumen")
    st.dataframe(resumen)

# --- INTERFAZ EN COLUMNAS ---
col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    st.markdown("### 📁 Subir archivo")
    tipo_fuente = st.radio("Fuente de datos", ["Excel", "Google Sheets"], key="k_fuente")

    if tipo_fuente == "Excel":
        file = st.file_uploader("Sube un archivo Excel", type=["xlsx", "xls"], key="k_excel")
        if file:
            st.session_state.data = load_excel(file)
    else:
        with st.form(key="form_gsheet"):
            url = st.text_input("URL de Google Sheet", value=st.session_state.sheet_url, key="k_url")
            conectar = st.form_submit_button("Conectar")
        if conectar and url:
            st.session_state.sheet_url = url
            st.session_state.data = load_gsheet(st.secrets["GOOGLE_CREDENTIALS"], url)

data = st.session_state.data

with col2:
    if data:
        st.markdown("### 📄 Vista previa")
        for name, df in data.items():
            st.markdown(f"#### 📘 Hoja: {name}")
            st.dataframe(df.head(10))

with col3:
    if data:
        st.markdown("### 🤖 Consulta con IA")
        pregunta = st.text_area("Pregunta")

        if st.button("📊 Análisis General Automático"):
            analisis = analizar_datos_taller(st.session_state.data)
            texto_analisis = json.dumps(analisis, indent=2, ensure_ascii=False)
            prompt = f"""
Eres un controller financiero senior.

Con base en los datos calculados (reales) a continuación, entrega un análisis profesional, directo y accionable.
Si una visualización ayuda a entender mejor, incluye UNA instrucción exacta:
- grafico_torta:col_categoria|col_valor|titulo
- grafico_barras:col_categoria|col_valor|titulo
- tabla:col_categoria|col_valor

No inventes datos. Si falta información, dilo y propone cómo completarla.

Datos calculados:
{texto_analisis}
"""
            respuesta = ask_gpt(prompt)
            st.markdown(respuesta)
            st.session_state.historial.append({"pregunta": "Análisis general", "respuesta": respuesta})

        if st.button("Responder") and pregunta:
            analisis = analizar_datos_taller(st.session_state.data)
            texto_analisis = json.dumps(analisis, indent=2, ensure_ascii=False)
            prompt = f"""
Actúa estrictamente como un controller financiero senior de un taller de desabolladura y pintura.

Usa EXCLUSIVAMENTE los siguientes datos calculados (reales) para responder, sin inventar:
{texto_analisis}

Debes:
- Responder a la pregunta con análisis profesional, directo y conciso.
- Si el usuario pide o amerita una visualización y las columnas existen, incluye UNA instrucción exacta:
  - grafico_torta:col_categoria|col_valor|titulo
  - grafico_barras:col_categoria|col_valor|titulo
  - tabla:col_categoria|col_valor
- Entregar 1-3 recomendaciones accionables para la gerencia.
- Si falta información para responder con precisión, dilo y sugiere cómo completarla.

Pregunta del usuario:
{pregunta}
"""
            respuesta = ask_gpt(prompt)
            st.markdown(respuesta)
            st.session_state.historial.append({"pregunta": pregunta, "respuesta": respuesta})

            def safe_plot(plot_fn, hoja, df, col_cat, col_val, titulo):
                col_cat = col_cat.strip()
                col_val = col_val.strip()
                if col_cat not in df.columns or col_val not in df.columns:
                    st.warning(f"❗ No se pudo generar el gráfico en '{hoja}'. Revisar columnas: '{col_cat}' y '{col_val}'.")
                    return
                try:
                    plot_fn(df, col_cat, col_val, titulo)
                except Exception as e:
                    st.error(f"Error generando gráfico en '{hoja}': {e}")

            for linea in respuesta.splitlines():
                if "grafico_torta:" in linea:
                    partes = linea.replace("grafico_torta:", "").split("|")
                    if len(partes) == 3:
                        for hoja, df in st.session_state.data.items():
                            safe_plot(mostrar_grafico_torta, hoja, df, partes[0], partes[1], partes[2])
                if "grafico_barras:" in linea:
                    partes = linea.replace("grafico_barras:", "").split("|")
                    if len(partes) == 3:
                        for hoja, df in st.session_state.data.items():
                            safe_plot(mostrar_grafico_barras, hoja, df, partes[0], partes[1], partes[2])
                if "tabla:" in linea:
                    partes = linea.replace("tabla:", "").split("|")
                    if len(partes) == 2:
                        for hoja, df in st.session_state.data.items():
                            if partes[0].strip() in df.columns and partes[1].strip() in df.columns:
                                mostrar_tabla(df, partes[0].strip(), partes[1].strip())

    if st.session_state.historial:
        with st.expander("🧠 Historial de la sesión"):
            for i, h in enumerate(st.session_state.historial[-10:], 1):
                st.markdown(f"**Q{i}:** {h['pregunta']}")
                st.markdown(f"**A{i}:** {h['respuesta']}")
