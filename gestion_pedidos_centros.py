import os
import json
import base64
import datetime
import urllib.request
import urllib.parse
import pandas as pd
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_PEDIDOS = os.path.join(BASE_DIR, "Pedidos_Centros.json")
ARCHIVO_EQUIVALENCIAS = os.path.join(BASE_DIR, "Equivalencias.csv")
ARCHIVO_CATALOGO_PEDIDOS = os.path.join(BASE_DIR, "Catalogo_Pedidos.csv")

MAPA_CENTROS_CONFIG = {
    "ronda_sur": {
        "nombre": "Blitz Ronda Sur",
        "carpeta": "Entrada_Ronda_Sur",
        "icono": "📍"
    },
    "ronda": {
        "nombre": "Blitz Ronda Sur",
        "carpeta": "Entrada_Ronda_Sur",
        "icono": "📍"
    },
    "juan_borbon": {
        "nombre": "Blitz Juan de Borbón",
        "carpeta": "Entrada_Juan_Borbon",
        "icono": "📍"
    },
    "borbon": {
        "nombre": "Blitz Juan de Borbón",
        "carpeta": "Entrada_Juan_Borbon",
        "icono": "📍"
    },
    "juan": {
        "nombre": "Blitz Juan de Borbón",
        "carpeta": "Entrada_Juan_Borbon",
        "icono": "📍"
    }
}

def normalizar_clave_centro(clave):
    c = str(clave).strip().lower()
    if "ronda" in c:
        return "ronda_sur"
    if "borbon" in c or "juan" in c:
        return "juan_borbon"
    return c

def obtener_telegram_config():
    token = ""
    chat_id = ""
    # Intentar desde secrets de streamlit
    try:
        if "telegram_bot_token" in st.secrets:
            token = str(st.secrets["telegram_bot_token"]).strip()
        if "telegram_chat_id" in st.secrets:
            chat_id = str(st.secrets["telegram_chat_id"]).strip()
    except Exception:
        pass

    # Intentar desde archivo .streamlit/secrets.toml
    if not token or not chat_id:
        sec_path = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
        if os.path.isfile(sec_path):
            try:
                import tomllib
                with open(sec_path, "rb") as f:
                    cfg = tomllib.load(f)
                    token = cfg.get("telegram_bot_token", token)
                    chat_id = cfg.get("telegram_chat_id", chat_id)
            except Exception:
                pass
    return token, chat_id

def enviar_telegram(texto):
    token, chat_id = obtener_telegram_config()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "BlitzStock-Centers"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False

def sincronizar_github_silencioso(ruta_relativa, commit_msg):
    try:
        from sync_repo import sync_file
        sync_file(ruta_relativa, commit_msg)
    except Exception as e:
        print(f"[Sync GitHub Error] {e}")

