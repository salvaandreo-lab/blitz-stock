# 📋 Especificación Técnica de Integración: Camarero 10 ➔ Blitz Stock

Documento de referencia técnica guardado a partir del extracto real del TPV **Camarero 10** (Centro Juan de Borbón). Este esquema define la estructura de datos que se recibirá a través de la API (o archivos de cierre) para conectar las ventas con los escandallos y el inventario de Blitz Stock.

---

## 1. Estructura de Datos de Venta (Camarero 10)

Cada línea de ticket emitida por Camarero 10 contiene los siguientes campos clave:

| Campo Camarero 10 | Tipo de Dato | Descripción / Función en Blitz Stock |
| :--- | :--- | :--- |
| `Fecha` | `YYYY-MM-DD` | Fecha contable de la venta (imputa a la semana operativa correspondiente). |
| `Hora` | `HH:MM:SS` | Hora exacta del ticket o cobro. |
| `Número de ticket` | `String` | Serie y número único (ej: `V001-001-017608`). Permite agrupar líneas del mismo pedido. |
| `Terminal` | `String` | TPV o terminal que emitió la orden (ej: `TPV`). |
| `Recurso` | `String` | **Canal de venta**: `Glovo`, `Kiosko`, `Uber Eat`, `Just Eat`, `Sala`. |
| `Forma de pago` | `String` | `Tarjeta de crédito`, `Otros pagos` (agregadores), `Efectivo`. |
| `Producto` | `String` | Nombre del plato, subartículo o combo tal como está dado de alta en la carta. |
| `Ref. producto` | `String / Int` | **Identificador único de Camarero 10** (ej: `PROD 18`, `1745942027860`). |
| `Categoría` | `String / Null` | Categoría principal (`Hamburguesas`, `Entrantes`, `COMBOS`, `Postres`, `Refrescos`, `Cervezas`, `Pollo Burguers`). Es `Null` en modificadores y subartículos de combos. |
| `Unidades vendidas` | `Int` | Cantidad de unidades vendidas. |
| `Precio unidad(con IVA)` | `Float` | Precio tarifa unitario con IVA. |
| `Total sin IVA` | `Float` | Base imponible neta facturada. |
| `Total con IVA` | `Float` | Total cobrado con impuestos. |
| `Descuento` | `Float` | Promociones o descuentos aplicados en la línea. |
| `Empleado` | `String` | `Camarero` o `Usuario Web` (pedidos por app / kiosko). |
| `Mesa` | `Float / String` | Identificador de mesa física o ID virtual del pedido delivery. |

---

## 2. Lógica Especial: Combos y Modificadores

Camarero 10 estructura los combos y suplementos de la siguiente manera:

1. **Combos (`COMBO BLITZ` - Ref: `1777374676019`):**
   * Genera una línea cabecera con categoría `COMBOS` y el precio del combo (ej: 15,50 €).
   * Inmediatamente después, genera las líneas hijas con **`Categoría = Null`** y **`Ref. producto = Null`** que detallan:
     * La hamburguesa elegida (ej: `Hamburguesa Brutal Bacon`, `Hamburguesa Cheese Burguer 3 discos`, `Hamburguesa Emmy`, `Hamburguesa Colorá`, `Hamburguesa Criminal`).
     * La guarnición elegida (ej: `Guarnición Boniato Sweet`).
     * La bebida elegida (ej: `Refresco Coca-Cola 500 ml`).
   * *Regla para Blitz Stock:* Para el descuento de stock se contabilizan los platos hijos de los combos, evitando duplicar importes monetarios.

2. **Modificadores y Suplementos:**
   * Las líneas con `Categoría = Null` como `Guarnición Boniato Sweet` o variantes `SIN/CON` imputan consumos de ingredientes extra (como raciones de boniato o bacon adicional).

---

## 3. Diccionario Oficial: Camarero 10 ➔ Escandallos Blitz Stock (`Recetas.csv`)

