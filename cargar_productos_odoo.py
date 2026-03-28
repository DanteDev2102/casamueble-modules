#!/usr/bin/env python3
"""
cargar_productos_odoo.py
------------------------
Carga todos los productos del CSV unificado (productos_odoo.csv) directamente
en Odoo usando la API XML-RPC.

Flujo:
  1. Conecta y autentica con Odoo
  2. Crea las Unidades de Medida faltantes  (uom.uom)
  3. Crea las Categorías faltantes           (product.category)  con jerarquía
  4. Crea los Proveedores faltantes          (res.partner)
  5. Crea los Productos faltantes            (product.template)  — omite duplicados
  6. Establece el stock inicial              (stock.quant)

NOTA sobre action_apply_inventory:
  Odoo ejecuta la operación correctamente pero intenta serializar el dict de
  retorno (una acción IR) con allow_none=False, lo que lanza un Fault si el
  dict contiene algún campo None. Capturamos ese error específico y continuamos,
  ya que el stock quedó aplicado en el servidor.
"""

import csv
import xmlrpc.client
from pathlib import Path

# ────────────────────────────────────────────────────────────────
#  CONFIG
# ────────────────────────────────────────────────────────────────
ODOO_URL = "http://192.168.10.103:17000"
ODOO_DB = "casamueble"
ODOO_USER = "casamuebleca@gmail.com"
ODOO_PASSWORD = "8bc0615d3eb19925ef3607965de0ab6080fa47c9"

CSV_PATH = Path(__file__).parent / "productos_odoo.csv"

# Mapeo nombre → ID de UoM estándar de Odoo 17
# Evita crear UoMs tipo "reference" que rompen las categorías existentes
UOM_ID_MAP = {
    "unidad": 1,  # Units
    "unidades": 1,
    "und": 1,
    "metro": 6,  # m
    "metros": 6,
    "m": 6,
    "cm": 9,
    "kg": 13,
    "kilogramo": 13,
    "kilogramos": 13,
    "g": 14,
    "gramo": 14,
    "l": 11,
    "litro": 11,
    "litros": 11,
}


# ────────────────────────────────────────────────────────────────
#  CONEXIÓN XML-RPC
# ────────────────────────────────────────────────────────────────


def conectar():
    """Devuelve (uid, models_proxy) tras autenticarse en Odoo."""
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    try:
        version = common.version()
        print(f"🔗 Conectado a Odoo {version['server_version']} en {ODOO_URL}")
    except Exception as e:
        raise ConnectionError(
            f"❌ No se pudo conectar a Odoo en {ODOO_URL}\n"
            f"   Verifica que el contenedor esté corriendo: docker compose up -d\n"
            f"   Error: {e}"
        )
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    if not uid:
        raise PermissionError(
            f"❌ Autenticación fallida para '{ODOO_USER}' en BD '{ODOO_DB}'\n"
            f"   Verifica ODOO_USER y ODOO_PASSWORD en la sección CONFIG."
        )
    print(f"✅ Autenticado como uid={uid} (BD: {ODOO_DB})")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    return uid, models


def execute(models, uid, model, method, *args, **kwargs):
    """Atajo para models.execute_kw."""
    return models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD, model, method, list(args), kwargs
    )


def execute_safe(models, uid, model, method, *args, **kwargs):
    """
    Como execute() pero ignora el error 'cannot marshal None'.
    Úsalo para métodos que retornan dicts de acción con posibles None
    (p.ej. action_apply_inventory), donde la operación sí se ejecuta
    en el servidor pero la serialización XML-RPC falla.
    """
    try:
        return execute(models, uid, model, method, *args, **kwargs)
    except Exception as e:
        if "marshal" in str(e).lower() or "dump_nil" in str(e).lower():
            return None  # Operación ejecutada; solo falló la serialización
        raise


def buscar_o_crear(models, uid, model, domain, valores, label=""):
    """Busca un registro; si no existe lo crea. Devuelve (id, creado)."""
    ids = execute(models, uid, model, "search", domain)
    if ids:
        return ids[0], False
    new_id = execute(models, uid, model, "create", valores)
    if label:
        print(f"      ➕ Creado {label}: id={new_id}")
    return new_id, True


# ────────────────────────────────────────────────────────────────
#  1. UNIDADES DE MEDIDA
# ────────────────────────────────────────────────────────────────


