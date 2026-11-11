import os
import re
import csv
import json
import datetime
import pandas as pd
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_EVENTOS = os.path.join(BASE_DIR, "Registro_Eventos_FoodTruck.csv")
CARPETA_DATOS_EVENTOS = r"g:\Mi unidad\FOOD TRUCK\DATOS EVENTOS"

COLUMNAS_EVENTOS = [
    "Id_Evento",
    "Fecha",
    "Nombre_Evento",
    "Promotora",
    "Hamburguesa",
    "Carne_Gramos",
    "Coste_Hamburguesa",
    "Gasto_Genero",
    "Personal_Horas",
    "Coste_Personal",
    "Regaladas_Q",
    "Coste_Regaladas",
    "Entradas_Aforo",
    "Ventas_Q",
    "Ventas_Total",
    "Gastos_Extras",
    "Comision_Pct",
    "Coste_Total",
    "Beneficio_Neto",
    "Margen_Pct",
    "Detalle_Genero_Json",
    "Detalle_Personal_Json",
    "Detalle_Gastos_Json",
    "Archivo_Origen",
    "Notas"
]

def limpiar_numero(val):
    """Convierte de forma segura strings, porcentajes o floats a float."""
    if pd.isna(val) or val is None or str(val).strip() == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("€", "").replace("%", "").replace(" ", "")
    # Si viene en formato español (ej: 1.250,50)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

def extraer_fecha_y_promotora(texto):
    """Extrae fecha (dd/mm/aaaa) y nombre de promotora del campo combinado."""
    if not texto or pd.isna(texto):
        return "", ""
    s = str(texto).strip()
    match_f = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', s)
    fecha = ""
    promotora = s
    if match_f:
        fecha_cruda = match_f.group(1).replace("-", "/")
        # Normalizar fecha
        partes = fecha_cruda.split("/")
        if len(partes) == 3:
            d, m, y = partes[0].zfill(2), partes[1].zfill(2), partes[2]
            if len(y) == 2:
                y = "20" + y
            fecha = f"{d}/{m}/{y}"
        else:
            fecha = fecha_cruda
        promotora = s.replace(match_f.group(0), "").strip()
    # Limpiar espacios
    promotora = re.sub(r'\s+', ' ', promotora).strip()
    return fecha, promotora

