import os
import time
import json
import csv
import shutil
import urllib.request
import urllib.parse
from win11toast import toast
import functools

print = functools.partial(print, flush=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MAPA_CENTROS = {
    "Entrada_Juan_Borbon": "Blitz Juan de Borbón",
    "Entrada_Ronda_Sur": "Blitz Ronda Sur",
    "Entrada_FoodTruck_1": "Food Truck Grande",
    "Entrada_FoodTruck_2": "Food Truck Pequeña",
    "Albaranes_Pendientes": "Albaranes Pendientes"
}

CARPETAS_ENTRADA = [os.path.join(BASE_DIR, k) for k in MAPA_CENTROS.keys()]

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

def enviar_telegram(texto):
    cfg = cargar_configuracion()
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()
    if not token or not chat_id:
        print("[Telegram] Token o Chat ID no configurados.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "HTML"
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            print("[Telegram] Mensaje enviado con éxito.")
            return resp.status == 200
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False

def procesar_nuevo_albaran(ruta_completa):
    nom_archivo = os.path.basename(ruta_completa)
    nom_carpeta = os.path.basename(os.path.dirname(ruta_completa))
    centro = MAPA_CENTROS.get(nom_carpeta, nom_carpeta)
    rel_path = os.path.join(nom_carpeta, nom_archivo)
    
    print(f"\n[ALBARÁN DETECTADO] {nom_archivo} en {centro}")
    
    # 1. ENVIAR AVISO INMEDIATO A TELEGRAM (SIN ESPERAS, < 1 seg, formato HTML seguro y UTF-8)
    mensaje = (
        f"🔔 <b>¡TIENES UN ALBARÁN PENDIENTE!</b>\n\n"
        f"📍 <b>Centro:</b> {centro}\n"
        f"📄 <b>Archivo:</b> <code>{nom_archivo}</code>\n\n"
        f"👀 <i>Foto subida desde el centro. Ya disponible en Blitz Stock para revisar y archivar.</i>"
    )
    enviar_telegram(mensaje)
    
    # 2. Notificación local en Windows (no bloqueante)
    try:
        import threading
        threading.Thread(target=lambda: toast("🍔 Blitz Stock", f"Nuevo albarán en {centro}: {nom_archivo}", icon="🍔", duration="short"), daemon=True).start()
    except Exception:
        pass
        
    # 3. Sincronizar de inmediato a GitHub para que aparezca en Streamlit Cloud
    try:
        from sync_repo import sync_file
        sync_file(rel_path, f"Nuevo albarán en {centro}: {nom_archivo}")
    except Exception as e:
        print(f"[GitHub Sync] Error: {e}")

def limpiar_albaranes_archivados_local():
    """Mueve a Albaranes_Procesados cualquier archivo local que ya haya sido registrado en compras."""
    archivos_procesados = set()
    compras_csv = os.path.join(BASE_DIR, "Registro_Albaranes_Compras.csv")
    if os.path.exists(compras_csv):
        try:
            with open(compras_csv, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    arch = r.get("Archivo", "").strip()
                    if arch:
                        archivos_procesados.add(arch)
        except Exception:
            pass
            
    carpeta_procesados = os.path.join(BASE_DIR, "Albaranes_Procesados")
    for carpeta in CARPETAS_ENTRADA:
        if os.path.exists(carpeta):
            for f in os.listdir(carpeta):
                if f in archivos_procesados:
                    ruta_src = os.path.join(carpeta, f)
                    ruta_dst = os.path.join(carpeta_procesados, f)
                    if os.path.exists(ruta_dst):
                        base_n, ext_n = os.path.splitext(f)
                        ruta_dst = os.path.join(carpeta_procesados, f"{base_n}_{int(time.time())}{ext_n}")
                    try:
                        shutil.move(ruta_src, ruta_dst)
                        print(f"[Vigilante] Movido albarán ya archivado a Procesados: {f}")
                    except Exception:
                        pass

def vigilar_carpetas():
    print("==================================================")
    print("   VIGILANTE BLITZ STOCK ACTIVO (AVISOS TELEGRAM)")
    print("==================================================")
    archivos_conocidos = set()
    
    # Lectura inicial de lo que ya está en cola para no duplicar avisos al arrancar
    for carpeta in CARPETAS_ENTRADA:
        if os.path.exists(carpeta):
            for f in os.listdir(carpeta):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    archivos_conocidos.add(os.path.join(carpeta, f))
                    
    print(f"Estado inicial: {len(archivos_conocidos)} albaranes existentes monitorizados.")
    
    # Comprobación de copia de seguridad semanal al arrancar
    try:
        from copia_seguridad import verificar_y_ejecutar_semanal
        verificar_y_ejecutar_semanal()
    except Exception as e:
        print(f"[Backup] Error: {e}")
        
    ciclo_backup = 0
    while True:
        time.sleep(3) # Comprobar cada 3 segundos
        
        archivos_actuales = set()
        for carpeta in CARPETAS_ENTRADA:
            if os.path.exists(carpeta):
                for f in os.listdir(carpeta):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        archivos_actuales.add(os.path.join(carpeta, f))
                        
        nuevos = archivos_actuales - archivos_conocidos
        
        if nuevos:
            for ruta_nueva in nuevos:
                try:
                    procesar_nuevo_albaran(ruta_nueva)
                except Exception as e:
                    print(f"Error procesando {ruta_nueva}: {e}")
                    
        archivos_conocidos = archivos_actuales
        
        # Limpiar albaranes que ya hayan sido archivados en compras
        if ciclo_backup % 5 == 0:
            try:
                limpiar_albaranes_archivados_local()
            except Exception:
                pass
        
        ciclo_backup += 1
        if ciclo_backup >= 1200: # ~1 hora
            ciclo_backup = 0
            try:
                from copia_seguridad import verificar_y_ejecutar_semanal
                verificar_y_ejecutar_semanal()
            except Exception as e:
                pass
            try:
                import modulo_alertas_stock
                modulo_alertas_stock.disparar_alertas_externas_si_corresponde(minutos_cooldown=120)
            except Exception as e:
                print(f"[Alertas Stock Background] Error: {e}")

if __name__ == "__main__":
    vigilar_carpetas()
