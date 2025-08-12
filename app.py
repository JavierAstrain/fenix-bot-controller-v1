import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import gspread
import json
import re
import unicodedata
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
        try_user = st.secrets.get("USER", None)
        try_pass = st.secrets.get("PASSWORD", None)
        if try_user is None or try_pass is None:
            st.error("Secrets USER/PASSWORD no configurados. Agrega USER y PASSWORD en secrets.toml / Cloud.")
            return
        if username == try_user and password == try_pass:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Credenciales incorrectas")

if not st.session_state.authenticated:
    login()
    st.stop()

# --- ESTADO PERSISTENTE ---
if "historial" not in st.session_state:
    st.session_state.historial = []
if "data" not in st.session_state:
    st.session_state.data = None
if "sheet_url" not in st.session_state:
    st.session_state.sheet_url = ""

# --- CARGA DE DATOS (CACHE) ---
@st.cache_data(show_spinner=False)
def load_excel(file):
    return pd.read_excel(file, sheet_name=None)

@st.cache_data(show_spinner=False)
def load_gsheet(json_keyfile: str, sheet_url: str):
    creds_dict = json.loads(json_keyfile)
    scope = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(sheet_url)
    return {ws.title: pd.DataFrame(ws.get_all_records()) for ws in sheet.worksheets()}

# --- OPENAI ---
def ask_gpt(prompt):
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    messages = [{"role": "system", "content": "Eres un controller financiero experto de un taller de desabolladura y pintura."}]
    for h in st.session_state.historial[-8:]:
        messages.append({"role": "user", "content": h["pregunta"]})
        messages.append({"role": "assistant", "content": h["respuesta"]})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2
    )
    return response.choices[0].message.content

# --- VISUALIZACIONES (Excel-like) ---
def _fmt_miles(x, pos=None):
    try:
        return f"${int(x):,}".replace(",", ".")
    except Exception:
        return str(x)

def mostrar_grafico_torta(df, col_categoria, col_valor, titulo):
    resumen = df.groupby(col_categoria, dropna=False)[col_valor].sum().sort_values(ascending=False)
    fig, ax = plt.subplots()
    ax.pie(
        resumen.values,
        labels=[str(x) for x in resumen.index],
        autopct='%1.1f%%',
        startangle=90
    )
    ax.axis('equal')
    ax.set_title(titulo or f"{col_valor} por {col_categoria}")
    st.pyplot(fig)

def mostrar_grafico_barras(df, col_categoria, col_valor, titulo):
    resumen = df.groupby(col_categoria, dropna=False)[col_valor].sum().sort_values(ascending=False)
    fig, ax = plt.subplots()
    bars = ax.bar(resumen.index.astype(str), resumen.values)
    ax.set_title(titulo or f"{col_valor} por {col_categoria}")
    ax.set_ylabel(col_valor)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(_fmt_miles))
    ax.tick_params(axis='x', rotation=45, ha='right')
    for b in bars:
        ax.annotate(_fmt_miles(b.get_height()), xy=(b.get_x()+b.get_width()/2, b.get_height()),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)
    fig.tight_layout()
    st.pyplot(fig)

def mostrar_tabla(df, col_categoria, col_valor, titulo=None):
    resumen = (
        df.groupby(col_categoria, dropna=False)[col_valor]
          .sum()
          .sort_values(ascending=False)
          .reset_index()
    )
    resumen.columns = [str(col_categoria).title(), str(col_valor).title()]
    col_val = resumen.columns[1]
    try:
        resumen[col_val] = resumen[col_val].astype(float).round(0).astype(int)
    except Exception:
        pass
    st.markdown(f"### 📊 {titulo if titulo else f'{col_val} por {col_categoria}'}")
    st.dataframe(resumen, use_container_width=True)

# --- NORMALIZACIÓN & PARSER DE INSTRUCCIONES ---
def _normalize(s: str) -> str:
    s = str(s).strip()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    return s

def _build_aliases_for_sheets(data_dict: dict):
    aliases = {}
    for hoja, df in data_dict.items():
        m = {}
        for c in df.columns:
            m[_normalize(c)] = c
        aliases[hoja] = m
    return aliases

def _resolve_column(name: str, hoja: str, aliases_by_sheet: dict):
    n = _normalize(name)
    if hoja in aliases_by_sheet and n in aliases_by_sheet[hoja]:
        return aliases_by_sheet[hoja][n]
    for m in aliases_by_sheet.values():
        if n in m:
            return m[n]
    return None