def parsear_archivo_evento(ruta_archivo):
    """
    Parsea una hoja o libro de evento de Blitz Food Truck siguiendo la estructura oficial.
    Retorna una lista de diccionarios con los eventos extraídos.
    """
    eventos_encontrados = []
    nombre_archivo = os.path.basename(ruta_archivo)
    
    try:
        # Si es CSV
        if ruta_archivo.lower().endswith('.csv'):
            try:
                df_raw = pd.read_csv(ruta_archivo, header=None, encoding='utf-8-sig', dtype=str).fillna("")
            except Exception:
                df_raw = pd.read_csv(ruta_archivo, header=None, encoding='latin1', dtype=str).fillna("")
            hojas = [("Principal", df_raw)]
        # Si es Excel
        elif ruta_archivo.lower().endswith(('.xlsx', '.xls', '.xlsm')):
            xls = pd.ExcelFile(ruta_archivo)
            hojas = [(sheet, xls.parse(sheet, header=None, dtype=str).fillna("")) for sheet in xls.sheet_names]
        else:
            return []

        for nombre_hoja, df in hojas:
            if df.empty or len(df) < 2:
                continue

            # Buscar la fila de cabecera que contiene 'NOMBRE EVENTO' o 'EVENTO'
            fila_cabecera = -1
            for idx_r in range(min(15, len(df))):
                fila_vals = [str(x).upper().strip() for x in df.iloc[idx_r].tolist()]
                if any("NOMBRE EVENTO" in v or "NOMBRE DEL EVENTO" in v for v in fila_vals):
                    fila_cabecera = idx_r
                    break

            if fila_cabecera == -1:
                # Si no encontramos fila cabecera clásica, verificar si en fila 0 hay algo
                fila_vals_0 = [str(x).upper().strip() for x in df.iloc[0].tolist()]
                if any("EVENTO" in v or "HAMBURGUESA" in v for v in fila_vals_0):
                    fila_cabecera = 0
                else:
                    continue

            # Mapear nombres de columnas según la fila de cabecera
            cabeceras = [str(x).strip().upper() for x in df.iloc[fila_cabecera].tolist()]
            
            # La fila inmediatamente siguiente contiene los datos principales
            fila_datos_idx = fila_cabecera + 1
            if fila_datos_idx >= len(df):
                continue
            fila_datos = df.iloc[fila_datos_idx].tolist()

            # Diccionario temporal columna -> valor
            mapa_datos = {}
            for col_idx, col_nom in enumerate(cabeceras):
                if col_idx < len(fila_datos):
                    val = str(fila_datos[col_idx]).strip()
                    mapa_datos[col_nom] = val

            # Extraer campos clave con búsquedas flexibles
            def get_campo(posibles_nombres, default=""):
                for p in posibles_nombres:
                    for k, v in mapa_datos.items():
                        if p.upper() in k.upper():
                            return v
                return default

            nom_evento = get_campo(["NOMBRE EVENTO", "NOMBRE DEL EVENTO", "EVENTO"])
            if not nom_evento or nom_evento.upper() in ["NAN", "NONE", ""]:
                # Tomar nombre de hoja o de archivo como fallback
                nom_evento = nombre_hoja if nombre_hoja != "Principal" else os.path.splitext(nombre_archivo)[0]

            promotora_fecha_raw = get_campo(["PROMOTORA Y FECHA", "PROMOTORA Y  FECHA", "PROMOTORA", "FECHA"])
            fecha_ext, promotora_ext = extraer_fecha_y_promotora(promotora_fecha_raw)
            
            if not fecha_ext:
                fecha_ext = get_campo(["FECHA"])
                if not fecha_ext:
                    fecha_ext = datetime.date.today().strftime("%d/%m/%Y")

            if not promotora_ext:
                promotora_ext = get_campo(["PROMOTORA", "PRODUCTORA"], default="PRODUCCIÓN BLITZ")

            hamburguesa = get_campo(["HAMBURGUESA", "BURGER", "PLATO"], default="BRUTAL BACON")
            carne_gramos = get_campo(["CARNE", "GRAMAJE"], default="1 DE 90 GRS")
            
            coste_burger = limpiar_numero(get_campo(["COSTE HAMBURGUESA", "COSTE BURGER"]))
            gasto_genero = limpiar_numero(get_campo(["GASTO GÉNERO", "GASTO GENERO", "TOTAL GASTO MERCANCÍAS"]))
            coste_regaladas = limpiar_numero(get_campo(["COSTE HAMBURGUESAS REGALADAS", "REGALADAS COSTE"]))
            coste_personal = limpiar_numero(get_campo(["COSTE PERSONAL NETO", "COSTE PERSONAL", "PERSONAL NETO"]))
            entradas_aforo = limpiar_numero(get_campo(["ENTRADAS", "AFORO"]))
            ventas_q = limpiar_numero(get_campo(["VENTAS Q", "CANTIDAD VENDIDA", "UNIDADES VENDIDAS"]))
            ventas_total = limpiar_numero(get_campo(["TOTAL VENTAS €", "TOTAL VENTAS", "VENTAS TOTAL", "VENTAS €"]))
            coste_total = limpiar_numero(get_campo(["COSTE TOTAL", "TOTAL COSTE"]))
            comision_raw = limpiar_numero(get_campo(["COMISIÓN %", "COMISION %", "COMISIÓN", "COMISION"]))
            
            # Normalizar comisión: si viene como 0.3 -> 30.0%
            comision_pct = comision_raw * 100.0 if (0.0 < comision_raw <= 1.0) else comision_raw

            beneficio = limpiar_numero(get_campo(["BENEFICIO (€)", "BENEFICIO", "BENEFICIO NETO"]))
            margen_raw = limpiar_numero(get_campo(["% BENEFICIO", "MARGEN %", "BENEFICIO %"]))
            margen_pct = margen_raw * 100.0 if (0.0 < margen_raw <= 1.0) else margen_raw

            # ==========================================
            # PARSEAR DESGLOSE DE GÉNERO / MERCANCÍAS
            # ==========================================
            detalle_genero = []
            fila_genero_start = -1
            for r_i in range(len(df)):
                row_txt = " ".join([str(x).upper() for x in df.iloc[r_i].tolist()])
                if "GÉNERO" in row_txt or "GENERO" in row_txt:
                    fila_genero_start = r_i + 1
                    break

            if fila_genero_start != -1:
                for r_i in range(fila_genero_start, len(df)):
                    r_vals = [str(x).strip() for x in df.iloc[r_i].tolist()]
                    # Filtrar vacíos
                    r_vals_clean = [v for v in r_vals if v]
                    if not r_vals_clean:
                        continue
                    primero = r_vals_clean[0].upper()
                    if "TOTAL" in primero or "REGALADAS" in primero or "PERSONAL" in primero:
                        break
                    
                    nom_g = r_vals_clean[0]
                    p_ud = limpiar_numero(r_vals_clean[1]) if len(r_vals_clean) > 1 else 0.0
                    m_llevada = limpiar_numero(r_vals_clean[2]) if len(r_vals_clean) > 2 else 0.0
                    g_tot = limpiar_numero(r_vals_clean[3]) if len(r_vals_clean) > 3 else (p_ud * m_llevada)
                    
                    if nom_g and (m_llevada > 0 or g_tot > 0 or p_ud > 0):
                        detalle_genero.append({
                            "genero": nom_g,
                            "precio_ud": round(p_ud, 2),
                            "mercancia_llevada": round(m_llevada, 2),
                            "gasto": round(g_tot, 2)
                        })

            # ==========================================
            # PARSEAR DESGLOSE DE PERSONAL Y HORAS
            # ==========================================
            detalle_personal = []
            horas_empleados_str = "12:00"
            for r_i in range(len(df)):
                row_str = " ".join([str(x).upper() for x in df.iloc[r_i].tolist()])
                if "TOTAL HORAS EMPLEADOS" in row_str:
                    r_vals = [str(x).strip() for x in df.iloc[r_i].tolist() if str(x).strip()]
                    if len(r_vals) >= 2:
                        horas_empleados_str = r_vals[1]
                    break

            # ==========================================
            # RECALCULAR / VALIDAR CONSISTENCIA ECONÓMICA
            # ==========================================
            if ventas_total == 0.0 and ventas_q > 0 and coste_burger > 0:
                ventas_total = round(ventas_q * 12.0, 2) # Precio medio habitual 12€

            if beneficio == 0.0 and ventas_total > 0:
                com_eur = ventas_total * (comision_pct / 100.0)
                beneficio = ventas_total - com_eur - gasto_genero - coste_personal
                
            if margen_pct == 0.0 and ventas_total > 0:
                margen_pct = (beneficio / ventas_total) * 100.0

            raw_reg = get_campo(["REGALADAS Y PERSONAL (Q)", "REGALADAS", "HAMBURGUESAS REGALADAS"], default="0")
            try:
                regaladas_q = int(float(limpiar_numero(raw_reg)))
            except Exception:
                m_dig = re.search(r'\d+', str(raw_reg))
                regaladas_q = int(m_dig.group(0)) if m_dig else 0

            if coste_regaladas == 0.0 and regaladas_q > 0 and coste_burger > 0:
                coste_regaladas = round(regaladas_q * coste_burger, 2)

            id_evt = f"EVT-{nom_evento.replace(' ', '_')[:12]}-{fecha_ext.replace('/', '')[-4:]}"

            evento_dict = {
                "Id_Evento": id_evt,
                "Fecha": fecha_ext,
                "Nombre_Evento": nom_evento.strip().upper(),
                "Promotora": promotora_ext.strip().upper(),
                "Hamburguesa": hamburguesa.strip().upper(),
                "Carne_Gramos": carne_gramos.strip().upper(),
                "Coste_Hamburguesa": round(coste_burger, 2),
                "Gasto_Genero": round(gasto_genero, 2),
                "Personal_Horas": horas_empleados_str,
                "Coste_Personal": round(coste_personal, 2),
                "Regaladas_Q": regaladas_q,
                "Coste_Regaladas": round(coste_regaladas, 2),
                "Entradas_Aforo": int(entradas_aforo) if entradas_aforo else 0,
                "Ventas_Q": int(ventas_q) if ventas_q else 0,
                "Ventas_Total": round(ventas_total, 2),
                "Gastos_Extras": 0.0,
                "Comision_Pct": round(comision_pct, 1),
                "Coste_Total": round(coste_total, 2) if coste_total > 0 else round(gasto_genero + coste_personal, 2),
                "Beneficio_Neto": round(beneficio, 2),
                "Margen_Pct": round(margen_pct, 2),
                "Detalle_Genero_Json": json.dumps(detalle_genero, ensure_ascii=False),
                "Detalle_Personal_Json": json.dumps(detalle_personal, ensure_ascii=False),
                "Detalle_Gastos_Json": "[]",
                "Archivo_Origen": nombre_archivo,
                "Notas": f"Importado automáticamente desde {nombre_archivo}"
            }
            
            eventos_encontrados.append(evento_dict)

    except Exception as e:
        print(f"Error parseando archivo {ruta_archivo}: {e}")

    return eventos_encontrados

