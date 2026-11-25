"""
Batería de pruebas de regresión de solo lectura para Blitz Stock.
Verifica que ninguno de los errores ya solucionados vuelva a producirse,
sin modificar ningún CSV ni ejecutar la interfaz de Streamlit.
"""
import ast
import csv
import difflib
import hashlib
import json
import os
import py_compile
import re
import unicodedata
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PANEL_PATH = os.path.join(BASE_DIR, "panel.py")


def _cargar_funciones_panel():
    """Extrae funciones puras de panel.py via AST sin ejecutar código de Streamlit."""
    with open(PANEL_PATH, "r", encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src, filename=PANEL_PATH)

    objetivos = {
        "normalizar_texto",
        "normalizar_proveedor",
        "preparar_imagen_ia",
        "calcular_hash_archivo",
        "verificar_albaran_duplicado",
        "procesar_articulos_albaran_ia",
        "cargar_equivalencias",
        "seleccionar_variante_optima",
        "buscar_equivalencia",
    }

    ns = {
        "os": os,
        "csv": csv,
        "json": json,
        "re": re,
        "unicodedata": unicodedata,
        "difflib": difflib,
        "hashlib": hashlib,
        "Image": Image,
        "ImageEnhance": ImageEnhance,
        "ImageFilter": ImageFilter,
        "ImageOps": ImageOps,
        "BASE_DIR": BASE_DIR,
        "ARCHIVO_EQUIVALENCIAS": os.path.join(BASE_DIR, "Equivalencias.csv"),
        "ARCHIVO_COMPRAS_ALBARANES": os.path.join(BASE_DIR, "Registro_Albaranes_Compras.csv"),
        "ARCHIVO_HISTORICO_PRECIOS": os.path.join(BASE_DIR, "Historico_Precios.csv"),
        "CARPETA_PROCESADOS": os.path.join(BASE_DIR, "Albaranes_Procesados"),
        "CARPETA_DESCARTADOS": os.path.join(BASE_DIR, "Albaranes_Descartados"),
    }

    nodos_extraer = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "MAPA_PROVEEDORES_CANONICOS":
                    nodos_extraer.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in objetivos:
            nodos_extraer.append(node)

    mod = ast.Module(body=nodos_extraer, type_ignores=[])
    ast.fix_missing_locations(mod)
    exec(compile(mod, PANEL_PATH, "exec"), ns)
    return src, tree, ns


def test_01_sintaxis_modulos():
    for nombre in ["panel.py", "notificaciones.py", "modulo_consumos.py", "sync_repo.py"]:
        ruta = os.path.join(BASE_DIR, nombre)
        assert os.path.isfile(ruta), f"Falta archivo crítico: {nombre}"
        py_compile.compile(ruta, doraise=True)


def test_02_bloques_protegidos_intactos(src):
    assert "[BLOQUE PROTEGIDO]: CONVERSIÓN DE KILOS A CAJAS/BOLSAS" in src, (
        "Se ha eliminado o alterado el comentario/bloque protegido de conversión de kilos."
    )
    assert "[BLOQUE PROTEGIDO]: SELECCIÓN DE VARIANTE POR PRECIO" in src, (
        "Se ha eliminado o alterado el bloque protegido de selección de variante por precio."
    )


def test_03_sincronizacion_equivalencias_y_compras(src, tree):
    funciones_sync_obligatorio = {
        "guardar_nueva_equivalencia",
        "actualizar_precio_en_csv",
        "confirmar_borrado_diccionario",
    }
    encontradas = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in funciones_sync_obligatorio:
            encontradas.add(node.name)
            llamadas = [
                n.func.id
                for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            ]
            assert "_sincronizar_equivalencias_nube" in llamadas, (
                f"REGRESIÓN: {node.name}() no llama a _sincronizar_equivalencias_nube(). "
                "Los cambios hechos en la app web se perderían al reiniciar."
            )
    assert encontradas == funciones_sync_obligatorio, (
        f"Faltan funciones en panel.py: {funciones_sync_obligatorio - encontradas}"
    )
    assert 'sync_file("Stock_Actual.csv")' in src
    assert 'sync_file("Historico_Precios.csv")' in src
    assert 'sync_file("Registro_Albaranes_Compras.csv")' in src
    assert '_sincronizar_equivalencias_nube("Edicion manual de Equivalencias.csv")' in src


