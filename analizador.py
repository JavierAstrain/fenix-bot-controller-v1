import pandas as pd

def _describe_safe(df: pd.DataFrame):
    try:
        desc_num = df.select_dtypes(include='number').describe().to_dict()
        desc_obj = df.select_dtypes(exclude='number').describe().to_dict()
        return {"numericas": desc_num, "categoricas": desc_obj}
    except Exception:
        return {"numericas": {}, "categoricas": {}}

def analizar_datos_taller(data: dict) -> dict:
    """
    Recorre TODAS las hojas y filas.
    Devuelve un resumen por hoja con columnas, filas y un describe seguro.
    Este módulo es el 'motor' y puede ampliarse con métricas específicas.
    """
    analisis = {}
    for hoja, df in data.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            analisis[hoja] = {
                "columnas": list(df.columns),
                "filas_totales": int(len(df)),
                "resumen": _describe_safe(df)
            }
    return analisis