def sincronizar_carpeta_eventos():
    """Escanea la carpeta de Google Drive 'FOOD TRUCK > DATOS EVENTOS' e importa todos los archivos."""
    rutas_a_probar = [
        CARPETA_DATOS_EVENTOS,
        r"G:\Mi unidad\FOOD TRUCK\DATOS EVENTOS",
        r"g:\Mi unidad\FOOD TRUCK\DATOS EVENTOS",
        os.path.join(BASE_DIR, "DATOS_EVENTOS")
    ]
    
    carpeta_valida = ""
    for r in rutas_a_probar:
        if os.path.isdir(r):
            carpeta_valida = r
            break
            
    if not carpeta_valida:
        return 0, "No se encontró la carpeta en la ruta especificada."

    archivos_validos = []
    for root, dirs, files in os.walk(carpeta_valida):
        for f in files:
            if f.lower().endswith(('.xlsx', '.xls', '.xlsm', '.csv')) and not f.startswith('~$'):
                archivos_validos.append(os.path.join(root, f))

    if not archivos_validos:
        return 0, f"Carpeta localizada ({carpeta_valida}), pero no contiene archivos Excel o CSV."

    # Cargar eventos existentes para actualizar o agregar
    df_existente = cargar_eventos()
    nombres_existentes = set(df_existente["Nombre_Evento"].str.upper().tolist()) if not df_existente.empty else set()

    nuevos_eventos = []
    for ruta_f in archivos_validos:
        evts = parsear_archivo_evento(ruta_f)
        for ev in evts:
            # Si el evento no está en la base de datos o queremos refrescarlo
            if ev["Nombre_Evento"] not in nombres_existentes:
                nuevos_eventos.append(ev)
                nombres_existentes.add(ev["Nombre_Evento"])

    if nuevos_eventos:
        df_nuevos = pd.DataFrame(nuevos_eventos, columns=COLUMNAS_EVENTOS)
        df_final = pd.concat([df_existente, df_nuevos], ignore_index=True) if not df_existente.empty else df_nuevos
        df_final.to_csv(ARCHIVO_EVENTOS, index=False, encoding='utf-8-sig')
        return len(nuevos_eventos), f"¡Se importaron con éxito {len(nuevos_eventos)} eventos de {len(archivos_validos)} archivos!"
    else:
        return 0, f"Se analizaron {len(archivos_validos)} archivos. Todos los eventos ya estaban al día."