def asegurar_uom(models, uid, nombre_uom: str, cache: dict) -> int:
    """
    Devuelve el ID de la UoM.
    1. Busca en el mapeo fijo de Odoo estándar.
    2. Busca por nombre en la BD.
    3. Crea como 'bigger' (nunca 'reference' para no romper categorías).
    """
    if not nombre_uom or nombre_uom.strip() == "":
        return 1  # Units

    clave = nombre_uom.strip().lower()
    if clave in cache:
        return cache[clave]

    # Mapeo fijo
    if clave in UOM_ID_MAP:
        cache[clave] = UOM_ID_MAP[clave]
        return cache[clave]

    # Buscar por nombre
    ids = execute(
        models, uid, "uom.uom", "search", [("name", "=ilike", nombre_uom.strip())]
    )
    if ids:
        cache[clave] = ids[0]
        return ids[0]

    # Crear como 'bigger' dentro de la categoría Unit
    uom_id = execute(
        models,
        uid,
        "uom.uom",
        "create",
        {
            "name": nombre_uom.strip(),
            "category_id": 1,
            "uom_type": "bigger",
            "factor": 1.0,
            "active": True,
        },
    )
    print(f"      ➕ UoM creada: {nombre_uom} (id={uom_id})")
    cache[clave] = uom_id
    return uom_id


# ────────────────────────────────────────────────────────────────
#  2. CATEGORÍAS DE PRODUCTO
# ────────────────────────────────────────────────────────────────


def asegurar_categoria(models, uid, nombre_cat: str, cache: dict) -> int:
    """
    Garantiza que exista la categoría (y su padre si usa '/').
    Ejemplo: "Gomas / Azul" → crea padre "Gomas" primero.
    """
    if nombre_cat in cache:
        return cache[nombre_cat]

    partes = [p.strip() for p in nombre_cat.split("/")]
    parent_id = None
    ruta_acumulada = ""

    for parte in partes:
        ruta_acumulada = f"{ruta_acumulada}/{parte}".lstrip("/")

        if ruta_acumulada in cache:
            parent_id = cache[ruta_acumulada]
            continue

        domain = [("name", "=", parte)]
        if parent_id:
            domain.append(("parent_id", "=", parent_id))
        else:
            domain.append(("parent_id", "=", False))

        ids = execute(models, uid, "product.category", "search", domain)
        if ids:
            cat_id = ids[0]
        else:
            vals = {"name": parte}
            if parent_id:
                vals["parent_id"] = parent_id
            cat_id = execute(models, uid, "product.category", "create", vals)
            print(f"      ➕ Categoría creada: '{ruta_acumulada}' (id={cat_id})")

        cache[ruta_acumulada] = cat_id
        parent_id = cat_id

    cache[nombre_cat] = parent_id
    return parent_id


# ────────────────────────────────────────────────────────────────
#  3. PROVEEDORES (res.partner)
# ────────────────────────────────────────────────────────────────


def asegurar_proveedor(models, uid, nombre_proveedor: str, cache: dict):
    """
    Garantiza que exista el partner/proveedor.
    Devuelve su ID o None si el nombre está vacío.
    """
    if not nombre_proveedor or nombre_proveedor.strip() == "":
        return None

    nombre = nombre_proveedor.strip().title()
    if nombre in cache:
        return cache[nombre]

    # Buscar por nombre (con o sin supplier_rank)
    ids = execute(models, uid, "res.partner", "search", [("name", "=ilike", nombre)])
    if ids:
        pid = ids[0]
        execute(models, uid, "res.partner", "write", [pid], {"supplier_rank": 1})
    else:
        pid = execute(
            models,
            uid,
            "res.partner",
            "create",
            {
                "name": nombre,
                "supplier_rank": 1,
                "customer_rank": 0,
            },
        )
        print(f"      ➕ Proveedor creado: '{nombre}' (id={pid})")

    cache[nombre] = pid
    return pid


# ────────────────────────────────────────────────────────────────
#  4. PRODUCTOS
# ────────────────────────────────────────────────────────────────


def safe_float(val):
    """Convierte a float; None/vacío/nan → None."""
    if val is None or str(val).strip() in ("", "nan", "NaN"):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def cargar_producto(
    models, uid, row: dict, cat_cache: dict, prov_cache: dict, uom_cache: dict
):
    """
    Crea el product.template si no existe (busca por nombre exacto).
    Devuelve (tmpl_id, creado: bool).
    """
    nombre = row.get("Nombre del Producto", "").strip()
    if not nombre:
        return None, False

    # Campos relacionados
    nombre_uom = row.get("Unidad de Medida", "").strip() or "Unidad"
    uom_id = asegurar_uom(models, uid, nombre_uom, uom_cache)

    cat_nombre = row.get("Categoría", "").strip() or "All"
    cat_id = asegurar_categoria(models, uid, cat_nombre, cat_cache)

    prov_nombre = row.get("Proveedor", "").strip()
    prov_id = asegurar_proveedor(models, uid, prov_nombre, prov_cache)

    # Verificar duplicado
    existing = execute(
        models, uid, "product.template", "search", [("name", "=ilike", nombre)]
    )
    if existing:
        return existing[0], False

    # Construir valores del producto
    costo = safe_float(row.get("Costo por Unidad"))
    precio_vta = safe_float(row.get("Precio de Venta"))
    qty_min = safe_float(row.get("Cantidad Mínima a Comprar"))

    vals = {
        "name": nombre,
        "type": "product",  # almacenable en Odoo 17
        "categ_id": cat_id,
        "uom_id": uom_id,
        "uom_po_id": uom_id,
        "purchase_ok": True,
        "sale_ok": True,
    }
    if costo is not None:
        vals["standard_price"] = costo
    if precio_vta is not None:
        vals["list_price"] = precio_vta

    tmpl_id = execute(models, uid, "product.template", "create", vals)

    # Registrar proveedor en supplierinfo
    if prov_id:
        si_vals = {
            "partner_id": prov_id,
            "product_tmpl_id": tmpl_id,
            "price": costo if costo is not None else 0.0,
        }
        if qty_min is not None:
            si_vals["min_qty"] = qty_min
        execute(models, uid, "product.supplierinfo", "create", si_vals)

    return tmpl_id, True


