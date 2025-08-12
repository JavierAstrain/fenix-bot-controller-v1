import pandas as pd

def analizar_facturacion(df):
    resumen = {}
    if 'Monto Neto' in df.columns:
        resumen["ingresos_totales"] = df["Monto Neto"].sum()
    if {'Tipo Cliente', 'Monto Neto'}.issubset(df.columns):
        resumen["ingresos_por_cliente"] = df.groupby("Tipo Cliente")["Monto Neto"].sum().to_dict()
    if {'Mes', 'Monto Neto'}.issubset(df.columns):
        resumen["ingresos_por_mes"] = df.groupby("Mes")["Monto Neto"].sum().to_dict()
    if {'Tipo Vehiculo', 'Monto Neto'}.issubset(df.columns):
        resumen["ingresos_por_vehiculo"] = df.groupby("Tipo Vehiculo")["Monto Neto"].sum().to_dict()
    return resumen

def analizar_finanzas(df):
    resumen = {}
    if {'Mes', 'Monto'}.issubset(df.columns):
        resumen["costos_por_mes"] = df.groupby("Mes")["Monto"].sum().to_dict()
    if {'Categoria', 'Monto'}.issubset(df.columns):
        resumen["costos_por_categoria"] = df.groupby("Categoria")["Monto"].sum().to_dict()
    if "Monto" in df.columns:
        resumen["costos_totales"] = df["Monto"].sum()
    return resumen

def analizar_recepcion(df):
    resumen = {}
    if 'Estado Presupuesto' in df.columns:
        conteo = df['Estado Presupuesto'].value_counts().to_dict()
        total = sum(conteo.values())
        resumen["conversion_presupuestos"] = {k: round(v / total * 100, 2) for k, v in conteo.items()}
    if 'Tipo Cliente' in df.columns:
        resumen["recepcion_por_cliente"] = df['Tipo Cliente'].value_counts().to_dict()
    if 'Tipo Vehiculo' in df.columns:
        resumen["recepcion_por_vehiculo"] = df['Tipo Vehiculo'].value_counts().to_dict()
    return resumen

def analizar_reparacion(df):
    resumen = {}
    if 'Tipo Proceso' in df.columns:
        resumen["procesos_realizados"] = df['Tipo Proceso'].value_counts().to_dict()
    if 'Especialista' in df.columns:
        resumen["procesos_por_especialista"] = df['Especialista'].value_counts().to_dict()
    return resumen

def analizar_datos_taller(data):
    analisis = {}
    if "FACTURACION" in data:
        analisis["facturacion"] = analizar_facturacion(data["FACTURACION"])
    if "FINANZAS" in data:
        analisis["finanzas"] = analizar_finanzas(data["FINANZAS"])
    if "RECEPCION" in data:
        analisis["recepcion"] = analizar_recepcion(data["RECEPCION"])
    if "REPARACION" in data:
        analisis["reparacion"] = analizar_reparacion(data["REPARACION"])
    return analisis

