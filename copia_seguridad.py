import os
import shutil
import zipfile
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "Copia_de_Seguridad")

FILES_TO_BACKUP = [
    "panel.py",
    "notificaciones.py",
    "sync_repo.py",
    "copia_seguridad.py",
    "requirements.txt",
    "Equivalencias.csv",
    "Stock_Actual.csv",
    "Historico_Precios.csv",
    "Recetas.csv",
    "Stock_Minimo.csv",
    "Precios_Venta.csv",
    "blitz_logo.jpg",
    "blitz_icon.ico",
    "Catalogo_Pedidos.csv",
    "Pedidos_Centros.json"
]

def realizar_copia_seguridad(motivo="Programada"):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    hoy = datetime.datetime.now()
    fecha_str = hoy.strftime("%Y-%m-%d")
    
    zip_semanal = os.path.join(BACKUP_DIR, f"Copia_Blitz_Stock_{fecha_str}.zip")
    zip_ultima = os.path.join(BACKUP_DIR, "Copia_Blitz_Stock_ULTIMA.zip")
    
    try:
        with zipfile.ZipFile(zip_semanal, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in FILES_TO_BACKUP:
                p = os.path.join(BASE_DIR, f)
                if os.path.exists(p):
                    zf.write(p, arcname=f)
            
            secrets_p = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
            if os.path.exists(secrets_p):
                zf.write(secrets_p, arcname=os.path.join(".streamlit", "secrets.toml"))
                
        shutil.copy2(zip_semanal, zip_ultima)
        
        # Guardar registro de la fecha
        registro_p = os.path.join(BACKUP_DIR, "registro_copias.txt")
        with open(registro_p, "a", encoding="utf-8") as f:
            f.write(f"[{hoy.strftime('%Y-%m-%d %H:%M:%S')}] Copia creada ({motivo}): {os.path.basename(zip_semanal)}\n")
            
        print(f"[Copia de Seguridad] Guardada exitosamente: {zip_semanal}")
        return True
    except Exception as e:
        print(f"[Copia de Seguridad] Error al crear copia: {e}")
        return False

def verificar_y_ejecutar_semanal():
    """Comprueba si han pasado más de 7 días desde la última copia y la realiza si toca."""
    registro_p = os.path.join(BACKUP_DIR, "ultimo_backup.timestamp")
    tocar_hacer_copia = False
    
    if not os.path.exists(registro_p):
        tocar_hacer_copia = True
    else:
        try:
            with open(registro_p, "r", encoding="utf-8") as f:
                ts = float(f.read().strip())
            dias_pasados = (datetime.datetime.now().timestamp() - ts) / (24 * 3600)
            if dias_pasados >= 7.0:
                tocar_hacer_copia = True
        except Exception:
            tocar_hacer_copia = True
            
    if tocar_hacer_copia:
        ok = realizar_copia_seguridad(motivo="Semanal Automática")
        if ok:
            try:
                with open(registro_p, "w", encoding="utf-8") as f:
                    f.write(str(datetime.datetime.now().timestamp()))
            except Exception:
                pass

if __name__ == "__main__":
    realizar_copia_seguridad("Manual")