| Producto Camarero 10 | Ref. Camarero 10 | Categoría | Plato Mapeado en `Recetas.csv` |
| :--- | :--- | :--- | :--- |
| **Brutal Bacon** / `Hamburguesa Brutal Bacon` | `PROD 18` | Hamburguesas | `BRUTAL BACON` |
| **Emmy** / `Hamburguesa Emmy` | `PROD 17` | Hamburguesas | `EMY` |
| **BURGUER DEL MES NOVIEMBRE:LA CONDESA** | `1793185496406` | Hamburguesas | `BURGUER DEL MES NOVIEMBRE:LA CONDESA` |
| **"LA INFILTRADA"** | `1782918460101` | Hamburguesas | `INFILTRADA` |
| **LA "CRIMINAL"** / `Hamburguesa Criminal` | `1754556771546` | Hamburguesas | `LA CRIMINAL` |
| **Cheeseburger 1 disco 100gr** | `1745941808805` | Hamburguesas | `CHEESE BURGUER 1 DISCO` |
| **Cheeseburger 2 discos 100gr** | `1745942027860` | Hamburguesas | `CHEESE BURGUER 2 DISCOS` |
| **Cheeseburger 3 discos 100gr** / `Hamburguesa Cheese Burguer 3 discos` | `1745942119079` | Hamburguesas | `CHEESE BURGUER 3 DISCOS` |
| **Classic** | `PROD 15` | Hamburguesas | `CLASSIC` |
| **Paquita** | `PROD 19` | Hamburguesas | `PAQUITA` |
| **Distrufona** | `PROD 22` | Hamburguesas | `DISTRUFONA` |
| **Original** | `PROD 16` | Hamburguesas | `ORIGINAL` |
| **Colorá** / `Hamburguesa Colorá` | `1745232881772` | Hamburguesas | `COLORÁ` |
| **Traviesa** | `PROD 21` | Hamburguesas | `TRAVIESA` |
| **Tijuana** | `PROD 20` | Hamburguesas | `TIJUANA` |
| **RUTA 66** | `1793102515316` | Pollo Burguers | `RUTA 66` |
| **LA POLLO MODO GOD** | `1792574300272` | Pollo Burguers | `LA POLLO MODO GOD` |
| **Patatas Bacon&Cheese** | `PROD 13` | Entrantes | `PATATAS BACON CHEESE` |
| **Patatas Blitz** | `PROD 14` | Entrantes | `PATATAS BLITZ` |
| **Tequeños** | `PROD 08` | Entrantes | `TEQUEÑOS DE QUESO` |
| **Nuggets de pollo** | `1751450527486` | Entrantes | `NUGGETS` |
| **Alitas Tex-Mex** | `1768401939360` | Entrantes | `ALITAS` |
| **Croqueta Explosión Jamón** | `1768402364723` | Entrantes | `CROQUETA EXPLOSIÓN JAMÓN` |
| **Tequeños Nutella** | `PROD 23` | Postres | `TEQUEÑOS DE NUTELLA` |
| **Tequeños Oreo** | `PROD 24` | Postres | `TEQUEÑOS DE OREO` |
| **Tequeños Chocoblanco** | `PROD 25` | Postres | `TEQUEÑOS DE CHOCO BLANCO` |
| **TARTA QUESO LOTUS BY ANDRÉS MÁRMOL** | `1790960159135` | Postres | `TARTA QUESO LOTUS BY ANDRÉS MÁRMOL` |
| **TARTA QUESO TRADICIONAL BY ANDRÉS MÁRMOL** | `1790959944236` | Postres | `TARTA QUESO CLÁSICA BY ANDRÉS MÁRMOL` |
| **Guarnición Boniato Sweet** | *(Modificador)* | Modificador/Extra | `BONIATO` |

---

## 4. Endpoints esperados al conectar la API REST de Camarero 10

Cuando conectemos con las credenciales de vuestro ERP:
1. `GET /ventas` o `GET /tickets`: Filtrando por `fecha_inicio`, `fecha_fin` e `id_centro` / `id_terminal`.
2. `GET /articulos` o `GET /carta`: Para obtener el catálogo de productos con sus códigos `Ref. producto`.
3. `POST /webhook` (Opcional): Si Camarero 10 permite avisos en tiempo real cada vez que se realiza un cierre de caja diario.


