"""
Clasifica las reviews por tema con Claude (Haiku) y guarda el resultado en analitica.review_temas
(tema, sentimiento, severidad, cita, acción sugerida).

Uso (desde la carpeta andina_analytics):
    python -m analitica.reviews_ia --dry-run --limite 3   # muestra qué se enviaría, sin gastar
    python -m analitica.reviews_ia --limite 5             # prueba con 5 reviews
    python -m analitica.reviews_ia                        # todas las que faltan
    python -m analitica.reviews_ia --reclasificar         # todas de nuevo (reemplaza temas)

Qué se envía: nombre del anuncio, notas por categoría, comentario público y comentario privado.
NO se envía el nombre del huésped, el código de reserva ni ningún dato personal.
Costo aproximado con Haiku: menos de 1 USD por cada ~500 reviews.
"""

import argparse
import json
import time

from . import db
from .config import ANTHROPIC_API_KEY, MODELO_REVIEWS, precio

TEMAS = ["limpieza", "ropa_de_cama", "mantenimiento", "equipamiento", "cocina", "bano", "climatizacion",
         "wifi_tv", "privacidad", "ruido", "seguridad", "check_in", "comunicacion", "ubicacion",
         "precio_valor", "exactitud", "espacio", "vista", "externo", "otro"]
SENTIMIENTOS = ("positivo", "negativo", "neutro")
CITA_ELOGIO_GENERAL = "(elogio general, sin temas concretos)"

SISTEMA = """Eres analista de calidad de una empresa de arriendo de corto plazo (Airbnb) con \
departamentos en Santiago y Pucón (Chile) y una casa en Porto Seguro (Brasil).
Recibes UNA review de un huésped (notas de 1 a 5 y comentarios en español, portugués o inglés).
Tu trabajo: extraer los temas concretos que menciona, para que el equipo de operaciones sepa qué
mantener y qué corregir en ESA propiedad.

Reglas:
- Un tema por cada asunto concreto mencionado. No inventes temas que el texto no menciona.
- Si un comentario es solo un elogio general ("todo excelente") sin detalle, no generes temas:
  devuelve la lista vacía.
- sentimiento: "positivo" (elogio), "negativo" (queja o problema), "neutro" (sugerencia amable,
  algo que faltó sin enojo).
- severidad (solo negativos y neutros): 1 = detalle menor, 2 = molestia clara que afecta la
  estadía, 3 = grave (higiene, seguridad, algo que no funcionó en toda la estadía).
- cita: la frase textual del huésped que respalda el tema (máximo 25 palabras, en su idioma).
- fuente: "privado" si sale del comentario privado, "publico" si sale del público.
- accion_sugerida: solo para negativos/neutros, una acción operativa concreta y breve en español
  (ej. "Revisar presión y temperatura del agua caliente"). Para positivos, vacío.
- Usa "externo" cuando el problema no dependía del anfitrión (clima, cortes de luz, obras).
- Notas bajo 5 en una categoría sin explicación en el texto: no inventes la causa.
Responde siempre llamando a la herramienta registrar_temas."""

HERRAMIENTA = {
    "name": "registrar_temas",
    "description": "Registra los temas encontrados en la review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "temas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tema": {"type": "string", "enum": TEMAS},
                        "sentimiento": {"type": "string", "enum": list(SENTIMIENTOS)},
                        "severidad": {"type": ["integer", "null"], "enum": [1, 2, 3, None]},
                        "cita": {"type": "string"},
                        "fuente": {"type": "string", "enum": ["publico", "privado"]},
                        "accion_sugerida": {"type": ["string", "null"]},
                    },
                    "required": ["tema", "sentimiento", "cita", "fuente"],
                },
            }
        },
        "required": ["temas"],
    },
}

NOMBRES_NOTAS = {
    "rating_general": "General", "rating_limpieza": "Limpieza", "rating_exactitud": "Exactitud del anuncio",
    "rating_checkin": "Check-in", "rating_comunicacion": "Comunicación", "rating_ubicacion": "Ubicación",
    "rating_valor": "Relación calidad-precio",
}

SQL_PENDIENTES = """
    SELECT a.id_avaliacion, a.fecha, p.nome_anuncio AS propiedad,
           a.rating_general, a.rating_limpieza, a.rating_exactitud, a.rating_checkin,
           a.rating_comunicacion, a.rating_ubicacion, a.rating_valor,
           a.comentario_publico, a.comentario_privado
    FROM public.avaliaciones a
    LEFT JOIN public.dim_propiedades p ON p.id_interno = a.id_propriedade
    WHERE (NULLIF(trim(a.comentario_publico), '') IS NOT NULL
           OR NULLIF(trim(a.comentario_privado), '') IS NOT NULL)
      {filtro}
    ORDER BY a.fecha, a.id_avaliacion
"""


def reviews_pendientes(reclasificar=False, limite=None):
    filtro = "" if reclasificar else \
        "AND NOT EXISTS (SELECT 1 FROM analitica.review_temas t WHERE t.id_avaliacion = a.id_avaliacion)"
    sql = SQL_PENDIENTES.format(filtro=filtro)
    if limite:
        sql += f" LIMIT {int(limite)}"
    return db.leer(sql)


def _txt(v):
    return None if v is None or (isinstance(v, float) and v != v) or str(v).strip() == "" else str(v).strip()