def cargar_pedidos():
    if os.path.isfile(ARCHIVO_PEDIDOS):
        try:
            with open(ARCHIVO_PEDIDOS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_pedidos_archivo(pedidos_dict):
    try:
        with open(ARCHIVO_PEDIDOS, "w", encoding="utf-8") as f:
            json.dump(pedidos_dict, f, ensure_ascii=False, indent=2)
        sincronizar_github_silencioso("Pedidos_Centros.json", "Actualizar pedidos de centros")
        return True
    except Exception as e:
        print(f"[Error guardar pedidos] {e}")
        return False

def obtener_articulos_maestros():
    """Obtiene el catálogo de artículos para pedidos, priorizando Catalogo_Pedidos.csv y garantizando unicidad."""
    if os.path.isfile(ARCHIVO_CATALOGO_PEDIDOS):
        try:
            df = pd.read_csv(ARCHIVO_CATALOGO_PEDIDOS)
            df = df.drop_duplicates(subset=["Producto"], keep="first")
            resultado = []
            for _, r in df.iterrows():
                resultado.append({
                    "nombre": str(r["Producto"]).strip(),
                    "unidad": str(r.get("Unidad", "UD")).strip(),
                    "zona": str(r.get("Zona", "📦 Almacén Seco")).strip()
                })
            return resultado
        except Exception as e:
            print(f"[Error leyendo Catalogo_Pedidos] {e}")

    if not os.path.isfile(ARCHIVO_EQUIVALENCIAS):
        return []
    try:
        df = pd.read_csv(ARCHIVO_EQUIVALENCIAS)
        if "Producto_Maestro_Blitz" in df.columns:
            col_uni = "Unidad_Inventario" if "Unidad_Inventario" in df.columns else None
            df_unicos = df.drop_duplicates(subset=["Producto_Maestro_Blitz"], keep="first")
            df_unicos = df_unicos.sort_values("Producto_Maestro_Blitz")
            resultado = []
            for _, r in df_unicos.iterrows():
                u = str(r[col_uni]).strip() if col_uni and pd.notna(r[col_uni]) else "UD"
                resultado.append({
                    "nombre": str(r["Producto_Maestro_Blitz"]).strip(),
                    "unidad": u,
                    "zona": "General"
                })
            return resultado
        else:
            unicos = sorted(df["Producto_Maestro_Blitz"].dropna().unique())
            return [{"nombre": str(u).strip(), "unidad": "UD", "zona": "General"} for u in unicos]
    except Exception as e:
        print(f"[Error leyendo Equivalencias] {e}")
    return []

# -------------------------------------------------------------------------
# INTERFAZ PARA TRABAJADORES DEL CENTRO (SIN CONTRASEÑAS, 100% DIRECTA)
# -------------------------------------------------------------------------
def render_interfaz_centro(centro_param):
    centro_key = normalizar_clave_centro(centro_param)
    conf = MAPA_CENTROS_CONFIG.get(centro_key, {
        "nombre": f"Blitz {centro_param.capitalize()}",
        "carpeta": f"Entrada_{centro_key}",
        "icono": "📍"
    })
    nombre_centro = conf["nombre"]
    carpeta_destino = conf["carpeta"]

    # Inyección de estilos CSS mobile-first
    st.markdown("""
    <style>
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 3rem !important;
            max-width: 650px !important;
        }
        .center-card-btn {
            background: linear-gradient(135deg, #ffffff 0%, #f9fafb 100%);
            border: 2px solid #e5e7eb;
            border-radius: 18px;
            padding: 24px 20px;
            text-align: center;
            box-shadow: 0 4px 14px rgba(0,0,0,0.06);
            margin-bottom: 16px;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .center-card-btn:hover {
            border-color: #ef4444;
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(239,68,68,0.15);
        }
        .center-card-icon {
            font-size: 3rem;
            margin-bottom: 8px;
        }
        .center-card-title {
            font-size: 1.35rem;
            font-weight: 800;
            color: #111827;
            margin-bottom: 4px;
        }
        .center-card-sub {
            font-size: 0.90rem;
            color: #6b7280;
        }
        .stButton>button {
            border-radius: 12px;
            font-weight: 700;
        }
    </style>
    """, unsafe_allow_html=True)

    # Estado de la vista para este centro
    session_vista_key = f"vista_centro_{centro_key}"
    if session_vista_key not in st.session_state:
        st.session_state[session_vista_key] = "menu"

    vista_actual = st.session_state[session_vista_key]

    # Cabecera superior común
    c_logo, c_info = st.columns([1, 4])
    with c_logo:
        ruta_logo = os.path.join(BASE_DIR, "blitz_logo.jpg")
        if os.path.isfile(ruta_logo):
            st.image(ruta_logo, width=80)
        else:
            st.markdown("### 🍔")
    with c_info:
        st.markdown(f"<h2 style='margin:0; padding:0; color:#111827;'>{nombre_centro}</h2>", unsafe_allow_html=True)
        st.caption("Panel de Operaciones Diarias · Sin contraseñas")

    st.divider()

    # =========================================================================
    # VISTA 1: MENÚ PRINCIPAL (2 ICONOS GRANDES)
    # =========================================================================
    if vista_actual == "menu":
        pedidos_data = cargar_pedidos()
        pedido_previo = pedidos_data.get(centro_key)
        
        if pedido_previo and "fecha" in pedido_previo:
            st.info(f"🕒 **Último pedido enviado:** {pedido_previo['fecha']} ({len(pedido_previo.get('items', []))} productos)")

        st.markdown("<h4 style='text-align: center; color: #374151; margin-top: 10px; margin-bottom: 20px;'>¿Qué quieres hacer ahora?</h4>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            <div class="center-card-btn">
                <div class="center-card-icon">📸</div>
                <div class="center-card-title">Escanear Albarán</div>
                <div class="center-card-sub">Haz foto al albarán recibido</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Abrir Cámara / Albarán ➔", key="btn_go_cam", use_container_width=True, type="primary"):
                st.session_state[session_vista_key] = "escaner"
                st.rerun()

        with col2:
            st.markdown("""
            <div class="center-card-btn">
                <div class="center-card-icon">📋</div>
                <div class="center-card-title">Pedido Semanal</div>
                <div class="center-card-sub">Editar unidades y enviar a Salva</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Hacer Pedido Semanal ➔", key="btn_go_ped", use_container_width=True, type="secondary"):
                st.session_state[session_vista_key] = "pedido"
                st.rerun()

        st.markdown("<div style='margin-top: 30px; text-align:center;'>", unsafe_allow_html=True)
        st.caption("🔒 Acceso asignado automáticamente a este centro.")
        st.markdown("</div>", unsafe_allow_html=True)

    # =========================================================================
    # VISTA 2: ESCANEAR ALBARÁN (CÁMARA DEL MÓVIL / ESCÁNER NATIVO)
    # =========================================================================
    elif vista_actual == "escaner":
        if st.button("⬅️ Volver al Menú Principal", use_container_width=True):
            st.session_state[session_vista_key] = "menu"
            st.rerun()

        st.subheader(f"📸 Escanear Albarán · {nombre_centro}")
        
        st.markdown("""
        <div style="background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border: 2px dashed #2563eb; border-radius: 18px; padding: 20px 14px; text-align: center; margin: 10px 0 16px 0; box-shadow: 0 4px 14px rgba(37,99,235,0.08);">
            <div style="font-size: 3.2rem; margin-bottom: 6px;">📷</div>
            <div style="font-size: 1.25rem; font-weight: 800; color: #1e3a8a;">Toca abajo para Abrir la Cámara / Escáner</div>
            <div style="font-size: 0.90rem; color: #2563eb; margin-top: 6px; line-height: 1.4;">
                Se abrirá tu <b>cámara nativa a pantalla completa</b> a máxima resolución.
            </div>
            <div style="background:#ffffff; border-radius:12px; padding:10px 14px; margin-top:12px; font-size:0.84rem; color:#1e40af; text-align:left; border: 1px solid #bfdbfe;">
                📄 <b>Modo Escaneo (Bordes automáticos):</b><br>
                Al abrir la cámara y apuntar al albarán sobre la mesa, aparecerá en la pantalla un <b>botón amarillo "Escanear"</b> (o un icono de folio / 'T').<br>
                👉 <b>Tócalo:</b> recortará la mesa automáticamente, centrará el papel y lo dejará perfecto como un escáner.
            </div>
        </div>
        """, unsafe_allow_html=True)

        foto_final = st.file_uploader(
            "Toca para abrir la cámara o escanear documento:",
            type=["jpg", "jpeg", "png", "webp", "pdf"],
            help="Al tocar, tu móvil te permitirá elegir 'Cámara' (pantalla completa) o 'Escanear documento' de Google Drive."
        )

        if foto_final is not None:
            es_pdf = foto_final.name.lower().endswith(".pdf")
            if not es_pdf:
                st.image(foto_final, caption="Vista previa del albarán (alta resolución)", use_container_width=True)
            else:
                st.info(f"📄 Albarán PDF preparado: **{foto_final.name}**")
            
            if st.button("🚀 Enviar Albarán a Salva", use_container_width=True, type="primary"):
                with st.spinner("Enviando y notificando..."):
                    ahora = datetime.datetime.now()
                    ext = "pdf" if es_pdf else "jpg"
                    nombre_archivo = f"Albaran_{centro_key}_{ahora.strftime('%Y%m%d_%H%M%S')}.{ext}"
                    
                    # 1. Guardar en la carpeta física de entrada del centro
                    carpeta_ruta = os.path.join(BASE_DIR, carpeta_destino)
                    os.makedirs(carpeta_ruta, exist_ok=True)
                    ruta_guardada = os.path.join(carpeta_ruta, nombre_archivo)
                    
                    with open(ruta_guardada, "wb") as f_out:
                        f_out.write(foto_final.getbuffer())

                    # 2. Sincronizar de inmediato a GitHub (para que lo vea Streamlit Cloud)
                    ruta_relativa = os.path.join(carpeta_destino, nombre_archivo)
                    sincronizar_github_silencioso(ruta_relativa, f"Albarán enviado desde móvil: {nombre_centro}")

                    # 3. Notificación Telegram Inmediata a Salva
                    mensaje_telegram = (
                        f"🔔 *¡TIENES UN ALBARÁN PENDIENTE!*\n\n"
                        f"📍 *Centro:* {nombre_centro}\n"
                        f"📄 *Archivo:* `{nombre_archivo}`\n\n"
                        f"👀 _Escaneado a máxima resolución desde el móvil del centro._"
                    )
                    enviar_telegram(mensaje_telegram)

                    st.success("✅ ¡Albarán enviado con éxito! Salva ya ha recibido la notificación en Telegram.")
                    st.balloons()
                    
                    if st.button("⬅️ Terminar y volver al inicio", use_container_width=True):
                        st.session_state[session_vista_key] = "menu"
                        st.rerun()

    # =========================================================================
    # VISTA 3: PEDIDO SEMANAL (LISTA + CONTADORES)
    # =========================================================================
    elif vista_actual == "pedido":
        if st.button("⬅️ Volver al Menú Principal", use_container_width=True):
            st.session_state[session_vista_key] = "menu"
            st.rerun()

        st.subheader("📋 Pedido Semanal")
        st.markdown(f"Ajusta las cantidades que necesitas recibir en **{nombre_centro}**:")

        articulos = obtener_articulos_maestros()
        if not articulos:
            st.error("No se han podido cargar los artículos desde el Diccionario (Equivalencias.csv).")
            return

        pedidos_data = cargar_pedidos()
        pedido_previo = pedidos_data.get(centro_key, {})
        cantidades_previas = {}
        if "items" in pedido_previo:
            for it in pedido_previo["items"]:
                cantidades_previas[it["producto"]] = it["cantidad"]

        if pedido_previo.get("fecha"):
            st.caption(f"🕒 Último pedido enviado: **{pedido_previo['fecha']}** (Se sustituirá al enviar el nuevo)")

        busqueda = st.text_input("🔍 Filtrar artículos por nombre:", placeholder="Ej: mayonesa, pan, burger, guantes...")

        arts_filtrados = articulos
        if busqueda.strip():
            b = busqueda.strip().lower()
            arts_filtrados = [a for a in articulos if b in a["nombre"].lower()]

        # Contenedor de formulario de pedido agrupado por zonas
        st.markdown(f"Mostrando **{len(arts_filtrados)}** artículos:")

        cantidades_actuales = {}

        # Agrupar por zona para optimizar el recorrido físico del trabajador
        from collections import defaultdict
        zonas_dict = defaultdict(list)
        for art in arts_filtrados:
            zonas_dict[art.get("zona", "📦 Almacén Seco")].append(art)

        ORDEN_ZONAS_PREFERIDO = [
            "🧊 Congelador 1 (Patatas, Boniato, Pollo)",
            "🧊 Congelador 2 (Alitas, Nuggets, Tequeños, Croquetas)",
            "❄️ Cámara Frigorífica",
            "❄️ Cámara",
            "📦 Almacén Seco",
            "🧼 Limpieza y Desechables"
        ]

        def orden_zona_key(z):
            if z in ORDEN_ZONAS_PREFERIDO:
                return ORDEN_ZONAS_PREFERIDO.index(z)
            return 999

        zonas_ordenadas = sorted(zonas_dict.keys(), key=orden_zona_key)
        vistos = set()

        for nombre_zona in zonas_ordenadas:
            items_zona = [it for it in zonas_dict[nombre_zona] if it["nombre"] not in vistos]
            for it in items_zona:
                vistos.add(it["nombre"])
            if not items_zona:
                continue

            st.markdown(f"<div style='background:#f3f4f6; padding:6px 12px; border-radius:8px; font-weight:700; margin: 14px 0 8px 0; color:#1f2937;'>{nombre_zona} ({len(items_zona)})</div>", unsafe_allow_html=True)
            for art in items_zona:
                nom = art["nombre"]
                uni = art["unidad"]
                key_input = f"cant_{centro_key}_{nom}"
                
                c1, c2 = st.columns([3, 2])
                with c1:
                    st.markdown(f"**{nom}**")
                    st.caption(f"Unidad: {uni}")
                with c2:
                    val = st.number_input(
                        label=nom,
                        min_value=0,
                        step=1,
                        value=0,
                        key=key_input,
                        label_visibility="collapsed"
                    )
                    cantidades_actuales[nom] = {
                        "cantidad": val,
                        "unidad": uni
                    }

        st.divider()
        observaciones = st.text_area(
            "📝 Observaciones o notas especiales para Salva:",
            value=pedido_previo.get("observaciones", "") if not busqueda else "",
            placeholder="Ej: Nos hace falta pan extra para el viernes por evento especial, revisar servilletas..."
        )

        # Botón Guardar y Enviar
        if st.button("🚀 Guardar y Enviar Pedido a Salva", use_container_width=True, type="primary"):
            # Filtrar solo artículos con cantidad > 0
            items_pedidos = []
            # Revisar todas las claves en session_state para no perder los no filtrados en la búsqueda
            for art in articulos:
                nom = art["nombre"]
                uni = art["unidad"]
                key_k = f"cant_{centro_key}_{nom}"
                cnt = st.session_state.get(key_k, 0)
                if cnt > 0:
                    items_pedidos.append({
                        "producto": nom,
                        "unidad": uni,
                        "cantidad": int(cnt)
                    })

            if not items_pedidos and not observaciones.strip():
                st.warning("⚠️ No has seleccionado ninguna unidad ni escrito ninguna observación.")
            else:
                ahora_str = datetime.datetime.now().strftime("%d/%m/%Y a las %H:%M")
                
                # Guardar sustituyendo el anterior (borrado de la semana anterior)
                pedidos_data[centro_key] = {
                    "centro": nombre_centro,
                    "fecha": ahora_str,
                    "observaciones": observaciones.strip(),
                    "items": items_pedidos
                }
                
                guardar_pedidos_archivo(pedidos_data)

                # Notificación Telegram a Salva
                resumen_telegram = []
                for it in items_pedidos[:8]:
                    resumen_telegram.append(f"• *{it['cantidad']} {it['unidad']}* de {it['producto']}")
                if len(items_pedidos) > 8:
                    resumen_telegram.append(f"_... y {len(items_pedidos)-8} productos más_")
                    
                items_txt = "\n".join(resumen_telegram) if resumen_telegram else "_(Sin productos de lista)_"
                notas_txt = f"\n\n📝 *Notas:* {observaciones.strip()}" if observaciones.strip() else ""

                msg_tel = (
                    f"📦 *¡NUEVO PEDIDO SEMANAL RECIBIDO!*\n\n"
                    f"📍 *Centro:* {nombre_centro}\n"
                    f"🕒 *Fecha:* {ahora_str}\n\n"
                    f"📋 *Artículos solicitados ({len(items_pedidos)}):*\n{items_txt}"
                    f"{notas_txt}\n\n"
                    f"✅ _Actualizado en tu panel de Blitz Stock._"
                )
                enviar_telegram(msg_tel)

                st.success("✅ ¡Pedido semanal enviado y registrado con éxito! Salva ya tiene la notificación en Telegram.")
                st.balloons()


# -------------------------------------------------------------------------
# PANEL ADMINISTRADOR PARA SALVA (DENTRO DEL DASHBOARD COMPLETO)
# -------------------------------------------------------------------------
def render_panel_admin_pedidos():
    st.markdown("""
    <div style="background:#ffffff; padding:18px 24px; border-radius:14px; border:1px solid #e5e7eb; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,0.04);">
        <h2 style="margin:0; color:#111827; font-weight:800;">📋 Pedidos Semanales de los Centros</h2>
        <div style="color:#6b7280; font-size:0.92rem; margin-top:4px;">
            Consulta lo que ha pedido cada centro, la fecha de la última petición y sus observaciones.
        </div>
    </div>
    """, unsafe_allow_html=True)

    pedidos = cargar_pedidos()

    tab_ronda, tab_borbon = st.tabs(["📍 Blitz Ronda Sur", "📍 Blitz Juan de Borbón"])

    for tab, c_key, c_nombre in [(tab_ronda, "ronda_sur", "Blitz Ronda Sur"), (tab_borbon, "juan_borbon", "Blitz Juan de Borbón")]:
        with tab:
            info = pedidos.get(c_key)
            if not info or (not info.get("items") and not info.get("observaciones")):
                st.info(f"Aún no hay ningún pedido registrado de **{c_nombre}** para esta semana.")
            else:
                col_h1, col_h2 = st.columns([3, 1])
                with col_h1:
                    st.markdown(f"#### 📅 Pedido del **{info.get('fecha', 'Fecha desconocida')}**")
                with col_h2:
                    if st.button(f"🗑️ Limpiar / Archivar", key=f"btn_clear_{c_key}"):
                        pedidos.pop(c_key, None)
                        guardar_pedidos_archivo(pedidos)
                        st.success(f"Pedido de {c_nombre} archivado y limpiado.")
                        st.rerun()

                if info.get("observaciones"):
                    st.warning(f"📝 **Observaciones del centro:**\n\n{info['observaciones']}")

                items = info.get("items", [])
                if items:
                    st.markdown(f"##### 📦 Productos Solicitados ({len(items)}):")
                    df_items = pd.DataFrame(items)
                    df_items.columns = ["Producto", "Unidad", "Cantidad Pedida"]
                    
                    st.dataframe(
                        df_items,
                        use_container_width=True,
                        hide_index=True
                    )

                    # Botón para copiar texto rápido
                    resumen_texto = f"PEDIDO {c_nombre.upper()} - {info.get('fecha')}\n"
                    for it in items:
                        resumen_texto += f"- {it['cantidad']} {it['unidad']} {it['producto']}\n"
                    if info.get("observaciones"):
                        resumen_texto += f"\nNotas: {info.get('observaciones')}\n"

                    st.text_area("📋 Texto rápido para copiar/pegar a proveedores o WhatsApp:", value=resumen_texto, height=130)
                else:
                    st.write("El centro solo envió notas/observaciones sin artículos de lista.")