def parse_and_render_instructions(respuesta_texto: str, data_dict: dict):
    """Detecta instrucciones aunque vengan con viñetas/codeblocks. Soporta @HOJA opcional.
    Formatos:
      - grafico_torta[:|@HOJA:]categoria|valor|titulo
      - grafico_barras[:|@HOJA:]categoria|valor|titulo
      - tabla[:|@HOJA:]categoria|valor[|titulo]
    """
    aliases = _build_aliases_for_sheets(data_dict)

    def safe_plot(plot_fn, hoja, df, col_cat, col_val, titulo):
        real_cat = _resolve_column(col_cat, hoja, aliases)
        real_val = _resolve_column(col_val, hoja, aliases)
        if not real_cat or not real_val or real_cat not in df.columns or real_val not in df.columns:
            st.warning(f"❗ No se pudo generar la visualización. Revisar columnas: '{col_cat}' y '{col_val}'.")
            return
        try:
            plot_fn(df, real_cat, real_val, titulo if titulo else f"{real_val} por {real_cat}")
        except Exception as e:
            st.error(f"Error generando visualización: {e}")

    patt = re.compile(r'(grafico_torta|grafico_barras|tabla)(?:@([^:\n\r\s]+))?\s*:\s*([^\n\r]+)', re.IGNORECASE)
    for m in patt.finditer(respuesta_texto):
        kind = m.group(1).lower()
        hoja_sel = m.group(2)
        body = m.group(3).strip().strip("`").lstrip("-*• ").strip()

        parts = [p.strip(" `*-•").strip() for p in body.split("|")]
        if kind in ("grafico_torta", "grafico_barras"):
            if len(parts) != 3:
                st.warning("Instrucción de gráfico inválida.")
                continue
            cat, val, title = parts
            if hoja_sel and hoja_sel in data_dict:
                safe_plot(mostrar_grafico_torta if kind == "grafico_torta" else mostrar_grafico_barras,
                          hoja_sel, data_dict[hoja_sel], cat, val, title)
            else:
                ok = False
                for hoja, df in data_dict.items():
                    safe_plot(mostrar_grafico_torta if kind == "grafico_torta" else mostrar_grafico_barras,
                              hoja, df, cat, val, title)
                    ok = True
                if not ok:
                    st.warning("No se pudo generar el gráfico en ninguna hoja.")
        else:  # tabla
            if len(parts) not in (2, 3):
                st.warning("Instrucción de tabla inválida.")
                continue
            cat, val = parts[0], parts[1]
            title = parts[2] if len(parts) == 3 else None

            def draw_table_on(df, hoja):
                real_cat = _resolve_column(cat, hoja, aliases)
                real_val = _resolve_column(val, hoja, aliases)
                if real_cat and real_val and real_cat in df.columns and real_val in df.columns:
                    mostrar_tabla(df, real_cat, real_val, titulo=title or f"Tabla: {real_val} por {real_cat} ({hoja})")
                    return True
                return False

            if hoja_sel and hoja_sel in data_dict:
                if not draw_table_on(data_dict[hoja_sel], hoja_sel):
                    st.warning(f"No se pudo generar la tabla en '{hoja_sel}'.")
            else:
                ok = False
                for hoja, df in data_dict.items():
                    ok = draw_table_on(df, hoja) or ok
                if not ok:
                    st.warning("No se pudo generar la tabla en ninguna hoja (verifica nombres de columnas).")

# --- UI ---
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
            try:
                nuevo = load_gsheet(st.secrets["GOOGLE_CREDENTIALS"], url)
                if nuevo and len(nuevo) > 0:
                    st.session_state.sheet_url = url
                    st.session_state.data = nuevo
                    st.success("Google Sheet conectado.")
                else:
                    st.warning("La hoja no tiene datos.")
            except Exception as e:
                st.error(f"Error conectando Google Sheet: {e}")

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
Si una visualización ayuda a entender mejor, incluye UNA instrucción exacta (sin viñetas, sola en una línea):
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
            parse_and_render_instructions(respuesta, st.session_state.data)

        if st.button("Responder") and pregunta:
            analisis = analizar_datos_taller(st.session_state.data)
            texto_analisis = json.dumps(analisis, indent=2, ensure_ascii=False)
            prompt = f"""
Actúa estrictamente como un controller financiero senior de un taller de desabolladura y pintura.

Usa EXCLUSIVAMENTE los siguientes datos calculados (reales) para responder, sin inventar:
{texto_analisis}

Debes:
- Responder a la pregunta con análisis profesional, directo y conciso.
- Si el usuario pide o amerita una visualización y las columnas existen, incluye UNA instrucción exacta (sin viñetas, sola en una línea):
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
            parse_and_render_instructions(respuesta, st.session_state.data)

    if st.session_state.historial:
        with st.expander("🧠 Historial de la sesión"):
            for i, h in enumerate(st.session_state.historial[-10:], 1):
                st.markdown(f"**Q{i}:** {h['pregunta']}")
                st.markdown(f"**A{i}:** {h['respuesta']}")
