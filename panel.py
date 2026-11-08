import os
import csv
import shutil
import json
import re
import base64
import unicodedata
import difflib
import streamlit as st
from PIL import Image
import pandas as pd
from google import genai

# ==========================================
# 1. CONFIGURACIÓN E INFRAESTRUCTURA
# ==========================================

def normalizar_texto(texto):
    """Normaliza un texto para búsqueda flexible: quita tildes, puntuación,
    sufijos comerciales (S.A., S.L., S.A.U.), normaliza unidades y espacios."""
    if not texto:
        return ""
    t = texto.strip().lower()
    # Quitar tildes/acentos
    t = unicodedata.normalize('NFD', t)
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    # Quitar sufijos empresariales comunes
    t = re.sub(r'\b(s\.?a\.?u?\.?|s\.?l\.?u?\.?|distribuci[oó]n\s+mayorista|servicio\s+integral\s+de\s+alimentaci[oó]n|distribuidor\s+mayorista)\b', '', t)
    # Normalizar unidades gramaticales comunes (ej: 90gr -> 90 g, 90 grs -> 90 g)
    t = re.sub(r'(\d+)\s*(grs?|gramos?)\b', r'\1 g ', t)
    t = re.sub(r'(\d+)\s*(kgs?|kilos?)\b', r'\1 kg ', t)
    t = re.sub(r'(\d+)\s*(lts?|litros?)\b', r'\1 l ', t)
    # Abreviaturas típicas en albaranes
    t = re.sub(r'\bpeq\b', 'pequena', t)
    # Quitar toda puntuación (comas, puntos, comillas, guiones, etc.)
    t = re.sub(r'[^\w\s]', '', t)
    # Colapsar espacios múltiples
    t = re.sub(r'\s+', ' ', t).strip()
    return t

MAPA_PROVEEDORES_CANONICOS = {
    "makro": "Makro",
    "morales": "Morales",
    "hermanos morales": "Morales",
    "joaquin ayora": "Joaquín Ayora",
    "ayora": "Joaquín Ayora",
    "jasa": "Joaquín Ayora",
    "lucas caballero": "Lucas Caballero",
    "pedro diaz": "Pedro Díaz",
    "pedrodiaz": "Pedro Díaz",
    "macanao": "Macanao",
    "angel linares": "Ángel Linares",
    "la vaca rosa": "La Vaca Rosa",
    "vaca rosa": "La Vaca Rosa",
    "aceites manzano": "Aceites Manzano",
    "manzano": "Aceites Manzano",
    "cielo de boca": "Cielo de Boca",
    "coca cola": "Coca-Cola",
    "coca-cola": "Coca-Cola",
    "andres marmol": "Andrés Mármol",
}

def normalizar_proveedor(nombre_crudo):
    """Convierte cualquier variante de nombre, razón social o abreviatura al nombre canónico oficial."""
    if not nombre_crudo:
        return "Varios"
    n = normalizar_texto(str(nombre_crudo))
    for clave, canonico in MAPA_PROVEEDORES_CANONICOS.items():
        if clave in n or n in clave:
            return canonico
    return str(nombre_crudo).strip()

# Configuración de clave Gemini (local o Streamlit Secrets)
API_KEY_GOOGLE = ""

def obtener_api_key_gemini():
    """Recupera la clave API activa para Google Gemini."""
    # 1. Streamlit Secrets (Nube o local)
    try:
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            k = str(st.secrets["GEMINI_API_KEY"]).strip()
            if k and k != "TU_CLAVE_API_AQUI":
                return k
    except Exception:
        pass
    # 2. Session state si el usuario la introdujo en pantalla
    if st.session_state.get("gemini_api_key"):
        k = str(st.session_state.gemini_api_key).strip()
        if k and k != "TU_CLAVE_API_AQUI":
            return k
    # 3. Variable de entorno
    env_k = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_k and env_k != "TU_CLAVE_API_AQUI":
        return env_k
    return ""

def obtener_cliente_ia():
    k = obtener_api_key_gemini()
    if k:
        try:
            return genai.Client(api_key=k)
        except Exception:
            return None
    return None

try:
    _init_k = obtener_api_key_gemini()
    cliente_ia = genai.Client(api_key=_init_k if _init_k else "PENDIENTE")
except Exception:
    cliente_ia = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_EQUIVALENCIAS = os.path.join(BASE_DIR, "Equivalencias.csv")
ARCHIVO_RECETAS = os.path.join(BASE_DIR, "Recetas.csv")
ARCHIVO_STOCK = os.path.join(BASE_DIR, "Stock_Actual.csv")
ARCHIVO_PRECIOS_VENTA = os.path.join(BASE_DIR, "Precios_Venta.csv")
ARCHIVO_STOCK_MINIMO = os.path.join(BASE_DIR, "Stock_Minimo.csv")
ARCHIVO_HISTORICO_PRECIOS = os.path.join(BASE_DIR, "Historico_Precios.csv")

