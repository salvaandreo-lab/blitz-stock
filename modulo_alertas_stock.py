import os
import time
import json
import urllib.request
import urllib.parse
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_STOCK = os.path.join(BASE_DIR, "Stock_Actual.csv")
ARCHIVO_STOCK_MINIMO = os.path.join(BASE_DIR, "Stock_Minimo.csv")
ARCHIVO_ESTADO_ALERTAS = os.path.join(BASE_DIR, ".estado_alertas.json")

def cargar_configuracion():
    secrets_file = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
    cfg = {}
    if os.path.exists(secrets_file):
        try:
            import tomllib
            with open(secrets_file, "rb") as f:
                cfg = tomllib.load(f)
        except Exception:
            pass
    return cfg

def obtener_articulos_bajo_minimo(centro=None):
    """
    Compara Stock_Actual.csv con Stock_Minimo.csv y devuelve un DataFrame
    con todos los productos que están en o por debajo del stock mínimo.
    """
    if not os.path.isfile(ARCHIVO_STOCK) or not os.path.isfile(ARCHIVO_STOCK_MINIMO):
        return pd.DataFrame()
        
    try:
        df_stock = pd.read_csv(ARCHIVO_STOCK, encoding='utf-8-sig', dtype=str).fillna("")
        df_min = pd.read_csv(ARCHIVO_STOCK_MINIMO, encoding='utf-8-sig', dtype=str).fillna("0.0")
        
        df_stock["Cantidad_Stock"] = pd.to_numeric(df_stock["Cantidad_Stock"], errors='coerce').fillna(0.0)
        df_min["Stock_Minimo"] = pd.to_numeric(df_min["Stock_Minimo"], errors='coerce').fillna(0.0)
        
        merged = pd.merge(df_stock, df_min, on=["Centro", "Producto_Maestro"], how="inner")
        
        if centro:
            merged = merged[merged["Centro"].str.lower() == str(centro).strip().lower()]
            
        bajo_minimo = merged[merged["Cantidad_Stock"] <= merged["Stock_Minimo"]].copy()
        
        if bajo_minimo.empty:
            return pd.DataFrame()
            
        bajo_minimo["Deficit"] = (bajo_minimo["Stock_Minimo"] - bajo_minimo["Cantidad_Stock"]).round(2)
        bajo_minimo["Es_Rotura"] = bajo_minimo["Cantidad_Stock"] <= 0
        
        # Ordenar primero por roturas críticas y luego por mayor déficit
        bajo_minimo = bajo_minimo.sort_values(by=["Es_Rotura", "Deficit"], ascending=[False, False])
        return bajo_minimo
    except Exception as e:
        print(f"[Error alertas stock] {e}")
        return pd.DataFrame()

def enviar_alerta_telegram_stock(df_bajo_minimo=None, origen="Panel"):
    """
    Envía un informe estructurado y legible a Telegram resumiendo los productos bajo mínimos.
    """
    if df_bajo_minimo is None:
        df_bajo_minimo = obtener_articulos_bajo_minimo()
        
    if df_bajo_minimo.empty:
        return False
        
    cfg = cargar_configuracion()
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()
    if not token or not chat_id:
        return False
        
    total_articulos = len(df_bajo_minimo)
    total_roturas = int(df_bajo_minimo["Es_Rotura"].sum())
    
    mensaje = (
        f"🚨 *ALERTA DE INVENTARIO BLITZ STOCK*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Se han detectado *{total_articulos} artículos* bajo stock mínimo.\n"
        f"🔴 *Roturas críticas (Stock 0):* {total_roturas}\n\n"
    )
    
    # Agrupar por Centro
    for centro, grupo in df_bajo_minimo.groupby("Centro"):
        roturas_c = int(grupo["Es_Rotura"].sum())
        mensaje += f"📍 *{centro}* ({len(grupo)} productos | {roturas_c} a cero):\n"
        
        # Mostrar los 5 más críticos por centro
        top_articulos = grupo.head(5)
        for _, r in top_articulos.iterrows():
            icono = "🔴" if r["Es_Rotura"] else "🟡"
            ud = r.get("Unidad_Inventario", "ud")
            mensaje += f"  {icono} _{r['Producto_Maestro']}_: `{r['Cantidad_Stock']:.1f}` / min: `{r['Stock_Minimo']:.1f}` {ud}\n"
            
        if len(grupo) > 5:
            mensaje += f"  _...y {len(grupo) - 5} artículos más bajo mínimos._\n"
        mensaje += "\n"
        
    mensaje += f"📱 _Consulta el asistente de pedidos en Blitz Stock para generar reposición._"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[Telegram Stock Error] {e}")
        return False

def enviar_alerta_windows_stock(df_bajo_minimo=None):
    """
    Lanza una notificación emergente nativa con sonido en Windows 11.
    """
    if df_bajo_minimo is None:
        df_bajo_minimo = obtener_articulos_bajo_minimo()
        
    if df_bajo_minimo.empty:
        return False
        
    total_articulos = len(df_bajo_minimo)
    total_roturas = int(df_bajo_minimo["Es_Rotura"].sum())
    
    # Texto de la notificación
    primeros_prods = ", ".join(df_bajo_minimo["Producto_Maestro"].head(3).tolist())
    cuerpo = f"{total_articulos} artículos bajo mínimos ({total_roturas} roturas críticas).\nEj: {primeros_prods}..."
    
    try:
        from win11toast import toast
        toast(
            "🚨 Blitz Stock - Alerta de Stock Mínimo",
            cuerpo,
            icon="🚨",
            duration="short"
        )
        return True
    except Exception as e:
        print(f"[Windows Toast Error] {e}")
        return False

def disparar_alertas_externas_si_corresponde(minutos_cooldown=60, forzar=False):
    """
    Dispara Telegram y Windows Toast si han pasado al menos X minutos desde la última alerta,
    o si se fuerza explícitamente (ej. tras registrar un cierre de ventas).
    """
    ahora = time.time()
    if not forzar and os.path.exists(ARCHIVO_ESTADO_ALERTAS):
        try:
            with open(ARCHIVO_ESTADO_ALERTAS, "r", encoding="utf-8") as f:
                datos = json.load(f)
                ultimo = datos.get("ultimo_aviso_stock", 0)
                if ahora - ultimo < (minutos_cooldown * 60):
                    return False
        except Exception:
            pass
            
    df_bajo = obtener_articulos_bajo_minimo()
    if df_bajo.empty:
        return False
        
    # Disparar alertas
    enviar_alerta_windows_stock(df_bajo)
    enviar_alerta_telegram_stock(df_bajo)
    
    # Guardar timestamp
    try:
        with open(ARCHIVO_ESTADO_ALERTAS, "w", encoding="utf-8") as f:
            json.dump({"ultimo_aviso_stock": ahora}, f)
    except Exception:
        pass
        
    return True
