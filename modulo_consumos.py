# -*- coding: utf-8 -*-
"""
MÓDULO: Control de Consumos y Ratio Compras vs Ventas (Food Cost)
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_VENTAS = os.path.join(BASE_DIR, "Registro_Ventas_Semanales.csv")
ARCHIVO_COMPRAS_ALBARANES = os.path.join(BASE_DIR, "Registro_Albaranes_Compras.csv")
ARCHIVO_CONFIG_CONSUMOS = os.path.join(BASE_DIR, "Config_Consumos.json")

# Umbrales por defecto (33% óptimo según instrucción explícita de Salva)
UMBRAL_OPTIMO_DEFECTO = 33.0
UMBRAL_ALERTA_DEFECTO = 38.0

CENTROS_LISTA = [
    "🏢 Total Empresa (Global)",
    "📍 Blitz Ronda Sur",
    "📍 Blitz Juan de Borbón"
]

MAPA_CENTROS_NORMALIZADOS = {
    "ronda sur": "Blitz Ronda Sur",
    "blitz ronda sur": "Blitz Ronda Sur",
    "juan de borbon": "Blitz Juan de Borbón",
    "juan de borbón": "Blitz Juan de Borbón",
    "borbon": "Blitz Juan de Borbón",
    "borbón": "Blitz Juan de Borbón",
    "blitz juan de borbón": "Blitz Juan de Borbón"
}

def normalizar_nombre_centro(centro_raw):
    if not centro_raw:
        return "Blitz Ronda Sur"
    c_low = str(centro_raw).strip().lower()
    for k, v in MAPA_CENTROS_NORMALIZADOS.items():
        if k in c_low or c_low in k:
            return v
    return str(centro_raw).strip()

def cargar_config_consumos():
    """Carga los umbrales configurables dejando la puerta abierta a cambios."""
    if os.path.exists(ARCHIVO_CONFIG_CONSUMOS):
        try:
            with open(ARCHIVO_CONFIG_CONSUMOS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "umbral_optimo": UMBRAL_OPTIMO_DEFECTO,
        "umbral_alerta": UMBRAL_ALERTA_DEFECTO
    }

def guardar_config_consumos(optimo, alerta):
    """Guarda la configuración modificada por el usuario."""
    try:
        data = {
            "umbral_optimo": float(optimo),
            "umbral_alerta": float(alerta)
        }
        with open(ARCHIVO_CONFIG_CONSUMOS, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False

def render_html_seguro(html_str):
    """Renderiza HTML eliminando cualquier sangría accidental para que Markdown nunca lo confunda con un bloque de código."""
    if not html_str:
        return
    html_limpio = "".join(l.strip() for l in html_str.splitlines() if l.strip())
    if hasattr(st, "html"):
        st.html(html_limpio)
    else:
        st.markdown(html_limpio, unsafe_allow_html=True)

# ==========================================
# CÁLCULO DE SEMANAS OPERATIVAS (MIÉRCOLES A DOMINGO)
# ==========================================
def calcular_ciclo_operativo(fecha_obj):
    """
    Hostelería Blitz: Apertura de Miércoles a Domingo.
    Calcula el inicio (miércoles) y fin (domingo/martes) de la semana operativa.
    El mes se atribuye al mes del fin de semana (viernes/sábado/domingo).
    """
    if isinstance(fecha_obj, str):
        try:
            # Formatos soportados: DD/MM/YYYY o YYYY-MM-DD
            if "/" in fecha_obj:
                partes = fecha_obj.split("/")
                if len(partes[0]) == 4:
                    fecha_obj = datetime.date(int(partes[0]), int(partes[1]), int(partes[2]))
                else:
                    fecha_obj = datetime.date(int(partes[2]), int(partes[1]), int(partes[0]))
            elif "-" in fecha_obj:
                partes = fecha_obj.split("-")
                fecha_obj = datetime.date(int(partes[0]), int(partes[1]), int(partes[2]))
        except Exception:
            fecha_obj = datetime.date.today()

    # weekday(): Lunes=0, Martes=1, Miércoles=2, Jueves=3, Viernes=4, Sábado=5, Domingo=6
    offset = (fecha_obj.weekday() - 2) % 7
    miercoles = fecha_obj - timedelta(days=offset)
    domingo = miercoles + timedelta(days=4)
    fin_ciclo = miercoles + timedelta(days=6) # hasta el martes siguiente

    # El mes operativo se ancla al fin de semana (sábado)
    sabado = miercoles + timedelta(days=3)
    meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    mes_nombre = meses_es[sabado.month - 1]
    año = sabado.year

    # Número de semana del mes: semana 1, 2, 3, 4, 5
    primer_dia_mes = datetime.date(año, sabado.month, 1)
    offset_mes = (primer_dia_mes.weekday() - 2) % 7
    primer_miercoles = primer_dia_mes - timedelta(days=offset_mes)
    num_semana = max(1, int((miercoles - primer_miercoles).days // 7) + 1)

    id_semana = f"{año}-M{sabado.month:02d}-Sem{num_semana}"
    etiqueta = f"Semana {num_semana} ({miercoles.strftime('%d/%m')} al {domingo.strftime('%d/%m')})"

    return {
        "id_semana": id_semana,
        "num_semana": num_semana,
        "etiqueta": etiqueta,
        "mes": mes_nombre,
        "mes_num": sabado.month,
        "año": año,
        "fecha_inicio": miercoles.strftime("%d/%m/%Y"),
        "fecha_fin": domingo.strftime("%d/%m/%Y"),
        "fecha_inicio_obj": miercoles,
        "fecha_fin_obj": domingo
    }

# ==========================================
# INICIALIZACIÓN Y PERSISTENCIA DE DATOS
# ==========================================
def inicializar_datos_si_no_existen():
    """Si no existen los CSV, crea la estructura e inserta el histórico de Octubre."""
    os.makedirs(BASE_DIR, exist_ok=True)
    
    # 1. Registro de Ventas Semanales
    if not os.path.exists(ARCHIVO_VENTAS) or os.path.getsize(ARCHIVO_VENTAS) == 0:
        with open(ARCHIVO_VENTAS, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Id_Semana", "Num_Semana", "Fecha_Inicio", "Fecha_Fin", "Mes", "Año", "Centro", "Ventas", "Observaciones"])
            
            # Datos reales de Octubre (Excel Salva)
            # Ronda Sur
            writer.writerow(["2026-M10-Sem1", "1", "02/10/2026", "06/10/2026", "Octubre", "2026", "Blitz Ronda Sur", "7048.40", ""])
            writer.writerow(["2026-M10-Sem2", "2", "09/10/2026", "13/10/2026", "Octubre", "2026", "Blitz Ronda Sur", "5825.09", ""])
            writer.writerow(["2026-M10-Sem3", "3", "16/10/2026", "20/10/2026", "Octubre", "2026", "Blitz Ronda Sur", "5471.33", ""])
            writer.writerow(["2026-M10-Sem4", "4", "23/10/2026", "27/10/2026", "Octubre", "2026", "Blitz Ronda Sur", "6187.51", ""])
            writer.writerow(["2026-M10-Sem5", "5", "30/10/2026", "03/11/2026", "Octubre", "2026", "Blitz Ronda Sur", "6869.46", ""])
            
            # Juan de Borbón
            writer.writerow(["2026-M10-Sem1", "1", "02/10/2026", "06/10/2026", "Octubre", "2026", "Blitz Juan de Borbón", "9061.49", ""])
            writer.writerow(["2026-M10-Sem2", "2", "09/10/2026", "13/10/2026", "Octubre", "2026", "Blitz Juan de Borbón", "8439.09", ""])
            writer.writerow(["2026-M10-Sem3", "3", "16/10/2026", "20/10/2026", "Octubre", "2026", "Blitz Juan de Borbón", "8151.70", ""])
            writer.writerow(["2026-M10-Sem4", "4", "23/10/2026", "27/10/2026", "Octubre", "2026", "Blitz Juan de Borbón", "8367.77", ""])
            writer.writerow(["2026-M10-Sem5", "5", "30/10/2026", "03/11/2026", "Octubre", "2026", "Blitz Juan de Borbón", "9033.10", ""])

    # 2. Registro de Albaranes de Compras
    if not os.path.exists(ARCHIVO_COMPRAS_ALBARANES) or os.path.getsize(ARCHIVO_COMPRAS_ALBARANES) == 0:
        with open(ARCHIVO_COMPRAS_ALBARANES, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Id_Albaran", "Fecha", "Proveedor", "Centro", "Base_Imponible", "Semana_Operativa", "Archivo", "Notas"])
            
            # Datos reales de compras desglosadas por proveedor de Octubre (Excel Salva)
            compras_octubre = [
                # RONDA SUR
                ("04/10/2026", "Paco Rosa", "Blitz Ronda Sur", 658.98, "2026-M10-Sem1"),
                ("04/10/2026", "Jasa", "Blitz Ronda Sur", 206.94, "2026-M10-Sem1"),
                ("04/10/2026", "Cielo de Boca", "Blitz Ronda Sur", 227.00, "2026-M10-Sem1"),
                ("04/10/2026", "Lucas Caballero", "Blitz Ronda Sur", 192.80, "2026-M10-Sem1"),
                ("04/10/2026", "Makro", "Blitz Ronda Sur", 323.14, "2026-M10-Sem1"),
                ("04/10/2026", "Macanao", "Blitz Ronda Sur", 341.70, "2026-M10-Sem1"),
                ("04/10/2026", "Pedro Díaz", "Blitz Ronda Sur", 93.80, "2026-M10-Sem1"),
                
                ("11/10/2026", "Paco Rosa", "Blitz Ronda Sur", 1255.22, "2026-M10-Sem2"),
                ("11/10/2026", "Jasa", "Blitz Ronda Sur", 491.31, "2026-M10-Sem2"),
                ("11/10/2026", "Cielo de Boca", "Blitz Ronda Sur", 227.00, "2026-M10-Sem2"),
                ("11/10/2026", "Lucas Caballero", "Blitz Ronda Sur", 125.00, "2026-M10-Sem2"),
                ("11/10/2026", "Makro", "Blitz Ronda Sur", 379.81, "2026-M10-Sem2"),
                ("11/10/2026", "Coca-Cola", "Blitz Ronda Sur", 101.58, "2026-M10-Sem2"),
                ("11/10/2026", "Pedro Díaz", "Blitz Ronda Sur", 226.90, "2026-M10-Sem2"),
                ("11/10/2026", "Morales", "Blitz Ronda Sur", 109.25, "2026-M10-Sem2"),
                
                ("18/10/2026", "Paco Rosa", "Blitz Ronda Sur", 796.12, "2026-M10-Sem3"),
                ("18/10/2026", "Jasa", "Blitz Ronda Sur", 174.83, "2026-M10-Sem3"),
                ("18/10/2026", "Cielo de Boca", "Blitz Ronda Sur", 227.00, "2026-M10-Sem3"),
                ("18/10/2026", "Lucas Caballero", "Blitz Ronda Sur", 150.40, "2026-M10-Sem3"),
                ("18/10/2026", "Makro", "Blitz Ronda Sur", 362.65, "2026-M10-Sem3"),
                ("18/10/2026", "Coca-Cola", "Blitz Ronda Sur", 51.00, "2026-M10-Sem3"),
                ("18/10/2026", "Pedro Díaz", "Blitz Ronda Sur", 71.30, "2026-M10-Sem3"),
                ("18/10/2026", "Manzano", "Blitz Ronda Sur", 119.25, "2026-M10-Sem3"),
                ("18/10/2026", "Morales", "Blitz Ronda Sur", 105.00, "2026-M10-Sem3"),
                ("18/10/2026", "Riscales", "Blitz Ronda Sur", 55.80, "2026-M10-Sem3"),
                
                ("25/10/2026", "Paco Rosa", "Blitz Ronda Sur", 1109.80, "2026-M10-Sem4"),
                ("25/10/2026", "Jasa", "Blitz Ronda Sur", 193.48, "2026-M10-Sem4"),
                ("25/10/2026", "Cielo de Boca", "Blitz Ronda Sur", 227.00, "2026-M10-Sem4"),
                ("25/10/2026", "Lucas Caballero", "Blitz Ronda Sur", 119.01, "2026-M10-Sem4"),
                ("25/10/2026", "Makro", "Blitz Ronda Sur", 343.03, "2026-M10-Sem4"),
                ("25/10/2026", "Macanao", "Blitz Ronda Sur", 306.00, "2026-M10-Sem4"),
                ("25/10/2026", "Pedro Díaz", "Blitz Ronda Sur", 168.90, "2026-M10-Sem4"),
                ("25/10/2026", "Manzano", "Blitz Ronda Sur", 79.50, "2026-M10-Sem4"),
                ("25/10/2026", "Morales", "Blitz Ronda Sur", 81.00, "2026-M10-Sem4"),
                
                ("01/11/2026", "Paco Rosa", "Blitz Ronda Sur", 785.62, "2026-M10-Sem5"),
                ("01/11/2026", "Jasa", "Blitz Ronda Sur", 302.71, "2026-M10-Sem5"),
                ("01/11/2026", "Cielo de Boca", "Blitz Ronda Sur", 340.50, "2026-M10-Sem5"),
                ("01/11/2026", "Lucas Caballero", "Blitz Ronda Sur", 221.40, "2026-M10-Sem5"),
                ("01/11/2026", "Coca-Cola", "Blitz Ronda Sur", 117.76, "2026-M10-Sem5"),
                ("01/11/2026", "Pedro Díaz", "Blitz Ronda Sur", 138.60, "2026-M10-Sem5"),
                ("01/11/2026", "Morales", "Blitz Ronda Sur", 123.85, "2026-M10-Sem5"),
                ("01/11/2026", "Riscales", "Blitz Ronda Sur", 75.44, "2026-M10-Sem5"),
                
                # JUAN DE BORBÓN
                ("04/10/2026", "Paco Rosa", "Blitz Juan de Borbón", 1213.36, "2026-M10-Sem1"),
                ("04/10/2026", "Jasa", "Blitz Juan de Borbón", 158.40, "2026-M10-Sem1"),
                ("04/10/2026", "Cielo de Boca", "Blitz Juan de Borbón", 340.50, "2026-M10-Sem1"),
                ("04/10/2026", "Lucas Caballero", "Blitz Juan de Borbón", 308.80, "2026-M10-Sem1"),
                ("04/10/2026", "Makro", "Blitz Juan de Borbón", 364.00, "2026-M10-Sem1"),
                ("04/10/2026", "Macanao", "Blitz Juan de Borbón", 231.20, "2026-M10-Sem1"),
                ("04/10/2026", "Pedro Díaz", "Blitz Juan de Borbón", 168.90, "2026-M10-Sem1"),
                ("04/10/2026", "Zambú", "Blitz Juan de Borbón", 101.67, "2026-M10-Sem1"),
                ("04/10/2026", "Andrés Mármol", "Blitz Juan de Borbón", 109.10, "2026-M10-Sem1"),
                ("04/10/2026", "Morales", "Blitz Juan de Borbón", 162.00, "2026-M10-Sem1"),
                
                ("11/10/2026", "Paco Rosa", "Blitz Juan de Borbón", 1437.63, "2026-M10-Sem2"),
                ("11/10/2026", "Jasa", "Blitz Juan de Borbón", 491.46, "2026-M10-Sem2"),
                ("11/10/2026", "Cielo de Boca", "Blitz Juan de Borbón", 340.50, "2026-M10-Sem2"),
                ("11/10/2026", "Lucas Caballero", "Blitz Juan de Borbón", 150.40, "2026-M10-Sem2"),
                ("11/10/2026", "Makro", "Blitz Juan de Borbón", 428.76, "2026-M10-Sem2"),
                ("11/10/2026", "Coca-Cola", "Blitz Juan de Borbón", 122.53, "2026-M10-Sem2"),
                ("11/10/2026", "Pedro Díaz", "Blitz Juan de Borbón", 191.40, "2026-M10-Sem2"),
                ("11/10/2026", "Morales", "Blitz Juan de Borbón", 225.05, "2026-M10-Sem2"),
                
                ("18/10/2026", "Paco Rosa", "Blitz Juan de Borbón", 1226.01, "2026-M10-Sem3"),
                ("18/10/2026", "Jasa", "Blitz Juan de Borbón", 108.43, "2026-M10-Sem3"),
                ("18/10/2026", "Cielo de Boca", "Blitz Juan de Borbón", 340.50, "2026-M10-Sem3"),
                ("18/10/2026", "Lucas Caballero", "Blitz Juan de Borbón", 96.60, "2026-M10-Sem3"),
                ("18/10/2026", "Makro", "Blitz Juan de Borbón", 262.22, "2026-M10-Sem3"),
                ("18/10/2026", "Pedro Díaz", "Blitz Juan de Borbón", 146.40, "2026-M10-Sem3"),
                ("18/10/2026", "Manzano", "Blitz Juan de Borbón", 119.25, "2026-M10-Sem3"),
                ("18/10/2026", "Morales", "Blitz Juan de Borbón", 257.00, "2026-M10-Sem3"),
                ("18/10/2026", "Riscales", "Blitz Juan de Borbón", 55.80, "2026-M10-Sem3"),
                
                ("25/10/2026", "Paco Rosa", "Blitz Juan de Borbón", 333.53, "2026-M10-Sem4"),
                ("25/10/2026", "Jasa", "Blitz Juan de Borbón", 219.83, "2026-M10-Sem4"),
                ("25/10/2026", "Cielo de Boca", "Blitz Juan de Borbón", 340.50, "2026-M10-Sem4"),
                ("25/10/2026", "Lucas Caballero", "Blitz Juan de Borbón", 221.40, "2026-M10-Sem4"),
                ("25/10/2026", "Makro", "Blitz Juan de Borbón", 443.57, "2026-M10-Sem4"),
                ("25/10/2026", "Macanao", "Blitz Juan de Borbón", 231.20, "2026-M10-Sem4"),
                ("25/10/2026", "Pedro Díaz", "Blitz Juan de Borbón", 168.90, "2026-M10-Sem4"),
                ("25/10/2026", "Manzano", "Blitz Juan de Borbón", 79.50, "2026-M10-Sem4"),
                ("25/10/2026", "Nicolás Valero", "Blitz Juan de Borbón", 120.40, "2026-M10-Sem4"),
                ("25/10/2026", "Morales", "Blitz Juan de Borbón", 54.00, "2026-M10-Sem4"),
                
                ("01/11/2026", "Paco Rosa", "Blitz Juan de Borbón", 333.53, "2026-M10-Sem5"),
                ("01/11/2026", "Jasa", "Blitz Juan de Borbón", 282.56, "2026-M10-Sem5"),
                ("01/11/2026", "Cielo de Boca", "Blitz Juan de Borbón", 340.50, "2026-M10-Sem5"),
                ("01/11/2026", "Lucas Caballero", "Blitz Juan de Borbón", 75.52, "2026-M10-Sem5"),
                ("01/11/2026", "Makro", "Blitz Juan de Borbón", 482.85, "2026-M10-Sem5"),
                ("01/11/2026", "Coca-Cola", "Blitz Juan de Borbón", 124.16, "2026-M10-Sem5"),
                ("01/11/2026", "Pedro Díaz", "Blitz Juan de Borbón", 89.80, "2026-M10-Sem5"),
                ("01/11/2026", "Riscales", "Blitz Juan de Borbón", 55.80, "2026-M10-Sem5")
            ]
            
            for i, c in enumerate(compras_octubre, 1):
                writer.writerow([f"OCT-BAL-{i:03d}", c[0], c[1], c[2], f"{c[3]:.2f}", c[4], "", "Carga Balance Octubre"])

# Inicializar automáticamente al importar
inicializar_datos_si_no_existen()

# ==========================================
# REGISTRO DE ALBARANES ARCHIVADOS (AUTOMÁTICO)
# ==========================================
def registrar_albaran_archivado(fecha, proveedor, centro, base_imponible, archivo="", notas=""):
    """
    Hook llamado automáticamente desde 'Archivar Albarán' en el Radar de Albaranes.
    Imputa el gasto a la semana operativa correspondiente (Miércoles a Domingo).
    """
    try:
        centro_norm = normalizar_nombre_centro(centro)
        ciclo = calcular_ciclo_operativo(fecha)
        id_semana = ciclo["id_semana"]
        
        # Generar ID
        ahora = datetime.datetime.now()
        id_alb = f"ALB-{ahora.strftime('%y%m%d%H%M%S')}"
        
        # Formato fecha DD/MM/YYYY
        fecha_str = fecha if isinstance(fecha, str) else fecha.strftime("%d/%m/%Y")
        if "-" in fecha_str and len(fecha_str.split("-")[0]) == 4:
            p = fecha_str.split("-")
            fecha_str = f"{p[2]}/{p[1]}/{p[0]}"
            
        fila = [id_alb, fecha_str, str(proveedor).strip(), centro_norm, f"{float(base_imponible):.2f}", id_semana, archivo, notas]
        
        archivo_nuevo = not os.path.exists(ARCHIVO_COMPRAS_ALBARANES) or os.path.getsize(ARCHIVO_COMPRAS_ALBARANES) == 0
        with open(ARCHIVO_COMPRAS_ALBARANES, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if archivo_nuevo:
                writer.writerow(["Id_Albaran", "Fecha", "Proveedor", "Centro", "Base_Imponible", "Semana_Operativa", "Archivo", "Notas"])
            writer.writerow(fila)
        return True
    except Exception as e:
        print(f"Error al registrar albarán en compras: {e}")
        return False

def registrar_ventas_semana(id_semana, num_semana, f_ini, f_fin, mes, año, centro, ventas, observaciones=""):
    """Registra o actualiza las ventas ingresadas por el usuario para una semana operativa."""
    centro_norm = normalizar_nombre_centro(centro)
    filas = []
    encontrado = False
    
    if os.path.exists(ARCHIVO_VENTAS):
        with open(ARCHIVO_VENTAS, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("Id_Semana") == id_semana and normalizar_nombre_centro(r.get("Centro")) == centro_norm:
                    r["Ventas"] = f"{float(ventas):.2f}"
                    r["Observaciones"] = observaciones
                    encontrado = True
                filas.append(r)
                
    if not encontrado:
        filas.append({
            "Id_Semana": id_semana,
            "Num_Semana": str(num_semana),
            "Fecha_Inicio": f_ini,
            "Fecha_Fin": f_fin,
            "Mes": mes,
            "Año": str(año),
            "Centro": centro_norm,
            "Ventas": f"{float(ventas):.2f}",
            "Observaciones": observaciones
        })
        
    with open(ARCHIVO_VENTAS, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Id_Semana", "Num_Semana", "Fecha_Inicio", "Fecha_Fin", "Mes", "Año", "Centro", "Ventas", "Observaciones"])
        for r in filas:
            writer.writerow([r.get("Id_Semana"), r.get("Num_Semana"), r.get("Fecha_Inicio"), r.get("Fecha_Fin"), r.get("Mes"), r.get("Año"), r.get("Centro"), r.get("Ventas"), r.get("Observaciones")])
    return True

# ==========================================
# LECTURA Y CONSOLIDACIÓN DE DATOS
# ==========================================
def parsear_fecha_str(f_str):
    if not f_str:
        return datetime.date(2026, 10, 1)
    try:
        if "/" in f_str:
            p = f_str.split("/")
            if len(p[0]) == 4:
                return datetime.date(int(p[0]), int(p[1]), int(p[2]))
            return datetime.date(int(p[2]), int(p[1]), int(p[0]))
        elif "-" in f_str:
            p = f_str.split("-")
            return datetime.date(int(p[0]), int(p[1]), int(p[2]))
    except Exception:
        pass
    return datetime.date(2026, 10, 1)

def cargar_datos_balance(centro_filtro, fecha_desde, fecha_hasta):
    """
    Recupera y cruza compras y ventas en el rango de fechas seleccionado.
    Devuelve:
    - kpis: totales de ventas, compras, % consumo, margen
    - semanas_tabla: lista de semanas ordenadas con ventas, compras y %
    - compras_por_proveedor: diccionario proveedor -> total €
    - matriz_proveedores_semanas: desglose semanal idéntico al Excel de Salva
    """
    inicializar_datos_si_no_existen()
    config = cargar_config_consumos()
    optimo = config.get("umbral_optimo", UMBRAL_OPTIMO_DEFECTO)
    alerta = config.get("umbral_alerta", UMBRAL_ALERTA_DEFECTO)
    
    c_filtro_norm = normalizar_nombre_centro(centro_filtro)
    es_global = "total" in str(centro_filtro).lower() or "global" in str(centro_filtro).lower()
    
    # 1. Leer Compras de Albaranes
    compras_filtradas = []
    if os.path.exists(ARCHIVO_COMPRAS_ALBARANES):
        with open(ARCHIVO_COMPRAS_ALBARANES, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                f_obj = parsear_fecha_str(r.get("Fecha", ""))
                if fecha_desde <= f_obj <= fecha_hasta:
                    c_norm = normalizar_nombre_centro(r.get("Centro", ""))
                    if es_global or c_norm == c_filtro_norm:
                        try:
                            bi = float(r.get("Base_Imponible", 0.0))
                        except Exception:
                            bi = 0.0
                        compras_filtradas.append({
                            "Fecha": r.get("Fecha", ""),
                            "Fecha_obj": f_obj,
                            "Proveedor": r.get("Proveedor", "Varios").strip(),
                            "Centro": c_norm,
                            "Base_Imponible": bi,
                            "Semana_Operativa": r.get("Semana_Operativa", "")
                        })

    # 2. Leer Ventas Semanales
    ventas_filtradas = {} # (Id_Semana, Centro) -> float
    ventas_info = {} # Id_Semana -> {Num_Semana, Fecha_Inicio, Fecha_Fin, Mes, Observaciones}
    if os.path.exists(ARCHIVO_VENTAS):
        with open(ARCHIVO_VENTAS, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                f_ini = parsear_fecha_str(r.get("Fecha_Inicio", ""))
                f_fin = parsear_fecha_str(r.get("Fecha_Fin", ""))
                # Se incluye si solapa con el rango
                if (f_ini <= fecha_hasta and f_fin >= fecha_desde) or (fecha_desde <= f_ini <= fecha_hasta):
                    c_norm = normalizar_nombre_centro(r.get("Centro", ""))
                    if es_global or c_norm == c_filtro_norm:
                        id_sem = r.get("Id_Semana", "")
                        try:
                            v = float(r.get("Ventas", 0.0))
                        except Exception:
                            v = 0.0
                        key = (id_sem, c_norm)
                        ventas_filtradas[key] = ventas_filtradas.get(key, 0.0) + v
                        if id_sem not in ventas_info:
                            ventas_info[id_sem] = {
                                "Num_Semana": r.get("Num_Semana", "1"),
                                "Fecha_Inicio": r.get("Fecha_Inicio", ""),
                                "Fecha_Fin": r.get("Fecha_Fin", ""),
                                "Mes": r.get("Mes", ""),
                                "Observaciones": r.get("Observaciones", "")
                            }

    # 3. Agrupar Compras por Semana y por Proveedor
    semanas_keys = set()
    compras_por_semana = {} # id_semana -> float
    compras_por_proveedor = {} # prov -> float
    matriz_prov_sem = {} # prov -> {id_semana -> float}
    
    for c in compras_filtradas:
        sem_id = c["Semana_Operativa"]
        if not sem_id:
            ciclo = calcular_ciclo_operativo(c["Fecha_obj"])
            sem_id = ciclo["id_semana"]
        if sem_id not in ventas_info:
            ciclo = calcular_ciclo_operativo(c["Fecha_obj"])
            ventas_info[sem_id] = {
                "Num_Semana": str(ciclo["num_semana"]),
                "Fecha_Inicio": ciclo["fecha_inicio"],
                "Fecha_Fin": ciclo["fecha_fin"],
                "Mes": ciclo["mes"],
                "Observaciones": ""
            }
        semanas_keys.add(sem_id)
        bi = c["Base_Imponible"]
        compras_por_semana[sem_id] = compras_por_semana.get(sem_id, 0.0) + bi
        
        prov = c["Proveedor"]
        compras_por_proveedor[prov] = compras_por_proveedor.get(prov, 0.0) + bi
        if prov not in matriz_prov_sem:
            matriz_prov_sem[prov] = {}
        matriz_prov_sem[prov][sem_id] = matriz_prov_sem[prov].get(sem_id, 0.0) + bi

    for (sem_id, _) in ventas_filtradas.keys():
        semanas_keys.add(sem_id)

    # Ordenar semanas cronológicamente
    semanas_ordenadas = sorted(list(semanas_keys))
    
    # 4. Construir tabla de semanas
    semanas_tabla = []
    total_ventas = 0.0
    total_compras = 0.0
    
    for sem_id in semanas_ordenadas:
        v_total_sem = 0.0
        if es_global:
            for (s_id, c_n), v_val in ventas_filtradas.items():
                if s_id == sem_id:
                    v_total_sem += v_val
        else:
            v_total_sem = ventas_filtradas.get((sem_id, c_filtro_norm), 0.0)
            
        c_total_sem = compras_por_semana.get(sem_id, 0.0)
        
        ratio = (c_total_sem / v_total_sem * 100.0) if v_total_sem > 0 else 0.0
        
        # Semáforo
        if v_total_sem == 0 and c_total_sem == 0:
            color = "gray"
            estado = "Sin datos"
            badge = "⚪ Sin datos"
        elif v_total_sem == 0:
            color = "#ef4444"
            estado = "Sin ventas"
            badge = "🔴 Sin ventas"
        elif ratio <= optimo:
            color = "#10b981"
            estado = "Óptimo"
            badge = f"🟢 Óptimo ({ratio:.1f}%)"
        elif ratio <= alerta:
            color = "#f59e0b"
            estado = "Aceptable"
            badge = f"🟡 Aceptable ({ratio:.1f}%)"
        else:
            color = "#ef4444"
            estado = "Alto / Alerta"
            badge = f"🔴 Alerta ({ratio:.1f}%)"
            
        info = ventas_info.get(sem_id, {"Num_Semana": sem_id, "Fecha_Inicio": "", "Fecha_Fin": "", "Mes": "", "Observaciones": ""})
        num_s_raw = str(info.get('Num_Semana', ''))
        if "Sem" in num_s_raw:
            num_s_final = num_s_raw.split("Sem")[-1].replace("-", "").strip()
        else:
            num_s_final = num_s_raw
        etiqueta_semana = f"Semana {num_s_final}"
        fechas_rango = f"{info['Fecha_Inicio']} - {info['Fecha_Fin']}" if info['Fecha_Inicio'] else ""
        
        semanas_tabla.append({
            "id_semana": sem_id,
            "semana_nombre": etiqueta_semana,
            "fechas": fechas_rango,
            "ventas": v_total_sem,
            "compras": c_total_sem,
            "ratio": ratio,
            "badge": badge,
            "color": color,
            "observaciones": info.get("Observaciones", "")
        })
        
        total_ventas += v_total_sem
        total_compras += c_total_sem

    ratio_global = (total_compras / total_ventas * 100.0) if total_ventas > 0 else 0.0
    margen_bruto_euros = total_ventas - total_compras
    margen_bruto_porc = (100.0 - ratio_global) if total_ventas > 0 else 0.0
    
    kpis = {
        "total_ventas": total_ventas,
        "total_compras": total_compras,
        "ratio_global": ratio_global,
        "margen_bruto_euros": margen_bruto_euros,
        "margen_bruto_porc": margen_bruto_porc,
        "umbral_optimo": optimo,
        "umbral_alerta": alerta
    }

    return kpis, semanas_tabla, compras_por_proveedor, matriz_prov_sem, semanas_ordenadas

# ==========================================
# INTERFAZ GRÁFICA PRINCIPAL
# ==========================================
def render_modulo_consumos():
    header_html = """
    <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 22px 26px; border-radius: 14px; margin-bottom: 22px; border: 1px solid #334155; box-shadow: 0 4px 16px rgba(0,0,0,0.25);">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
            <div>
                <h1 style="color: #f8fafc; font-size: 1.85rem; font-weight: 800; margin: 0; letter-spacing: -0.5px; display: flex; align-items: center; gap: 10px;">
                    📊 Control de Consumos y Ratio Compras vs Ventas
                </h1>
                <p style="color: #94a3b8; font-size: 0.95rem; margin: 6px 0 0 0;">
                    Seguimiento semanal del <strong>Food Cost (% Compras)</strong>, margen bruto y desglose por proveedor (Ciclo operativo Miércoles a Domingo).
                </p>
            </div>
            <div style="background: rgba(30, 41, 59, 0.8); border: 1px solid #475569; padding: 6px 14px; border-radius: 20px;">
                <span style="color: #38bdf8; font-size: 0.85rem; font-weight: 700;">🎯 Nivel Óptimo: ≤ 33.0%</span>
            </div>
        </div>
    </div>
    """
    render_html_seguro(header_html)

    # 1. Selector de Centro (3 pestañas limpias: Total, Ronda Sur, Juan de Borbón)
    c_tab1, c_tab2, c_tab3 = st.tabs([
        "🏢 Total Empresa (Global)",
        "📍 Blitz Ronda Sur",
        "📍 Blitz Juan de Borbón"
    ])
    tab_names = ["🏢 Total Empresa (Global)", "📍 Blitz Ronda Sur", "📍 Blitz Juan de Borbón"]
    
    # Fecha mínima obligatoria: 01/10/2026 (según directriz de Salva)
    FECHA_MINIMA = datetime.date(2026, 10, 1)
    hoy = datetime.date.today()
    primer_dia_defecto = FECHA_MINIMA
    ultimo_dia_defecto = datetime.date(2026, 11, 1) if hoy < datetime.date(2026, 11, 1) else hoy

    if "filtro_fecha_desde" not in st.session_state or st.session_state.filtro_fecha_desde < FECHA_MINIMA:
        st.session_state.filtro_fecha_desde = primer_dia_defecto
    if "filtro_fecha_hasta" not in st.session_state or st.session_state.filtro_fecha_hasta < FECHA_MINIMA:
        st.session_state.filtro_fecha_hasta = ultimo_dia_defecto

    # Renderizar el contenido según el tab activo
    tabs = [c_tab1, c_tab2, c_tab3]
    for idx_tab, tab in enumerate(tabs):
        with tab:
            centro_actual = tab_names[idx_tab]
            renderizar_panel_centro(centro_actual)


def renderizar_panel_centro(centro_nombre):
    """Renderiza todas las gráficas circulares, KPIs y tablas para el centro seleccionado."""
    FECHA_MINIMA = datetime.date(2026, 10, 1)
    hoy = datetime.date.today()
    fecha_desde = st.session_state.filtro_fecha_desde
    fecha_hasta = st.session_state.filtro_fecha_hasta

    kpis, semanas_tabla, prov_compras, matriz_prov_sem, semanas_ordenadas = cargar_datos_balance(
        centro_nombre, fecha_desde, fecha_hasta
    )

    optimo = kpis["umbral_optimo"]
    alerta = kpis["umbral_alerta"]
    ratio_global = kpis["ratio_global"]
    total_ventas = kpis["total_ventas"]
    total_compras = kpis["total_compras"]
    margen_euros = kpis["margen_bruto_euros"]

    # Color del semáforo global
    if total_ventas == 0 and total_compras == 0:
        badge_ratio = "⚪ Sin Datos"
        color_ratio = "#94a3b8"
    elif total_ventas == 0:
        badge_ratio = "🔴 Sin Ventas Registradas"
        color_ratio = "#ef4444"
    elif ratio_global <= optimo:
        badge_ratio = f"🟢 ÓPTIMO ({ratio_global:.1f}%)"
        color_ratio = "#10b981"
    elif ratio_global <= alerta:
        badge_ratio = f"🟡 ACEPTABLE ({ratio_global:.1f}%)"
        color_ratio = "#f59e0b"
    else:
        badge_ratio = f"🔴 ALTO / ALERTA ({ratio_global:.1f}%)"
        color_ratio = "#ef4444"

    # TARJETAS DE MÉTRICAS KPI SUPERIORES
    kpis_html = f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin: 10px 0 20px 0;">
        <div style="background: #1e293b; border-left: 5px solid #3b82f6; padding: 14px 18px; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.15);">
            <div style="color: #94a3b8; font-size: 0.82rem; font-weight: 700; text-transform: uppercase;">💰 Total Ventas</div>
            <div style="color: #f8fafc; font-size: 1.55rem; font-weight: 800; margin-top: 4px;">{total_ventas:,.2f} €</div>
            <div style="color: #64748b; font-size: 0.75rem; margin-top: 2px;">{len(semanas_tabla)} semanas en rango</div>
        </div>
        <div style="background: #1e293b; border-left: 5px solid #f97316; padding: 14px 18px; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.15);">
            <div style="color: #94a3b8; font-size: 0.82rem; font-weight: 700; text-transform: uppercase;">📦 Total Compras (Albaranes)</div>
            <div style="color: #f8fafc; font-size: 1.55rem; font-weight: 800; margin-top: 4px;">{total_compras:,.2f} €</div>
            <div style="color: #64748b; font-size: 0.75rem; margin-top: 2px;">Materias primas y bebidas</div>
        </div>
        <div style="background: #1e293b; border-left: 5px solid {color_ratio}; padding: 14px 18px; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.15);">
            <div style="color: #94a3b8; font-size: 0.82rem; font-weight: 700; text-transform: uppercase;">🎯 % Ratio Consumo (Food Cost)</div>
            <div style="color: {color_ratio}; font-size: 1.55rem; font-weight: 800; margin-top: 4px;">{ratio_global:.2f} %</div>
            <div style="color: {color_ratio}; font-size: 0.78rem; font-weight: 700; margin-top: 2px;">{badge_ratio}</div>
        </div>
        <div style="background: #1e293b; border-left: 5px solid #10b981; padding: 14px 18px; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.15);">
            <div style="color: #94a3b8; font-size: 0.82rem; font-weight: 700; text-transform: uppercase;">📈 Margen Bruto Restante</div>
            <div style="color: #10b981; font-size: 1.55rem; font-weight: 800; margin-top: 4px;">{margen_euros:,.2f} €</div>
            <div style="color: #64748b; font-size: 0.75rem; margin-top: 2px;">{(100.0 - ratio_global) if total_ventas > 0 else 0.0:.1f}% de las ventas</div>
        </div>
    </div>
    """
    render_html_seguro(kpis_html)

    # 2. ENCABEZADO CON SELECTOR DE FECHAS (JUSTO ENCIMA DE LOS DONUTS)
    st.markdown("#### 📅 Período de Análisis (Filtro Desde / Hasta)")
    
    col_rap1, col_rap2, col_rap3, col_rap4 = st.columns([1, 1, 1, 1.2])
    with col_rap1:
        if st.button("📅 Mes Octubre 2026", use_container_width=True, key=f"btn_oct_{centro_nombre}"):
            st.session_state.filtro_fecha_desde = datetime.date(2026, 10, 1)
            st.session_state.filtro_fecha_hasta = datetime.date(2026, 11, 1)
            st.rerun()
    with col_rap2:
        if st.button("📅 Este Mes (Noviembre)", use_container_width=True, key=f"btn_mes_act_{centro_nombre}"):
            st.session_state.filtro_fecha_desde = datetime.date(hoy.year, hoy.month, 1) if datetime.date(hoy.year, hoy.month, 1) >= FECHA_MINIMA else FECHA_MINIMA
            st.session_state.filtro_fecha_hasta = hoy
            st.rerun()
    with col_rap3:
        if st.button("📅 Últimas 4 Semanas", use_container_width=True, key=f"btn_4sem_{centro_nombre}"):
            st.session_state.filtro_fecha_desde = max(FECHA_MINIMA, hoy - timedelta(days=28))
            st.session_state.filtro_fecha_hasta = hoy
            st.rerun()
    with col_rap4:
        if st.button("📅 Todo el Histórico", use_container_width=True, key=f"btn_todo_{centro_nombre}"):
            st.session_state.filtro_fecha_desde = FECHA_MINIMA
            st.session_state.filtro_fecha_hasta = hoy + timedelta(days=30)
            st.rerun()

    # Inputs "Desde" y "Hasta" con fecha mínima fijada en 01/10/2026
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        f_desde_in = st.date_input(
            "📅 Fecha DESDE (Escribe o pulsa el icono de calendario):",
            value=st.session_state.filtro_fecha_desde,
            min_value=FECHA_MINIMA,
            format="DD/MM/YYYY",
            key=f"input_date_desde_{centro_nombre}"
        )
        if f_desde_in != st.session_state.filtro_fecha_desde:
            st.session_state.filtro_fecha_desde = f_desde_in
            st.rerun()

    with col_f2:
        f_hasta_in = st.date_input(
            "📅 Fecha HASTA (Escribe o pulsa el icono de calendario):",
            value=st.session_state.filtro_fecha_hasta,
            min_value=FECHA_MINIMA,
            format="DD/MM/YYYY",
            key=f"input_date_hasta_{centro_nombre}"
        )
        if f_hasta_in != st.session_state.filtro_fecha_hasta:
            st.session_state.filtro_fecha_hasta = f_hasta_in
            st.rerun()

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # 3. GRÁFICAS DE CÍRCULO (DONUT / TARTA)
    st.markdown("#### 🍩 Gráficas Circulares de Ratio y Reparto")
    col_g1, col_g2 = st.columns(2)

    # Intentar cargar Plotly si está disponible
    plotly_disponible = False
    try:
        import plotly.graph_objects as go
        plotly_disponible = True
    except Exception:
        plotly_disponible = False

    # GRÁFICA CIRCULAR 1: RATIO VENTAS VS COMPRAS (FOOD COST)
    with col_g1:
        st.markdown("**Ratio Ventas vs Compras (% Food Cost)**")
        if plotly_disponible and total_ventas > 0:
            compras_val = total_compras
            margen_val = max(0.0, total_ventas - total_compras)
            
            fig_ratio = go.Figure(data=[go.Pie(
                labels=['Compras (Food Cost)', 'Margen Bruto Restante'],
                values=[compras_val, margen_val],
                hole=0.58,
                marker=dict(colors=[color_ratio, '#10b981']),
                hoverinfo='label+percent+value',
                textinfo='percent',
                textfont=dict(size=14, color='white', family='Inter, sans-serif')
            )])
            fig_ratio.update_layout(
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
                margin=dict(t=15, b=30, l=15, r=15),
                height=290,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                annotations=[dict(
                    text=f"<b>{ratio_global:.1f}%</b><br><span style='font-size:10px; color:#94a3b8;'>Food Cost</span>",
                    x=0.5, y=0.5,
                    font_size=18,
                    font_color=color_ratio,
                    showarrow=False
                )]
            )
            st.plotly_chart(fig_ratio, use_container_width=True, key=f"donut_ratio_{centro_nombre}")
        else:
            # Versión visual nativa en HTML5 si Plotly no estuviera disponible
            st.markdown(f"""
            <div style="background: #1e293b; border-radius: 12px; padding: 22px; text-align: center; border: 1px solid #334155;">
                <div style="font-size: 2.4rem; font-weight: 900; color: {color_ratio};">{ratio_global:.1f} %</div>
                <div style="color: #f8fafc; font-weight: 700; margin-top: 4px;">Ratio de Compras vs Ventas</div>
                <div style="margin: 14px auto; width: 85%; background: #334155; border-radius: 10px; height: 16px; overflow: hidden; display: flex;">
                    <div style="width: {min(100.0, ratio_global):.1f}%; background: {color_ratio};"></div>
                    <div style="width: {max(0.0, 100.0 - ratio_global):.1f}%; background: #10b981;"></div>
                </div>
                <div style="display: flex; justify-content: space-around; font-size: 0.85rem; color: #94a3b8;">
                    <span>🔴 Compras: <strong>{total_compras:,.2f} €</strong></span>
                    <span>🟢 Margen: <strong>{margen_euros:,.2f} €</strong></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # GRÁFICA CIRCULAR 2: REPARTO DE COMPRAS POR PROVEEDOR
    with col_g2:
        st.markdown("**Reparto de Compras por Proveedor**")
        if prov_compras and total_compras > 0:
            # Top proveedores y agrupar pequeños en 'Otros'
            prov_ordenados = sorted(prov_compras.items(), key=lambda x: x[1], reverse=True)
            top_provs = prov_ordenados[:6]
            otros_total = sum(v for k, v in prov_ordenados[6:])
            labels_p = [p[0] for p in top_provs]
            values_p = [p[1] for p in top_provs]
            if otros_total > 0:
                labels_p.append("Otros Proveedores")
                values_p.append(otros_total)

            if plotly_disponible:
                colores_pie = ['#3b82f6', '#f59e0b', '#10b981', '#ec4899', '#8b5cf6', '#06b6d4', '#64748b']
                fig_prov = go.Figure(data=[go.Pie(
                    labels=labels_p,
                    values=values_p,
                    hole=0.48,
                    marker=dict(colors=colores_pie[:len(labels_p)]),
                    hoverinfo='label+percent+value',
                    textinfo='percent',
                    textfont=dict(size=12, color='white')
                )])
                fig_prov.update_layout(
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
                    margin=dict(t=15, b=40, l=15, r=15),
                    height=290,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_prov, use_container_width=True, key=f"donut_prov_{centro_nombre}")
            else:
                st.markdown("""<div style="background: #1e293b; border-radius: 12px; padding: 14px; border: 1px solid #334155;">""", unsafe_allow_html=True)
                for pr, val in top_provs:
                    pct = (val / total_compras * 100.0) if total_compras > 0 else 0.0
                    st.write(f"• **{pr}**: {val:,.2f} € ({pct:.1f}%)")
                st.markdown("""</div>""", unsafe_allow_html=True)
        else:
            st.info("ℹ️ No hay compras registradas de albaranes en el período seleccionado.")

    st.divider()

    # 4. TABLA RESUMEN POR SEMANAS (IDÉNTICA AL EXCEL DE SALVA)
    st.markdown(f"#### 📋 Resumen Semanal de Ventas, Compras y % Consumo ({centro_nombre})")
    
    if semanas_tabla:
        filas_html = ""
        for s in semanas_tabla:
            v_fmt = f"{s['ventas']:,.2f} €" if s['ventas'] > 0 else "-"
            c_fmt = f"{s['compras']:,.2f} €" if s['compras'] > 0 else "-"
            r_fmt = f"{s['ratio']:.2f} %" if s['ventas'] > 0 else "-"
            filas_html += f"""
            <tr style="border-bottom: 1px solid #334155;">
                <td style="padding: 10px 14px; font-weight: 700; color: #f8fafc;">{s['semana_nombre']} <span style="font-size:0.75rem; color:#94a3b8; font-weight:normal;">({s['fechas']})</span></td>
                <td style="padding: 10px 14px; text-align: right; color: #38bdf8; font-weight: 700;">{v_fmt}</td>
                <td style="padding: 10px 14px; text-align: right; color: #fb923c; font-weight: 700;">{c_fmt}</td>
                <td style="padding: 10px 14px; text-align: right; font-weight: 800; color: {s['color']};">{r_fmt}</td>
                <td style="padding: 10px 14px; text-align: center;"><span style="background: rgba(30,41,59,0.9); border: 1px solid {s['color']}; color: {s['color']}; padding: 3px 10px; border-radius: 12px; font-size: 0.78rem; font-weight: 700;">{s['badge']}</span></td>
                <td style="padding: 10px 14px; color: #94a3b8; font-size: 0.85rem;">{s['observaciones']}</td>
            </tr>
            """

        tot_v_fmt = f"{total_ventas:,.2f} €"
        tot_c_fmt = f"{total_compras:,.2f} €"
        tot_r_fmt = f"{ratio_global:.2f} %"

        tabla_html = f"""
        <div style="overflow-x: auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; box-shadow: 0 4px 10px rgba(0,0,0,0.2);">
            <table style="width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 0.9rem;">
                <thead>
                    <tr style="background: #0f172a; border-bottom: 2px solid #475569; color: #94a3b8; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.5px;">
                        <th style="padding: 12px 14px; text-align: left;">Semana Operativa</th>
                        <th style="padding: 12px 14px; text-align: right;">Ventas (€)</th>
                        <th style="padding: 12px 14px; text-align: right;">Compras (€)</th>
                        <th style="padding: 12px 14px; text-align: right;">% Consumo</th>
                        <th style="padding: 12px 14px; text-align: center;">Semáforo</th>
                        <th style="padding: 12px 14px; text-align: left;">Observaciones</th>
                    </tr>
                </thead>
                <tbody>
                    {filas_html}
                    <tr style="background: #0f172a; border-top: 2px solid #38bdf8; font-weight: 800; font-size: 0.98rem;">
                        <td style="padding: 14px; color: #f8fafc;">TOTAL PERÍODO</td>
                        <td style="padding: 14px; text-align: right; color: #38bdf8;">{tot_v_fmt}</td>
                        <td style="padding: 14px; text-align: right; color: #fb923c;">{tot_c_fmt}</td>
                        <td style="padding: 14px; text-align: right; color: {color_ratio};">{tot_r_fmt}</td>
                        <td style="padding: 14px; text-align: center;"><span style="color: {color_ratio};">{badge_ratio}</span></td>
                        <td style="padding: 14px; color: #94a3b8; font-size: 0.8rem;">Consolidado</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """
        render_html_seguro(tabla_html)
    else:
        st.info("ℹ️ No hay registros de ventas o compras para las fechas seleccionadas.")

    # 5. FORMULARIO RÁPIDO PARA INTRODUCIR O ACTUALIZAR LAS VENTAS DE UNA SEMANA
    with st.expander(f"➕ Introducir o Modificar Ventas Semanales ({centro_nombre})", expanded=False):
        st.markdown("Introduce las ventas de tu TPV o cierre semanal para calcular automáticamente el % de consumo:")
        col_v1, col_v2, col_v3 = st.columns([1.5, 1.2, 2])
        
        # Opciones de semanas calculadas a partir de la fecha seleccionada
        semanas_opciones = []
        fecha_cursor = fecha_desde
        while fecha_cursor <= fecha_hasta + timedelta(days=7):
            c_calc = calcular_ciclo_operativo(fecha_cursor)
            if c_calc["id_semana"] not in [x["id"] for x in semanas_opciones]:
                semanas_opciones.append({
                    "id": c_calc["id_semana"],
                    "label": f"{c_calc['etiqueta']} - {c_calc['mes']} {c_calc['año']}",
                    "data": c_calc
                })
            fecha_cursor += timedelta(days=7)
            
        with col_v1:
            sem_sel_label = st.selectbox(
                "Selecciona Semana:",
                [s["label"] for s in semanas_opciones],
                key=f"sel_sem_ventas_{centro_nombre}"
            )
            sem_sel_obj = next((s for s in semanas_opciones if s["label"] == sem_sel_label), semanas_opciones[0] if semanas_opciones else None)
            
        with col_v2:
            ventas_input = st.number_input(
                "Ventas Totales (€):",
                min_value=0.0,
                step=50.0,
                format="%.2f",
                key=f"val_ventas_{centro_nombre}"
            )
            
        with col_v3:
            obs_input = st.text_input(
                "Observaciones (opcional):",
                placeholder="Ej. Fin de semana de lluvia, puente...",
                key=f"obs_ventas_{centro_nombre}"
            )
            
        if st.button("💾 Guardar Ventas de la Semana", type="primary", key=f"btn_save_v_{centro_nombre}"):
            if sem_sel_obj and ventas_input > 0:
                d = sem_sel_obj["data"]
                # Si está en modo global, permitir elegir a cuál de los dos locales guardarlo
                centro_destino_guardado = centro_nombre
                if centro_nombre == "🏢 Total Empresa (Global)":
                    st.warning("⚠️ Selecciona la pestaña de un centro concreto (Ronda Sur o Juan de Borbón) para imputar las ventas exactas a ese local.")
                else:
                    registrar_ventas_semana(
                        d["id_semana"], d["num_semana"], d["fecha_inicio"], d["fecha_fin"],
                        d["mes"], d["año"], centro_destino_guardado, ventas_input, obs_input
                    )
                    st.success(f"✅ ¡Ventas de {ventas_input:,.2f} € guardadas para {centro_destino_guardado} en {d['etiqueta']}!")
                    import time; time.sleep(0.5)
                    st.rerun()

    # 6. TABLA INFERIOR DE DESGLOSE POR PROVEEDOR (SEMANA A SEMANA)
    st.markdown("#### 🛒 Desglose de Compras por Proveedor Semana a Semana")
    
    if matriz_prov_sem and semanas_ordenadas:
        # Encabezados de semanas
        th_semanas = "".join(f"<th style='padding: 10px 8px; text-align: right;'>{ventas_info_nombre(s)}</th>" for s in semanas_ordenadas)
        
        filas_prov_html = ""
        totales_columna = {s: 0.0 for s in semanas_ordenadas}
        total_absoluto = 0.0
        
        # Ordenar proveedores alfabéticamente o por volumen de gasto
        prov_lista = sorted(matriz_prov_sem.keys(), key=lambda p: sum(matriz_prov_sem[p].values()), reverse=True)
        
        for prov in prov_lista:
            total_fila_prov = 0.0
            td_semanas = ""
            for s in semanas_ordenadas:
                gasto = matriz_prov_sem[prov].get(s, 0.0)
                totales_columna[s] += gasto
                total_fila_prov += gasto
                txt_gasto = f"{gasto:,.2f} €" if gasto > 0 else "-"
                color_g = "#f8fafc" if gasto > 0 else "#64748b"
                td_semanas += f"<td style='padding: 8px 10px; text-align: right; color: {color_g};'>{txt_gasto}</td>"
                
            total_absoluto += total_fila_prov
            filas_prov_html += f"""
            <tr style="border-bottom: 1px solid #334155;">
                <td style="padding: 8px 12px; font-weight: 700; color: #f8fafc;">{prov}</td>
                {td_semanas}
                <td style="padding: 8px 12px; text-align: right; font-weight: 800; color: #fb923c; background: rgba(30,41,59,0.5);">{total_fila_prov:,.2f} €</td>
            </tr>
            """
            
        # Fila de totales
        td_totales_col = "".join(f"<td style='padding: 12px 10px; text-align: right; color: #fb923c;'>{totales_columna[s]:,.2f} €</td>" for s in semanas_ordenadas)
        
        tabla_prov_html = f"""
        <div style="overflow-x: auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; margin-top: 8px;">
            <table style="width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 0.86rem;">
                <thead>
                    <tr style="background: #0f172a; border-bottom: 2px solid #475569; color: #94a3b8; text-transform: uppercase; font-size: 0.75rem;">
                        <th style="padding: 10px 12px; text-align: left;">Proveedor</th>
                        {th_semanas}
                        <th style="padding: 10px 12px; text-align: right; color: #fb923c;">TOTAL</th>
                    </tr>
                </thead>
                <tbody>
                    {filas_prov_html}
                    <tr style="background: #0f172a; border-top: 2px solid #f97316; font-weight: 800;">
                        <td style="padding: 12px; color: #f8fafc;">TOTAL SEMANAL</td>
                        {td_totales_col}
                        <td style="padding: 12px; text-align: right; color: #f97316; font-size: 0.95rem;">{total_absoluto:,.2f} €</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """
        render_html_seguro(tabla_prov_html)
    else:
        st.info("ℹ️ No hay facturación desglosada por proveedor en este período.")

    # 7. EXPANDER DE CONFIGURACIÓN DE UMBRALES (DEJAR PUERTA ABIERTA A MODIFICACIONES)
    with st.expander("⚙️ Ajustes de Objetivos de Food Cost (Dejar la puerta abierta a cambios)", expanded=False):
        st.markdown("""
        Personaliza los límites porcentuales para el semáforo de tu hamburguesería:
        """)
        c_cfg1, c_cfg2, c_cfg3 = st.columns([2, 2, 1.5])
        with c_cfg1:
            nuevo_optimo = st.number_input(
                "Nivel Óptimo (%) - Verde hasta:",
                min_value=15.0,
                max_value=50.0,
                value=float(optimo),
                step=0.5,
                key=f"cfg_opt_{centro_nombre}"
            )
        with c_cfg2:
            nuevo_alerta = st.number_input(
                "Nivel Alerta (%) - Rojo a partir de:",
                min_value=25.0,
                max_value=60.0,
                value=float(alerta),
                step=0.5,
                key=f"cfg_alt_{centro_nombre}"
            )
        with c_cfg3:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            if st.button("💾 Guardar Umbrales", key=f"btn_save_cfg_{centro_nombre}", use_container_width=True):
                if nuevo_optimo < nuevo_alerta:
                    guardar_config_consumos(nuevo_optimo, nuevo_alerta)
                    st.success("✅ ¡Umbrales actualizados con éxito!")
                    import time; time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("El umbral óptimo debe ser menor que el umbral de alerta.")

def ventas_info_nombre(semana_id):
    """Devuelve un nombre corto para encabezados de tabla de proveedor (ej. 'Sem 1')."""
    if "Sem" in semana_id:
        return semana_id.split("Sem")[-1].replace("-", "").strip()
    return semana_id