def registrar_en_historico_precios(proveedor, sinonimo, maestro, ref, precio, unidad, centro=""):
    try:
        precio_val = float(precio)
        if precio_val <= 0: return
    except (ValueError, TypeError):
        return
    proveedor = normalizar_proveedor(proveedor)
    archivo_hist = ARCHIVO_HISTORICO_PRECIOS
    existe = os.path.isfile(archivo_hist) and os.path.getsize(archivo_hist) > 0
    fecha_hoy = pd.Timestamp.now().strftime("%Y-%m-%d")
    try:
        with open(archivo_hist, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            if not existe:
                writer.writerow(["Fecha", "Proveedor", "Sinonimo", "Producto_Maestro", "Referencia", "Precio", "Unidad", "Centro"])
            writer.writerow([fecha_hoy, proveedor, sinonimo, maestro, ref, f"{precio_val:.2f}", unidad, centro])
    except Exception:
        pass
CARPETAS_ENTRADA = [
    os.path.join(BASE_DIR, "Albaranes_Pendientes"), 
    os.path.join(BASE_DIR, "Entrada_Juan_Borbon"), 
    os.path.join(BASE_DIR, "Entrada_Ronda_Sur"), 
    os.path.join(BASE_DIR, "Entrada_FoodTruck_1"), 
    os.path.join(BASE_DIR, "Entrada_FoodTruck_2")
]
CARPETA_PROCESADOS = os.path.join(BASE_DIR, "Albaranes_Procesados")

CENTROS_BLITZ = [
    "Blitz  Juan de Borbón", 
    "Blitz Ronda Sur", 
    "Food Truck Grande", 
    "Food Truck Pequeña"
]
centros_blitz = CENTROS_BLITZ

for carpeta in CARPETAS_ENTRADA:
    try:
        os.makedirs(carpeta, exist_ok=True)
    except OSError:
        pass
try:
    os.makedirs(CARPETA_PROCESADOS, exist_ok=True)
except OSError:
    pass

def cargar_rendimientos_maestros():
    rendimientos = {}
    if os.path.isfile(ARCHIVO_EQUIVALENCIAS):
        df = pd.read_csv(ARCHIVO_EQUIVALENCIAS, encoding='utf-8-sig', dtype=str).fillna("")
        for _, row in df.iterrows():
            m = row.get("Producto_Maestro_Blitz", "").strip()
            if not m: continue
            try:
                rend = float(row.get("Rendimiento", "1.0") or "1.0")
            except ValueError:
                rend = 1.0
            urec = row.get("Unidad_Receta", "")
            uinv = row.get("Unidad_Inventario", "")
            rendimientos[m] = {
                "rendimiento": rend,
                "unidad_receta": urec,
                "unidad_inv": uinv,
                "referencia": row.get("Referencia_Blitz", "")
            }
    return rendimientos

def procesar_articulos_albaran_ia(articulos_crudos, prov_nombre):
    grupos_articulos = {}
    for art in articulos_crudos:
        nombre_norm = normalizar_texto(art.get("nombre", ""))
        if not nombre_norm: continue
        if nombre_norm not in grupos_articulos:
            grupos_articulos[nombre_norm] = []
        grupos_articulos[nombre_norm].append(art)
    
    articulos_procesados = []
    for nombre_norm, lineas in grupos_articulos.items():
        nombre_mostrado = lineas[0].get("nombre", "")
        ud_val = lineas[0].get("unidad", "CAJA")
        es_cielo_pan = ("CIELO" in prov_nombre.upper() or "BOCA" in prov_nombre.upper()) and ("POTATO" in nombre_norm or "PAN" in nombre_norm)
        
        cantidades = []
        precios = []
        for l in lineas:
            try: c = float(l.get("cantidad", 0.0))
            except: c = 0.0
            try: p = float(l.get("precio_final", 0.0))
            except: p = 0.0
            cantidades.append(c)
            precios.append(p)
            
        total_cant = sum(cantidades)
        total_dinero = sum(c * p for c, p in zip(cantidades, precios))
        tiene_linea_gratis = any(p <= 0.001 for p in precios)
        
        if es_cielo_pan:
            # Regla Cielo de Boca: cada 10 cajas pagadas se regala 1 caja
            if tiene_linea_gratis:
                p_efectivo = round(total_dinero / total_cant, 2) if total_cant > 0 else 0.0
                art_dict = {
                    "nombre": nombre_mostrado,
                    "cantidad": total_cant,
                    "unidad": ud_val,
                    "precio_final": p_efectivo
                }
            else:
                if total_cant >= 10 and total_dinero > 0:
                    cajas_regalo = int(total_cant // 10)
                    cant_total_recibida = total_cant + cajas_regalo
                    p_efectivo = round(total_dinero / cant_total_recibida, 2)
                    art_dict = {
                        "nombre": nombre_mostrado,
                        "cantidad": cant_total_recibida,
                        "unidad": ud_val,
                        "precio_final": p_efectivo
                    }
                else:
                    p_efectivo = round(total_dinero / total_cant, 2) if total_cant > 0 else 0.0
                    art_dict = {
                        "nombre": nombre_mostrado,
                        "cantidad": total_cant,
                        "unidad": ud_val,
                        "precio_final": p_efectivo
                    }
        else:
            p_medio = round(total_dinero / total_cant, 2) if total_cant > 0 else 0.0
            art_dict = {
                "nombre": nombre_mostrado,
                "cantidad": total_cant,
                "unidad": ud_val,
                "precio_final": p_medio
            }
        articulos_procesados.append(art_dict)
    return articulos_procesados

def sumar_stock_albaran(centro, articulos_sumar):
    if not os.path.isfile(ARCHIVO_STOCK) or not articulos_sumar:
        return
    df_stock = pd.read_csv(ARCHIVO_STOCK, encoding='utf-8-sig', dtype=str)
    for m, cant in articulos_sumar.items():
        mask = (df_stock["Centro"] == centro) & (df_stock["Producto_Maestro"].str.upper() == m.upper())
        if mask.any():
            val_actual = float(df_stock.loc[mask, "Cantidad_Stock"].values[0] or 0.0)
            df_stock.loc[mask, "Cantidad_Stock"] = str(round(val_actual + cant, 2))
        else:
            df_stock = pd.concat([df_stock, pd.DataFrame([{
                "Centro": centro,
                "Producto_Maestro": m,
                "Referencia": "",
                "Cantidad_Stock": str(round(cant, 2)),
                "Unidad_Inventario": ""
            }])], ignore_index=True)
    df_stock.to_csv(ARCHIVO_STOCK, index=False, encoding='utf-8-sig')

# ==========================================
# 2. CEREBRO DEL DICCIONARIO
# ==========================================
def cargar_equivalencias():
    equivalencias = {}
    # Índice secundario: clave normalizada -> clave original exacta
    indice_normalizado = {}
    if os.path.isfile(ARCHIVO_EQUIVALENCIAS):
        with open(ARCHIVO_EQUIVALENCIAS, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    prov = row.get("Proveedor", "").strip().lower()
                    sinonimo = row.get("Sinonimo_Proveedor", "").strip().lower()
                    if not sinonimo or sinonimo == "sinonimo_proveedor": continue
                    factor = float(row.get("Factor_Multiplicador", "1.0").strip())
                    precio_str = row.get("Precio_Actual", "0.0").strip()
                    precio_actual = float(precio_str) if precio_str else 0.0
                    
                    clave_exacta = (prov, sinonimo)
                    ucompra = row.get("Unidad_Compra", "").strip().upper()
                    uinv = row.get("Unidad_Inventario", "KG").strip().upper()
                    rend = float(row.get("Rendimiento", "1.0") or "1.0")
                    urec = row.get("Unidad_Receta", "").strip().upper()
                    datos = {
                        "proveedor_orig": row.get("Proveedor", "").strip(),
                        "sinonimo_orig": row.get("Sinonimo_Proveedor", "").strip(),
                        "producto_maestro": row.get("Producto_Maestro_Blitz", ""),
                        "referencia": row.get("Referencia_Blitz", ""),
                        "unidad_compra": ucompra,
                        "factor": factor,
                        "unidad_inv": uinv,
                        "precio_actual": precio_actual,
                        "rendimiento": rend,
                        "unidad_receta": urec
                    }
                    if clave_exacta not in equivalencias:
                        equivalencias[clave_exacta] = dict(datos)
                        equivalencias[clave_exacta]["variantes"] = [datos]
                    else:
                        equivalencias[clave_exacta]["variantes"].append(datos)
                        # Preferir el registro con factor 1.0 o que coincida con la unidad de inventario principal como cabecera por defecto
                        if ucompra == uinv or factor == 1.0:
                            vars_list = equivalencias[clave_exacta]["variantes"]
                            equivalencias[clave_exacta] = dict(datos)
                            equivalencias[clave_exacta]["variantes"] = vars_list
                    
                    # Crear clave normalizada para búsqueda flexible
                    prov_norm = normalizar_texto(prov)
                    sino_norm = normalizar_texto(sinonimo)
                    clave_norm = (prov_norm, sino_norm)
                    if clave_norm not in indice_normalizado or ucompra == uinv or factor == 1.0:
                        indice_normalizado[clave_norm] = clave_exacta
                except ValueError:
                    continue
    return equivalencias, indice_normalizado

def seleccionar_variante_optima(eq_info, ud_leida=None, precio_detectado=None):
    if not eq_info:
        return eq_info
    variantes = eq_info.get("variantes", [])
    if not variantes or len(variantes) <= 1:
        return eq_info
        
    # =========================================================================
    # [BLOQUE PROTEGIDO]: SELECCIÓN DE VARIANTE POR PRECIO (NO MODIFICAR SIN PERMISO)
    # 0. Coincidencia inteligente por precio detectado (ej: 11.50 € Carne Smash -> fila KG)
    # =========================================================================
    if precio_detectado is not None and float(precio_detectado) > 0.0:
        p_det = float(precio_detectado)
        mejor_v = None
        min_p_diff = 999999.0
        for v in variantes:
            p_v = float(v.get("precio_actual", 0.0))
            if p_v > 0.0:
                diff = abs(p_det - p_v)
                if diff < min_p_diff:
                    min_p_diff = diff
                    mejor_v = v
        if mejor_v is not None and (min_p_diff <= 0.25 or (p_det > 0 and min_p_diff / p_det < 0.05)):
            res = dict(mejor_v)
            res["variantes"] = variantes
            return res
            
    if not ud_leida:
        return eq_info
    
    ud_norm = str(ud_leida).strip().upper()
    # 1. Coincidencia exacta de Unidad_Compra
    for v in variantes:
        if v.get("unidad_compra", "").strip().upper() == ud_norm:
            res = dict(v)
            res["variantes"] = variantes
            return res
            
    # 2. Coincidencia por tipo de unidad (peso / bolsas / cajas)
    if ud_norm in ["KG", "KGS", "KILO", "KILOS"]:
        for v in variantes:
            if v.get("unidad_compra", "").strip().upper() in ["KG", "KGS", "KILO", "KILOS"]:
                res = dict(v)
                res["variantes"] = variantes
                return res
                
    if ud_norm in ["BOLSA", "BOLSAS"]:
        for v in variantes:
            if v.get("unidad_compra", "").strip().upper() in ["BOLSA", "BOLSAS"]:
                res = dict(v)
                res["variantes"] = variantes
                return res
                
    if ud_norm in ["CAJA", "CAJAS", "BULTO", "BULTOS"]:
        for v in variantes:
            if v.get("unidad_compra", "").strip().upper() in ["CAJA", "CAJAS", "BULTO", "BULTOS"]:
                res = dict(v)
                res["variantes"] = variantes
                return res
                
    return eq_info

def buscar_equivalencia(diccionario_eq, indice_norm, prov_key, prod_key, ud_leida=None, precio_detectado=None):
    """Busca primero por clave exacta, luego por clave normalizada, producto exacto y finalmente similitud difusa protegida.
    Devuelve (eq_info, encontrado) o (None, False)."""
    # Función auxiliar para comparar nombres de proveedor tolerando 'sa', 'sl', espacios y puntuación
    def proveedores_compatibles(p1, p2):
        if normalizar_proveedor(p1).lower() == normalizar_proveedor(p2).lower():
            return True
        c1 = re.sub(r'[^a-z0-9]', '', str(p1).lower())
        c2 = re.sub(r'[^a-z0-9]', '', str(p2).lower())
        for s in ['sau', 'slu', 'sa', 'sl']:
            if c1.endswith(s): c1 = c1[:-len(s)]
            if c2.endswith(s): c2 = c2[:-len(s)]
        return c1 == c2 or (len(c1) >= 4 and len(c2) >= 4 and (c1 in c2 or c2 in c1))

    # 1) Match exacto
    clave_exacta = (prov_key, prod_key)
    if clave_exacta in diccionario_eq:
        return seleccionar_variante_optima(diccionario_eq[clave_exacta], ud_leida, precio_detectado), True
    
    # 2) Match normalizado (quita acentos, puntuación, sufijos comerciales, normaliza unidades)
    prov_norm = normalizar_texto(prov_key)
    prod_norm = normalizar_texto(prod_key)
    clave_norm = (prov_norm, prod_norm)
    if clave_norm in indice_norm:
        clave_original = indice_norm[clave_norm]
        return seleccionar_variante_optima(diccionario_eq[clave_original], ud_leida, precio_detectado), True

    # 2b) Match prioritario: MISMO producto exacto (sn == prod_norm) con proveedor compatible
    for (pn, sn), clave_original in indice_norm.items():
        if sn == prod_norm and proveedores_compatibles(pn, prov_norm):
            return seleccionar_variante_optima(diccionario_eq[clave_original], ud_leida, precio_detectado), True

    # 2c) Match de producto normalizado exacto en cualquier proveedor del catálogo
    for (pn, sn), clave_original in indice_norm.items():
        if sn == prod_norm:
            return seleccionar_variante_optima(diccionario_eq[clave_original], ud_leida, precio_detectado), True

    # 3) Match dentro del mismo proveedor por similitud difusa (>= 82%), con protección de palabras críticas
    mejor_ratio = 0.0
    mejor_clave = None
    palabras_criticas = ["cheddar", "gouda", "bacon", "pollo", "mayonesa", "barbacoa", "cerdo", "ternera", "trufa", "cebolla", "guacamole"]
    
    for (pn, sn), clave_original in indice_norm.items():
        if proveedores_compatibles(pn, prov_norm):
            # Prohibir cruces de productos distintos (ej. Cheddar vs Gouda)
            conflicto = False
            for w in palabras_criticas:
                if (w in prod_norm and w not in sn) or (w in sn and w not in prod_norm):
                    conflicto = True
                    break
            if conflicto:
                continue
                
            ratio = difflib.SequenceMatcher(None, sn, prod_norm).ratio()
            if ratio > mejor_ratio:
                mejor_ratio = ratio
                mejor_clave = clave_original
                
    if mejor_ratio >= 0.82 and mejor_clave is not None:
        return seleccionar_variante_optima(diccionario_eq[mejor_clave], ud_leida, precio_detectado), True
            
    # 4) Match global por similitud difusa muy alta (>= 90%) sin conflicto
    mejor_ratio_global = 0.0
    mejor_clave_global = None
    for (pn, sn), clave_original in indice_norm.items():
        conflicto = False
        for w in palabras_criticas:
            if (w in prod_norm and w not in sn) or (w in sn and w not in prod_norm):
                conflicto = True
                break
        if conflicto:
            continue
            
        ratio = difflib.SequenceMatcher(None, sn, prod_norm).ratio()
        if ratio > mejor_ratio_global:
            mejor_ratio_global = ratio
            mejor_clave_global = clave_original
            
    if mejor_ratio_global >= 0.90 and mejor_clave_global is not None:
        return seleccionar_variante_optima(diccionario_eq[mejor_clave_global], ud_leida, precio_detectado), True
    
    return None, False

def guardar_nueva_equivalencia(proveedor, sinonimo, maestro, referencia, unidad_compra, factor, unidad_inv, precio_actual=0.0, rendimiento=1.0, unidad_receta=""):
    proveedor = normalizar_proveedor(proveedor)
    archivo_nuevo = not os.path.isfile(ARCHIVO_EQUIVALENCIAS) or os.path.getsize(ARCHIVO_EQUIVALENCIAS) == 0
    if not archivo_nuevo:
        df = pd.read_csv(ARCHIVO_EQUIVALENCIAS, encoding='utf-8-sig', dtype=str)
        cambio_columnas = False
        if "Precio_Actual" not in df.columns:
            df["Precio_Actual"] = "0.0"
            cambio_columnas = True
        if "Rendimiento" not in df.columns:
            df["Rendimiento"] = "1.0"
            df["Unidad_Receta"] = df["Unidad_Inventario"]
            cambio_columnas = True
        if cambio_columnas:
            df.to_csv(ARCHIVO_EQUIVALENCIAS, index=False, encoding='utf-8-sig')
            
    with open(ARCHIVO_EQUIVALENCIAS, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if archivo_nuevo:
            writer.writerow(["Proveedor", "Sinonimo_Proveedor", "Producto_Maestro_Blitz", "Referencia_Blitz", "Unidad_Compra", "Factor_Multiplicador", "Unidad_Inventario", "Precio_Actual", "Rendimiento", "Unidad_Receta"])
        writer.writerow([proveedor, sinonimo, maestro, referencia, unidad_compra, factor, unidad_inv, precio_actual, rendimiento, unidad_receta])

def actualizar_precio_en_csv(proveedor, sinonimo, nuevo_precio, referencia="", precio_kilo=None):
    if not os.path.isfile(ARCHIVO_EQUIVALENCIAS): return
    proveedor = normalizar_proveedor(proveedor)
    df = pd.read_csv(ARCHIVO_EQUIVALENCIAS, encoding='utf-8-sig', dtype=str)
    if "Precio_Actual" not in df.columns:
        df["Precio_Actual"] = "0.0"
        
    mask = (df["Proveedor"].str.strip().str.lower() == proveedor.strip().lower()) & (df["Sinonimo_Proveedor"].str.strip().str.lower() == sinonimo.strip().lower())
    if not mask.any() and referencia:
        mask = (df["Proveedor"].str.strip().str.lower() == proveedor.strip().lower()) & (df["Referencia_Blitz"].str.strip() == str(referencia).strip())
    if not mask.any():
        prov_norm = normalizar_texto(proveedor)
        sino_norm = normalizar_texto(sinonimo)
        mask = df.apply(lambda r: normalizar_texto(r.get("Proveedor", "")) == prov_norm and normalizar_texto(r.get("Sinonimo_Proveedor", "")) == sino_norm, axis=1)
        
    if mask.any():
        for idx in df[mask].index:
            u_c = str(df.loc[idx, "Unidad_Compra"]).strip().upper()
            if u_c in ["KG", "KGS", "KILO", "KILOS"] and precio_kilo is not None:
                df.loc[idx, "Precio_Actual"] = f"{float(precio_kilo):.2f}"
            else:
                df.loc[idx, "Precio_Actual"] = f"{float(nuevo_precio):.2f}"
        df.to_csv(ARCHIVO_EQUIVALENCIAS, index=False, encoding='utf-8-sig')
        p_hist = precio_kilo if precio_kilo is not None else nuevo_precio
        u_hist = "KG" if precio_kilo is not None else ""
        registrar_en_historico_precios(proveedor, sinonimo, maestro="", ref=referencia, precio=p_hist, unidad=u_hist)

@st.dialog("¿Es referencia nueva?")
def confirmar_nueva_referencia(proveedor, prod_original, maestro_final, ref_final, ud_leida, factor_nuevo, unidad_inv_nueva, precio_detectado, rend_nuevo, urec_nueva):
    st.warning(f"Se va a crear el artículo **{maestro_final}** con la nueva referencia **{ref_final}**.")
    st.write("¿Confirmas que es correcto y deseas crearlo?")
    col1, col2 = st.columns(2)
    if col1.button("✅ Sí", use_container_width=True):
        guardar_nueva_equivalencia(proveedor, prod_original, maestro_final, ref_final, ud_leida, factor_nuevo, unidad_inv_nueva, precio_detectado, rend_nuevo, urec_nueva)
        st.rerun()
    if col2.button("❌ No / Cancelar", use_container_width=True):
        st.rerun()

@st.dialog("⚠️ ¡Alerta de Precio Distinto al del Diccionario!")
def confirmar_cambio_precio(proveedor, producto, precio_antiguo, precio_nuevo, ref="", maestro="", unidad=""):
    ref_txt = f"[{ref}] " if ref else ""
    maestro_txt = f" ({maestro})" if maestro else ""
    st.warning(f"**Artículo:** {ref_txt}**{producto}**{maestro_txt}\n\n**Proveedor:** {proveedor}")
    st.write(f"• Precio guardado en Diccionario: **{precio_antiguo:.2f} €/{unidad}**")
    st.write(f"• Precio detectado en este Albarán: **{precio_nuevo:.2f} €/{unidad}**")
    st.info("💡 **¿El proveedor te ha subido el precio?** Pulsa **Actualizar Precio** para guardarlo en el diccionario.\n\n"
            "💡 **¿Es una compra puntual o más cara por rotura de stock?** Pulsa **Ignorar** y el precio del diccionario no cambiará.")
    col1, col2 = st.columns(2)
    if col1.button("✅ Actualizar Precio en Diccionario", use_container_width=True):
        actualizar_precio_en_csv(proveedor, producto, precio_nuevo, referencia=ref)
        st.success("Precio actualizado en el diccionario.")
        import time; time.sleep(0.8)
        st.rerun()
    if col2.button("❌ Ignorar (Mantener precio del Diccionario)", use_container_width=True):
        st.rerun()

@st.dialog("⚠️ Confirmar Borrado")
def confirmar_borrado_diccionario(datos_editados):
    st.warning("¿Estás seguro de que quieres borrar los artículos seleccionados? Esta acción no se puede deshacer.")
    col1, col2 = st.columns(2)
    if col1.button("✅ Sí, Borrar", use_container_width=True):
        df_final = datos_editados[datos_editados["Seleccionar"] == False].drop(columns=["Seleccionar"])
        df_final.to_csv(ARCHIVO_EQUIVALENCIAS, index=False, encoding='utf-8-sig')
        st.success("✅ Productos eliminados.")
        import time; time.sleep(0.5); st.rerun()
    if col2.button("❌ No / Cancelar", use_container_width=True):
        st.rerun()

# ==========================================
# 3. INTERFAZ Y MEMORIA
# ==========================================
st.set_page_config(page_title="Blitz Stock", page_icon="🍔", layout="wide")

# Ocultar unicamente menu de desarrollo y pie de pagina
st.markdown("""
<style>
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
</style>
""", unsafe_allow_html=True)

# Forzar idioma español, bloquear traductor y desactivar el generador automatico de contraseñas de Google
import streamlit.components.v1 as components
components.html(
    """
    <script>
        const html = window.parent.document.querySelector("html");
        if (html) {
            html.setAttribute("lang", "es");
            html.setAttribute("translate", "no");
        }
        function bloquearSugerenciasGoogle() {
            try {
                const doc = window.parent.document;
                const passInputs = doc.querySelectorAll('input[type="password"]');
                passInputs.forEach(inp => {
                    inp.setAttribute('autocomplete', 'current-password');
                    inp.setAttribute('data-lpignore', 'true');
                    inp.setAttribute('data-1p-ignore', 'true');
                });
            } catch (e) {}
        }
        setInterval(bloquearSugerenciasGoogle, 400);
    </script>
    """,
    width=0, height=0
)

# ==========================================
# 2.5 CONTROL DE ACCESO Y AUTENTICACIÓN
# ==========================================
def obtener_configuracion_seguridad():
    cfg = {
        "password": "Blitz008",
        "recovery_email": "salvaandreo@gmail.com",
        "recovery_pin": "2004",
        "telegram_bot_token": "9094467418:AAF_392aZ2KLYT9ZDxam_W3hnphsKXUFkLc",
        "telegram_chat_id": "9177850452"
    }
    try:
        if hasattr(st, "secrets"):
            if "password" in st.secrets: cfg["password"] = str(st.secrets["password"]).strip()
            if "recovery_email" in st.secrets: cfg["recovery_email"] = str(st.secrets["recovery_email"]).strip()
            if "recovery_pin" in st.secrets: cfg["recovery_pin"] = str(st.secrets["recovery_pin"]).strip()
            if "telegram_bot_token" in st.secrets: cfg["telegram_bot_token"] = str(st.secrets["telegram_bot_token"]).strip()
            if "telegram_chat_id" in st.secrets: cfg["telegram_chat_id"] = str(st.secrets["telegram_chat_id"]).strip()
    except Exception:
        pass
        
    secrets_path = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
    if os.path.isfile(secrets_path):
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_s = line.strip()
                    for k in ["password", "recovery_email", "recovery_pin", "telegram_bot_token", "telegram_chat_id"]:
                        if line_s.startswith(k):
                            parts = line_s.split("=", 1)
                            if len(parts) == 2:
                                cfg[k] = parts[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return cfg

def enviar_notificacion_telegram(proveedor, centro, articulos):
    """Envía un resumen inmediato del albarán archivado por Telegram."""
    cfg = obtener_configuracion_seguridad()
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()
    if not token or not chat_id:
        return
        
    lineas_art = []
    total_dinero = 0.0
    for art in articulos:
        if art.get("ignorado", False): continue
        n = art.get("nombre", "")[:28]
        c = art.get("val_calc_final", art.get("cantidad", 0))
        p = art.get("precio_unitario_final", art.get("precio_final", 0.0))
        u = art.get("unidad", "")
        try:
            total_dinero += float(c) * float(p)
        except:
            pass
        lineas_art.append(f"• {c} {u} *{n}*")
        
    resumen_items = "\n".join(lineas_art[:6])
    if len(lineas_art) > 6:
        resumen_items += f"\n_... y {len(lineas_art) - 6} productos más_"
        
    mensaje = (
        f"🍔 *BLITZ STOCK · ALBARÁN ARCHIVADO*\n\n"
        f"📍 *Centro:* {centro}\n"
        f"🏢 *Proveedor:* {proveedor}\n"
        f"💰 *Total estimado:* {total_dinero:.2f} €\n\n"
        f"📦 *Productos:* \n{resumen_items}\n\n"
        f"✅ _Stock sumado y actualizado en tiempo real_"
    )
    
    try:
        import urllib.request
        import json
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": mensaje,
            "parse_mode": "Markdown"
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Blitz-Stock-App"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            pass
    except Exception:
        pass

def guardar_nueva_password(nueva_clave):
    secrets_path = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
    lineas = []
    encontrado = False
    if os.path.isfile(secrets_path):
        with open(secrets_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("password"):
                    lineas.append(f'password = "{nueva_clave}"\n')
                    encontrado = True
                else:
                    lineas.append(line)
    if not encontrado:
        lineas.insert(0, f'password = "{nueva_clave}"\n')
    with open(secrets_path, "w", encoding="utf-8") as f:
        f.writelines(lineas)

def verificar_autenticacion():
    if st.session_state.get("autenticado", False):
        return True

    cfg = obtener_configuracion_seguridad()

    st.markdown("""
    <style>
        .login-card {
            max-width: 440px;
            margin: 24px auto 10px auto;
            background: #ffffff;
            border-radius: 16px;
            padding: 28px 24px 20px 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.06);
            border: 1px solid #e5e7eb;
            text-align: center;
        }
        .login-title {
            font-size: 1.55rem;
            font-weight: 800;
            color: #111827;
            margin-top: 10px;
            margin-bottom: 4px;
            font-family: 'Inter', -apple-system, sans-serif;
        }
        .login-sub {
            font-size: 0.88rem;
            color: #6b7280;
            margin-bottom: 20px;
        }
    </style>
    """, unsafe_allow_html=True)

    ruta_logo = os.path.join(BASE_DIR, "blitz_logo.jpg")
    logo_tag = ""
    if os.path.isfile(ruta_logo):
        with open(ruta_logo, "rb") as f_img:
            b64 = base64.b64encode(f_img.read()).decode()
            logo_tag = f'<img src="data:image/jpeg;base64,{b64}" style="width: 135px; border-radius: 12px; margin-bottom: 6px;">'

    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        if st.session_state.get("modo_recuperacion", False):
            # -------------------------------------------------------------
            # MODO RECUPERACIÓN DE CONTRASEÑA
            # -------------------------------------------------------------
            st.markdown(f"""
            <div class="login-card">
                {logo_tag}
                <div class="login-title">🔑 Recuperar Clave</div>
                <div class="login-sub">Correo vinculado: <b>{cfg.get("recovery_email", "salvaandreo@gmail.com")}</b></div>
            </div>
            """, unsafe_allow_html=True)

            with st.form("form_recuperar"):
                st.caption("Verifica tu identidad con tu correo y el PIN maestro:")
                email_input = st.text_input("Correo de recuperación:", placeholder="salvaandreo@gmail.com")
                pin_input = st.text_input("PIN Maestro de Seguridad:", type="password", placeholder="Introduce tu PIN maestro...")
                nueva_pass = st.text_input("Nueva contraseña deseada:", type="password", placeholder="Escribe tu nueva clave...")
                
                btn_cambiar = st.form_submit_button("🔄 Restablecer y Guardar Contraseña", use_container_width=True, type="primary")
                
                if btn_cambiar:
                    email_ok = (email_input.strip().lower() == cfg.get("recovery_email", "").strip().lower())
                    pin_ok = (pin_input.strip() == cfg.get("recovery_pin", "").strip())
                    
                    if not email_ok:
                        st.error("❌ El correo no coincide con el correo de recuperación registrado.")
                    elif not pin_ok:
                        st.error("❌ El PIN Maestro de seguridad es incorrecto.")
                    elif not nueva_pass.strip():
                        st.warning("⚠️ Debes escribir una nueva contraseña válida.")
                    else:
                        guardar_nueva_password(nueva_pass.strip())
                        st.success("✅ ¡Contraseña cambiada con éxito! Ya puedes iniciar sesión con tu nueva clave.")
                        st.session_state["modo_recuperacion"] = False
                        st.session_state["pass_restablecida"] = True

            col_v1, col_v2 = st.columns([1, 1])
            if col_v1.button("⬅️ Volver al Login", use_container_width=True):
                st.session_state["modo_recuperacion"] = False
                st.rerun()

        else:
            # -------------------------------------------------------------
            # MODO LOGIN HABITUAL
            # -------------------------------------------------------------
            st.markdown(f"""
            <div class="login-card">
                {logo_tag}
                <div class="login-title">🍔 Blitz Stock</div>
                <div class="login-sub">Acceso restringido · Introduce tu contraseña</div>
            </div>
            """, unsafe_allow_html=True)

            if st.session_state.get("pass_restablecida", False):
                st.success("✅ Contraseña actualizada correctamente. Entra con tu nueva clave.")
                st.session_state["pass_restablecida"] = False

            with st.form("form_autenticacion", clear_on_submit=False):
                clave = st.text_input("Contraseña de acceso", type="password", placeholder="Escribe tu contraseña...", label_visibility="collapsed")
                enviado = st.form_submit_button("🔓 Iniciar Sesión", use_container_width=True, type="primary")

                if enviado:
                    p_valida = cfg.get("password", "Blitz008")
                    if clave.strip() in [p_valida, p_valida + "."]:
                        st.session_state["autenticado"] = True
                        st.rerun()
                    else:
                        st.error("❌ Contraseña incorrecta. Inténtalo de nuevo.")

            st.markdown("<div style='text-align: center; margin-top: 14px;'>", unsafe_allow_html=True)
            if st.button("❓ ¿Has olvidado tu contraseña?", key="btn_olvide_pass"):
                st.session_state["modo_recuperacion"] = True
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

# -------------------------------------------------------------------------
# ACCESO DIRECTO PARA CENTROS (SIN CONTRASEÑAS NI PINS)
# E.g. https://blitz-stock.streamlit.app/?centro=ronda_sur
# Build: v3.9.7 - Camara completa nativa garantizada
# -------------------------------------------------------------------------
centro_param = st.query_params.get("centro", "")
if isinstance(centro_param, list):
    centro_param = centro_param[0] if centro_param else ""
centro_param = str(centro_param).strip().lower()

if centro_param in ["ronda_sur", "juan_borbon", "ronda", "borbon", "juan"]:
    import importlib
    import gestion_pedidos_centros
    importlib.reload(gestion_pedidos_centros)
    gestion_pedidos_centros.render_interfaz_centro(centro_param)
    st.stop()

verificar_autenticacion()

# ==========================================
# GESTOR DE TEMAS Y ESTILO CORPORATIVO
# ==========================================
with st.sidebar:
    ruta_logo_side = os.path.join(BASE_DIR, "blitz_logo.jpg")
    logo_b64 = ""
    if os.path.isfile(ruta_logo_side):
        with open(ruta_logo_side, "rb") as f_img:
            logo_b64 = base64.b64encode(f_img.read()).decode()

    # Encabezado lateral estilo Grubtech o Blitz
    if "tema_activo" not in st.session_state:
        st.session_state.tema_activo = "🏢 Oficina (GrubCenter)"

    if st.session_state.tema_activo == "🏢 Oficina (GrubCenter)":
        st.markdown("""
        <div style="display:flex; align-items:center; gap:8px; margin: 0 0 16px 2px; padding-top: 2px;">
            <span style="font-size:2.05rem; font-weight:800; color:#0066ff; letter-spacing:-0.5px; font-family:'Inter', sans-serif;">blitz<span style="color:#111827;">stock</span></span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="display:flex; align-items:center; gap:8px; margin: 0 0 14px 2px; padding-top: 2px;">
            <span style="font-size:2.05rem; font-weight:900; color:#ff0055; letter-spacing:0.5px; text-shadow:0 0 12px rgba(255,0,85,0.6);">BLITZ<span style="color:#ffffff;">STOCK</span></span>
        </div>
        """, unsafe_allow_html=True)
        if os.path.isfile(ruta_logo_side):
            st.image(ruta_logo_side, width=120)

    st.markdown('<p style="font-size:0.8rem; font-weight:700; color:#9ca3af; text-transform:uppercase; letter-spacing:1px; margin:14px 0 10px 4px;">MENÚ PRINCIPAL</p>', unsafe_allow_html=True)
    
    if "seccion_activa" not in st.session_state:
        st.session_state.seccion_activa = "📡 Radar de Albaranes"
        
    if "nav_counter" not in st.session_state:
        st.session_state.nav_counter = 0

    opciones_stock = [
        "📚 Gestor de Diccionario",
        "📖 Gestión de Menú y Recetas",
        "⚡ Ventas y Cierre (Camarero10)",
        "📦 Control de Inventario"
    ]

    es_radar = (st.session_state.seccion_activa == "📡 Radar de Albaranes")
    
    # 1. Radar de Albaranes
    if st.button("📡 Radar de Albaranes", use_container_width=True, type="primary" if es_radar else "secondary", key="btn_nav_radar"):
        st.session_state.seccion_activa = "📡 Radar de Albaranes"
        st.session_state.nav_counter += 1
        st.rerun()
        
    st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
    
    # 1.1 Pedidos Centros
    es_pedidos_centros = (st.session_state.seccion_activa == "📋 Pedidos Centros")
    if st.button("📋 Pedidos Centros", use_container_width=True, type="primary" if es_pedidos_centros else "secondary", key="btn_nav_pedidos_centros"):
        st.session_state.seccion_activa = "📋 Pedidos Centros"
        st.session_state.nav_counter += 1
        st.rerun()
        
    st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
    
    # 2. Desplegable "Opciones de Stock"
    idx_stock = opciones_stock.index(st.session_state.seccion_activa) if st.session_state.seccion_activa in opciones_stock else None
    
    seleccion_stock = st.selectbox(
        "Opciones de Stock",
        opciones_stock,
        index=idx_stock,
        placeholder="🔽 Opciones de Stock...",
        key=f"sb_opciones_stock_{st.session_state.nav_counter}"
    )
    
    if seleccion_stock and seleccion_stock != st.session_state.seccion_activa:
        st.session_state.seccion_activa = seleccion_stock
        st.rerun()
        
    st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
    
    # 3. Opciones separadas (estilo Radar de Albaranes)
    es_food_cost = (st.session_state.seccion_activa == "💰 Rentabilidad y Food Cost")
    if st.button("💰 Rentabilidad y Food Cost", use_container_width=True, type="primary" if es_food_cost else "secondary", key="btn_nav_food_cost"):
        st.session_state.seccion_activa = "💰 Rentabilidad y Food Cost"
        st.session_state.nav_counter += 1
        st.rerun()
        
    es_pedidos = (st.session_state.seccion_activa == "🛒 Asistente de Compras y Pedidos")
    if st.button("🛒 Asistente de Compras y Pedidos", use_container_width=True, type="primary" if es_pedidos else "secondary", key="btn_nav_pedidos"):
        st.session_state.seccion_activa = "🛒 Asistente de Compras y Pedidos"
        st.session_state.nav_counter += 1
        st.rerun()
        
    es_graficas = (st.session_state.seccion_activa == "📈 Evolución y Comparativa de Precios")
    if st.button("📈 Evolución y Comparativa de Precios", use_container_width=True, type="primary" if es_graficas else "secondary", key="btn_nav_graficas"):
        st.session_state.seccion_activa = "📈 Evolución y Comparativa de Precios"
        st.session_state.nav_counter += 1
        st.rerun()
        
    seccion_activa = st.session_state.seccion_activa
    
    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
    st.divider()
    
    # Pie de barra lateral idéntico al panel de Grubtech
    st.markdown("""
    <div style="display:flex; flex-direction:column; gap:6px; font-size:0.85rem; margin-bottom:12px;">
        <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 10px; border-radius:6px; background:rgba(0,0,0,0.02);">
            <span>🔔 Notificaciones</span>
            <span style="color:#10b981; font-weight:700; font-size:0.75rem;">● ACTIVO</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 10px; border-radius:6px; background:rgba(0,0,0,0.02);">
            <span>🌐 Idioma</span>
            <span style="font-weight:600; font-size:0.8rem;">ES</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 12px; background:rgba(0,102,255,0.08); border-radius:8px; color:#0066ff; font-weight:700;">
            <span>👤 BLITZ FOOD S.L</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    with st.expander("🎨 Ajustar Tema Visual"):
        nuevo_tema = st.radio("Modo:", ["🏢 Oficina (GrubCenter)", "🍔 Blitz Neón"], 
                              index=0 if st.session_state.tema_activo == "🏢 Oficina (GrubCenter)" else 1,
                              key="radio_tema")
        if nuevo_tema != st.session_state.tema_activo:
            st.session_state.tema_activo = nuevo_tema
            st.rerun()

    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    if st.button("🚪 Cerrar Sesión", use_container_width=True, key="btn_cerrar_sesion"):
        st.session_state["autenticado"] = False
        st.rerun()

tema_activo = st.session_state.tema_activo

if tema_activo == "🍔 Blitz Neón":
    watermark_style = f"""
    .stApp::before {{
        content: "";
        position: fixed;
        top: 50%;
        left: 55%;
        transform: translate(-50%, -50%);
        width: 620px;
        height: 620px;
        background-image: url('data:image/jpeg;base64,{logo_b64}');
        background-size: contain;
        background-repeat: no-repeat;
        background-position: center;
        opacity: 0.07;
        pointer-events: none;
        z-index: 0;
        border-radius: 50%;
        filter: drop-shadow(0 0 50px rgba(255, 0, 85, 0.5));
    }}
    """ if logo_b64 else ""

    st.markdown(f"""
    <style>
        {watermark_style}
        /* Fondo más suave, carbón antracita */
        .stApp {{
            background-color: #141720 !important;
            color: #f1f5f9 !important;
        }}
        .blitz-title {{
            font-size: 2.2rem !important;
            font-weight: 900 !important;
            letter-spacing: 0.5px !important;
            color: #ffffff !important;
            text-transform: uppercase !important;
            margin: 0 !important;
            padding: 0 !important;
        }}
        .blitz-subtitle {{
            color: #ff0055 !important;
            font-weight: 700 !important;
            font-size: 0.95rem !important;
            letter-spacing: 1.5px !important;
            text-shadow: 0 0 12px rgba(255, 0, 85, 0.6) !important;
            margin: 2px 0 0 0 !important;
        }}
        .kpi-card {{
            background: linear-gradient(135deg, #1b202c 0%, #151924 100%);
            border: 1px solid #283244;
            border-left: 4px solid #ff0055 !important;
            border-radius: 10px;
            padding: 12px 16px;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
            margin-bottom: 12px;
            position: relative;
            z-index: 1;
        }}
        .kpi-title {{
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            color: #94a3b8;
            letter-spacing: 0.8px;
        }}
        .kpi-value {{
            font-size: 1.7rem;
            font-weight: 800;
            color: #ffffff;
            margin-top: 2px;
        }}
        div.stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, #ff0055 0%, #d60047 100%) !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 700 !important;
            box-shadow: 0 4px 15px rgba(255, 0, 85, 0.4) !important;
            transition: all 0.2s ease !important;
        }}
        div.stButton > button[kind="primary"]:hover {{
            transform: scale(1.02) !important;
            box-shadow: 0 6px 22px rgba(255, 0, 85, 0.75) !important;
        }}
        div.stButton > button:not([kind="primary"]) {{
            background-color: #1a202c !important;
            color: #e2e8f0 !important;
            border: 1px solid #2d3748 !important;
            border-radius: 8px !important;
        }}
        div.stButton > button:not([kind="primary"]):hover {{
            border-color: #ff0055 !important;
            color: #ff0055 !important;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 6px;
            border-bottom: 2px solid #252e3d;
        }}
        .stTabs [data-baseweb="tab"] {{
            background-color: #181d28;
            border-radius: 8px 8px 0 0;
            padding: 8px 16px;
            color: #94a3b8;
            font-weight: 600;
            border: 1px solid #252e3d;
            border-bottom: none;
        }}
        .stTabs [aria-selected="true"] {{
            background-color: #212837 !important;
            color: #ffffff !important;
            border-color: #ff0055 !important;
            box-shadow: 0 -2px 12px rgba(255, 0, 85, 0.35) !important;
        }}
        /* Subir encabezado blitzstock bien arriba reduciendo padding */
        [data-testid="stSidebarHeader"] {{
            height: 0 !important;
            min-height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            display: none !important;
        }}
        [data-testid="stSidebarContent"] {{
            padding-top: 0.8rem !important;
        }}
        [data-testid="stSidebarUserContent"] {{
            padding-top: 0.2rem !important;
        }}
        [data-testid="stSidebar"] {{
            background-color: #10131b !important;
            border-right: 1px solid #202735;
        }}
        /* Menú lateral vertical con más espacio y letras grandes */
        [data-testid="stSidebar"] [data-testid="stRadioGroup"],
        [data-testid="stSidebar"] div[role="radiogroup"] {{
            gap: 12px !important;
            display: flex !important;
            flex-direction: column !important;
            margin-top: 4px !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadioOption"],
        [data-testid="stSidebar"] div[role="radiogroup"] > label,
        [data-testid="stSidebar"] [data-testid="stRadioGroup"] > div {{
            padding: 10px 14px !important;
            border-radius: 9px !important;
            width: 100% !important;
            margin: 0 !important;
            margin-bottom: 5px !important;
            cursor: pointer !important;
            transition: all 0.18s ease-in-out !important;
            display: flex !important;
            align-items: center !important;
            min-height: 44px !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover,
        [data-testid="stSidebar"] div[role="radiogroup"] > label:hover,
        [data-testid="stSidebar"] [data-testid="stRadioGroup"] > div:hover {{
            background-color: rgba(255, 255, 255, 0.05) !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:checked),
        [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {{
            background-color: rgba(255, 0, 85, 0.15) !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] p,
        [data-testid="stSidebar"] [data-testid="stRadioGroup"] p,
        [data-testid="stSidebar"] [data-testid="stRadioOption"] p,
        [data-testid="stSidebar"] div[role="radiogroup"] p,
        [data-testid="stSidebar"] div[role="radiogroup"] span {{
            font-size: 0.985rem !important;
            line-height: 1.4 !important;
            letter-spacing: -0.2px !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:checked) p,
        [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {{
            color: #ff0055 !important;
            font-weight: 700 !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:not(:has(input:checked)) p,
        [data-testid="stSidebar"] div[role="radiogroup"] > label:not(:has(input:checked)) p {{
            color: #94a3b8 !important;
            font-weight: 500 !important;
        }}
    </style>
    """, unsafe_allow_html=True)
else:
    # 🏢 MODO OFICINA: INSPIRADO DIRECTAMENTE EN GRUBTECH / GRUBCENTER
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        html, body, [data-testid="stAppViewContainer"], .stApp, [data-testid="stSidebar"], .stMarkdown, p, h1, h2, h3, h4, h5, h6, input, select, textarea, div.stButton > button {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }
        /* Preservar la fuente de iconos nativa de Streamlit para que los desplegables y flechas no muestren texto _arrow_right */
        [data-testid="stIconMaterial"], [data-testid="stIcon"], [data-testid*="Chevron"], [data-testid*="Icon"] {
            font-family: "Material Symbols Rounded" !important;
        }
        .stApp {
            background-color: #f3f4f6 !important;
            color: #111827 !important;
        }
        .blitz-title {
            font-size: 1.85rem !important;
            font-weight: 800 !important;
            color: #111827 !important;
            letter-spacing: -0.5px !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .blitz-subtitle {
            color: #0066ff !important;
            font-weight: 600 !important;
            font-size: 0.85rem !important;
            letter-spacing: 0.5px !important;
            margin: 2px 0 0 0 !important;
        }
        .kpi-card {
            background: #ffffff !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 8px !important;
            padding: 14px 18px !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05), 0 1px 2px rgba(0, 0, 0, 0.03) !important;
            margin-bottom: 12px !important;
        }
        .kpi-title {
            font-size: 0.75rem !important;
            font-weight: 600 !important;
            text-transform: uppercase !important;
            color: #6b7280 !important;
            letter-spacing: 0.5px !important;
        }
        .kpi-value {
            font-size: 1.65rem !important;
            font-weight: 700 !important;
            color: #111827 !important;
            margin-top: 4px !important;
        }
        div.stButton > button[kind="primary"] {
            background-color: #0066ff !important;
            color: #ffffff !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
            border: none !important;
            padding: 8px 16px !important;
            box-shadow: 0 1px 2px rgba(0, 102, 255, 0.2) !important;
            transition: all 0.15s ease-in-out !important;
        }
        div.stButton > button[kind="primary"]:hover {
            background-color: #0052cc !important;
            box-shadow: 0 4px 10px rgba(0, 102, 255, 0.3) !important;
        }
        div.stButton > button:not([kind="primary"]) {
            background-color: #ffffff !important;
            color: #374151 !important;
            border: 1px solid #d1d5db !important;
            border-radius: 6px !important;
            font-weight: 500 !important;
        }
        div.stButton > button:not([kind="primary"]):hover {
            background-color: #f9fafb !important;
            border-color: #9ca3af !important;
            color: #111827 !important;
        }
        /* Subir encabezado blitzstock bien arriba reduciendo padding del sidebar */
        [data-testid="stSidebarHeader"] {
            height: 0 !important;
            min-height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            display: none !important;
        }
        [data-testid="stSidebarContent"] {
            padding-top: 0.8rem !important;
        }
        [data-testid="stSidebarUserContent"] {
            padding-top: 0.2rem !important;
        }
        [data-testid="stSidebar"] {
            background-color: #ffffff !important;
            border-right: 1px solid #e5e7eb !important;
        }

        /* Menú lateral vertical GrubCenter: espaciado generoso a lo alto sin apelotonamiento */
        [data-testid="stSidebar"] [data-testid="stRadioGroup"],
        [data-testid="stSidebar"] div[role="radiogroup"] {
            gap: 12px !important;
            display: flex !important;
            flex-direction: column !important;
            margin-top: 4px !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadioOption"],
        [data-testid="stSidebar"] div[role="radiogroup"] > label,
        [data-testid="stSidebar"] [data-testid="stRadioGroup"] > div {
            padding: 10px 14px !important;
            border-radius: 9px !important;
            width: 100% !important;
            margin: 0 !important;
            margin-bottom: 5px !important;
            cursor: pointer !important;
            transition: all 0.18s ease-in-out !important;
            display: flex !important;
            align-items: center !important;
            background-color: transparent !important;
            min-height: 44px !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover,
        [data-testid="stSidebar"] div[role="radiogroup"] > label:hover,
        [data-testid="stSidebar"] [data-testid="stRadioGroup"] > div:hover {
            background-color: #f3f4f6 !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:checked),
        [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked),
        [data-testid="stSidebar"] [data-testid="stRadioOption"][aria-checked="true"] {
            background-color: #e8f0fe !important;
        }

        /* Tipografía de las opciones: TAMAÑO AJUSTADO JUSTO POR ENCIMA DEL ORIGINAL */
        [data-testid="stSidebar"] [data-testid="stRadio"] p,
        [data-testid="stSidebar"] [data-testid="stRadioGroup"] p,
        [data-testid="stSidebar"] [data-testid="stRadioOption"] p,
        [data-testid="stSidebar"] div[role="radiogroup"] p,
        [data-testid="stSidebar"] div[role="radiogroup"] span {
            font-size: 0.985rem !important;
            line-height: 1.4 !important;
            letter-spacing: -0.2px !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:checked) p,
        [data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p,
        [data-testid="stSidebar"] [data-testid="stRadioOption"][aria-checked="true"] p {
            color: #0066ff !important;
            font-weight: 700 !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:not(:has(input:checked)) p,
        [data-testid="stSidebar"] div[role="radiogroup"] > label:not(:has(input:checked)) p {
            color: #1f2937 !important;
            font-weight: 500 !important;
        }
        [data-testid="stDataFrame"] {
            border: 1px solid #e5e7eb !important;
            border-radius: 8px !important;
            background: #ffffff !important;
        }
    </style>
    """, unsafe_allow_html=True)

# Encabezado con Logo Oficial
col_head_logo, col_head_txt = st.columns([1, 11])
with col_head_logo:
    ruta_logo_ico = os.path.join(BASE_DIR, "blitz_logo.jpg")
    if os.path.isfile(ruta_logo_ico):
        st.image(ruta_logo_ico, width=72)
with col_head_txt:
    st.markdown('<h1 class="blitz-title">BLITZ STOCK</h1>', unsafe_allow_html=True)
    st.markdown('<p class="blitz-subtitle">CENTRO DE MANDO &bull; CONTROL DE INVENTARIO Y ESCANDALLOS</p>', unsafe_allow_html=True)

if "ia_procesada" not in st.session_state:
    st.session_state.ia_procesada = False
if "articulos_ia" not in st.session_state:
    st.session_state.articulos_ia = []
if "proveedor_ia" not in st.session_state:
    st.session_state.proveedor_ia = ""
if "archivo_actual" not in st.session_state:
    st.session_state.archivo_actual = None
if "centro_destino" not in st.session_state:
    st.session_state.centro_destino = ""

# ==========================================
# SECCIÓN: CONTENIDO PRINCIPAL POR MENÚ LATERAL
# ==========================================
if seccion_activa == "📡 Radar de Albaranes":
    # Métricas Dinámicas (KPIs) - Visibles exclusivamente en Radar de Albaranes
    total_albaranes = 0
    for carpeta in CARPETAS_ENTRADA:
        if os.path.exists(carpeta):
            for f in os.listdir(carpeta):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    total_albaranes += 1

    total_recetas = 0
    if os.path.isfile(ARCHIVO_RECETAS):
        try:
            df_r_kpi = pd.read_csv(ARCHIVO_RECETAS, encoding='utf-8-sig')
            total_recetas = len(df_r_kpi["Plato"].dropna().unique())
        except Exception:
            pass

    total_maestros = 0
    if os.path.isfile(ARCHIVO_EQUIVALENCIAS):
        try:
            df_e_kpi = pd.read_csv(ARCHIVO_EQUIVALENCIAS, encoding='utf-8-sig')
            total_maestros = len(df_e_kpi["Producto_Maestro_Blitz"].dropna().unique())
        except Exception:
            pass

    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    col_k1.markdown(f'<div class="kpi-card"><div class="kpi-title">📥 Albaranes en Cola</div><div class="kpi-value">{total_albaranes}</div></div>', unsafe_allow_html=True)
    col_k2.markdown(f'<div class="kpi-card"><div class="kpi-title">🍔 Platos en Carta</div><div class="kpi-value">{total_recetas}</div></div>', unsafe_allow_html=True)
    col_k3.markdown(f'<div class="kpi-card"><div class="kpi-title">📚 Artículos Diccionario</div><div class="kpi-value">{total_maestros}</div></div>', unsafe_allow_html=True)
    col_k4.markdown(f'<div class="kpi-card"><div class="kpi-title">⚡ Motor IA Vision</div><div class="kpi-value" style="color:#10b981;font-size:1.4rem;margin-top:6px;">ACTIVO (v3.8)</div></div>', unsafe_allow_html=True)
    st.write("")

    archivos_en_cola = []
    for carpeta in CARPETAS_ENTRADA:
        if os.path.exists(carpeta):
            for f in sorted(os.listdir(carpeta)):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    archivos_en_cola.append((carpeta, f))
    
    if len(archivos_en_cola) == 0:
        st.info("Bandeja limpia. Esperando nuevos albaranes...")
    else:
        carpeta_origen, archivo_actual = archivos_en_cola[0]
        ruta_origen = os.path.join(carpeta_origen, archivo_actual)
        
        st.warning(f"Tienes {len(archivos_en_cola)} albarán(es) pendiente(s).")
        
        if st.session_state.archivo_actual != ruta_origen:
            st.session_state.ia_procesada = False
            st.session_state.articulos_ia = []
            st.session_state.proveedor_ia = ""
            st.session_state.centro_destino = ""
            st.session_state.archivo_actual = ruta_origen

        col_foto, col_datos = st.columns([1, 2])
        with col_foto:
            st.image(ruta_origen, caption=f"En cola: {archivo_actual}", use_container_width=True)
            
        with col_datos:
            centros_blitz = [
                "Blitz  Juan de Borbón", 
                "Blitz Ronda Sur", 
                "Food Truck Grande", 
                "Food Truck Pequeña"
            ]
            
            # 🛡️ Detectar centro automáticamente desde la carpeta de origen
            carpeta_norm = os.path.normpath(carpeta_origen)
            if "Entrada_Ronda_Sur" in carpeta_norm or "Ronda_Sur" in carpeta_norm:
                idx_centro = 1
            elif "Entrada_FoodTruck_1" in carpeta_norm or "FoodTruck_1" in carpeta_norm:
                idx_centro = 2
            elif "Entrada_FoodTruck_2" in carpeta_norm or "FoodTruck_2" in carpeta_norm:
                idx_centro = 3
            elif "Entrada_Juan_Borbon" in carpeta_norm or "Juan_Borbon" in carpeta_norm:
                idx_centro = 0
            else:
                idx_centro = 0
                
            centro_seleccionado = st.selectbox(
                "📍 Centro de Recepción (Autodetectado por carpeta):", 
                centros_blitz, 
                index=idx_centro,
                key=f"centro_{archivo_actual}"
            )
            st.session_state.centro_destino = centro_seleccionado
            st.info(f"📁 Origen del escaneo: **{carpeta_origen}**")

            
            clave_activa_check = obtener_api_key_gemini()
            if not clave_activa_check:
                st.error("🔑 **Falta configurar la clave API de Google Gemini (Google AI Studio)**")
                st.markdown("""
                Para leer albaranes con Inteligencia Artificial se requiere una clave gratuita de **Google AI Studio** (empieza siempre por `AIzaSy...`).
                
                👉 **[Consigue tu clave gratis en 15 segundos aquí](https://aistudio.google.com/app/apikey)** (Inicia sesión con tu cuenta de Google y pulsa *Create API key*).
                """)
                c_k1, c_k2 = st.columns([3, 1])
                with c_k1:
                    k_input = st.text_input("Pega tu API Key de Gemini aquí:", type="password", placeholder="AIzaSy...", label_visibility="collapsed", key=f"input_k_{archivo_actual}")
                with c_k2:
                    if st.button("💾 Guardar Clave", key=f"btn_save_k_{archivo_actual}", use_container_width=True):
                        if len(k_input.strip()) >= 15:
                            st.session_state.gemini_api_key = k_input.strip()
                            try:
                                sec_file = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
                                os.makedirs(os.path.dirname(sec_file), exist_ok=True)
                                txt = ""
                                if os.path.exists(sec_file):
                                    with open(sec_file, "r", encoding="utf-8") as sf:
                                        txt = sf.read()
                                lines = [l for l in txt.splitlines() if not l.startswith("GEMINI_API_KEY")]
                                lines.append(f'GEMINI_API_KEY = "{k_input.strip()}"')
                                with open(sec_file, "w", encoding="utf-8") as sf:
                                    sf.write("\n".join(lines) + "\n")
                            except Exception:
                                pass
                            st.success("✅ ¡Clave guardada con éxito!")
                            st.rerun()
                        else:
                            st.error("Por favor, introduce una clave API válida de Google.")

            if st.button("🧠 Procesar con Inteligencia Artificial", type="primary"):
                st.session_state.centro_destino = centro_seleccionado
                with st.spinner('Analizando documento con Visión Artificial...'):
                    try:
                        clave_activa = obtener_api_key_gemini()
                        if not clave_activa:
                            raise ValueError("Clave API de Google no configurada.")

                        cliente_ia_activo = genai.Client(api_key=clave_activa)
                        img = Image.open(ruta_origen)
                        img.thumbnail((1500, 1500))
                        
                        prompt_estricto = """
                        Eres un OCR experto de facturas y albaranes de hostelería. Lee este documento con máxima precisión.
                        Reglas de extracción obligatorias:
                        1. Ignora líneas de agrupaciones o categorías. Solo extrae productos reales.
                        2. Si la cantidad tiene formato '12/12' extrae el segundo número.
                        3. Extrae la unidad exacta (ej. CAJA, BOTE, KG, etc.).
                        4. Prohibido traducir los nombres de los productos.
                        5. REGLA DE PRECIO Y DESCUENTO: Extrae SIEMPRE el PRECIO UNITARIO NETO por envase/caja. Si la línea tiene columna de descuento en porcentaje (DTO %) o descuento en euros (DTO €), APLICA SIEMPRE EL DESCUENTO AL PRECIO UNITARIO: si es DTO %, precio_final = precio * (1 - dto/100); si es DTO € (descuento en euros), resta el descuento al precio: precio_final = precio - dto_euros (ejemplo: si Precio es 12.25 y Dto € es 0.90, el precio_final neto es 11.35). Pon siempre el precio unitario neto resultante.
                        6. REGLA DE PESO Y UNIDADES: Si un artículo está facturado por peso (la columna de cantidad son kilos, ej. "58.8" o "58.8 KG" a un precio por kilo como 11.50 €), extrae la unidad "KG" y cantidad exacta de kilos (58.8). NO pongas unidad "CAJA" si la cantidad son kilos (58.8 kilos no son 58.8 cajas). Solo si la línea indica explícitamente el número de bultos/cajas facturadas (ej. "6 CAJAS"), pon "CAJA".
                        7. REGLA DE LÍNEAS DE REGALO / PROMOCIONES: Si un albarán tiene líneas del mismo producto con precio 0.00 € (ej. regalo, promoción 10+1), extráelas también con su cantidad real y precio 0.00.
                        8. REGLA DE COMPROBACIÓN MATEMÁTICA Y LEGIBILIDAD (DOBLE CHECK OBLIGATORIO): En albaranes con impresión matricial, números poco nítidos o tinta tenue (como albaranes de MORALES, Hermanos Morales, tickets de caja, etc.), verifica SIEMPRE matemáticamente con las columnas de Importe: precio_final = importe_linea / cantidad (o precio x cantidad = importe). Si el número impreso es ambiguo (por ejemplo parece 4.05 pero 12 x 4.50 = 54.00), usa SIEMPRE el precio matemáticamente coherente con el importe total (4.50).
                        9. REGLA DE CONTEXTO DE HAMBURGUESERÍA (NUNCA SALMÓN): Este negocio es una hamburguesería gourmet (Blitz Burger). En albaranes de charcutería/embutidos (como MORALES, etc.) donde aparezca una palabra cortada o poco nítida en el margen izquierdo como '[...]ON AHUMADO LONCHAS' o '...N AHUMADO LONCHAS' (a precio ~4.50 €/kg), se trata SIEMPRE de 'BACON AHUMADO LONCHAS', JAMÁS de salmón. El salmón no se utiliza en hamburguesería y tiene un precio muy superior.
                        
                        Devuelve ÚNICAMENTE un bloque JSON. Prohibido texto explicativo. Formato:
                        {
                            "proveedor": "Nombre del proveedor",
                            "articulos": [
                                {"nombre": "Producto Ejemplo", "cantidad": 1.0, "unidad": "CAJA", "precio_final": 4.75}
                            ]
                        }
                        """
                        
                        import time
                        # Cadena de modelos de máxima resiliencia ante picos de demanda (503 / 429)
                        modelos_a_probar = ['gemini-3.5-flash-lite', 'gemini-3.5-flash', 'gemini-flash-latest', 'gemini-3.8-flash']
                        respuesta = None
                        ultimo_error = None
                        
                        for mod in modelos_a_probar:
                            for intento in range(2):
                                try:
                                    respuesta = cliente_ia_activo.models.generate_content(
                                        model=mod,
                                        contents=[prompt_estricto, img]
                                    )
                                    if respuesta and respuesta.text:
                                        break
                                except Exception as api_error:
                                    ultimo_error = api_error
                                    err_msg = str(api_error).lower()
                                    # Si la cuota diaria está agotada (429/quota), saltar de inmediato al siguiente modelo
                                    if any(s in err_msg for s in ['429', 'resourceexhausted', 'quota']):
                                        break
                                    # Si es pico de saturación temporal (503/demand), esperar y reintentar
                                    if any(s in err_msg for s in ['503', 'unavailable', 'demand']) and intento == 0:
                                        time.sleep(1.5)
                                        continue
                                    break
                            if respuesta and respuesta.text:
                                break
                                
                        if not respuesta or not respuesta.text:
                            if ultimo_error:
                                raise ultimo_error
                            raise ValueError("Respuesta vacía de la IA.")
                            
                        match = re.search(r'\{.*\}', respuesta.text, re.DOTALL)
                        if not match:
                            raise ValueError(f"No se encontró un JSON válido. Respuesta cruda: {respuesta.text}")
                            
                        datos_ia = json.loads(match.group(0))
                        prov_crudo = datos_ia.get("proveedor", "Desconocido")
                        prov_canonico = normalizar_proveedor(prov_crudo)
                        st.session_state.proveedor_ia = prov_canonico
                        
                        # CÁLCULO INTELIGENTE DE PROMOCIONES CIELO DE BOCA (OK)
                        articulos_crudos = datos_ia.get("articulos", [])
                        prov_nombre = str(prov_canonico).upper()
                        
                        articulos_procesados = procesar_articulos_albaran_ia(articulos_crudos, prov_nombre)
                        articulos_vistos = {}
                        
                        if False:  # Sustituido por procesar_articulos_albaran_ia
                            nombre_norm = normalizar_texto(art.get("nombre", ""))
                            try: cant_val = float(art.get("cantidad", 0.0))
                            except: cant_val = 0.0
                            try: p_val = float(art.get("precio_final", 0.0))
                            except: p_val = 0.0
                            ud_val = art.get("unidad", "CAJA")
                            
                            es_cielo_pan = ("CIELO" in prov_nombre or "BOCA" in prov_nombre) and ("POTATO" in nombre_norm or "PAN" in nombre_norm)
                            
                            if nombre_norm in articulos_vistos:
                                # Fusionar líneas repetidas (ej. 30 cajas pagadas + 3 de regalo a 0€)
                                prev = articulos_vistos[nombre_norm]
                                cant_total = prev["cantidad"] + cant_val
                                dinero_total = (prev["cantidad"] * prev["precio_final"]) + (cant_val * p_val)
                                p_medio = round(dinero_total / cant_total, 2) if cant_total > 0 else 0.0
                                
                                prev["cantidad"] = cant_total
                                prev["precio_final"] = p_medio
                            else:
                                if es_cielo_pan and cant_val >= 10 and p_val > 0:
                                    cajas_regalo = int(cant_val // 10)
                                    cant_total = cant_val + cajas_regalo
                                    p_efectivo = round((cant_val * p_val) / cant_total, 2)
                                    art_dict = {
                                        "nombre": art.get("nombre", ""),
                                        "cantidad": cant_total,
                                        "unidad": ud_val,
                                        "precio_final": p_efectivo
                                    }
                                else:
                                    art_dict = {
                                        "nombre": art.get("nombre", ""),
                                        "cantidad": cant_val,
                                        "unidad": ud_val,
                                        "precio_final": p_val
                                    }
                                articulos_vistos[nombre_norm] = art_dict
                                articulos_procesados.append(art_dict)
                                
                        st.session_state.articulos_ia = articulos_procesados
                        st.session_state.ia_procesada = True
                        
                    except Exception as e:
                        err_str = str(e)
                        if any(s in err_str.lower() for s in ['503', 'unavailable', 'demand', 'high demand']):
                            st.error("⚠️ **Los servidores de Google Gemini están experimentando un pico temporal de saturación (Error 503).**")
                            st.info("💡 Este aviso es momentáneo debido a sobrecarga en los servidores mundiales de Google. Simplemente espera 5-10 segundos y vuelve a pulsar **🧠 Procesar con Inteligencia Artificial**.")
                        elif any(s in err_str.lower() for s in ['401', 'unauthenticated', 'access_token_type_unsupported', 'api key not valid']):
                            st.error("🛑 **DIAGNÓSTICO DE ERROR: 401 UNAUTHENTICATED (Clave rechazada por Google).**")
                            st.warning("Google ha rechazado la clave configurada (`ACCESS_TOKEN_TYPE_UNSUPPORTED`). La clave debe ser una API Key oficial de **Google AI Studio** que empiece por **`AIzaSy...`**.")
                            st.info("👉 Puedes generar tu clave gratuita en 15 segundos en: [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)")
                        else:
                            st.error(f"🛑 DIAGNÓSTICO DE ERROR: {err_str}")
                        st.session_state.ia_procesada = False

            # ==========================================
            # 4. RED DE SEGURIDAD (HUMAN-IN-THE-LOOP)
            # ==========================================
            if st.session_state.ia_procesada:
                st.divider()
                st.subheader(f"🏢 Proveedor: **{st.session_state.proveedor_ia}** ➔ 📍 Destino: **{st.session_state.centro_destino}**")
                
                diccionario_eq, indice_norm = cargar_equivalencias()
                formatos_unidades = ["KG", "BANDEJAS", "BOLSAS", "BOTELLAS", "ESTUCHE", "BOTE", "GARRAFA", "ROLLOS", "UNIDADES", "CAJAS"]
                
                for i, articulo in enumerate(st.session_state.articulos_ia):
                    prod = str(articulo.get("nombre", ""))
                    cant = str(articulo.get("cantidad", "0"))
                    ud_leida = str(articulo.get("unidad", "KG")).upper()
                    precio_detectado = float(articulo.get("precio_final", 0.0))
                    
                    prov_key = st.session_state.proveedor_ia.strip().lower()
                    prod_key = prod.strip().lower()
                    
                    st.write(f"📦 **Extraído:** {cant} *{prod}* - Precio leído: **{precio_detectado:.2f} €**")
                    
                    eq_info, encontrado = buscar_equivalencia(diccionario_eq, indice_norm, prov_key, prod_key, ud_leida, precio_detectado)
                    if encontrado:
                        try:
                            cant_float = float(cant) if float(cant) > 0 else 1.0
                            m_nombre = eq_info.get("producto_maestro", "").strip().upper()
                            ref_str = f"[{eq_info['referencia']}] " if eq_info.get('referencia') else ""
                            uinv = str(eq_info.get("unidad_inv", "KG")).strip().upper()
                            factor = float(eq_info.get("factor", 1.0)) if float(eq_info.get("factor", 1.0)) > 0 else 1.0
                            precio_guardado = float(eq_info.get("precio_actual", 0.0))
                            rendimiento = float(eq_info.get("rendimiento", 1.0) or 1.0)
                            urec = str(eq_info.get("unidad_receta", "")).strip().upper()
                            
                            # 1. IDENTIFICACIÓN Y VARIANTES DEL PRODUCTO
                            variantes = eq_info.get("variantes", [eq_info])
                            p_kilo_guardado = None
                            p_envase_guardado = None
                            factor_kg = None
                            
                            for v in variantes:
                                u_c = str(v.get("unidad_compra", "")).strip().upper()
                                f_v = float(v.get("factor", 1.0))
                                p_v = float(v.get("precio_actual", 0.0))
                                if u_c in ["KG", "KGS", "KILO", "KILOS"]:
                                    if f_v > 0 and f_v != 1.0:
                                        factor_kg = f_v
                                    if p_v > 0.0:
                                        p_kilo_guardado = p_v
                                elif float(v.get("factor", 1.0)) == 1.0 or u_c == uinv:
                                    if p_v > 0.0:
                                        p_envase_guardado = p_v
                                        
                            # 2. DETERMINAR SI ES PRODUCTO DE PESO/KILO (kilos_por_uinv)
                            # Las unidades discretas (botes, botellas, garrafas, tarrinas, bolsas, bandejas, etc.) se gestionan por unidades físicas exactas
                            UNIDADES_DISCRETAS_ESTRICTAS = ["BOTE", "BOTES", "BOTELLAS", "BOTELLA", "GARRAFA", "GARRAFAS", "ROLLOS", "ESTUCHE", "UNIDADES", "PACK", "CUBO", "TARRINA", "TARRINAS", "FRASCO", "FRASCOS", "BANDEJA", "BANDEJAS", "BRIK", "PAQUETES", "PQ"]
                            
                            kilos_por_uinv = None
                            if uinv in UNIDADES_DISCRETAS_ESTRICTAS:
                                es_producto_peso = False
                            elif uinv in ["KG", "KGS", "KILO", "KILOS"]:
                                kilos_por_uinv = 1.0
                                es_producto_peso = True
                            elif factor_kg is not None and factor_kg > 0:
                                kilos_por_uinv = round(1.0 / factor_kg, 4)
                                es_producto_peso = True
                            elif m_nombre in ["BONIATO", "PATATAS FRITAS"]:
                                kilos_por_uinv = 2.5
                                es_producto_peso = True
                            elif m_nombre in ["BACON DADOS", "CEBOLLA CRISPY"]:
                                kilos_por_uinv = 2.0
                                es_producto_peso = True
                            elif m_nombre in ["CARNE BURGUER 90 GRS", "CARNE BURGUER"]:
                                kilos_por_uinv = 9.54
                                es_producto_peso = True
                            elif m_nombre in ["NUGGETS POLLO", "NUGGETS"]:
                                kilos_por_uinv = 4.5
                                es_producto_peso = True
                            elif ud_leida in ["KG", "KGS", "KILO", "KILOS"] and uinv in ["CAJAS", "CAJA", "BOLSAS", "BOLSA"]:
                                if urec == "GRS" and rendimiento > 0:
                                    kilos_por_uinv = rendimiento / 1000.0
                                elif urec in ["KG", "KGS", "KILO", "KILOS"] and rendimiento > 0:
                                    kilos_por_uinv = rendimiento
                                es_producto_peso = (kilos_por_uinv is not None and kilos_por_uinv > 0)
                            else:
                                es_producto_peso = False
                                
                            if es_producto_peso and kilos_por_uinv and p_kilo_guardado and not p_envase_guardado:
                                p_envase_guardado = round(p_kilo_guardado * kilos_por_uinv, 2)
                            elif es_producto_peso and kilos_por_uinv and p_envase_guardado and not p_kilo_guardado:
                                p_kilo_guardado = round(p_envase_guardado / kilos_por_uinv, 2)
                            
                            # =========================================================================
                            # [BLOQUE PROTEGIDO]: CONVERSIÓN DE KILOS A CAJAS/BOLSAS Y PRECIOS HOMOGÉNEOS
                            # ESTA LÓGICA ESTÁ BLINDADA: NO MODIFICAR SIN PERMISO EXPLÍCITO DEL USUARIO
                            # =========================================================================
                            if es_producto_peso and kilos_por_uinv and kilos_por_uinv != 1.0:
                                # Comprobar matemáticamente si la línea viene facturada en KILOS o en CAJAS/BOLSAS
                                if p_kilo_guardado and p_envase_guardado and p_kilo_guardado > 0 and p_envase_guardado > 0 and p_envase_guardado != p_kilo_guardado:
                                    diff_kilo = abs(precio_detectado - p_kilo_guardado)
                                    diff_envase = abs(precio_detectado - p_envase_guardado)
                                    linea_en_kilos = (diff_kilo < diff_envase) or (ud_leida in ["KG", "KGS", "KILO", "KILOS"])
                                else:
                                    linea_en_kilos = (ud_leida in ["KG", "KGS", "KILO", "KILOS"]) or \
                                                     (p_kilo_guardado and abs(precio_detectado - p_kilo_guardado) <= 0.5) or \
                                                     (cant_float > (kilos_por_uinv * 2.0) and precio_detectado < (p_envase_guardado or 999.0) / 2.0)
                                                     
                                if linea_en_kilos:
                                    # FACTURADO POR KILO (ej. 58.8 KG a 11.50 €/kg -> 6 cajas a 109.71 €)
                                    precio_kilo_albaran = round(precio_detectado, 2)
                                    precio_unitario_real = round(precio_kilo_albaran * kilos_por_uinv, 2)
                                    val_calc = cant_float / kilos_por_uinv
                                else:
                                    # FACTURADO POR ENVASE/CAJA (ej. 6 CAJAS a 109.71 €/caja)
                                    if factor > 1.0 and ud_leida in ["CAJA", "CAJAS", "BULTO", "BULTOS"] and precio_detectado > ((p_envase_guardado or 0) * 1.5):
                                        precio_unitario_real = round(precio_detectado / factor, 2)
                                    else:
                                        precio_unitario_real = round(precio_detectado, 2)
                                    precio_kilo_albaran = round(precio_unitario_real / kilos_por_uinv, 2)
                                    val_calc = cant_float * factor
                                    
                                unidades_discretas = ["CAJAS", "BANDEJAS", "BOLSAS", "BOTELLAS", "ESTUCHE", "BOTE", "GARRAFA", "ROLLOS", "UNIDADES"]
                                if uinv in unidades_discretas:
                                    val_calc = int(round(val_calc))
                                else:
                                    val_calc = round(val_calc, 2)
                                    
                                precio_kilo_dict = p_kilo_guardado if p_kilo_guardado is not None else 0.0
                                precio_envase_dict = p_envase_guardado if p_envase_guardado is not None else precio_guardado
                                
                                articulo["val_calc_final"] = val_calc
                                articulo["precio_unitario_final"] = precio_unitario_real
                                
                                st.success(f"✅ Mapeado a **{ref_str}{eq_info['producto_maestro']}** ({val_calc} {eq_info['unidad_inv']}) • Precio: **{precio_kilo_albaran:.2f} €/KG** ({precio_unitario_real:.2f} €/{eq_info['unidad_inv']})")
                                
                                # Comparar SIEMPRE por PRECIO KILO
                                if precio_kilo_albaran > 0.0 and precio_kilo_dict > 0.0 and abs(precio_kilo_albaran - precio_kilo_dict) > 0.02:
                                    st.warning(
                                        f"⚠️ **PRECIO DISTINTO AL DEL DICCIONARIO**\n\n"
                                        f"• **Precio en Diccionario:** {precio_kilo_dict:.2f} €/KG ({precio_envase_dict:.2f} €/{eq_info['unidad_inv']})\n\n"
                                        f"• **Precio en este Albarán:** {precio_kilo_albaran:.2f} €/KG ({precio_unitario_real:.2f} €/{eq_info['unidad_inv']})"
                                    )
                                    col_p1, col_p2 = st.columns([1, 1])
                                    if col_p1.button(f"🔄 Actualizar Diccionario ({precio_kilo_albaran:.2f} €/KG • {precio_unitario_real:.2f} €/{eq_info['unidad_inv']})", key=f"btn_act_p_{i}"):
                                        actualizar_precio_en_csv(
                                            st.session_state.proveedor_ia, 
                                            eq_info.get("sinonimo_orig", prod), 
                                            precio_unitario_real, 
                                            referencia=eq_info.get("referencia", ""),
                                            precio_kilo=precio_kilo_albaran
                                        )
                                        st.success(f"✅ Precio del diccionario actualizado a {precio_kilo_albaran:.2f} €/KG ({precio_unitario_real:.2f} €/{eq_info['unidad_inv']}).")
                                        import time; time.sleep(0.6)
                                        st.rerun()
                                    if col_p2.button(f"❌ Ignorar (Compra puntual / Mantener {precio_kilo_dict:.2f} €/KG)", key=f"btn_ign_p_{i}"):
                                        st.info("ℹ️ Precio del diccionario mantenido sin cambios.")
                                elif precio_kilo_dict == 0.0 and precio_kilo_albaran > 0.0:
                                    actualizar_precio_en_csv(
                                        st.session_state.proveedor_ia, 
                                        eq_info.get("sinonimo_orig", prod), 
                                        precio_unitario_real, 
                                        referencia=eq_info.get("referencia", ""),
                                        precio_kilo=precio_kilo_albaran
                                    )
                                    st.info(f"💾 Precio inicial de {precio_kilo_albaran:.2f} €/KG ({precio_unitario_real:.2f} €/{eq_info['unidad_inv']}) guardado.")
                            else:
                                # PRODUCTOS DISCRETOS O NO PESADOS (LITROS, ROLLOS, BANDEJAS, UNIDADES, ETC.)
                                if uinv in ["KG", "L", "LITROS", "LITRO"]:
                                    es_directa = (uinv == "KG" and ud_leida in ["KG", "KGS", "KILO", "KILOS"]) or \
                                                 (uinv in ["L", "LITROS", "LITRO"] and ud_leida in ["L", "LTS", "LITRO", "LITROS"])
                                    val_calc = round(cant_float if es_directa else cant_float * factor, 2)
                                else:
                                    val_calc = cant_float * factor
                                    unidades_discretas = ["CAJAS", "BANDEJAS", "BOLSAS", "BOTELLAS", "ESTUCHE", "BOTE", "GARRAFA", "ROLLOS", "UNIDADES", "TARRINA", "TARRINAS", "FRASCO", "FRASCOS", "CUBO", "BRIK", "PAQUETES", "PQ"]
                                    if uinv in unidades_discretas:
                                        val_calc = int(round(val_calc))
                                    else:
                                        val_calc = round(val_calc, 2)
                                if factor > 1.0:
                                    cand_directo = precio_detectado
                                    cand_envase = precio_detectado / factor
                                    cand_total = precio_detectado / (cant_float * factor) if cant_float > 0 else cand_envase
                                    
                                    if precio_guardado > 0.0:
                                        diff_directo = abs(cand_directo - precio_guardado)
                                        diff_envase = abs(cand_envase - precio_guardado)
                                        diff_total = abs(cand_total - precio_guardado) if cant_float > 1.0 else 999999.0
                                        
                                        min_diff = min(diff_directo, diff_envase, diff_total)
                                        if min_diff == diff_envase:
                                            precio_unitario_real = round(cand_envase, 2)
                                        elif min_diff == diff_directo:
                                            precio_unitario_real = round(cand_directo, 2)
                                        else:
                                            precio_unitario_real = round(cand_total, 2)
                                    else:
                                        if ud_leida in ["CAJA", "CAJAS", "BULTOS", "GARRAFA", "PACK", "ESTUCHE"]:
                                            precio_unitario_real = round(cand_envase, 2)
                                        else:
                                            precio_unitario_real = round(cand_directo, 2)
                                else:
                                    precio_unitario_real = round(precio_detectado, 2)
                                        
                                articulo["val_calc_final"] = val_calc
                                articulo["precio_unitario_final"] = precio_unitario_real
                                    
                                st.success(f"✅ Mapeado a **{ref_str}{eq_info['producto_maestro']}** ({val_calc} {eq_info['unidad_inv']}) • Precio: **{precio_unitario_real:.2f} €/{eq_info['unidad_inv']}**")
                                
                                if precio_unitario_real > 0.0 and abs(precio_unitario_real - precio_guardado) > 0.01:
                                    if precio_guardado > 0.0:
                                        st.warning(
                                            f"⚠️ **PRECIO DISTINTO AL DEL DICCIONARIO**\n\n"
                                            f"• **Precio en Diccionario:** {precio_guardado:.2f} €/{eq_info['unidad_inv']}\n\n"
                                            f"• **Precio en este Albarán:** {precio_unitario_real:.2f} €/{eq_info['unidad_inv']}"
                                        )
                                        col_p1, col_p2 = st.columns([1, 1])
                                        if col_p1.button(f"🔄 Actualizar Diccionario ({precio_unitario_real:.2f} €)", key=f"btn_act_p_{i}"):
                                            actualizar_precio_en_csv(
                                                st.session_state.proveedor_ia, 
                                                eq_info.get("sinonimo_orig", prod), 
                                                precio_unitario_real, 
                                                referencia=eq_info.get("referencia", "")
                                            )
                                            st.success(f"✅ Precio del diccionario actualizado a {precio_unitario_real:.2f} €/{eq_info['unidad_inv']}.")
                                            import time; time.sleep(0.6)
                                            st.rerun()
                                        if col_p2.button(f"❌ Ignorar (Compra puntual / Mantener {precio_guardado:.2f} €)", key=f"btn_ign_p_{i}"):
                                            st.info("ℹ️ Precio del diccionario mantenido sin cambios.")
                                    else:
                                        # Primer registro del precio
                                        actualizar_precio_en_csv(
                                            st.session_state.proveedor_ia, 
                                            eq_info.get("sinonimo_orig", prod), 
                                            precio_unitario_real, 
                                            referencia=eq_info.get("referencia", "")
                                        )
                                        st.info(f"💾 Precio inicial de {precio_unitario_real:.2f}€/{eq_info['unidad_inv']} guardado.")
                                    
                        except ValueError:
                            st.error("Error matemático en la cantidad.")
                    else:
                        st.warning(f"🛑 ALERTA: Producto nuevo detectado en albarán.")
                        
                        # Extraer lista de productos maestros ya existentes en el diccionario
                        maestros_unicos = {}
                        for data in diccionario_eq.values():
                            m = data.get("producto_maestro", "").strip()
                            r = data.get("referencia", "").strip()
                            if m:
                                maestros_unicos[m] = r
                                
                        opciones = ["➕ Crear Producto Completamente Nuevo"] + sorted(list(maestros_unicos.keys()))
                        
                        c_sel, c_ref, c_fact, c_uni = st.columns([2, 1, 1, 1])
                        
                        busqueda = c_sel.text_input(f"🔍 Escribe para Buscar o Crear (y pulsa Enter):", key=f"busq_{i}", help="Escribe el nombre. Si no existe, se preparará como nuevo automáticamente.")
                        
                        es_nuevo = False
                        maestro_final = ""
                        ref_final = ""
                        
                        if busqueda:
                            busqueda_limpia = busqueda.strip().upper()
                            coincidencias = [m for m in maestros_unicos.keys() if busqueda_limpia in m.upper()]
                            
                            if busqueda_limpia in [m.upper() for m in maestros_unicos.keys()]:
                                maestro_final = next(m for m in maestros_unicos.keys() if m.upper() == busqueda_limpia)
                                ref_final = maestros_unicos[maestro_final]
                                c_sel.success(f"✅ Vinculado a: {maestro_final}")
                            elif len(coincidencias) > 0:
                                opcion_radio = c_sel.radio(
                                    "Sugerencias encontradas:",
                                    ["➕ Crear como NUEVO: " + busqueda_limpia] + coincidencias,
                                    key=f"radio_{i}"
                                )
                                if opcion_radio.startswith("➕ Crear"):
                                    es_nuevo = True
                                    maestro_final = busqueda_limpia
                                else:
                                    maestro_final = opcion_radio
                                    ref_final = maestros_unicos[opcion_radio]
                            else:
                                es_nuevo = True
                                maestro_final = busqueda_limpia
                                c_sel.info(f"✨ Se creará como producto nuevo")
                        else:
                            opciones = ["(Despliega para ver catálogo)"] + sorted(list(maestros_unicos.keys()))
                            seleccion_lista = c_sel.selectbox("O vincula desde la lista completa:", opciones, key=f"sel_{i}")
                            if seleccion_lista != "(Despliega para ver catálogo)":
                                maestro_final = seleccion_lista
                                ref_final = maestros_unicos[seleccion_lista]
                        
                        if es_nuevo:
                            # Auto-generar la siguiente referencia
                            max_ref = 0
                            for data in diccionario_eq.values():
                                ref_str = data.get("referencia", "")
                                if ref_str.isdigit():
                                    max_ref = max(max_ref, int(ref_str))
                            ref_final = f"{max_ref + 1:04d}"
                            c_ref.text_input("Ref. Auto:", value=ref_final, disabled=True, key=f"ref_nuevo_{i}")
                        else:
                            c_ref.text_input("Ref. Blitz:", value=ref_final, disabled=True, key=f"ref_existente_{i}")
                            
                        factor_nuevo = c_fact.number_input("Mult.:", min_value=0.0001, value=1.0, format="%.4f", key=f"fact_{i}")
                        idx = formatos_unidades.index(ud_leida) if ud_leida in formatos_unidades else 0
                        unidad_inv_nueva = c_uni.selectbox("Unidad:", formatos_unidades, index=idx, key=f"uinv_{i}")
                        
                        with st.expander("🍔 Datos para Escandallos (Camarero10) - Opcional"):
                            col_r1, col_r2 = st.columns(2)
                            rend_nuevo = col_r1.number_input("Unidades por envase (Rendimiento):", min_value=0.01, value=1.0, key=f"rend_{i}")
                            
                            opciones_receta = ["UNIDADES", "LONCHAS", "GRS", "KG", "ML", "L", "CAJAS", "BANDEJAS", "BOLSAS"]
                            if unidad_inv_nueva not in opciones_receta:
                                opciones_receta.append(unidad_inv_nueva)
                            idx_receta = opciones_receta.index(unidad_inv_nueva)
                            urec_nueva = col_r2.selectbox("Unidad de consumo:", opciones_receta, index=idx_receta, key=f"urec_{i}")
                        
                        if st.button("Guardar en Diccionario", key=f"btn_guardar_{i}"):
                            if maestro_final:
                                precio_norm = precio_detectado / factor_nuevo if factor_nuevo > 0 else precio_detectado
                                
                                if es_nuevo:
                                    confirmar_nueva_referencia(
                                        st.session_state.proveedor_ia, prod, 
                                        maestro_final, ref_final, ud_leida, 
                                        factor_nuevo, unidad_inv_nueva, precio_norm, rend_nuevo, urec_nueva
                                    )
                                else:
                                    guardar_nueva_equivalencia(st.session_state.proveedor_ia, prod, maestro_final, ref_final, ud_leida, factor_nuevo, unidad_inv_nueva, precio_norm, rend_nuevo, urec_nueva)
                                    st.success("¡Vinculado con éxito!")
                                    import time
                                    time.sleep(0.5)
                                    st.rerun()
                            else:
                                st.error("Debes indicar un nombre o seleccionarlo.")
                
                st.divider()
                if st.button("✅ Archivar Albarán"):
                    articulos_sumar = {}
                    diccionario_eq, indice_norm = cargar_equivalencias()
                    for art in st.session_state.articulos_ia:
                        prod = str(art.get("nombre", "")).strip().lower()
                        try:
                            cant = float(art.get("cantidad", 0))
                        except (ValueError, TypeError):
                            cant = 0.0
                        prov_key = st.session_state.proveedor_ia.strip().lower()
                        eq_info, encontrado = buscar_equivalencia(diccionario_eq, indice_norm, prov_key, prod, art.get("unidad", ""))
                        if encontrado:
                            m = eq_info["producto_maestro"]
                            if "val_calc_final" in art:
                                val_calc = art["val_calc_final"]
                            else:
                                uinv = str(eq_info.get("unidad_inv", "KG")).strip().upper()
                                factor = float(eq_info.get("factor", 1.0)) if float(eq_info.get("factor", 1.0)) > 0 else 1.0
                                if uinv in ["KG", "L", "LITROS", "LITRO"]:
                                    ud_l = str(art.get("unidad", "")).upper()
                                    es_directa_arch = (uinv == "KG" and ud_l in ["KG", "KGS", "KILO", "KILOS"]) or \
                                                      (uinv in ["L", "LITROS", "LITRO"] and ud_l in ["L", "LTS", "LITRO", "LITROS"])
                                    if es_directa_arch:
                                        val_calc = round(cant, 2)
                                    else:
                                        val_calc = round(cant * factor, 2)
                                else:
                                    val_calc = cant * factor
                                    unidades_discretas = ["CAJAS", "BANDEJAS", "BOLSAS", "BOTELLAS", "ESTUCHE", "BOTE", "GARRAFA", "ROLLOS", "UNIDADES", "TARRINA", "TARRINAS", "FRASCO", "FRASCOS", "CUBO", "BRIK", "PAQUETES", "PQ"]
                                    if uinv in unidades_discretas:
                                        val_calc = int(round(val_calc))
                                    else:
                                        val_calc = round(val_calc, 2)
                            articulos_sumar[m] = articulos_sumar.get(m, 0.0) + val_calc
                    
                    if articulos_sumar and st.session_state.centro_destino:
                        sumar_stock_albaran(st.session_state.centro_destino, articulos_sumar)
                        
                    for art in st.session_state.articulos_ia:
                        if not art.get("ignorado", False):
                            eq_info, encontrado = buscar_equivalencia(diccionario_eq, indice_norm, st.session_state.proveedor_ia.strip().lower(), art.get("nombre", ""), art.get("unidad", ""))
                            m_nom = eq_info.get("producto_maestro", art.get("nombre", "")) if encontrado else art.get("nombre", "")
                            ref_nom = eq_info.get("referencia", "") if encontrado else ""
                            p_final = art.get("precio_unitario_final", art.get("precio_final", 0.0))
                            u_final = eq_info.get("unidad_inv", art.get("unidad", "")) if encontrado else art.get("unidad", "")
                            registrar_en_historico_precios(st.session_state.proveedor_ia, art.get("nombre", ""), m_nom, ref_nom, p_final, u_final, st.session_state.centro_destino)
                            
                    ruta_destino = os.path.join(CARPETA_PROCESADOS, archivo_actual)
                    shutil.move(ruta_origen, ruta_destino)
                    
                    # Eliminar de la cola de GitHub y sincronizar CSVs en background
                    try:
                        import threading
                        from sync_repo import delete_file_from_github, sync_file
                        rel_origen = os.path.relpath(ruta_origen, BASE_DIR)
                        def _bg_sync():
                            try:
                                delete_file_from_github(rel_origen)
                                sync_file("Stock_Actual.csv")
                                sync_file("Historico_Precios.csv")
                            except Exception:
                                pass
                        threading.Thread(target=_bg_sync, daemon=True).start()
                    except Exception:
                        pass
                    
                    # Notificación instantánea en tiempo real por Telegram
                    enviar_notificacion_telegram(st.session_state.proveedor_ia, st.session_state.centro_destino, st.session_state.articulos_ia)
                    
                    st.session_state.ia_procesada = False
                    st.session_state.centro_destino = ""
                    st.success("✅ Albarán archivado, stock sumado y aviso enviado por Telegram.")
                    import time; time.sleep(0.8)
                    st.rerun()

elif seccion_activa == "📋 Pedidos Centros":
    import importlib
    import gestion_pedidos_centros
    importlib.reload(gestion_pedidos_centros)
    gestion_pedidos_centros.render_panel_admin_pedidos()

elif seccion_activa == "📚 Gestor de Diccionario":
    st.subheader("🛠️ Panel de Control y Auditoría del Diccionario")
    if os.path.isfile(ARCHIVO_EQUIVALENCIAS) and os.path.getsize(ARCHIVO_EQUIVALENCIAS) > 0:
        try:
            df_diccionario = pd.read_csv(ARCHIVO_EQUIVALENCIAS, encoding='utf-8-sig', dtype=str, index_col=False, on_bad_lines='skip')
            if isinstance(df_diccionario.index, pd.MultiIndex):
                df_diccionario = df_diccionario.reset_index(drop=True)
            df_diccionario = df_diccionario.fillna("")
            
            df_diccionario.insert(0, "Seleccionar", False)
            
            st.info("💡 Haz doble clic en cualquier celda para editarla. Marca la casilla 'Seleccionar' para borrar un producto.")
            
            # Usar un contenedor para el botón de borrar justo encima de la tabla a la derecha
            col_izq, col_der = st.columns([3, 1])
            
            # Configurar las columnas para que sea súper fácil editar los escandallos en línea
            columnas_configuradas = {
                "Unidad_Receta": st.column_config.SelectboxColumn(
                    "Unidad Receta",
                    help="Unidad de consumo para escandallos",
                    options=["UNIDADES", "LONCHAS", "GRS", "KG", "ML", "L", "CAJAS", "BANDEJAS", "BOLSAS"]
                ),
                "Rendimiento": st.column_config.NumberColumn(
                    "Rendimiento",
                    help="Unidades por envase",
                    format="%.2f"
                )
            }
            
            datos_editados = st.data_editor(
                df_diccionario, 
                num_rows="fixed", 
                use_container_width=True, 
                key="editor_diccionario",
                column_config=columnas_configuradas
            )
            
            filas_a_borrar = datos_editados[datos_editados["Seleccionar"] == True]
            
            with col_der:
                if not filas_a_borrar.empty:
                    if st.button("🗑️ Borrar Seleccionados", type="primary"):
                        confirmar_borrado_diccionario(datos_editados)
            
            st.divider()
            if st.button("💾 Guardar Cualquier Cambio (Edición manual)"):
                df_final = datos_editados.drop(columns=["Seleccionar"])
                df_final.to_csv(ARCHIVO_EQUIVALENCIAS, index=False, encoding='utf-8-sig')
                st.success("✅ Diccionario guardado.")
                
        except Exception as e:
            st.error(f"⚠️ Error CSV: {e}")
    else:
        st.info("Aún no hay productos guardados.")

# ==========================================
# PESTAÑA 3: GESTOR DE ESCANDALLOS Y RECETAS
# ==========================================
elif seccion_activa == "📖 Gestión de Menú y Recetas":
    st.subheader("📖 Escandallos y Recetas de Platos")
    st.info("💡 Consulta o modifica las recetas de los platos de venta. Los ingredientes coinciden con tus productos maestros del diccionario.")
    
    if os.path.isfile(ARCHIVO_RECETAS):
        df_recetas = pd.read_csv(ARCHIVO_RECETAS, encoding='utf-8-sig', dtype=str).fillna("")
        
        platos_disponibles = sorted(list(df_recetas["Plato"].dropna().unique()))
        plato_filtro = st.selectbox("🔍 Filtrar por plato de venta:", ["(Todos los Platos)"] + platos_disponibles)
        
        if plato_filtro != "(Todos los Platos)":
            df_mostrar = df_recetas[df_recetas["Plato"] == plato_filtro].copy()
        else:
            df_mostrar = df_recetas.copy()
            
        df_mostrar.insert(0, "Seleccionar", False)
        
        col_r_izq, col_r_der = st.columns([3, 1])
        
        recetas_editadas = st.data_editor(
            df_mostrar,
            use_container_width=True,
            num_rows="fixed",
            key=f"editor_recetas_{plato_filtro}",
            column_config={
                "Plato": st.column_config.TextColumn("Plato de Venta"),
                "Ingrediente": st.column_config.TextColumn("Ingrediente (Producto Maestro)"),
                "Cantidad": st.column_config.NumberColumn("Cantidad", format="%.2f"),
                "Unidad": st.column_config.SelectboxColumn("Unidad", options=["GRS", "LONCHAS", "UNIDADES", "DISCOS", "ML", "L", "KG"])
            }
        )
        
        filas_rec_borrar = recetas_editadas[recetas_editadas["Seleccionar"] == True]
        with col_r_der:
            if not filas_rec_borrar.empty:
                if st.button("🗑️ Borrar Líneas Seleccionadas", type="primary"):
                    indices_borrar = filas_rec_borrar.index
                    df_rec_final = df_recetas.drop(indices_borrar, errors='ignore')
                    df_rec_final.to_csv(ARCHIVO_RECETAS, index=False, encoding='utf-8-sig')
                    st.success("Líneas eliminadas.")
                    import time; time.sleep(0.5); st.rerun()
            
        st.divider()
        if st.button("💾 Guardar Cambios en Recetas"):
            if plato_filtro != "(Todos los Platos)":
                df_otras = df_recetas[df_recetas["Plato"] != plato_filtro]
                df_actualizadas = recetas_editadas.drop(columns=["Seleccionar"], errors='ignore')
                df_final_rec = pd.concat([df_otras, df_actualizadas], ignore_index=True)
            else:
                df_final_rec = recetas_editadas.drop(columns=["Seleccionar"], errors='ignore')
            df_final_rec.to_csv(ARCHIVO_RECETAS, index=False, encoding='utf-8-sig')
            st.success("✅ Recetas guardadas correctamente.")
            import time; time.sleep(0.5); st.rerun()
            
        with st.expander("➕ Añadir Ingrediente o Nueva Receta"):
            with st.form("form_nueva_receta"):
                c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                rend_info = cargar_rendimientos_maestros()
                maestros_lista = sorted(list(rend_info.keys()))
                
                nuevo_plato = c1.text_input("Nombre del Plato (ej. BRUTAL CRUNCH):")
                nuevo_ingrediente = c2.selectbox("Ingrediente (Producto Maestro):", maestros_lista if maestros_lista else [""])
                nueva_cantidad = c3.number_input("Cantidad:", min_value=0.01, value=1.0)
                nueva_unidad = c4.selectbox("Unidad:", ["GRS", "LONCHAS", "UNIDADES", "DISCOS", "ML", "L", "KG"])
                
                if st.form_submit_button("Añadir a la Receta"):
                    if nuevo_plato and nuevo_ingrediente:
                        nueva_fila = pd.DataFrame([{
                            "Plato": nuevo_plato.strip().upper(),
                            "Ingrediente": nuevo_ingrediente.strip().upper(),
                            "Cantidad": str(nueva_cantidad),
                            "Unidad": nueva_unidad
                        }])
                        df_total = pd.concat([df_recetas, nueva_fila], ignore_index=True)
                        df_total.to_csv(ARCHIVO_RECETAS, index=False, encoding='utf-8-sig')
                        st.success(f"Añadido {nuevo_ingrediente} a {nuevo_plato.upper()}.")
                        import time; time.sleep(0.5); st.rerun()
                    else:
                        st.error("Debes indicar el plato y el ingrediente.")
    else:
        st.warning("No se encontró el archivo Recetas.csv.")

# ==========================================
# PESTAÑA 4: VENTAS Y CIERRE CAMARERO10
# ==========================================
elif seccion_activa == "⚡ Ventas y Cierre (Camarero10)":
    st.subheader("⚡ Ventas y Cierre de Caja (Camarero10)")
    st.info("Introduce las unidades vendidas en el cierre de caja. El sistema calculará el consumo de cada ingrediente según los escandallos y descontará automáticamente el stock del local seleccionado.")
    
    centro_ventas = st.selectbox("📍 Centro para aplicar el cierre:", centros_blitz, key="sel_centro_ventas")
    
    if os.path.isfile(ARCHIVO_RECETAS) and os.path.isfile(ARCHIVO_STOCK):
        df_rec = pd.read_csv(ARCHIVO_RECETAS, encoding='utf-8-sig', dtype=str).fillna("")
        platos_lista = sorted(list(df_rec["Plato"].dropna().unique()))
        
        # Tabla de introducción de ventas
        df_input_ventas = pd.DataFrame({
            "Plato": platos_lista,
            "Unidades Vendidas": [0] * len(platos_lista)
        })
        
        ventas_editadas = st.data_editor(
            df_input_ventas,
            column_config={
                "Plato": st.column_config.TextColumn("Plato de Venta (Camarero10)", disabled=True),
                "Unidades Vendidas": st.column_config.NumberColumn("Unidades Vendidas", min_value=0, step=1)
            },
            use_container_width=True,
            key="editor_ventas_camarero10"
        )
        
        ventas_reales = ventas_editadas[ventas_editadas["Unidades Vendidas"] > 0]
        
        if not ventas_reales.empty:
            st.divider()
            st.write(f"📊 **Resumen de Consumo Calculado ({len(ventas_reales)} platos vendidos):**")
            
            rend_maestros = cargar_rendimientos_maestros()
            consumos_calculados = {}
            
            for _, fila_v in ventas_reales.iterrows():
                plato = fila_v["Plato"]
                uds_vendidas = float(fila_v["Unidades Vendidas"])
                
                receta_plato = df_rec[df_rec["Plato"] == plato]
                for _, fila_r in receta_plato.iterrows():
                    ingrediente = fila_r["Ingrediente"].strip().upper()
                    try:
                        cant_r = float(fila_r["Cantidad"] or 0.0)
                    except ValueError:
                        cant_r = 0.0
                    ud_r = fila_r["Unidad"].strip().upper()
                    
                    consumo_total_rec = uds_vendidas * cant_r
                    
                    info_rend = rend_maestros.get(ingrediente, {"rendimiento": 1.0, "unidad_inv": "UNIDADES"})
                    rendimiento = info_rend["rendimiento"] if info_rend["rendimiento"] > 0 else 1.0
                    uinv = info_rend["unidad_inv"] or "UNIDADES"
                    
                    consumo_inv = consumo_total_rec / rendimiento
                    
                    if ingrediente not in consumos_calculados:
                        consumos_calculados[ingrediente] = {
                            "consumo_receta": consumo_total_rec,
                            "unidad_receta": ud_r,
                            "consumo_inv": consumo_inv,
                            "unidad_inv": uinv
                        }
                    else:
                        consumos_calculados[ingrediente]["consumo_receta"] += consumo_total_rec
                        consumos_calculados[ingrediente]["consumo_inv"] += consumo_inv

            df_stock_act = pd.read_csv(ARCHIVO_STOCK, encoding='utf-8-sig', dtype=str).fillna("0.0")
            df_stock_centro = df_stock_act[df_stock_act["Centro"] == centro_ventas].copy()
            
            filas_comparativa = []
            for ing, data in consumos_calculados.items():
                mask_stock = df_stock_centro["Producto_Maestro"].str.upper() == ing
                stock_previo = float(df_stock_centro.loc[mask_stock, "Cantidad_Stock"].values[0]) if mask_stock.any() else 0.0
                cons_inv = round(data["consumo_inv"], 3)
                stock_resultante = round(stock_previo - cons_inv, 3)
                
                filas_comparativa.append({
                    "Producto Maestro": ing,
                    "Stock Previo": stock_previo,
                    "Consumo en Ventas": cons_inv,
                    "Stock Resultante": stock_resultante,
                    "Unidad Stock": data["unidad_inv"],
                    "Desglose Receta": f"{round(data['consumo_receta'], 1)} {data['unidad_receta']}"
                })
                
            df_comp = pd.DataFrame(filas_comparativa)
            st.dataframe(df_comp, use_container_width=True)
            
            negativos = df_comp[df_comp["Stock Resultante"] < 0]
            if not negativos.empty:
                st.warning(f"⚠️ Hay {len(negativos)} artículos que quedarán con stock negativo.")
                
            if st.button("⚡ CONFIRMAR Y DESCONTAR DEL STOCK", type="primary"):
                for _, fila_c in df_comp.iterrows():
                    m = fila_c["Producto Maestro"]
                    consumo = float(fila_c["Consumo en Ventas"])
                    mask_update = (df_stock_act["Centro"] == centro_ventas) & (df_stock_act["Producto_Maestro"].str.upper() == m)
                    if mask_update.any():
                        val_act = float(df_stock_act.loc[mask_update, "Cantidad_Stock"].values[0] or 0.0)
                        df_stock_act.loc[mask_update, "Cantidad_Stock"] = str(round(val_act - consumo, 3))
                    else:
                        df_stock_act = pd.concat([df_stock_act, pd.DataFrame([{
                            "Centro": centro_ventas,
                            "Producto_Maestro": m,
                            "Referencia": "",
                            "Cantidad_Stock": str(round(-consumo, 3)),
                            "Unidad_Inventario": fila_c["Unidad Stock"]
                        }])], ignore_index=True)
                        
                df_stock_act.to_csv(ARCHIVO_STOCK, index=False, encoding='utf-8-sig')
                st.success(f"✅ ¡Stock descontado y actualizado con éxito para {centro_ventas}!")
                import time; time.sleep(1.2); st.rerun()
        else:
            st.caption("Escribe las cantidades vendidas de los platos para previsualizar el descuento.")

# ==========================================
# PESTAÑA 5: CONTROL DE STOCK EN VIVO
# ==========================================
elif seccion_activa == "📦 Control de Inventario":
    st.subheader("📦 Control de Stock en Vivo")
    st.info("💡 Consulta y ajusta manualmente el inventario de cada centro (ideal para inventarios físicos de recuento o ajustes de mermas).")
    
    centro_ver_stock = st.selectbox("📍 Selecciona el Centro:", centros_blitz, key="sel_centro_control_stock")
    
    if os.path.isfile(ARCHIVO_STOCK):
        df_stock_todos = pd.read_csv(ARCHIVO_STOCK, encoding='utf-8-sig', dtype=str).fillna("0.0")
        df_stock_filtro = df_stock_todos[df_stock_todos["Centro"] == centro_ver_stock].copy()
        
        if not df_stock_filtro.empty:
            df_stock_filtro["Cantidad_Stock"] = pd.to_numeric(df_stock_filtro["Cantidad_Stock"], errors='coerce').fillna(0.0)
            
            stock_editado = st.data_editor(
                df_stock_filtro[["Producto_Maestro", "Referencia", "Cantidad_Stock", "Unidad_Inventario"]],
                use_container_width=True,
                key=f"editor_stock_{centro_ver_stock}",
                column_config={
                    "Producto_Maestro": st.column_config.TextColumn("Producto Maestro", disabled=True),
                    "Referencia": st.column_config.TextColumn("Ref.", disabled=True),
                    "Cantidad_Stock": st.column_config.NumberColumn("Cantidad en Stock", format="%.2f"),
                    "Unidad_Inventario": st.column_config.TextColumn("Unidad", disabled=True)
                }
            )
            
            if st.button("💾 Guardar Ajuste de Stock en Vivo"):
                for _, row in stock_editado.iterrows():
                    m = row["Producto_Maestro"]
                    cant_nueva = row["Cantidad_Stock"]
                    mask = (df_stock_todos["Centro"] == centro_ver_stock) & (df_stock_todos["Producto_Maestro"] == m)
                    if mask.any():
                        df_stock_todos.loc[mask, "Cantidad_Stock"] = str(cant_nueva)
                df_stock_todos.to_csv(ARCHIVO_STOCK, index=False, encoding='utf-8-sig')
                st.success(f"✅ Stock de {centro_ver_stock} guardado correctamente.")
                import time; time.sleep(0.5); st.rerun()
        else:
            st.warning(f"No hay registros de stock para {centro_ver_stock}.")

# ==========================================
# PESTAÑA 6: RENTABILIDAD Y FOOD COST
# ==========================================
elif seccion_activa == "💰 Rentabilidad y Food Cost":
    st.subheader("💰 Rentabilidad y Food Cost por Plato")
    st.markdown('<p style="color:#64748b; font-size:0.95rem; margin-top:-10px;">Monitorización de márgenes brutos, coste de ingredientes y rentabilidad en tiempo real sobre tu carta de ventas.</p>', unsafe_allow_html=True)
    
    if os.path.isfile(ARCHIVO_RECETAS) and os.path.isfile(ARCHIVO_EQUIVALENCIAS):
        df_rec = pd.read_csv(ARCHIVO_RECETAS, encoding='utf-8-sig', dtype=str).fillna("")
        df_eq = pd.read_csv(ARCHIVO_EQUIVALENCIAS, encoding='utf-8-sig', dtype=str).fillna("")
        
        # Cargar precios de venta PVP
        if os.path.isfile(ARCHIVO_PRECIOS_VENTA):
            df_pvp = pd.read_csv(ARCHIVO_PRECIOS_VENTA, encoding='utf-8-sig', dtype=str).fillna("")
            dict_pvp = dict(zip(df_pvp["Plato"].str.strip().str.upper(), df_pvp["PVP"].astype(float)))
        else:
            dict_pvp = {}
            
        def get_coste_unitario_ing(ingrediente, ud_receta):
            sub = df_eq[df_eq['Producto_Maestro_Blitz'].str.strip().str.upper() == ingrediente.strip().upper()]
            if sub.empty: return 0.0, "Sin equivalencia", 1.0, 0.0
            
            # Preferir coincidencia por unidad de receta
            match_ud = sub[sub['Unidad_Receta'].str.strip().str.upper() == ud_receta.strip().upper()]
            if not match_ud.empty:
                candidato = match_ud[pd.to_numeric(match_ud['Precio_Actual'], errors='coerce').fillna(0) > 0]
                row = candidato.iloc[0] if not candidato.empty else match_ud.iloc[0]
            else:
                candidato = sub[pd.to_numeric(sub['Precio_Actual'], errors='coerce').fillna(0) > 0]
                row = candidato.iloc[0] if not candidato.empty else sub.iloc[0]
                
            try: p = float(row['Precio_Actual'] or 0.0)
            except: p = 0.0
            try: rend = float(row['Rendimiento'] or 1.0)
            except: rend = 1.0
            if rend <= 0: rend = 1.0
            return (p / rend), row.get('Proveedor', ''), rend, p

        # Calcular métricas por plato
        platos_lista = sorted(list(df_rec["Plato"].dropna().unique()))
        datos_platos = []
        desglose_ingredientes = {}
        
        for p in platos_lista:
            sub = df_rec[df_rec['Plato'] == p]
            coste_total_materia = 0.0
            items_ing = []
            
            for _, r in sub.iterrows():
                ing = r['Ingrediente'].strip().upper()
                try: cant = float(r['Cantidad'] or 0.0)
                except: cant = 0.0
                ud = r['Unidad'].strip().upper()
                coste_ud, prov, rend, p_base = get_coste_unitario_ing(ing, ud)
                coste_ing = cant * coste_ud
                coste_total_materia += coste_ing
                items_ing.append({
                    "Ingrediente": ing,
                    "Cantidad": cant,
                    "Unidad": ud,
                    "Proveedor": prov,
                    "Coste_Unitario": coste_ud,
                    "Coste_Total": coste_ing
                })
                
            desglose_ingredientes[p] = items_ing
            
            # PVP venta
            pvp_venta = float(dict_pvp.get(p.strip().upper(), 11.50))
            pvp_neto = round(pvp_venta / 1.10, 2)  # 10% IVA hostelería
            margen_bruto = round(pvp_neto - coste_total_materia, 2)
            food_cost_pct = round((coste_total_materia / pvp_neto * 100), 1) if pvp_neto > 0 else 0.0
            margen_pct = round(100.0 - food_cost_pct, 1)
            
            # Semáforo de salud financiera
            if food_cost_pct <= 28.0:
                estado = "🟢 Óptimo (<28%)"
            elif food_cost_pct <= 35.0:
                estado = "🟡 Moderado (28-35%)"
            else:
                estado = "🔴 Alerta (>35%)"
                
            datos_platos.append({
                "Plato": p,
                "Coste_Materia": round(coste_total_materia, 2),
                "PVP": pvp_venta,
                "PVP_Neto": pvp_neto,
                "Margen_Bruto": margen_bruto,
                "Food_Cost_Pct": food_cost_pct,
                "Margen_Pct": margen_pct,
                "Estado": estado
            })
            
        df_kpis = pd.DataFrame(datos_platos)
        
        # 1. TARJETAS KPIS GENERALES
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🍔 Platos en Carta", len(df_kpis))
        coste_medio = df_kpis["Coste_Materia"].mean() if not df_kpis.empty else 0.0
        c2.metric("💵 Coste Medio Ingredientes", f"{coste_medio:.2f} €")
        margen_medio = df_kpis["Margen_Bruto"].mean() if not df_kpis.empty else 0.0
        fc_medio = df_kpis["Food_Cost_Pct"].mean() if not df_kpis.empty else 0.0
        c3.metric("📈 Margen Bruto Medio", f"{margen_medio:.2f} €", f"Food Cost: {fc_medio:.1f}%", delta_color="inverse")
        alertas_cnt = len(df_kpis[df_kpis["Food_Cost_Pct"] > 32.0])
        c4.metric("⚠️ Platos en Alerta Margen", alertas_cnt, delta="Revisar PVP" if alertas_cnt > 0 else "Todo en rango", delta_color="inverse")
        
        st.divider()
        
        # PESTAÑAS DE VISUALIZACIÓN
        tab_tabla, tab_detalle, tab_simulador = st.tabs([
            "📊 Tabla General y Edición de PVP", 
            "🔍 Radiografía de Escandallo por Plato", 
            "🎛️ Simulador de Precios y Costes"
        ])
        
        with tab_tabla:
            st.write("💡 Modifica el **PVP** de cualquier plato directamente en la tabla y pulsa **Guardar Cambios de PVP** para actualizar tus márgenes:")
            
            df_editor_pvp = df_kpis[["Plato", "Coste_Materia", "PVP", "PVP_Neto", "Margen_Bruto", "Food_Cost_Pct", "Estado"]].copy()
            
            edicion_pvp = st.data_editor(
                df_editor_pvp,
                use_container_width=True,
                column_config={
                    "Plato": st.column_config.TextColumn("Plato de Venta", disabled=True),
                    "Coste_Materia": st.column_config.NumberColumn("Coste Materia Prima", format="%.2f €", disabled=True),
                    "PVP": st.column_config.NumberColumn("PVP Venta (IVA inc.)", format="%.2f €", min_value=0.0, step=0.10),
                    "PVP_Neto": st.column_config.NumberColumn("PVP Neto (s/IVA)", format="%.2f €", disabled=True),
                    "Margen_Bruto": st.column_config.NumberColumn("Margen (€)", format="%.2f €", disabled=True),
                    "Food_Cost_Pct": st.column_config.NumberColumn("Food Cost (%)", format="%.1f %%", disabled=True),
                    "Estado": st.column_config.TextColumn("Semáforo Rentabilidad", disabled=True)
                },
                key="editor_tabla_pvp"
            )
            
            if st.button("💾 Guardar Cambios de PVP en Carta", type="primary"):
                rows_save = []
                for _, r in edicion_pvp.iterrows():
                    rows_save.append({"Plato": r["Plato"], "PVP": f"{float(r['PVP']):.2f}"})
                pd.DataFrame(rows_save).to_csv(ARCHIVO_PRECIOS_VENTA, index=False, encoding='utf-8-sig')
                st.success("✅ ¡Precios de venta actualizados correctamente!")
                import time; time.sleep(0.6); st.rerun()
                
        with tab_detalle:
            col_sel1, col_sel2 = st.columns([2, 1])
            plato_sel = col_sel1.selectbox("Selecciona un plato para ver el desglose:", platos_lista, key="sel_plato_escandallo")
            
            if plato_sel in desglose_ingredientes:
                items_p = desglose_ingredientes[plato_sel]
                df_ing = pd.DataFrame(items_p)
                
                info_p = df_kpis[df_kpis["Plato"] == plato_sel].iloc[0]
                
                with col_sel2:
                    st.metric("Coste Total del Plato", f"{info_p['Coste_Materia']:.2f} €")
                    st.metric("Food Cost Actual", f"{info_p['Food_Cost_Pct']:.1f} %", info_p['Estado'])
                    
                if not df_ing.empty:
                    df_ing["% del Coste"] = (df_ing["Coste_Total"] / info_p["Coste_Materia"] * 100).round(1)
                    
                    st.subheader(f"📊 Desglose de Ingredientes: {plato_sel}")
                    
                    # Gráfico de barras de coste por ingrediente
                    chart_data = df_ing.set_index("Ingrediente")[["Coste_Total"]].rename(columns={"Coste_Total": "Coste (€)"})
                    st.bar_chart(chart_data)
                    
                    st.dataframe(
                        df_ing[["Ingrediente", "Cantidad", "Unidad", "Proveedor", "Coste_Unitario", "Coste_Total", "% del Coste"]],
                        use_container_width=True,
                        column_config={
                            "Coste_Unitario": st.column_config.NumberColumn("Coste Unit.", format="%.4f €"),
                            "Coste_Total": st.column_config.NumberColumn("Coste en Plato", format="%.2f €"),
                            "% del Coste": st.column_config.NumberColumn("% del Coste", format="%.1f %%")
                        }
                    )
                    
        with tab_simulador:
            st.subheader("🎛️ Simulador de Margen e Inflación")
            st.write("Evalúa cómo afecta a tu beneficio una subida de costes de proveedores o un cambio de precios en carta:")
            
            sim_col1, sim_col2 = st.columns(2)
            subida_costes = sim_col1.slider("Impacto de Inflación / Subida Proveedores (%):", min_value=0, max_value=40, value=5, step=1)
            ajuste_pvp = sim_col2.slider("Ajuste general en PVP de platos (€):", min_value=-2.0, max_value=3.0, value=0.5, step=0.10)
            
            df_sim = df_kpis.copy()
            df_sim["Coste_Simulado"] = (df_sim["Coste_Materia"] * (1 + subida_costes / 100.0)).round(2)
            df_sim["PVP_Simulado"] = (df_sim["PVP"] + ajuste_pvp).clip(lower=0.5).round(2)
            df_sim["PVP_Neto_Sim"] = (df_sim["PVP_Simulado"] / 1.10).round(2)
            df_sim["Margen_Sim"] = (df_sim["PVP_Neto_Sim"] - df_sim["Coste_Simulado"]).round(2)
            df_sim["Food_Cost_Sim"] = ((df_sim["Coste_Simulado"] / df_sim["PVP_Neto_Sim"]) * 100).round(1)
            
            m1, m2, m3 = st.columns(3)
            diff_margen = (df_sim["Margen_Sim"].mean() - df_kpis["Margen_Bruto"].mean())
            m1.metric("Margen Medio Simulado", f"{df_sim['Margen_Sim'].mean():.2f} €", f"{diff_margen:+.2f} €/plato")
            m2.metric("Food Cost Medio Simulado", f"{df_sim['Food_Cost_Sim'].mean():.1f} %")
            m3.metric("Beneficio Estimado por cada 1000 ventas", f"{(df_sim['Margen_Sim'].mean() * 1000):,.0f} €", f"{(diff_margen * 1000):+,.0f} €")
            
            st.dataframe(
                df_sim[["Plato", "Coste_Materia", "Coste_Simulado", "PVP", "PVP_Simulado", "Margen_Bruto", "Margen_Sim", "Food_Cost_Pct", "Food_Cost_Sim"]],
                use_container_width=True,
                column_config={
                    "Coste_Materia": st.column_config.NumberColumn("Coste Actual", format="%.2f €"),
                    "Coste_Simulado": st.column_config.NumberColumn("Coste Simulado", format="%.2f €"),
                    "PVP": st.column_config.NumberColumn("PVP Actual", format="%.2f €"),
                    "PVP_Simulado": st.column_config.NumberColumn("PVP Simulado", format="%.2f €"),
                    "Margen_Bruto": st.column_config.NumberColumn("Margen Actual", format="%.2f €"),
                    "Margen_Sim": st.column_config.NumberColumn("Margen Simulado", format="%.2f €"),
                    "Food_Cost_Pct": st.column_config.NumberColumn("FC Actual (%)", format="%.1f %%"),
                    "Food_Cost_Sim": st.column_config.NumberColumn("FC Simulado (%)", format="%.1f %%")
                }
            )
    else:
        st.warning("Faltan archivos de Recetas o Diccionario para calcular la rentabilidad.")

# ==========================================
# PESTAÑA 7: ASISTENTE DE COMPRAS Y PEDIDOS
# ==========================================
elif seccion_activa == "🛒 Asistente de Compras y Pedidos":
    st.subheader("🛒 Asistente Inteligente de Compras y Pedidos")
    st.markdown('<p style="color:#64748b; font-size:0.95rem; margin-top:-10px;">Detección automática de roturas, sugerencia de reposición según stock mínimo y generación instantánea de pedidos para WhatsApp.</p>', unsafe_allow_html=True)
    
    if os.path.isfile(ARCHIVO_STOCK) and os.path.isfile(ARCHIVO_EQUIVALENCIAS):
        df_stock_todos = pd.read_csv(ARCHIVO_STOCK, encoding='utf-8-sig', dtype=str).fillna("")
        df_eq = pd.read_csv(ARCHIVO_EQUIVALENCIAS, encoding='utf-8-sig', dtype=str).fillna("")
        
        # Cargar niveles mínimos
        if os.path.isfile(ARCHIVO_STOCK_MINIMO):
            df_minimos = pd.read_csv(ARCHIVO_STOCK_MINIMO, encoding='utf-8-sig', dtype=str).fillna("0.0")
        else:
            df_minimos = pd.DataFrame(columns=["Centro", "Producto_Maestro", "Stock_Minimo"])
            
        dict_minimos = {}
        for _, r in df_minimos.iterrows():
            c = r["Centro"].strip()
            m = r["Producto_Maestro"].strip().upper()
            try: dict_minimos[(c, m)] = float(r["Stock_Minimo"] or 0.0)
            except: dict_minimos[(c, m)] = 0.0
            
        # Diccionario de proveedor habitual y unidad de compra
        info_proveedor = {}
        for _, r in df_eq.iterrows():
            m = r["Producto_Maestro_Blitz"].strip().upper()
            if m and m not in info_proveedor:
                try: p_act = float(r["Precio_Actual"] or 0.0)
                except: p_act = 0.0
                info_proveedor[m] = {
                    "proveedor": r.get("Proveedor", "Varios"),
                    "ud_compra": r.get("Unidad_Compra", "UNIDADES"),
                    "factor": float(r.get("Factor_Multiplicador", "1.0") or 1.0),
                    "precio": p_act
                }
                
        # FILTROS
        f_col1, f_col2, f_col3 = st.columns([1.5, 1.5, 2])
        centro_pedido = f_col1.selectbox("📍 Centro para realizar el pedido:", centros_blitz, key="sel_centro_asistente_pedidos")
        
        todos_provs = sorted(list(set(df_eq["Proveedor"].dropna().unique())))
        filtro_prov = f_col2.selectbox("🏢 Filtrar por Proveedor:", ["(Todos los Proveedores)"] + todos_provs, key="filtro_prov_pedido")
        
        filtro_estado = f_col3.radio(
            "Ver:", 
            ["🔴 Solo artículos bajo mínimos (Sugeridos para pedir)", "📋 Ver inventario completo"], 
            index=0, 
            horizontal=True
        )
        
        # Filtrar stock del centro
        df_stock_c = df_stock_todos[df_stock_todos["Centro"] == centro_pedido].copy()
        
        filas_pedido = []
        for _, r in df_stock_c.iterrows():
            m = r["Producto_Maestro"].strip().upper()
            try: cant_stock = float(r["Cantidad_Stock"] or 0.0)
            except: cant_stock = 0.0
            ud_inv = r.get("Unidad_Inventario", "")
            
            s_min = dict_minimos.get((centro_pedido, m), 5.0)
            prov_data = info_proveedor.get(m, {"proveedor": "Varios", "ud_compra": ud_inv, "factor": 1.0, "precio": 0.0})
            
            # Filtro por proveedor si aplica
            if filtro_prov != "(Todos los Proveedores)":
                if prov_data["proveedor"].strip().lower() != filtro_prov.strip().lower():
                    continue
                    
            deficit = s_min - cant_stock
            bajo_minimos = (cant_stock <= s_min)
            
            if filtro_estado.startswith("🔴") and not bajo_minimos:
                continue
                
            # Cantidad sugerida
            if bajo_minimos:
                sugerida = max(1.0, round(deficit, 1))
            else:
                sugerida = 0.0
                
            estado_txt = "🔴 ROTURA CRÍTICA" if cant_stock <= 0 else ("🟡 BAJO MÍNIMOS" if bajo_minimos else "🟢 OK")
            
            filas_pedido.append({
                "Producto": m,
                "Proveedor": prov_data["proveedor"],
                "Stock_Actual": cant_stock,
                "Stock_Minimo": s_min,
                "Estado": estado_txt,
                "Cantidad_Pedir": sugerida,
                "Unidad_Compra": prov_data["ud_compra"],
                "Precio_Unit": prov_data["precio"],
                "Subtotal_Est": round(sugerida * prov_data["precio"], 2)
            })
            
        df_ped = pd.DataFrame(filas_pedido)
        
        if not df_ped.empty:
            # KPIS
            uds_pedir = df_ped[df_ped["Cantidad_Pedir"] > 0]
            k1, k2, k3 = st.columns(3)
            k1.metric("📦 Artículos para Pedir", len(uds_pedir))
            total_pedido_est = uds_pedir["Subtotal_Est"].sum()
            k2.metric("💰 Estimación Total Pedido", f"{total_pedido_est:,.2f} €")
            criticos = len(df_ped[df_ped["Stock_Actual"] <= 0])
            k3.metric("⚠️ Artículos Agotados (Stock 0)", criticos, delta="URGENTE" if criticos > 0 else "Normal", delta_color="inverse")
            
            st.divider()
            
            st.write("💡 Ajusta la columna **Cantidad a Pedir** y el **Stock Mínimo** deseado. Luego puedes generar el pedido para WhatsApp o guardar los mínimos:")
            
            editor_pedido = st.data_editor(
                df_ped,
                use_container_width=True,
                column_config={
                    "Producto": st.column_config.TextColumn("Producto Maestro", disabled=True),
                    "Proveedor": st.column_config.TextColumn("Proveedor", disabled=True),
                    "Stock_Actual": st.column_config.NumberColumn("Stock Actual", format="%.2f", disabled=True),
                    "Stock_Minimo": st.column_config.NumberColumn("Stock Mínimo Deseado", format="%.1f", min_value=0.0),
                    "Estado": st.column_config.TextColumn("Estado", disabled=True),
                    "Cantidad_Pedir": st.column_config.NumberColumn("Cantidad a Pedir", min_value=0.0, step=1.0),
                    "Unidad_Compra": st.column_config.TextColumn("Unidad Compra", disabled=True),
                    "Precio_Unit": st.column_config.NumberColumn("Precio Est. (€)", format="%.2f €", disabled=True),
                    "Subtotal_Est": st.column_config.NumberColumn("Subtotal (€)", format="%.2f €", disabled=True)
                },
                key="editor_tabla_pedidos"
            )
            
            col_b1, col_b2 = st.columns([1, 1])
            with col_b1:
                if st.button("💾 Guardar Ajustes de Stock Mínimo"):
                    # Actualizar memoria y guardar CSV
                    for _, r in editor_pedido.iterrows():
                        m = r["Producto"]
                        dict_minimos[(centro_pedido, m)] = float(r["Stock_Minimo"])
                    rows_out = [{"Centro": c, "Producto_Maestro": m, "Stock_Minimo": val} for (c, m), val in dict_minimos.items()]
                    pd.DataFrame(rows_out).to_csv(ARCHIVO_STOCK_MINIMO, index=False, encoding='utf-8-sig')
                    st.success("✅ ¡Niveles de stock mínimo guardados con éxito!")
                    import time; time.sleep(0.6); st.rerun()
                    
            st.divider()
            
            # GENERADOR DE MENSAJE PARA WHATSAPP
            st.subheader("📲 Generador de Pedido para WhatsApp")
            articulos_a_pedir = editor_pedido[editor_pedido["Cantidad_Pedir"] > 0]
            
            if not articulos_a_pedir.empty:
                prov_texto = filtro_prov if filtro_prov != "(Todos los Proveedores)" else "Proveedores Varios"
                fecha_actual = pd.Timestamp.now().strftime("%d/%m/%Y")
                
                lineas_articulos = []
                for _, r in articulos_a_pedir.iterrows():
                    cant = int(r['Cantidad_Pedir']) if float(r['Cantidad_Pedir']).is_integer() else r['Cantidad_Pedir']
                    lineas_articulos.append(f"• {cant} x {r['Producto']} ({r['Unidad_Compra']})")
                    
                total_ped_calculado = sum(float(r["Cantidad_Pedir"]) * float(r["Precio_Unit"]) for _, r in articulos_a_pedir.iterrows())
                
                texto_whatsapp = f"""🍔 *PEDIDO BLITZ FOOD*
📍 *Centro:* {centro_pedido}
📅 *Fecha:* {fecha_actual}
🏢 *Proveedor:* {prov_texto}
-------------------------------------
""" + "\n".join(lineas_articulos) + f"""
-------------------------------------
💰 *Total Estimado:* ~{total_ped_calculado:,.2f} €
🚚 *Entrega:* Por favor confirmar recepción de pedido.
¡Muchas gracias!"""

                st.write("Copia este texto y pégalo directamente en el chat con tu proveedor o comercial:")
                st.code(texto_whatsapp, language="markdown")
                
                import urllib.parse
                url_wa = f"https://api.whatsapp.com/send?text={urllib.parse.quote(texto_whatsapp)}"
                st.link_button("📲 Abrir y Enviar en WhatsApp Web", url_wa, type="primary")
            else:
                st.info("No hay artículos con cantidad a pedir superior a 0 en la tabla.")
        else:
            st.info(f"No hay artículos que coincidan con los filtros seleccionados para {centro_pedido}.")
    else:
        st.warning("Faltan archivos de Stock o Diccionario para generar pedidos.")

# ==========================================
# PESTAÑA 8: EVOLUCIÓN Y COMPARATIVA DE PRECIOS
# ==========================================
elif seccion_activa == "📈 Evolución y Comparativa de Precios":
    st.subheader("📈 Evolución y Comparativa de Precios de Compra")
    st.markdown('<p style="color:#64748b; font-size:0.95rem; margin-top:-10px;">Análisis de fluctuación de precios de materias primas en el tiempo y comparador de ahorro multiproveedor.</p>', unsafe_allow_html=True)
    
    if os.path.isfile(ARCHIVO_HISTORICO_PRECIOS) and os.path.isfile(ARCHIVO_EQUIVALENCIAS):
        df_hist = pd.read_csv(ARCHIVO_HISTORICO_PRECIOS, encoding='utf-8-sig').fillna("")
        df_eq = pd.read_csv(ARCHIVO_EQUIVALENCIAS, encoding='utf-8-sig').fillna("")
        
        df_hist["Precio"] = pd.to_numeric(df_hist["Precio"], errors='coerce').fillna(0.0)
        df_hist["Fecha"] = pd.to_datetime(df_hist["Fecha"], errors='coerce')
        df_hist = df_hist.sort_values(by="Fecha")
        # Filtrar únicamente a partir del 01/11/2026 (inicio del registro real de albaranes)
        df_hist = df_hist[df_hist["Fecha"] >= "2026-11-01"]
        
        tab_h1, tab_h2, tab_h3 = st.tabs([
            "📈 Curva de Precio por Producto",
            "⚖️ Radar de Ahorro Multiproveedor",
            "🏢 Catálogo y Tarifas por Proveedor"
        ])
        
        with tab_h1:
            st.write("Selecciona cualquier producto para ver su gráfica de precios y cómo le ha afectado la inflación:")
            
            maestros_hist = sorted(list(df_hist["Producto_Maestro"].dropna().unique()))
            col_m1, col_m2 = st.columns([2, 1])
            maestro_sel = col_m1.selectbox("Producto Maestro:", maestros_hist, key="sel_producto_historico")
            
            df_prod = df_hist[df_hist["Producto_Maestro"] == maestro_sel].copy()
            
            if not df_prod.empty:
                # Métricas
                p_actual = df_prod["Precio"].iloc[-1]
                p_min = df_prod["Precio"].min()
                p_max = df_prod["Precio"].max()
                p_inicial = df_prod["Precio"].iloc[0]
                
                var_pct = ((p_actual - p_inicial) / p_inicial * 100) if p_inicial > 0 else 0.0
                
                with col_m2:
                    delta_str = f"{var_pct:+.1f} %"
                    st.metric("Precio Actual", f"{p_actual:.2f} €", delta_str, delta_color="inverse")
                    
                m_c1, m_c2, m_c3 = st.columns(3)
                m_c1.metric("Precio Mínimo Histórico", f"{p_min:.2f} €")
                m_c2.metric("Precio Máximo Histórico", f"{p_max:.2f} €")
                m_c3.metric("Última Compra", df_prod["Fecha"].iloc[-1].strftime("%d/%m/%Y") if pd.notnull(df_prod["Fecha"].iloc[-1]) else "-")
                
                st.subheader(f"Evolución del precio: {maestro_sel}")
                
                # Selector de estilo para comparar Plotly vs Clásico
                col_tg1, col_tg2 = st.columns([2, 1])
                tipo_grafica = col_tg1.radio(
                    "Estilo de visualización:",
                    ["✨ Gráfica Interactiva Plotly", "📊 Gráfica Clásica Streamlit"],
                    horizontal=True,
                    key=f"tg_{maestro_sel}"
                )
                
                if "Plotly" in tipo_grafica:
                    try:
                        import plotly.express as px
                        
                        cols_custom = [c for c in ["Proveedor", "Sinonimo", "Centro"] if c in df_prod.columns]
                        fig = px.line(
                            df_prod,
                            x="Fecha",
                            y="Precio",
                            markers=True,
                            hover_data=cols_custom if cols_custom else None,
                            labels={"Precio": "Precio Unitario (€)", "Fecha": "Fecha Albarán"}
                        )
                        fig.update_traces(
                            line=dict(color="#2563eb", width=3),
                            marker=dict(size=9, color="#ef4444", symbol="circle")
                        )
                        fig.update_layout(
                            template="plotly_white",
                            hovermode="x unified",
                            margin=dict(l=10, r=10, t=20, b=20),
                            height=380
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        chart_df = df_prod.set_index("Fecha")[["Precio"]]
                        st.line_chart(chart_df)
                else:
                    # Gráfica de línea clásica
                    chart_df = df_prod.set_index("Fecha")[["Precio"]]
                    st.line_chart(chart_df)
                
                st.write("📋 **Registro Histórico de Compras y Albaranes:**")
                df_prod_show = df_prod.copy()
                df_prod_show["Fecha"] = df_prod_show["Fecha"].dt.strftime("%d/%m/%Y")
                st.dataframe(
                    df_prod_show[["Fecha", "Proveedor", "Sinonimo", "Precio", "Unidad", "Centro"]],
                    use_container_width=True,
                    column_config={
                        "Precio": st.column_config.NumberColumn("Precio Pagado", format="%.2f €")
                    }
                )
                
        with tab_h2:
            st.subheader("⚖️ Comparador de Proveedores (¿Quién vende más barato?)")
            st.info("Compara el coste del mismo artículo entre diferentes proveedores para optimizar tus márgenes de compra.")
            
            # Buscar artículos con más de un proveedor en equivalencias
            df_eq_val = df_eq.copy()
            df_eq_val["Precio_Actual"] = pd.to_numeric(df_eq_val["Precio_Actual"], errors='coerce').fillna(0.0)
            
            articulos_agrupados = df_eq_val.groupby("Producto_Maestro_Blitz").filter(lambda x: len(x["Proveedor"].unique()) > 1)
            maestros_multi = sorted(list(articulos_agrupados["Producto_Maestro_Blitz"].dropna().unique()))
            
            if maestros_multi:
                sel_multi = st.selectbox("Selecciona un artículo con varios proveedores:", maestros_multi, key="sel_multi_proveedor")
                
                sub_multi = df_eq_val[df_eq_val["Producto_Maestro_Blitz"] == sel_multi].copy()
                
                # Gráfico comparativo
                st.bar_chart(sub_multi.set_index("Proveedor")[["Precio_Actual"]].rename(columns={"Precio_Actual": "Precio Actual (€)"}))
                
                # Tabla comparativa y cálculo de ahorro
                p_menor = sub_multi["Precio_Actual"].min()
                prov_menor = sub_multi[sub_multi["Precio_Actual"] == p_menor]["Proveedor"].iloc[0]
                p_mayor = sub_multi["Precio_Actual"].max()
                prov_mayor = sub_multi[sub_multi["Precio_Actual"] == p_mayor]["Proveedor"].iloc[0]
                
                ahorro_abs = p_mayor - p_menor
                ahorro_pct = (ahorro_abs / p_mayor * 100) if p_mayor > 0 else 0.0
                
                if ahorro_abs > 0:
                    st.success(f"💡 **Oportunidad de Ahorro:** Comprando a **{prov_menor}** ({p_menor:.2f} €) en lugar de **{prov_mayor}** ({p_mayor:.2f} €) ahorras **{ahorro_abs:.2f} € por unidad ({ahorro_pct:.1f}%)**.")
                    
                st.dataframe(
                    sub_multi[["Proveedor", "Sinonimo_Proveedor", "Precio_Actual", "Unidad_Compra", "Rendimiento", "Unidad_Receta"]],
                    use_container_width=True,
                    column_config={
                        "Precio_Actual": st.column_config.NumberColumn("Precio Actual", format="%.2f €")
                    }
                )
            else:
                st.info("Actualmente tus productos están asignados a un único proveedor principal en el diccionario. Conforme agregues opciones de otros distribuidores para un mismo producto maestro, aparecerán automáticamente en esta comparativa.")
                
        with tab_h3:
            st.subheader("🏢 Catálogo y Tarifas Vigentes por Proveedor")
            provs_lista = sorted(list(df_eq["Proveedor"].dropna().unique()))
            prov_cat = st.selectbox("Selecciona un Distribuidor:", provs_lista, key="sel_catalogo_prov")
            
            sub_cat = df_eq[df_eq["Proveedor"] == prov_cat].copy()
            sub_cat["Precio_Actual"] = pd.to_numeric(sub_cat["Precio_Actual"], errors='coerce').fillna(0.0)
            
            k_c1, k_c2 = st.columns(2)
            k_c1.metric("Artículos Suministrados", len(sub_cat))
            k_c2.metric("Precio Medio de Catálogo", f"{sub_cat['Precio_Actual'].mean():.2f} €")
            
            st.dataframe(
                sub_cat[["Referencia_Blitz", "Producto_Maestro_Blitz", "Sinonimo_Proveedor", "Precio_Actual", "Unidad_Compra", "Factor_Multiplicador", "Unidad_Inventario"]],
                use_container_width=True,
                column_config={
                    "Referencia_Blitz": st.column_config.TextColumn("Ref."),
                    "Producto_Maestro_Blitz": st.column_config.TextColumn("Producto Maestro"),
                    "Sinonimo_Proveedor": st.column_config.TextColumn("Nombre en Albarán"),
                    "Precio_Actual": st.column_config.NumberColumn("Precio Tarifa (€)", format="%.2f €")
                }
            )
    else:
        st.warning("No se encontró el archivo de histórico de precios.")