def test_04_multipagina_makro_y_cocacola(src):
    for marcador in [
        "pagina_actual",
        "total_paginas",
        "archivo_segunda_pagina",
        "chk_multi_",
        "ESPECIAL MAKRO Y COCA-COLA",
        "paginas_coinciden",
        "REGLA ANTI-MEZCLA OBLIGATORIA",
        "desajuste_paginas_msg",
    ]:
        assert marcador in src, f"REGRESIÓN multipágina: falta '{marcador}' en panel.py"

    notif_path = os.path.join(BASE_DIR, "notificaciones.py")
    with open(notif_path, "r", encoding="utf-8") as f:
        notif_src = f.read()
    assert 'arch.split("+")' in notif_src, (
        "REGRESIÓN en notificaciones.py: falta soporte para archivos combinados con '+'."
    )

    # Verificar que modulo_consumos soporta fechas con puntos (ej. Coca-Cola 20.11.2026)
    import modulo_consumos
    ciclo = modulo_consumos.calcular_ciclo_operativo("20.11.2026")
    assert ciclo["id_semana"].startswith("2026-M11-"), f"REGRESIÓN fecha con puntos: {ciclo}"


def test_05_detector_duplicados_5_niveles(ns):
    verificar = ns["verificar_albaran_duplicado"]

    # Albaranes reales de noviembre ya archivados: deben ser bloqueados aunque ruta_origen esté vacía
    es_dup1, _, tipo1 = verificar(
        ruta_origen="",
        proveedor="Pedro Diaz",
        num_albaran="A26/48078",
        centro="Blitz Juan de Borbón",
        total_bi=48.8,
        fecha_doc="04/11/2026",
        pagina_actual=1,
        total_paginas=1,
    )
    assert es_dup1 is True, f"REGRESIÓN duplicados: Pedro Diaz A26/48078 no fue bloqueado ({tipo1})"

    es_dup2, _, tipo2 = verificar(
        ruta_origen="",
        proveedor="Coca-Cola",
        num_albaran="4538642480",
        centro="Blitz Ronda Sur",
        total_bi=114.1,
        fecha_doc="06/11/2026",
        pagina_actual=1,
        total_paginas=1,
    )
    assert es_dup2 is True, f"REGRESIÓN duplicados: Coca-Cola 4538642480 no fue bloqueado ({tipo2})"

    # Albarán completamente nuevo: no debe dar falso positivo
    es_dup_nuevo, _, _ = verificar(
        ruta_origen="",
        proveedor="Proveedor Test Inexistente",
        num_albaran="ALB-REGRESION-999999",
        centro="Blitz Ronda Sur",
        total_bi=88.5,
        fecha_doc="25/11/2026",
        pagina_actual=1,
        total_paginas=1,
    )
    assert es_dup_nuevo is False, "REGRESIÓN: falso positivo de duplicado en albarán nuevo."

    # Albarán completo ya archivado (Makro 9-255722753 del 12/11): incluso enviando solo la 2/2 debe bloquearse
    es_dup_completo, _, _ = verificar(
        ruta_origen="",
        proveedor="Makro",
        num_albaran="9-255722753",
        centro="Blitz Juan de Borbón",
        total_bi=42.10,
        fecha_doc="12/11/2026",
        pagina_actual=2,
        total_paginas=2,
    )
    assert es_dup_completo is True, (
        "REGRESIÓN duplicados: 9-255722753 completo ya archivado no fue bloqueado al reenviar página 2/2."
    )

    # Continuación Página 2/2 de un albarán registrado explícitamente solo como Página 1/2: NO debe bloquearse
    import tempfile
    tmp_csv = tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8-sig", newline="")
    try:
        w = csv.writer(tmp_csv)
        w.writerow(["Id_Albaran", "Fecha", "Proveedor", "Centro", "Base_Imponible", "Semana_Operativa", "Archivo", "Num_Albaran", "Notas"])
        w.writerow(["ALB-TEST-P1", "25/11/2026", "Makro", "Blitz Juan de Borbón", "180.00", "2026-M11-Sem4", "test1.jpg", "9-999888777", "Albarán escaneado de Makro (Nº 9-999888777 - Pág 1/2)"])
        tmp_csv.close()
        orig_compras = ns["ARCHIVO_COMPRAS_ALBARANES"]
        ns["ARCHIVO_COMPRAS_ALBARANES"] = tmp_csv.name
        try:
            es_dup_pag2, _, _ = verificar(
                ruta_origen="",
                proveedor="Makro",
                num_albaran="9-999888777",
                centro="Blitz Juan de Borbón",
                total_bi=42.10,
                fecha_doc="25/11/2026",
                pagina_actual=2,
                total_paginas=2,
            )
            assert es_dup_pag2 is False, (
                "REGRESIÓN multipágina: la página 2/2 fue bloqueada erróneamente tras registrar solo Pág 1/2."
            )
        finally:
            ns["ARCHIVO_COMPRAS_ALBARANES"] = orig_compras
    finally:
        if os.path.exists(tmp_csv.name):
            os.remove(tmp_csv.name)