# ────────────────────────────────────────────────────────────────
#  5. STOCK INICIAL
# ────────────────────────────────────────────────────────────────


def establecer_stock(models, uid, tmpl_id: int, qty):
    """
    Ajusta el stock inicial usando stock.quant.
    Solo actúa si qty es un número > 0.

    action_apply_inventory puede lanzar un Fault de serialización
    ("cannot marshal None") porque el dict de retorno contiene None.
    La operación SÍ se ejecuta en Odoo — solo capturamos ese error.
    """
    qty = safe_float(qty)
    if qty is None or qty <= 0:
        return

    # Producto almacenable
    pp_ids = execute(
        models, uid, "product.product", "search", [("product_tmpl_id", "=", tmpl_id)]
    )
    if not pp_ids:
        return
    product_id = pp_ids[0]

    # Ubicación WH/Stock
    loc_ids = execute(
        models,
        uid,
        "stock.location",
        "search",
        [("usage", "=", "internal"), ("complete_name", "ilike", "WH/Stock")],
    )
    if not loc_ids:
        loc_ids = execute(
            models, uid, "stock.location", "search", [("usage", "=", "internal")]
        )
    if not loc_ids:
        return
    location_id = loc_ids[0]

    # Buscar quant existente o crear uno nuevo
    quant_ids = execute(
        models,
        uid,
        "stock.quant",
        "search",
        [("product_id", "=", product_id), ("location_id", "=", location_id)],
    )
    if quant_ids:
        execute(
            models, uid, "stock.quant", "write", quant_ids, {"inventory_quantity": qty}
        )
        apply_ids = quant_ids
    else:
        new_id = execute(
            models,
            uid,
            "stock.quant",
            "create",
            {
                "product_id": product_id,
                "location_id": location_id,
                "inventory_quantity": qty,
            },
        )
        apply_ids = [new_id]

    # Aplicar ajuste — capturamos el error de serialización del dict de retorno
    execute_safe(models, uid, "stock.quant", "action_apply_inventory", apply_ids)


# ────────────────────────────────────────────────────────────────
#  MAIN
# ────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  🚀  Cargador de productos → Odoo")
    print("=" * 60)

    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"❌ No se encontró '{CSV_PATH}'\n"
            f"   Ejecuta primero: python3 convertir_productos_odoo.py"
        )

    uid, models = conectar()

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    print(f"\n📋 Productos a procesar: {len(filas)}")

    cat_cache = {}
    prov_cache = {}
    uom_cache = {}

    creados = 0
    omitidos = 0
    errores = 0

    print("\n🔄 Procesando productos...\n")
    for i, row in enumerate(filas, 1):
        nombre = row.get("Nombre del Producto", "").strip()
        if not nombre:
            continue

        try:
            tmpl_id, creado = cargar_producto(
                models, uid, row, cat_cache, prov_cache, uom_cache
            )

            if tmpl_id and creado:
                establecer_stock(models, uid, tmpl_id, row.get("Stock Actual"))
                creados += 1
                estado = "✅"
            elif tmpl_id:
                omitidos += 1
                estado = "⏭️ "
            else:
                errores += 1
                estado = "⚠️ "

            cat = row.get("Categoría", "")
            print(f"  {estado} [{i:>3}/{len(filas)}] {nombre[:55]:<55} [{cat}]")

        except Exception as e:
            errores += 1
            print(f"  ❌ [{i:>3}/{len(filas)}] {nombre[:55]:<55} ERROR: {e}")

    print("\n" + "=" * 60)
    print(f"  📦 Productos creados  : {creados}")
    print(f"  ⏭️  Ya existían        : {omitidos}")
    print(f"  ❌ Errores            : {errores}")
    print("=" * 60)
    print(f"\n✨ Importación completada. Revisa Odoo en {ODOO_URL}")


if __name__ == "__main__":
    main()
