# -*- coding: utf-8 -*-
"""
MÓDULO: Traspasos Internos de Mercancía entre Centros y Food Truck
Blitz Burger / Blitz Food S.L.
"""

import os
import csv
import json
import datetime
from datetime import timedelta
try:
    import streamlit as st
except ImportError:
    st = None
try:
    import pandas as pd
except ImportError:
    pd = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_STOCK = os.path.join(BASE_DIR, "Stock_Actual.csv")
ARCHIVO_EQUIVALENCIAS = os.path.join(BASE_DIR, "Equivalencias.csv")
ARCHIVO_CATALOGO_PEDIDOS = os.path.join(BASE_DIR, "Catalogo_Pedidos.csv")
ARCHIVO_HISTORICO_PRECIOS = os.path.join(BASE_DIR, "Historico_Precios.csv")
ARCHIVO_COMPRAS_ALBARANES = os.path.join(BASE_DIR, "Registro_Albaranes_Compras.csv")
ARCHIVO_TRASPASOS = os.path.join(BASE_DIR, "Registro_Traspasos.csv")

CENTROS_OPCIONES = [
    "🚚 Eventos / Food Truck",
    "📍 Blitz Ronda Sur",
    "📍 Blitz Juan de Borbón"
]

def mapear_centro_para_stock(centro_display):
    """Mapea el nombre de centro al usado internamente en Stock_Actual.csv"""
    c_low = str(centro_display).lower()
    if "ronda" in c_low:
        return "Blitz Ronda Sur"
    elif "borbon" in c_low or "borbón" in c_low:
        return "Blitz  Juan de Borbón"
    elif "food" in c_low or "evento" in c_low or "truck" in c_low:
        return "Food Truck Grande"
    return centro_display

def mapear_centro_para_consumos(centro_display):
    """Mapea el nombre de centro al usado en Registro_Albaranes_Compras.csv"""
    c_low = str(centro_display).lower()
    if "ronda" in c_low:
        return "Blitz Ronda Sur"
    elif "borbon" in c_low or "borbón" in c_low:
        return "Blitz Juan de Borbón"
    elif "food" in c_low or "evento" in c_low or "truck" in c_low:
        return "Eventos / Food Truck"
    return centro_display

def render_html_seguro(html_str):
    """Renderiza HTML eliminando sangrías para evitar que Markdown lo tome como código."""
    if not html_str or st is None:
        return
    html_limpio = "".join(l.strip() for l in html_str.splitlines() if l.strip())
    if hasattr(st, "html"):
        st.html(html_limpio)
    else:
        st.markdown(html_limpio, unsafe_allow_html=True)