def test_06_diccionario_y_palabras_clave(ns):
    dicc, idx = ns["cargar_equivalencias"]()
    buscar = ns["buscar_equivalencia"]

    # 1. Patatas Morales nombre largo exacto
    eq1, ok1 = buscar(dicc, idx, "morales", "patatas surecrisp fry'n dip corte teja con piel 5x2.5kg mccain", "KG", 2.17)
    assert ok1 and eq1["producto_maestro"] == "PATATAS FRITAS", f"Fallo mapeo patatas Morales largo: {eq1}"

    # 2. Patatas Morales con palabras intercaladas (match por tokens 2e)
    eq2, ok2 = buscar(dicc, idx, "morales", "patata fry'n dip corte especial mccain 2.5kg", "KG", 2.15)
    assert ok2 and eq2["producto_maestro"] == "PATATAS FRITAS", f"Fallo mapeo por tokens patatas Morales: {eq2}"

    # 3. Protección de palabra crítica: Boniato nunca se cruza con Patatas
    eq3, ok3 = buscar(dicc, idx, "morales", "boniato patata dulce prefrita 11/11mm 4x2.5kg mccain", "KG", 4.75)
    assert ok3 and eq3["producto_maestro"] == "BONIATO", f"REGRESIÓN conflicto Boniato vs Patatas: {eq3}"

    # 4. Cielo de Boca Pan Potato Roll (ambos sinónimos)
    for sino in ["oj-potato roll 80 gr c/18 udes", "pan hamburguesa brioche 80 gr c/18 unid"]:
        eq_pan, ok_pan = buscar(dicc, idx, "cielo de boca", sino, "CAJAS", 10.23)
        assert ok_pan and eq_pan["producto_maestro"] == "PAN POTATO ROLL 80 GRS 18 UNIDADES", (
            f"Fallo mapeo Cielo de Boca '{sino}': {eq_pan}"
        )

    # 5. Protección crítica Fanta Limón vs Fanta Naranja
    eq_lim, ok_lim = buscar(dicc, idx, "coca-cola", "fanta lim lata33 c24", "CAJA", 0.52)
    assert ok_lim and eq_lim["producto_maestro"] == "FANTA LIMON", (
        f"REGRESIÓN cruce Fanta Limón vs Naranja: {eq_lim}"
    )


def test_07_promocion_cielo_de_boca(ns):
    proc = ns["procesar_articulos_albaran_ia"]
    res = proc(
        [
            {"nombre": "PAN HAMBURGUESA BRIOCHE 80 GR C/18 UNID", "cantidad": 40.0, "unidad": "UNID", "precio_final": 11.25},
            {"nombre": "PAN HAMBURGUESA BRIOCHE 80 GR C/18 UNID", "cantidad": 4.0, "unidad": "UNID", "precio_final": 0.00},
        ],
        "CIELO DE BOCA",
    )
    assert len(res) == 1
    assert res[0]["cantidad"] == 44.0, f"Agrupación promoción incorrecta: {res[0]}"
    assert res[0]["precio_final"] == 10.23, f"Precio medio efectivo incorrecto: {res[0]}"