def armar_mensaje(r):
    """Texto que se envía a la IA. Sin datos personales del huésped."""
    notas = ", ".join(f"{nombre}: {int(r[campo])}" for campo, nombre in NOMBRES_NOTAS.items()
                      if r.get(campo) is not None and r.get(campo) == r.get(campo))
    return "\n".join([
        f"Propiedad: {_txt(r.get('propiedad')) or 'desconocida'}",
        f"Notas: {notas or 'sin notas'}",
        f"Comentario público: {_txt(r.get('comentario_publico')) or '(vacío)'}",
        f"Comentario privado al anfitrión: {_txt(r.get('comentario_privado')) or '(vacío)'}",
    ])


def llamar(cliente, modelo, mensaje, intentos=3):
    for intento in range(intentos):
        try:
            return cliente.messages.create(
                model=modelo, max_tokens=1500, system=SISTEMA, tools=[HERRAMIENTA],
                tool_choice={"type": "tool", "name": "registrar_temas"},
                messages=[{"role": "user", "content": mensaje}],
            )
        except Exception:
            if intento == intentos - 1:
                raise
            time.sleep(2 * (intento + 1))


def extraer(resp):
    """Saca la lista de temas válidos de la respuesta (ignora lo que no cumpla el formato)."""
    for bloque in resp.content:
        if getattr(bloque, "type", None) == "tool_use" and bloque.name == "registrar_temas":
            datos = bloque.input if isinstance(bloque.input, dict) else json.loads(bloque.input)
            return [t for t in datos.get("temas", [])
                    if t.get("tema") in TEMAS and t.get("sentimiento") in SENTIMIENTOS]
    return []


def filas_a_guardar(id_avaliacion, temas, modelo):
    filas = []
    for t in temas:
        negativo = t["sentimiento"] in ("negativo", "neutro")
        sev = t.get("severidad") if negativo else None
        filas.append({
            "a": int(id_avaliacion), "tema": t["tema"], "s": t["sentimiento"],
            "sev": sev if sev in (1, 2, 3) else (1 if negativo else None),
            "cita": (t.get("cita") or "")[:500],
            "f": t.get("fuente") if t.get("fuente") in ("publico", "privado") else "publico",
            "acc": (t.get("accion_sugerida") or None) if negativo else None, "m": modelo,
        })
    if not filas:  # elogio general: queda marcada como revisada
        filas.append({"a": int(id_avaliacion), "tema": "otro", "s": "positivo", "sev": None,
                      "cita": CITA_ELOGIO_GENERAL, "f": "publico", "acc": None, "m": modelo})
    return filas


def guardar(id_avaliacion, filas):
    with db.transaccion() as con:
        db.ejecutar(con, "DELETE FROM analitica.review_temas WHERE id_avaliacion = :a", {"a": int(id_avaliacion)})
        db.ejecutar(con, """
            INSERT INTO analitica.review_temas
                (id_avaliacion, tema, sentimiento, severidad, cita, fuente, accion_sugerida, modelo_ia)
            VALUES (:a, :tema, :s, :sev, :cita, :f, :acc, :m)""", filas)


def clasificar(reclasificar=False, limite=None, dry_run=False, cliente=None, salida=print):
    reviews = reviews_pendientes(reclasificar, limite)
    if reviews.empty:
        salida("No hay reviews pendientes de clasificar.")
        return {"hechas": 0, "errores": 0}

    if dry_run:
        for r in reviews.to_dict("records"):
            salida(f"\n--- review {r['id_avaliacion']} ({r['fecha']}) ---")
            salida(armar_mensaje(r))
        salida(f"\n--dry-run: {len(reviews)} reviews; no se llamó a la API.")
        return {"hechas": 0, "errores": 0}

    if cliente is None:
        if not ANTHROPIC_API_KEY:
            raise SystemExit("Falta ANTHROPIC_API_KEY en el archivo .env (consíguela en platform.claude.com).")
        import anthropic
        cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    modelo = MODELO_REVIEWS
    hechas = errores = temas_total = tok_in = tok_out = 0
    for i, r in enumerate(reviews.to_dict("records"), 1):
        try:
            resp = llamar(cliente, modelo, armar_mensaje(r))
        except Exception as e:  # red, límite de uso, etc.: sigue con la siguiente
            errores += 1
            salida(f"  review {r['id_avaliacion']}: {e}")
            continue
        tok_in += resp.usage.input_tokens
        tok_out += resp.usage.output_tokens
        filas = filas_a_guardar(r["id_avaliacion"], extraer(resp), modelo)
        guardar(r["id_avaliacion"], filas)
        hechas += 1
        temas_total += len(filas)
        if i % 10 == 0:
            salida(f"  {i}/{len(reviews)} reviews...")

    p_in, p_out = precio(modelo)
    costo = tok_in / 1e6 * p_in + tok_out / 1e6 * p_out
    salida(f"✅ {hechas} reviews clasificadas ({temas_total} temas). Errores: {errores}. "
           f"Tokens: {tok_in:,} entrada / {tok_out:,} salida ≈ {costo:.3f} USD")
    return {"hechas": hechas, "errores": errores, "temas": temas_total, "costo_usd": costo}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Clasifica reviews por tema con Claude.")
    ap.add_argument("--limite", type=int, default=None, help="Máximo de reviews a procesar.")
    ap.add_argument("--reclasificar", action="store_true", help="Vuelve a clasificar también las ya clasificadas.")
    ap.add_argument("--dry-run", action="store_true", help="Muestra lo que se enviaría, sin llamar a la API.")
    a = ap.parse_args(argv)
    clasificar(a.reclasificar, a.limite, a.dry_run)


if __name__ == "__main__":
    main()