def cargar_catalogo_maestro():
    """
    Carga todos los productos con su unidad por defecto, proveedor habitual
    y último precio unitario registrado.
    """
    catalogo = {}

    # 1. Base desde Equivalencias.csv (maestro principal)
    if os.path.exists(ARCHIVO_EQUIVALENCIAS):
        try:
            with open(ARCHIVO_EQUIVALENCIAS, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    p_nom = r.get("Producto_Maestro_Blitz", "").strip().upper()
                    if p_nom and p_nom not in catalogo:
                        try:
                            pr = float(r.get("Precio_Actual", 0.0) or 0.0)
                        except Exception:
                            pr = 0.0
                        catalogo[p_nom] = {
                            "nombre": p_nom,
                            "proveedor": r.get("Proveedor", "Varios").strip(),
                            "unidad": r.get("Unidad_Inventario", "UNIDADES").strip().upper(),
                            "precio": pr,
                            "ref": r.get("Referencia_Blitz", "").strip()
                        }
        except Exception as e:
            print(f"Error cargando Equivalencias: {e}")

    # 2. Complementar desde Catalogo_Pedidos.csv
    if os.path.exists(ARCHIVO_CATALOGO_PEDIDOS):
        try:
            with open(ARCHIVO_CATALOGO_PEDIDOS, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    p_nom = r.get("Producto", "").strip().upper()
                    if p_nom:
                        if p_nom not in catalogo:
                            catalogo[p_nom] = {
                                "nombre": p_nom,
                                "proveedor": r.get("Proveedor", "Varios").strip(),
                                "unidad": r.get("Unidad", "UNIDADES").strip().upper(),
                                "precio": 0.0,
                                "ref": ""
                            }
                        else:
                            if not catalogo[p_nom]["proveedor"] or catalogo[p_nom]["proveedor"] == "Varios":
                                catalogo[p_nom]["proveedor"] = r.get("Proveedor", "Varios").strip()
        except Exception as e:
            print(f"Error cargando Catalogo_Pedidos: {e}")

    # 3. Precios recientes desde Historico_Precios.csv
    if os.path.exists(ARCHIVO_HISTORICO_PRECIOS):
        try:
            with open(ARCHIVO_HISTORICO_PRECIOS, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    p_nom = r.get("Producto_Maestro", "").strip().upper()
                    if p_nom in catalogo:
                        try:
                            pr = float(r.get("Precio", 0.0) or 0.0)
                            if pr > 0:
                                catalogo[p_nom]["precio"] = pr
                                if r.get("Proveedor"):
                                    catalogo[p_nom]["proveedor"] = r.get("Proveedor").strip()
                        except Exception:
                            pass
        except Exception as e:
            print(f"Error cargando Historico_Precios: {e}")

    return catalogo

def calcular_semana_traspaso(fecha_obj):
    """Calcula la semana operativa para imputar los consumos."""
    try:
        import modulo_consumos
        return modulo_consumos.calcular_ciclo_operativo(fecha_obj)
    except Exception:
        # Fallback si no está disponible modulo_consumos
        offset = (fecha_obj.weekday() - 2) % 7
        miercoles = fecha_obj - timedelta(days=offset)
        sabado = miercoles + timedelta(days=3)
        return {
            "id_semana": f"{sabado.year}-M{sabado.month:02d}-Sem1",
            "etiqueta": f"Semana ({miercoles.strftime('%d/%m')})"
        }

def ejecutar_traspaso(centro_origen, centro_destino, fecha_traspaso, items, notas_generales=""):
    """
    Ejecuta el traspaso completo:
    1. Modifica cantidades en Stock_Actual.csv (resta origen, suma destino).
    2. Modifica compras por centro y proveedor en Registro_Albaranes_Compras.csv (- origen, + destino).
    3. Registra el traspaso detallado en Registro_Traspasos.csv.
    4. Sincroniza en background con GitHub.
    """
    if not items:
        return False, "No hay artículos para traspasar."
    
    if centro_origen == centro_destino:
        return False, "El centro de origen y destino deben ser diferentes."

    now = datetime.datetime.now()
    id_traspaso = f"TR-{now.strftime('%y%m%d-%H%M%S')}"
    fecha_str = fecha_traspaso.strftime("%d/%m/%Y")
    hora_str = now.strftime("%H:%M:%S")
    ciclo = calcular_semana_traspaso(fecha_traspaso)
    id_semana = ciclo.get("id_semana", f"{fecha_traspaso.year}-M{fecha_traspaso.month:02d}-Sem1")

    centro_origen_stock = mapear_centro_para_stock(centro_origen)
    centro_destino_stock = mapear_centro_para_stock(centro_destino)
    centro_origen_consumos = mapear_centro_para_consumos(centro_origen)
    centro_destino_consumos = mapear_centro_para_consumos(centro_destino)

    total_traspaso_euros = sum(item["subtotal"] for item in items)

    # ==========================================
    # 1. ACTUALIZAR STOCK_ACTUAL.CSV
    # ==========================================
    try:
        filas_stock = []
        indices_stock = {} # (Centro, Producto_Maestro) -> idx en filas_stock
        header_stock = ["Centro", "Producto_Maestro", "Referencia", "Cantidad_Stock", "Unidad_Inventario"]

        if os.path.exists(ARCHIVO_STOCK):
            with open(ARCHIVO_STOCK, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for r in reader:
                    if not r: continue
                    if not filas_stock:
                        header_stock = r
                        filas_stock.append(r)
                        continue
                    filas_stock.append(r)
                    k = (r[0].strip().lower(), r[1].strip().upper())
                    indices_stock[k] = len(filas_stock) - 1

        for item in items:
            prod_nom = item["articulo"].strip().upper()
            cant = float(item["cantidad"])
            ud = item["unidad"]
            ref = item.get("ref", "")

            # 1.1 Restar a Origen
            k_orig = (centro_origen_stock.strip().lower(), prod_nom)
            if k_orig in indices_stock:
                idx = indices_stock[k_orig]
                try:
                    cant_actual = float(filas_stock[idx][3])
                except Exception:
                    cant_actual = 0.0
                nueva_cant = max(0.0, cant_actual - cant)
                filas_stock[idx][3] = f"{nueva_cant:.1f}"
            else:
                # Si no existía fila en origen, registramos fila en 0
                nueva_fila = [centro_origen_stock, prod_nom, ref, "0.0", ud]
                filas_stock.append(nueva_fila)
                indices_stock[k_orig] = len(filas_stock) - 1

            # 1.2 Sumar a Destino
            k_dest = (centro_destino_stock.strip().lower(), prod_nom)
            if k_dest in indices_stock:
                idx = indices_stock[k_dest]
                try:
                    cant_actual = float(filas_stock[idx][3])
                except Exception:
                    cant_actual = 0.0
                nueva_cant = cant_actual + cant
                filas_stock[idx][3] = f"{nueva_cant:.1f}"
            else:
                nueva_fila = [centro_destino_stock, prod_nom, ref, f"{cant:.1f}", ud]
                filas_stock.append(nueva_fila)
                indices_stock[k_dest] = len(filas_stock) - 1

        with open(ARCHIVO_STOCK, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerows(filas_stock)

    except Exception as e_stock:
        return False, f"Error actualizando Stock_Actual.csv: {e_stock}"

    # ==========================================
    # 2. ACTUALIZAR REGISTRO_ALBARANES_COMPRAS.CSV (AJUSTE FINANCIERO FOOD COST)
    # ==========================================
    try:
        # Agrupar importes por proveedor
        compras_por_prov = {}
        for item in items:
            pr = item["proveedor"].strip() or "Varios"
            compras_por_prov[pr] = compras_por_prov.get(pr, 0.0) + item["subtotal"]

        filas_nuevas_compras = []
        for prov_nom, subtotal_prov in compras_por_prov.items():
            if subtotal_prov <= 0:
                continue
            
            # Apunte negativo en centro origen (reduce compras de ese proveedor en la semana)
            id_sal = f"{id_traspaso}-SAL"
            nota_sal = f"Traspaso salida hacia {centro_destino} (Ref: {id_traspaso})"
            filas_nuevas_compras.append([
                id_sal, fecha_str, prov_nom, centro_origen_consumos, f"{-subtotal_prov:.2f}", id_semana, "", nota_sal
            ])

            # Apunte positivo en centro destino (suma compras de ese proveedor en la semana)
            id_ent = f"{id_traspaso}-ENT"
            nota_ent = f"Traspaso entrada desde {centro_origen} (Ref: {id_traspaso})"
            filas_nuevas_compras.append([
                id_ent, fecha_str, prov_nom, centro_destino_consumos, f"{subtotal_prov:.2f}", id_semana, "", nota_ent
            ])

        if filas_nuevas_compras and os.path.exists(ARCHIVO_COMPRAS_ALBARANES):
            with open(ARCHIVO_COMPRAS_ALBARANES, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                for f_compra in filas_nuevas_compras:
                    writer.writerow(f_compra)

    except Exception as e_comp:
        return False, f"Error actualizando Registro_Albaranes_Compras.csv: {e_comp}"

    # ==========================================
    # 3. REGISTRAR HISTORIAL AUDITABLE (REGISTRO_TRASPASOS.CSV)
    # ==========================================
    try:
        file_exists = os.path.exists(ARCHIVO_TRASPASOS) and os.path.getsize(ARCHIVO_TRASPASOS) > 0
        with open(ARCHIVO_TRASPASOS, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "Id_Traspaso", "Fecha", "Hora", "Origen", "Destino",
                    "Articulo", "Cantidad", "Unidad", "Precio_Unitario",
                    "Total_Euros", "Proveedor", "Semana_Operativa", "Notas"
                ])
            for item in items:
                writer.writerow([
                    id_traspaso, fecha_str, hora_str, centro_origen, centro_destino,
                    item["articulo"], f"{float(item['cantidad']):.2f}", item["unidad"],
                    f"{float(item['precio']):.2f}", f"{float(item['subtotal']):.2f}",
                    item["proveedor"], id_semana, notas_generales
                ])
    except Exception as e_hist:
        print(f"Error escribiendo histórico de traspasos: {e_hist}")

    # ==========================================
    # 4. AVISO POR TELEGRAM
    # ==========================================
    try:
        from notificaciones import notificador_telegram
        if hasattr(notificador_telegram, "enviar_mensaje"):
            resumen_articulos = ", ".join([f"{it['cantidad']} {it['unidad']} de {it['articulo']}" for it in items[:3]])
            if len(items) > 3:
                resumen_articulos += f" y {len(items)-3} más..."
            msg_tg = (
                f"🔄 *TRASPASO DE MERCANCÍA REGISTRADO*\n\n"
                f"📤 *Origen:* {centro_origen}\n"
                f"📥 *Destino:* {centro_destino}\n"
                f"💰 *Importe:* {total_traspaso_euros:,.2f} €\n"
                f"📦 *Artículos:* {resumen_articulos}\n"
                f"📅 *Fecha:* {fecha_str} ({ciclo.get('etiqueta', '')})"
            )
            notificador_telegram.enviar_mensaje(msg_tg)
    except Exception:
        pass

    # ==========================================
    # 5. SINCRONIZACIÓN EN SEGUNDO PLANO CON GITHUB
    # ==========================================
    try:
        import threading
        from sync_repo import sync_file
        def _bg_sync():
            try:
                sync_file("Stock_Actual.csv", f"Sync: Actualizar stock por traspaso {id_traspaso}")
                sync_file("Registro_Albaranes_Compras.csv", f"Sync: Imputar traspaso compras {id_traspaso}")
                sync_file("Registro_Traspasos.csv", f"Sync: Log histórico traspaso {id_traspaso}")
            except Exception:
                pass
        threading.Thread(target=_bg_sync, daemon=True).start()
    except Exception:
        pass

    return True, f"✅ ¡Traspaso {id_traspaso} de {total_traspaso_euros:,.2f} € registrado con éxito!"


# ==========================================
# INTERFAZ GRÁFICA PRINCIPAL STREAMLIT
# ==========================================
def render_modulo_traspasos():
    """Renderiza la pantalla completa de Traspasos entre Centros."""
    
    # Encabezado visual estilo Blitz
    header_html = """
    <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 22px 26px; border-radius: 14px; margin-bottom: 22px; border: 1px solid #334155; box-shadow: 0 4px 16px rgba(0,0,0,0.25);">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
            <div>
                <h1 style="color: #f8fafc; font-size: 1.85rem; font-weight: 800; margin: 0; letter-spacing: -0.5px; display: flex; align-items: center; gap: 10px;">
                    🔄 Traspasos de Mercancía entre Centros y Food Truck
                </h1>
                <p style="color: #94a3b8; font-size: 0.95rem; margin: 6px 0 0 0;">
                    Reubicación de género sobrante de eventos e intercambio de stock entre locales con <strong>ajuste automático de costes, inventario y proveedores</strong>.
                </p>
            </div>
            <div style="background: rgba(30, 41, 59, 0.8); border: 1px solid #475569; padding: 6px 14px; border-radius: 20px;">
                <span style="color: #38bdf8; font-size: 0.85rem; font-weight: 700;">⚡ Ajuste Inmediato de Stock y Food Cost</span>
            </div>
        </div>
    </div>
    """
    render_html_seguro(header_html)

    # Estado de sesión para los artículos en el "carrito" de traspaso actual
    if "traspaso_items" not in st.session_state:
        st.session_state.traspaso_items = []

    # Cargar catálogo maestro de artículos y precios
    catalogo = cargar_catalogo_maestro()
    nombres_articulos = sorted(list(catalogo.keys()))

    # ==========================================
    # 1. SELECTORES DE ORIGEN, DESTINO Y FECHA
    # ==========================================
    st.markdown("### 📍 1. Datos del Traspaso (De ➔ Hacia)")
    
    col_c1, col_c2, col_c3 = st.columns([1.5, 1.5, 1.2])
    with col_c1:
        centro_de = st.selectbox(
            "📤 Centro Origen (\"DE\"): ",
            CENTROS_OPCIONES,
            index=0,
            key="sel_traspaso_de"
        )
    with col_c2:
        # Preseleccionar por defecto un centro distinto para que sea cómodo
        idx_def_hacia = 1 if centro_de == CENTROS_OPCIONES[0] else 0
        centro_hacia = st.selectbox(
            "📥 Centro Destino (\"HACIA\"): ",
            CENTROS_OPCIONES,
            index=idx_def_hacia,
            key="sel_traspaso_hacia"
        )
    with col_c3:
        fecha_traspaso = st.date_input(
            "📅 Fecha del traspaso:",
            value=datetime.date.today(),
            format="DD/MM/YYYY",
            key="input_fecha_traspaso"
        )

    if centro_de == centro_hacia:
        st.warning("⚠️ El centro de origen y destino deben ser diferentes.")

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # ==========================================
    # 2. FORMULARIO PARA AÑADIR ARTÍCULOS
    # ==========================================
    st.markdown("### 📦 2. Añadir Artículos al Traspaso")

    # Guardar catálogo en session_state para sincronizar widgets
    st.session_state["_cat_traspasos"] = catalogo

    def _sync_producto_callback():
        sel = st.session_state.get("sel_art_traspaso")
        cat = st.session_state.get("_cat_traspasos", {})
        if sel and sel in cat:
            item_info = cat[sel]
            st.session_state["num_precio_traspaso"] = float(item_info.get("precio", 0.0))
            st.session_state["txt_prov_traspaso"] = str(item_info.get("proveedor", "Varios"))
            st.session_state["num_cant_traspaso"] = 1.0

    # Inicialización la primera vez que se carga la pantalla
    if "sel_art_traspaso" not in st.session_state and nombres_articulos:
        first_p = nombres_articulos[0]
        first_d = catalogo.get(first_p, {})
        st.session_state["num_precio_traspaso"] = float(first_d.get("precio", 0.0))
        st.session_state["txt_prov_traspaso"] = str(first_d.get("proveedor", "Varios"))
        st.session_state["num_cant_traspaso"] = 1.0

    col_a1, col_a2, col_a3, col_a4, col_a5 = st.columns([2.5, 1, 1.1, 1.4, 1.2])

    with col_a1:
        art_sel = st.selectbox(
            "Selecciona Producto:",
            nombres_articulos,
            key="sel_art_traspaso",
            on_change=_sync_producto_callback
        )
        info_prod = catalogo.get(art_sel, {
            "nombre": art_sel, "proveedor": "Varios", "unidad": "KG", "precio": 0.0, "ref": ""
        })

    with col_a2:
        cant_input = st.number_input(
            f"Cantidad ({info_prod['unidad']}):",
            min_value=0.1,
            step=1.0,
            key="num_cant_traspaso"
        )

    with col_a3:
        precio_input = st.number_input(
            "Precio/Ud (€):",
            min_value=0.0,
            step=0.10,
            format="%.2f",
            key="num_precio_traspaso"
        )

    with col_a4:
        prov_input = st.text_input(
            "Proveedor:",
            key="txt_prov_traspaso"
        )

    with col_a5:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("➕ Añadir Fila", type="secondary", use_container_width=True, key="btn_add_item_traspaso"):
            subtot = round(cant_input * precio_input, 2)
            st.session_state.traspaso_items.append({
                "articulo": art_sel,
                "cantidad": cant_input,
                "unidad": info_prod["unidad"],
                "precio": precio_input,
                "subtotal": subtot,
                "proveedor": prov_input.strip() or "Varios",
                "ref": info_prod.get("ref", "")
            })
            st.rerun()

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # ==========================================
    # 3. TABLA DEL TRASPASO EN CURSO Y RESUMEN ECONÓMICO
    # ==========================================
    if st.session_state.traspaso_items:
        st.markdown("### 📋 Artículos en el Traspaso Actual")

        total_euros = sum(it["subtotal"] for it in st.session_state.traspaso_items)
        
        # Agrupación por proveedor para mostrar desglose
        prov_totales = {}
        for it in st.session_state.traspaso_items:
            pr = it["proveedor"]
            prov_totales[pr] = prov_totales.get(pr, 0.0) + it["subtotal"]

        filas_html = ""
        for idx, it in enumerate(st.session_state.traspaso_items):
            filas_html += f"""
            <tr style="border-bottom: 1px solid #334155;">
                <td style="padding: 10px 12px; font-weight: 700; color: #f8fafc;">{idx+1}</td>
                <td style="padding: 10px 12px; font-weight: 700; color: #38bdf8;">{it['articulo']}</td>
                <td style="padding: 10px 12px; color: #94a3b8;">{it['proveedor']}</td>
                <td style="padding: 10px 12px; text-align: right; color: #f8fafc; font-weight: 700;">{it['cantidad']:.1f} {it['unidad']}</td>
                <td style="padding: 10px 12px; text-align: right; color: #94a3b8;">{it['precio']:.2f} €</td>
                <td style="padding: 10px 12px; text-align: right; font-weight: 800; color: #fb923c;">{it['subtotal']:.2f} €</td>
            </tr>
            """

        tabla_html = f"""
        <div style="overflow-x: auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px;">
            <table style="width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 0.9rem;">
                <thead>
                    <tr style="background: #0f172a; border-bottom: 2px solid #475569; color: #94a3b8; text-transform: uppercase; font-size: 0.75rem;">
                        <th style="padding: 10px 12px; text-align: left;">#</th>
                        <th style="padding: 10px 12px; text-align: left;">Artículo</th>
                        <th style="padding: 10px 12px; text-align: left;">Proveedor</th>
                        <th style="padding: 10px 12px; text-align: right;">Cantidad</th>
                        <th style="padding: 10px 12px; text-align: right;">Precio/Ud</th>
                        <th style="padding: 10px 12px; text-align: right; color: #fb923c;">Subtotal</th>
                    </tr>
                </thead>
                <tbody>
                    {filas_html}
                    <tr style="background: #0f172a; border-top: 2px solid #38bdf8; font-weight: 800;">
                        <td colspan="5" style="padding: 12px; color: #f8fafc; text-align: right;">TOTAL TRASPASO:</td>
                        <td style="padding: 12px; text-align: right; color: #38bdf8; font-size: 1.15rem;">{total_euros:,.2f} €</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """
        render_html_seguro(tabla_html)

        # Botón para borrar última fila o vaciar
        col_btn_del1, col_btn_del2, col_vacio = st.columns([1.5, 1.5, 3])
        with col_btn_del1:
            if st.button("🗑️ Quitar Último Artículo", use_container_width=True, key="btn_del_last"):
                st.session_state.traspaso_items.pop()
                st.rerun()
        with col_btn_del2:
            if st.button("🧹 Vaciar Todo el Traspaso", use_container_width=True, key="btn_clear_all"):
                st.session_state.traspaso_items = []
                st.rerun()

        # Resumen del impacto financiero
        desglose_prov_txt = ", ".join([f"**{pr}** ({val:,.2f} €)" for pr, val in prov_totales.items()])
        ciclo_est = calcular_semana_traspaso(fecha_traspaso)

        st.markdown(f"""
        <div style="background: #1e293b; border-left: 5px solid #10b981; border-radius: 12px; padding: 18px 22px; margin: 20px 0; border: 1px solid #334155;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                <div>
                    <h3 style="color: #f8fafc; margin: 0; font-size: 1.25rem;">💰 Impacto Financiero del Traspaso</h3>
                    <div style="color: #94a3b8; font-size: 0.88rem; margin-top: 6px;">
                        Semana de imputación: <strong style="color:#f8fafc;">{ciclo_est.get('etiqueta', '')}</strong>
                    </div>
                    <div style="color: #ef4444; font-size: 0.9rem; margin-top: 6px;">
                        📉 <strong>Restará {total_euros:,.2f} €</strong> de compras e inventario a: <strong>{centro_de}</strong>
                    </div>
                    <div style="color: #10b981; font-size: 0.9rem; margin-top: 4px;">
                        📈 <strong>Sumará {total_euros:,.2f} €</strong> de compras e inventario a: <strong>{centro_hacia}</strong>
                    </div>
                    <div style="color: #94a3b8; font-size: 0.82rem; margin-top: 8px;">
                        🏢 Proveedores ajustados: {desglose_prov_txt}
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 2.1rem; font-weight: 900; color: #38bdf8;">{total_euros:,.2f} €</div>
                    <div style="color: #94a3b8; font-size: 0.8rem;">{len(st.session_state.traspaso_items)} artículos en total</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        notas_traspaso = st.text_input(
            "Notas u observaciones del traspaso (opcional):",
            placeholder="Ej. Sobrante hamburguesas y pan del evento de fin de semana...",
            key="txt_notas_traspaso"
        )

        # Botón maestro de confirmación
        puede_ejecutar = (centro_de != centro_hacia and total_euros > 0)
        if st.button("💾 CONFIRMAR Y EJECUTAR TRASPASO", type="primary", use_container_width=True, disabled=not puede_ejecutar, key="btn_confirmar_traspaso"):
            with st.spinner("Procesando traspaso, actualizando stock y ajustando consumos..."):
                exito, mensaje = ejecutar_traspaso(
                    centro_origen=centro_de,
                    centro_destino=centro_hacia,
                    fecha_traspaso=fecha_traspaso,
                    items=st.session_state.traspaso_items,
                    notas_generales=notas_traspaso
                )
                if exito:
                    st.success(mensaje)
                    st.session_state.traspaso_items = []
                    import time; time.sleep(1.2)
                    st.rerun()
                else:
                    st.error(mensaje)
    else:
        st.info("ℹ️ Selecciona un artículo, indica la cantidad y pulsa **➕ Añadir Fila** para empezar a registrar el traspaso.")

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

    # ==========================================
    # 4. HISTORIAL DE TRASPASOS REALIZADOS
    # ==========================================
    with st.expander("📋 Histórico de Traspasos Realizados", expanded=False):
        if os.path.exists(ARCHIVO_TRASPASOS) and os.path.getsize(ARCHIVO_TRASPASOS) > 0:
            try:
                if pd is not None:
                    df_hist = pd.read_csv(ARCHIVO_TRASPASOS, encoding="utf-8-sig")
                    if not df_hist.empty:
                        st.markdown(f"Mostrando los últimos **{len(df_hist)}** registros de traspasos:")
                        df_show = df_hist.iloc[::-1].copy()
                        st.dataframe(df_show, use_container_width=True, hide_index=True)
                    else:
                        st.info("Aún no se han registrado traspasos.")
                else:
                    with open(ARCHIVO_TRASPASOS, "r", encoding="utf-8-sig") as f:
                        rows = list(csv.DictReader(f))
                        if rows:
                            st.write(rows[::-1])
                        else:
                            st.info("Aún no se han registrado traspasos.")
            except Exception as e_df:
                st.error(f"Error cargando histórico: {e_df}")
        else:
            st.info("Aún no se ha realizado ningún traspaso de mercancía entre centros.")