---

## 5. Estructura del Informe Contable Oficial de Cierre (Ventas Diarias y Canales)

Además del desglose por plato individual, Camarero 10 emite el **Informe Contable Diario / Mensual** estructurado por fecha contable, canal de cobro y desglose impositivo:

### Campos del informe contable diario:
| Campo | Descripción |
| :--- | :--- |
| `Fecha` | Marca temporal del día contable (`YYYY-MM-DD 00:00:00`) o etiqueta de desglose (`Desglose de pagos`, `Desglose de impuestos`). |
| `Propinas (en tar.)` | Propinas capturadas electrónicamente. |
| `Total (con iva)` | Facturación total bruta cobrada en el día. |
| `Total (sin iva)` | Base imponible neta facturada en el día. |
| `Tipo Iva` | Tipo impositivo aplicado (`0.10` para hostelería / 10%). |
| `IVA` | Cuota de IVA soportada. |

### Canales de cobro registrados (`Desglose de pagos`):
* `Otros pagos Glovo` (Canal Delivery principal)
* `Otros pagos Uber Eat` (Canal Delivery)
* `Otros pagos Just Eat` (Canal Delivery)
* `Tarjeta de crédito` (TPV Sala / Kiosko de pedidos)
* `Efectivo` (Caja física)

### Datos Reales Verificados (Centro Juan de Borbón - Octubre 2026):
* **Período:** 30/09/2026 al 01/11/2026 (25 días de apertura, Miércoles a Domingo, Lunes y Martes cerrado).
* **Total Facturado Con IVA:** **47.358,48 €**
* **Base Imponible Neta (Sin IVA):** **43.052,60 €**
* **Cuota IVA (10%):** **4.305,88 €**
* **Reparto por Canales de Pago:**
  * **Glovo:** 22.656,33 € *(47,8 %)*
  * **Tarjeta de crédito:** 10.274,37 € *(21,7 %)*
  * **Uber Eats:** 7.587,75 € *(16,0 %)*
  * **Just Eat:** 3.592,32 € *(7,6 %)*
  * **Efectivo:** 3.247,71 € *(6,9 %)*

### Datos Reales Verificados (Centro Ronda Sur - Octubre 2026):
* **Período:** 30/09/2026 al 01/11/2026 (25 días de apertura, Miércoles a Domingo, Lunes y Martes cerrado).
* **Total Facturado Con IVA:** **34.541,99 €**
* **Base Imponible Neta (Sin IVA):** **31.401,47 €**
* **Cuota IVA (10%):** **3.140,52 €**
* **Reparto por Canales de Pago:**
  * **Glovo:** 18.547,51 € *(53,7 %)*
  * **Tarjeta de crédito:** 9.208,71 € *(26,7 %)*
  * **Uber Eats:** 3.766,24 € *(10,9 %)*
  * **Efectivo:** 3.019,53 € *(8,7 %)*
  * **Just Eat:** 0,00 € *(0,0 % - no opera en este centro)*

### Resumen Global Consolidado (Ambos Centros - Octubre 2026):
* **Facturación Total Red Blitz Con IVA:** **81.900,47 €**
* **Base Imponible Neta Total (Sin IVA):** **74.454,07 €**
* **Cuota Total de IVA (10%):** **7.446,40 €**
* **Volumen Global por Canales de Venta:**
  * **Glovo:** 41.203,84 € *(50,3 % de las ventas globales)*
  * **Tarjeta de crédito:** 19.483,08 € *(23,8 % de las ventas globales)*
  * **Uber Eats:** 11.353,99 € *(13,9 % de las ventas globales)*
  * **Efectivo:** 6.267,24 € *(7,7 % de las ventas globales)*
  * **Just Eat:** 3.592,32 € *(4,4 % de las ventas globales)*