def cargar_eventos():
    """Carga el CSV maestro de eventos con tipado numérico correcto."""
    if not os.path.isfile(ARCHIVO_EVENTOS):
        # Crear inicial
        df_vacio = pd.DataFrame(columns=COLUMNAS_EVENTOS)
        df_vacio.to_csv(ARCHIVO_EVENTOS, index=False, encoding='utf-8-sig')
        # Intentar sincronizar de inmediato con la carpeta
        sincronizar_carpeta_eventos()

    try:
        df = pd.read_csv(ARCHIVO_EVENTOS, encoding='utf-8-sig', dtype=str).fillna("")
        cols_num = [
            "Coste_Hamburguesa", "Gasto_Genero", "Coste_Personal", 
            "Regaladas_Q", "Coste_Regaladas", "Entradas_Aforo", 
            "Ventas_Q", "Ventas_Total", "Gastos_Extras", 
            "Comision_Pct", "Coste_Total", "Beneficio_Neto", "Margen_Pct"
        ]
        for c in cols_num:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
        return df
    except Exception as e:
        st.error(f"Error cargando eventos: {e}")
        return pd.DataFrame(columns=COLUMNAS_EVENTOS)

def guardar_evento(nuevo_evento):
    df = cargar_eventos()
    df = pd.concat([df, pd.DataFrame([nuevo_evento])], ignore_index=True)
    df.to_csv(ARCHIVO_EVENTOS, index=False, encoding='utf-8-sig')

