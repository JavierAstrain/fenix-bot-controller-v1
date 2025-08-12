
def analizar_datos_taller(data):
    # Analiza TODAS las filas y hojas de la planilla
    analisis = {}
    for hoja, df in data.items():
        if not df.empty:
            analisis[hoja] = {
                "columnas": list(df.columns),
                "filas_totales": len(df),
                "resumen": df.describe(include='all').to_dict()
            }
    return analisis