def test_08_fotos_borrosas_sin_rotar_y_ui_dinamica(src, ns):
    assert "def preparar_imagen_ia(" in src
    assert "chk_nitidez_" in src
    assert "ed_cant_" in src
    # No debe existir botón de rotación manual (petición explícita del usuario)
    assert "btn_rotar" not in src and "Rotar imagen" not in src, (
        "REGRESIÓN: apareció opción de rotar imagen no deseada."
    )
    # Keys dinámicas para que Ref. Blitz y Unidad se actualicen al elegir del catálogo
    assert 'key=f"ref_existente_{i}_{ref_final}"' in src
    assert 'key=f"uinv_{i}_{maestro_final}"' in src

    # Prueba en memoria de preparar_imagen_ia sin escribir nada en disco
    sample_dir = os.path.join(BASE_DIR, "Entrada_Ronda_Sur")
    if os.path.isdir(sample_dir):
        jpgs = [f for f in os.listdir(sample_dir) if f.lower().endswith(".jpg")]
        if jpgs:
            ruta = os.path.join(sample_dir, jpgs[0])
            im_norm = ns["preparar_imagen_ia"](ruta, mejorar_nitidez=False)
            im_nit = ns["preparar_imagen_ia"](ruta, mejorar_nitidez=True)
            assert max(im_norm.size) <= 2000
            assert max(im_nit.size) <= 2500


def test_09_integridad_csvs(ns):
    norm = ns["normalizar_texto"]

    # Equivalencias sin claves duplicadas (Proveedor, Sinonimo, Unidad_Compra)
    with open(os.path.join(BASE_DIR, "Equivalencias.csv"), "r", encoding="utf-8-sig") as f:
        eq_rows = list(csv.DictReader(f))
    assert len(eq_rows) > 100
    vistos_eq = set()
    dups_eq = []
    for r in eq_rows:
        k = (
            norm(r.get("Proveedor", "")),
            norm(r.get("Sinonimo_Proveedor", "")),
            str(r.get("Unidad_Compra", "")).strip().upper(),
        )
        if k in vistos_eq:
            dups_eq.append(k)
        vistos_eq.add(k)
    assert not dups_eq, f"Filas duplicadas en Equivalencias.csv: {dups_eq[:5]}"

    # Histórico de precios: estructura válida y precios numéricos
    with open(os.path.join(BASE_DIR, "Historico_Precios.csv"), "r", encoding="utf-8-sig") as f:
        reader_hp = csv.DictReader(f)
        for col in ["Fecha", "Proveedor", "Producto_Maestro", "Precio", "Centro"]:
            assert col in (reader_hp.fieldnames or []), f"Falta columna '{col}' en Historico_Precios.csv"
        hp_rows = list(reader_hp)
    assert len(hp_rows) > 0, "Historico_Precios.csv está vacío"
    for r in hp_rows:
        float(r["Precio"])


def main():
    src, tree, ns = _cargar_funciones_panel()
    pruebas = [
        ("01 Sintaxis de módulos Python", lambda: test_01_sintaxis_modulos()),
        ("02 Bloques protegidos intactos", lambda: test_02_bloques_protegidos_intactos(src)),
        ("03 Persistencia GitHub Equivalencias/CSVs", lambda: test_03_sincronizacion_equivalencias_y_compras(src, tree)),
        ("04 Soporte multipágina Makro y Coca-Cola", lambda: test_04_multipagina_makro_y_cocacola(src)),
        ("05 Detector de duplicados 5 niveles", lambda: test_05_detector_duplicados_5_niveles(ns)),
        ("06 Diccionario, palabras clave y conflictos", lambda: test_06_diccionario_y_palabras_clave(ns)),
        ("07 Promoción 10+1 Cielo de Boca", lambda: test_07_promocion_cielo_de_boca(ns)),
        ("08 Modo borroso, edición manual y sin rotar", lambda: test_08_fotos_borrosas_sin_rotar_y_ui_dinamica(src, ns)),
        ("09 Integridad y no duplicidad de CSVs", lambda: test_09_integridad_csvs(ns)),
    ]
    fallos = []
    for nombre, fn in pruebas:
        try:
            fn()
            print(f"[OK] {nombre}")
        except Exception as e:
            print(f"[FAIL] {nombre}: {e}")
            fallos.append((nombre, str(e)))
    if fallos:
        raise SystemExit(1)
    print(f"\nTODAS LAS PRUEBAS PASARON ({len(pruebas)}/{len(pruebas)}).")


if __name__ == "__main__":
    main()