def render_modulo_eventos():
    # Encabezado
    st.markdown("""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
        <div>
            <h1 class="blitz-title" style="margin-bottom:2px;">🚚 Food Truck y Eventos</h1>
            <p class="blitz-subtitle">Control y liquidación de festivales, ferias, conciertos, escandallos y rentabilidad</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Estado de sincronización con la carpeta
    col_inf1, col_inf2 = st.columns([3, 1.2])
    with col_inf1:
        st.markdown(f"""
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:8px 14px; font-size:0.85rem; color:#475569;">
            📁 <b>Carpeta Vinculada:</b> <code>G:\\Mi unidad\\FOOD TRUCK\\DATOS EVENTOS</code>
        </div>
        """, unsafe_allow_html=True)
    with col_inf2:
        if st.button("🔄 Sincronizar Carpeta", use_container_width=True, type="secondary"):
            with st.spinner("Escaneando archivos de eventos en Google Drive..."):
                cant, msg = sincronizar_carpeta_eventos()
                if cant > 0:
                    st.success(msg)
                else:
                    st.info(msg)
                import time; time.sleep(0.8)
                st.rerun()

    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

    df_eventos = cargar_eventos()

    # Si está vacío tras cargar, lanzar un escaneo automático inicial
    if df_eventos.empty:
        cant, msg = sincronizar_carpeta_eventos()
        if cant > 0:
            df_eventos = cargar_eventos()

    if df_eventos.empty:
        st.warning("⚠️ No se encontraron eventos en la carpeta. Pulsa '🔄 Sincronizar Carpeta' o registra uno manualmente.")
        return

    # ==========================================
    # BARRA DE BÚSQUEDA Y FILTROS AVANZADOS
    # ==========================================
    st.markdown("""
    <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:10px; padding:12px 16px; margin-bottom:14px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
        <span style="font-weight:700; color:#111827; font-size:0.95rem;">🔍 Buscador y Filtros</span>
    </div>
    """, unsafe_allow_html=True)

    col_busq, col_f_fecha, col_f_prod = st.columns([2, 1, 1])

    with col_busq:
        busqueda_texto = st.text_input(
            "🔍 Buscar por Evento, Promotora o Hamburguesa:",
            placeholder="Escribe para buscar (ej: Viva Suecia, Monkey Pro, Brutal Bacon)...",
            label_visibility="visible"
        ).strip().lower()

    with col_f_fecha:
        fechas_disponibles = ["(Todas las fechas)"] + sorted(list(df_eventos["Fecha"].dropna().unique()), reverse=True)
        sel_fecha = st.selectbox("📅 Filtrar por Fecha:", fechas_disponibles)

    with col_f_prod:
        promotoras_disponibles = ["(Todas las productoras)"] + sorted(list(df_eventos["Promotora"].dropna().unique()))
        sel_promotora = st.selectbox("🏢 Filtrar por Productora:", promotoras_disponibles)

    # Aplicar filtros
    df_filtrado = df_eventos.copy()

    if busqueda_texto:
        mask_busq = (
            df_filtrado["Nombre_Evento"].str.lower().str.contains(busqueda_texto, na=False) |
            df_filtrado["Promotora"].str.lower().str.contains(busqueda_texto, na=False) |
            df_filtrado["Hamburguesa"].str.lower().str.contains(busqueda_texto, na=False) |
            df_filtrado["Fecha"].str.contains(busqueda_texto, na=False)
        )
        df_filtrado = df_filtrado[mask_busq]

    if sel_fecha != "(Todas las fechas)":
        df_filtrado = df_filtrado[df_filtrado["Fecha"] == sel_fecha]

    if sel_promotora != "(Todas las productoras)":
        df_filtrado = df_filtrado[df_filtrado["Promotora"] == sel_promotora]

    # ==========================================
    # KPIS DE RESUMEN DEL FILTRO SELECCIONADO
    # ==========================================
    total_evts = len(df_filtrado)
    total_ventas = df_filtrado["Ventas_Total"].sum()
    total_hamburguesas = int(df_filtrado["Ventas_Q"].sum())
    total_genero = df_filtrado["Gasto_Genero"].sum()
    total_personal = df_filtrado["Coste_Personal"].sum()
    total_beneficio = df_filtrado["Beneficio_Neto"].sum()
    margen_medio = (total_beneficio / total_ventas * 100.0) if total_ventas > 0 else 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("🎪 Total Eventos", total_evts)
    k2.metric("🍔 Burgers Vendidas", f"{total_hamburguesas:,}".replace(",", "."))
    k3.metric("💰 Ventas Totales", f"{total_ventas:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
    k4.metric("📈 Beneficio Neto", f"{total_beneficio:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
    k5.metric("🎯 % Margen Medio", f"{margen_medio:.1f} %")

    st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

    # ==========================================
    # TABLA DE EVENTOS
    # ==========================================
    st.subheader(f"📋 Listado de Eventos ({total_evts})")

    columnas_tabla = [
        "Fecha", "Nombre_Evento", "Promotora", "Hamburguesa", 
        "Ventas_Q", "Ventas_Total", "Gasto_Genero", "Coste_Personal", 
        "Comision_Pct", "Beneficio_Neto", "Margen_Pct"
    ]

    df_tabla = df_filtrado[columnas_tabla].copy()

    config_columnas = {
        "Fecha": st.column_config.TextColumn("📅 Fecha"),
        "Nombre_Evento": st.column_config.TextColumn("🎪 Evento"),
        "Promotora": st.column_config.TextColumn("🏢 Promotora"),
        "Hamburguesa": st.column_config.TextColumn("🍔 Burger"),
        "Ventas_Q": st.column_config.NumberColumn("Uds.", format="%d"),
        "Ventas_Total": st.column_config.NumberColumn("Ventas (€)", format="%.2f €"),
        "Gasto_Genero": st.column_config.NumberColumn("Género (€)", format="%.2f €"),
        "Coste_Personal": st.column_config.NumberColumn("Personal (€)", format="%.2f €"),
        "Comision_Pct": st.column_config.NumberColumn("Comisión (%)", format="%.1f %%"),
        "Beneficio_Neto": st.column_config.NumberColumn("Beneficio Neto", format="%.2f €"),
        "Margen_Pct": st.column_config.NumberColumn("% Margen", format="%.1f %%")
    }

    st.dataframe(
        df_tabla,
        use_container_width=True,
        hide_index=True,
        column_config=config_columnas
    )

    # ==========================================
    # DETALLE Y LIQUIDACIÓN COMPLETA DE UN EVENTO
    # ==========================================
    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

    nombres_para_detalle = df_filtrado["Nombre_Evento"].tolist()
    if nombres_para_detalle:
        with st.expander("🔎 Ver Ficha y Liquidación Detallada de un Evento", expanded=True):
            col_sel_det, _ = st.columns([2, 1])
            with col_sel_det:
                evento_sel_nombre = st.selectbox("Selecciona un evento para ver su escandallo y desglose completo:", nombres_para_detalle)

            fila_sel = df_filtrado[df_filtrado["Nombre_Evento"] == evento_sel_nombre].iloc[0]

            c_d1, c_d2, c_d3, c_d4 = st.columns(4)
            c_d1.markdown(f"**📅 Fecha:** {fila_sel['Fecha']}")
            c_d2.markdown(f"**🏢 Promotora:** {fila_sel['Promotora']}")
            c_d3.markdown(f"**🍔 Hamburguesa:** {fila_sel['Hamburguesa']} ({fila_sel['Carne_Gramos']})")
            c_d4.markdown(f"**🎟️ Entradas/Aforo:** {int(fila_sel['Entradas_Aforo']):,}".replace(",", "."))

            st.divider()

            tab_g, tab_p, tab_l = st.tabs(["🥩 Mercancía y Escandallo", "👥 Horas y Personal", "💵 Resumen Económico"])

            with tab_g:
                st.markdown("##### 📦 Mercancía Llevada vs Consumida")
                raw_genero = str(fila_sel.get("Detalle_Genero_Json", ""))
                if raw_genero and raw_genero.startswith("["):
                    try:
                        list_gen = json.loads(raw_genero)
                        if list_gen:
                            df_gen = pd.DataFrame(list_gen)
                            df_gen.columns = ["Género / Producto", "Precio Ud (€)", "Mercancía Llevada", "Gasto (€)"]
                            st.dataframe(
                                df_gen, 
                                use_container_width=True, 
                                hide_index=True,
                                column_config={
                                    "Precio Ud (€)": st.column_config.NumberColumn(format="%.2f €"),
                                    "Mercancía Llevada": st.column_config.NumberColumn(format="%.2f"),
                                    "Gasto (€)": st.column_config.NumberColumn(format="%.2f €")
                                }
                            )
                        else:
                            st.info("Sin líneas de desglose de mercancía.")
                    except Exception:
                        st.caption(f"Detalle en texto: {raw_genero}")
                else:
                    st.info("Sin desglose detallado de género por producto para este evento.")

                g1, g2 = st.columns(2)
                g1.metric("Gasto Total Género", f"{fila_sel['Gasto_Genero']:.2f} €")
                g2.metric("Hamburguesas Regaladas / Personal", f"{int(fila_sel['Regaladas_Q'])} uds ({fila_sel['Coste_Regaladas']:.2f} €)")

            with tab_p:
                st.markdown("##### 👥 Personal y Horas Trabajadas")
                p1, p2 = st.columns(2)
                p1.metric("Total Horas Empleados", f"{fila_sel['Personal_Horas']}")
                p2.metric("Coste Neto Personal (€)", f"{fila_sel['Coste_Personal']:.2f} €")

            with tab_l:
                st.markdown("##### 💰 Cuenta de Resultados del Evento")
                v_tot = float(fila_sel["Ventas_Total"])
                g_gen = float(fila_sel["Gasto_Genero"])
                c_pers = float(fila_sel["Coste_Personal"])
                g_ext = float(fila_sel["Gastos_Extras"])
                com_pct = float(fila_sel["Comision_Pct"])
                com_eur = v_tot * (com_pct / 100.0)
                beneficio = float(fila_sel["Beneficio_Neto"])
                margen = float(fila_sel["Margen_Pct"])

                filas_liquidacion = [
                    {"Concepto": "➕ Total Ventas Brutas", "Importe": f"{v_tot:,.2f} €", "Tipo": "Ingreso"},
                    {"Concepto": "➖ Comisión Promotora (" + f"{com_pct:.1f}%" + ")", "Importe": f"-{com_eur:,.2f} €", "Tipo": "Gasto"},
                    {"Concepto": "➖ Gasto Género Consumido", "Importe": f"-{g_gen:,.2f} €", "Tipo": "Gasto"},
                    {"Concepto": "➖ Coste Personal Neto", "Importe": f"-{c_pers:,.2f} €", "Tipo": "Gasto"},
                    {"Concepto": "➖ Gastos Extras (Gasolina, Furgoneta, Truss...)", "Importe": f"-{g_ext:,.2f} €", "Tipo": "Gasto"},
                    {"Concepto": "🏁 BENEFICIO NETO LIMPIO", "Importe": f"{beneficio:,.2f} €", "Tipo": "Resultado"},
                    {"Concepto": "🎯 Margen de Beneficio Real", "Importe": f"{margen:.2f} %", "Tipo": "Resultado"}
                ]

                df_liq = pd.DataFrame(filas_liquidacion)
                st.dataframe(df_liq, use_container_width=True, hide_index=True)

                if fila_sel.get("Notas"):
                    st.caption(f"📝 **Notas del evento:** {fila_sel['Notas']}")

    # ==========================================
    # REGISTRAR O IMPORTAR NUEVOS EVENTOS MANUALMENTE
    # ==========================================
    with st.expander("➕ Añadir / Registrar Nuevo Evento Manualmente", expanded=False):
        with st.form("form_nuevo_evento"):
            st.markdown("##### 📝 Datos Generales")
            c_n1, c_n2, c_n3 = st.columns(3)
            nuevo_nombre = c_n1.text_input("Nombre del Evento (ej: Warm Up 2026):")
            nueva_fecha = c_n2.text_input("Fecha (dd/mm/aaaa):", value=datetime.date.today().strftime("%d/%m/%Y"))
            nueva_promotora = c_n3.text_input("Promotora / Productora:", placeholder="ej: Monkey Pro, Ibolele...")

            c_h1, c_h2, c_h3, c_h4 = st.columns(4)
            nueva_burger = c_h1.text_input("Hamburguesa:", value="Brutal Bacon")
            nuevo_gramaje = c_h2.text_input("Gramaje carne:", value="1 de 90 grs")
            nuevo_coste_burger = c_h3.number_input("Coste Unitario Burger (€):", value=2.67, format="%.2f")
            nuevo_aforo = c_h4.number_input("Aforo / Entradas:", value=5000, step=500)

            st.markdown("##### 💵 Cifras Económicas y Ventas")
            c_v1, c_v2, c_v3, c_v4 = st.columns(4)
            nuevas_ventas_q = c_v1.number_input("Burgers Vendidas (Uds):", min_value=0, value=300, step=10)
            nuevas_ventas_eur = c_v2.number_input("Total Facturado (€):", min_value=0.0, value=3600.0, step=50.0)
            nuevo_gasto_gen = c_v3.number_input("Gasto en Género (€):", min_value=0.0, value=650.0, step=20.0)
            nuevo_coste_pers = c_v4.number_input("Coste Personal (€):", min_value=0.0, value=300.0, step=20.0)

            c_x1, c_x2, c_x3 = st.columns(3)
            nueva_comision_pct = c_x1.number_input("Comisión Promotora (%):", min_value=0.0, max_value=100.0, value=30.0, step=1.0)
            nuevos_extras = c_x2.number_input("Gastos Extras (Furgoneta, gasolina, etc.):", min_value=0.0, value=0.0, step=10.0)
            nuevas_regaladas = c_x3.number_input("Burgers Regaladas / Contrato:", min_value=0, value=25, step=5)

            nuevas_notas = st.text_area("Observaciones / Notas del evento:", placeholder="Comentarios del servicio, clima, problemas o puntos fuertes...")

            btn_guardar_evt = st.form_submit_button("💾 Guardar y Liquidar Evento", use_container_width=True, type="primary")

            if btn_guardar_evt:
                if not nuevo_nombre.strip():
                    st.error("Debes indicar al menos el nombre del evento.")
                else:
                    com_eur_calc = nuevas_ventas_eur * (nueva_comision_pct / 100.0)
                    coste_total_calc = nuevo_gasto_gen + nuevo_coste_pers + nuevos_extras
                    beneficio_calc = nuevas_ventas_eur - com_eur_calc - coste_total_calc
                    margen_calc = (beneficio_calc / nuevas_ventas_eur * 100.0) if nuevas_ventas_eur > 0 else 0.0
                    coste_regaladas_calc = nuevas_regaladas * nuevo_coste_burger

                    nuevo_id = f"EVT-2026-{len(df_eventos)+1:03d}"

                    registro = {
                        "Id_Evento": nuevo_id,
                        "Fecha": nueva_fecha.strip(),
                        "Nombre_Evento": nuevo_nombre.strip().upper(),
                        "Promotora": nueva_promotora.strip().upper(),
                        "Hamburguesa": nueva_burger.strip(),
                        "Carne_Gramos": nuevo_gramaje.strip(),
                        "Coste_Hamburguesa": round(nuevo_coste_burger, 2),
                        "Gasto_Genero": round(nuevo_gasto_gen, 2),
                        "Personal_Horas": "12:00",
                        "Coste_Personal": round(nuevo_coste_pers, 2),
                        "Regaladas_Q": int(nuevas_regaladas),
                        "Coste_Regaladas": round(coste_regaladas_calc, 2),
                        "Entradas_Aforo": int(nuevo_aforo),
                        "Ventas_Q": int(nuevas_ventas_q),
                        "Ventas_Total": round(nuevas_ventas_eur, 2),
                        "Gastos_Extras": round(nuevos_extras, 2),
                        "Comision_Pct": round(nueva_comision_pct, 2),
                        "Coste_Total": round(coste_total_calc, 2),
                        "Beneficio_Neto": round(beneficio_calc, 2),
                        "Margen_Pct": round(margen_calc, 2),
                        "Detalle_Genero_Json": "[]",
                        "Detalle_Personal_Json": "[]",
                        "Detalle_Gastos_Json": "[]",
                        "Archivo_Origen": "Manual",
                        "Notas": nuevas_notas.strip()
                    }

                    guardar_evento(registro)
                    st.success(f"✅ ¡Evento '{nuevo_nombre}' guardado con éxito! Beneficio: {beneficio_calc:,.2f} € ({margen_calc:.1f}%)")
                    import time; time.sleep(1.0)
                    st.rerun()
