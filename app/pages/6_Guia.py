"""Guía de uso: cómo funciona el dashboard y cómo leer cada página. No consulta datos."""
import streamlit as st
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "app" else Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import comun as c

c.configurar("Guía del dashboard")
META = c.dinero(c.META_INGRESO_MENSUAL_CLP, "CLP")
DIAS = c.DIAS_PARA_REVIEW

(t_base, t_inicio, t_ocupacion, t_reviews, t_conversion,
 t_reporte, t_finanzas, t_glosario) = st.tabs(["Lo básico", "Inicio", "Ocupación", "Reviews", "Conversión",
                                               "Reporte semanal", "Finanzas", "Glosario"])

with t_base:
    st.markdown(f"""
### Qué es
El dashboard muestra cómo van las propiedades de Andina en Chile y Brasil: ingresos, ocupación, reviews y
conversión en Airbnb. Es de solo lectura: nada de lo que hagas aquí cambia los datos.

### Dónde mirar según lo que quieras saber
| Pregunta | Página |
|---|---|
| ¿Cómo vamos este mes? | **Inicio** |
| ¿Qué propiedad se está vendiendo mejor o peor? ¿Qué noches siguen libres? | **Ocupación** |
| ¿Qué propiedad tiene problemas de nota? ¿Quién dejó review y quién no? | **Reviews** |
| ¿Por qué un anuncio no recibe reservas? | **Conversión** |
| ¿De dónde sale exactamente el ingreso de un mes? | **Finanzas** |
| Necesito un resumen para compartir | **Reporte semanal** |

### De dónde salen los datos
1. Las reservas, reviews y capturas de Airbnb se importan en **andina_lab**.
2. En el computador se calculan el pronóstico y la clasificación de comentarios con IA.
3. `python -m analitica.subir_bigquery` copia los datos a BigQuery, y el dashboard lee de ahí.

**Los datos no son en vivo:** muestran lo que había en la última subida. La línea bajo el título de cada página
dice hasta qué fecha llegan y cuándo se subieron; si pasó más de una semana aparece ⚠️ *conviene actualizar*.
Una subida nueva aparece sola en máximo 10 minutos. Para verla antes, usa **🔄 Actualizar datos** en la barra lateral.

### Convenciones en todas las páginas
- **Chile va siempre antes que Brasil.** ADR y RevPAR van en la moneda de cada mercado (CLP o BRL); los ingresos
  totales y la meta van en CLP, con Brasil convertido.
- **Estado de una meta:** ✅ En meta (100 % o más) · ⚠️ Cerca (70 % o más) · 🔴 Lejos (menos de 70 %).
- **Pasa el mouse** por un gráfico para ver el detalle, o por el ícono **?** de una tarjeta para ver su definición.
- **Ver tabla**, bajo muchos gráficos, abre los números exactos. Las tablas se ordenan con un clic en la columna.
- Una tarjeta muestra el valor grande y, debajo, cómo cambió respecto al período anterior.
""")

with t_inicio:
    st.markdown(f"""
Inicio responde **cómo vamos hoy**. Lo primero es el mes en curso; el último mes cerrado queda plegado más abajo.

### Lo que llevamos del mes
- **Ingreso del mes, reservado a hoy:** noches ya ocurridas más noches futuras de este mes ya reservadas, comparado
  con la meta de {META}. Puede subir con nuevas reservas o bajar con cancelaciones.
- **Ya ocurrido** y **Reservado por ocurrir:** las dos partes de ese ingreso. Sumadas dan el total.
- **Barra de avance:** cuánto de la meta está cubierto y cuánto falta.

### Por mercado
Hay dos lecturas de ocupación, y responden preguntas distintas:

| Tarjeta | Qué cuenta | Para qué sirve |
|---|---|---|
| **Ocupación** | Noches vendidas sobre las noches que **ya ocurrieron** este mes | Ver cómo se vendió lo que ya pasó. Se compara con el mes anterior |
| **Reservado: X de Y noches** | Ocurridas más futuras reservadas, sobre **todas** las noches del mes | Ver cuánto del mes ya está asegurado |

A principios de mes la primera se calcula con pocas noches y se mueve mucho, y la segunda se ve baja porque aún
faltan reservas: no es mala señal por sí sola. **ADR** y **RevPAR** también usan solo noches ya ocurridas.

### Cómo nos fue con las reviews
Evalúa todas las reviews recibidas en el mes, de todos los anuncios, según la **fecha de la review**. Parte en el mes
en curso y el selector permite ver otro.

| Evaluación | Regla |
|---|---|
| 🟢 Buen mes | Nota del mes de 4,90 o más |
| 🟠 Mes regular | Nota del mes desde 4,80 y bajo 4,90 |
| 🔴 Mes con problemas | Nota del mes bajo 4,80, **o** alguna review de 3 o menos |
| ⚪ Aún pocas reviews | Menos de {c.MIN_REVIEWS_EVALUAR} reviews: todavía no alcanza para evaluar |

La tabla lista **todos los anuncios**, con los que necesitan atención arriba. *Estado hoy* y *Anuncios en OK* usan las
reglas de la página Reviews y no cambian con el selector. *Categoría más baja* indica por dónde empezar a mejorar.

### Reservas y reviews
Muestra el mes en curso; el selector permite ver otro. Se cuenta por mes de **salida**: por eso sus números no
calzan con los de la sección anterior, que cuenta por fecha de la review.

### Pronóstico y Próximos 7 días
- **Pronóstico:** ocupación esperada del mes en curso y los siguientes, y lo que había reservado el día en que se
  calculó (por eso puede ser menos que lo de arriba). Si tiene más de 7 días, conviene recalcularlo.
- **Próximos 7 días:** noches sin vender desde hoy, por propiedad, según las reservas. Son las más urgentes.

### Último mes cerrado
Al abrirlo se ven el ingreso final y los indicadores por mercado. Es el número definitivo del mes.

Si aparece un aviso de **controles de calidad**, algún dato necesita revisión en andina_lab.
""")

with t_ocupacion:
    st.markdown(f"""
Aquí se analiza un período en detalle. **Usa los filtros de la barra lateral:** un mes o un rango, y los anuncios.
Casi todas las secciones responden a ellos.

A diferencia de Inicio, esta página trabaja con el **mes completo**: noches ocurridas más futuras reservadas, sobre
todas las noches del mes. En meses en curso esos números todavía pueden cambiar.

| Sección | Cómo leerla |
|---|---|
| **Resumen del período** | Ocupación, ADR, RevPAR y noches vendidas por mercado. |
| **Ingresos vs meta** | Ingreso contra {META} por mes. Es de **todo el portafolio**: no cambia al filtrar anuncios. Barras: verde en meta, amarillo sobre 70 %, rojo lejos. |
| **Ocupación por anuncio** | Cada dona es un anuncio: color = noches vendidas, gris = libres, «fut.» = noches futuras ya reservadas. |
| **Noches del período** | Separa vendidas, reservadas futuras, libres que ya pasaron (no se recuperan) y libres por vender. |
| **Quién aporta el ingreso** | Participación de cada anuncio, en CLP. |
| **Con cuánta anticipación reservan** | Días entre la reserva y la llegada. Mediana baja = reservan a última hora, así que una noche libre cercana aún puede venderse. Solo usa reservas con fecha confiable. |
| **Reservas y reviews** | Qué % de las estadías terminadas dejó review, por mes y por anuncio. |
| **Pronóstico** | Azul oscuro = ya reservado; azul claro = lo que se espera vender. No depende del filtro de meses y todavía no considera temporada. |
| **Noches libres en los próximos 21 días** | Cada celda es una noche. Gris = reservada. Azul = libre: más oscuro, más probable que se venda. **Las celdas claras son las que necesitan precio o promoción.** |

**Sobre el pronóstico:** parte de lo ya reservado y suma las noches libres por su probabilidad histórica de venderse
con esa anticipación. Es una estimación: úsalo para priorizar, no como número exacto.
""")

with t_reviews:
    st.markdown(f"""
### Estado actual
Una fila por propiedad, con las que necesitan atención arriba.

| Estado | Regla |
|---|---|
| 🔴 Crítico | Acumulado bajo 4,80, **o** promedio de 3 meses bajo 4,70, **o** una review de 3 o menos este mes |
| 🟠 Alerta | Acumulado bajo 4,90, **o** promedio de 3 meses bajo 4,85 |
| 🟢 OK | El resto |
| ⚪ Sin datos suficientes | Menos de 3 reviews |

La columna **Motivo** dice qué regla se activó. **Este mes** cuenta las reviews recibidas en el mes actual.

### Qué departamentos tienen review
Elige un mes de **salida** (check-out): la review llega después de la estadía.

- **✅ Dejaron review:** departamentos con al menos una review de ese mes. Puede que falten otras: míralo en
  *Aún pueden* y *Plazo vencido*.
- **⏳ Tuvieron reservas, aún sin review:** tuvieron reservas ese mes y ninguna review todavía.

Cada reserva está en una de estas situaciones:

| Situación | Significado |
|---|---|
| ✅ Con review | El huésped ya la dejó |
| ⏳ Aún puede dejarla | Hizo check-out hace {DIAS} días o menos |
| ⌛ Plazo vencido, sin review | Pasaron más de {DIAS} días: Airbnb ya no la permite |
| 🛏️ Estadía en curso | Ya llegó y aún no sale |
| 📅 Por llegar | Tiene salida en el mes, pero aún no llega |

**Ver reserva por reserva** identifica cada estadía por sus fechas. La última lista junta las estadías con ventana
abierta hoy, aunque sean del mes pasado. Es la lista útil para pedir una review a tiempo.

### Notas por categoría
Promedio de los últimos 3 meses en cada categoría de Airbnb. La barra va de 4 a 5: sirve para ver la categoría más
débil de cada propiedad.

### Qué dicen los comentarios (IA)
Una IA clasifica cada comentario por tema y sentimiento. El filtro de propiedad cambia toda esta sección.

- **Gráfico:** quejas (naranjo) y elogios (azul) por tema, últimos 90 días.
- **Pendientes por corregir:** ordenados por **prioridad**, la suma de las severidades de cada mención. Empieza por
  arriba. *En privado* indica cuántas menciones vienen de comentarios privados.
- **Fortalezas:** lo más elogiado. Sirve para el título y la descripción del anuncio.

La IA puede equivocarse: revisa las citas antes de actuar.

### Nota general por mes
Mapa de calor con el promedio mensual. Naranjo: bajo 4,80 · tonos claros: entre 4,80 y 4,90 · azul: 4,90 o más ·
vacío: sin reviews. Un mes con una sola review pesa mucho: revisa la cantidad pasando el mouse.
""")

with t_conversion:
    st.markdown("""
Muestra en qué parte del camino se pierde la gente, con las capturas de Airbnb cargadas en andina_lab. Las capturas
se copian a mano, así que esta página está tan al día como la última. **En la barra lateral** eliges una captura o un
rango de fechas, y los anuncios.

### Las tres etapas
| Etapa | Pregunta | Si está baja, revisa |
|---|---|---|
| **Visibilidad** | ¿Apareces en la 1ª página? | Precio vs. competencia, estadía mínima, disponibilidad, calificación |
| **Atractivo** | ¿Hacen clic en tu anuncio? | Foto de portada, título, precio en la búsqueda |
| **Cierre** | ¿Reservan después de verlo? | Precio final con tarifas, fotos interiores, descripción, reseñas recientes, reglas |

**Conversión general** resume el camino desde la búsqueda hasta la reserva.

### Cómo leer cada sección
- **Portafolio:** cada dona muestra cuánto de la meta se alcanza (llena = cumplida). Al centro está el promedio real.
- **Embudo por anuncio:** los anuncios van de menor a mayor conversión. *Si 1.000 personas te ven* traduce las tasas
  a personas, e indica el **cuello de botella**: la etapa más lejos de su meta.
- **Comparación entre anuncios:** una pestaña por etapa. La línea punteada es la meta.
- **¿Dónde se pierden?:** cuántos anuncios tienen cada cuello de botella y qué revisar.
- **Tendencia:** evolución entre capturas. Con una sola captura todavía no hay tendencia.
- **Acciones registradas y su efecto:** cambios hechos a un anuncio, con sus tasas antes y después.

Las metas están en `parametros_conversion` (andina_lab).
""")

with t_reporte:
    st.markdown("""
Resumen semanal para leer o compartir: ingresos vs meta, último mes cerrado, pronóstico, noches libres, reviews,
conversión y controles de datos.

- **Ver un reporte:** elígelo en *Reportes generados*. Se lee ahí mismo y se puede descargar.
- **Generar uno:** solo desde el computador con la base local. En la versión publicada se ven los que ya se subieron.
- **Texto con IA:** si está activado, la IA redacta el resumen y las acciones; las tablas son las mismas. Sin IA, el
  texto se escribe con reglas fijas.
""")

with t_finanzas:
    st.markdown(f"""
Explica **de dónde sale el ingreso del KPI**, reserva por reserva. Elige el mes arriba; parte en el mes en curso.

**Cómo se calcula:** a cada reserva no cancelada se le resta la limpieza, el resultado se reparte en partes iguales
por noche y se suman las noches del mes. Luego se convierte a CLP con el tipo de cambio del mes.

**Es ingreso bruto por alojamiento:** no descuenta comisión ni costos de operación.

| Sección | Cómo leerla |
|---|---|
| **Tarjetas** | El ingreso coincide con Inicio y con el reporte semanal, comparado con la meta de {META}. |
| **Cómo se llega al número** | Puente por mercado, desde el total de reservas hasta el ingreso en CLP. |
| **Por propiedad** | Ingreso, noches y participación de cada propiedad en el mes. |
| **Reserva por reserva** | Cada fila suma su *Ingreso CLP* al total. Se puede descargar en CSV. |
| **Canceladas, no suman** | Reservas canceladas con noches en ese mes, solo como referencia. |

Una reserva que cruza de un mes a otro aporta a ambos. Si aparece un aviso de **tipo de cambio**, esas noches no están
sumando: hay que agregar la tasa del mes en andina_lab.
""")

with t_glosario:
    st.markdown(f"""
| Término | Significado |
|---|---|
| **ADR** | Precio promedio por noche vendida: ingreso ÷ noches vendidas. |
| **RevPAR** | Ingreso por noche disponible, vendida o no: ingreso ÷ noches disponibles. Combina precio y ocupación. |
| **Ocupación** | Noches vendidas ÷ noches disponibles. |
| **Noche disponible** | Noche en que la propiedad estaba activa, entre su fecha de alta y de baja. |
| **Mes en curso** | El mes de hoy: sus números todavía pueden cambiar. |
| **Mes cerrado** | Mes ya terminado: sus números son definitivos. |
| **A la fecha** | Solo las noches anteriores a hoy. |
| **Mes completo** | Noches ocurridas más futuras ya reservadas, sobre todas las noches del mes. |
| **Ingreso por alojamiento** | Total de la reserva menos limpieza. No descuenta comisión. |
| **Meta** | {META} al mes de ingreso por alojamiento, para todo el portafolio. |
| **pp (puntos porcentuales)** | Diferencia directa entre porcentajes: de 70 % a 75 % son +5 pp. |
| **Estadía terminada** | Reserva cuyo check-out ya pasó. |
| **Ventana de review** | Los {DIAS} días después del check-out en que Airbnb permite dejar review. |
| **Acumulado** | Promedio de todas las reviews de una propiedad. |
| **Pronóstico (pickup)** | Lo ya reservado más las noches libres por su probabilidad histórica de venderse. |
| **Cuello de botella** | La etapa de conversión más lejos de su meta. |
| **Captura** | Foto de las métricas de conversión de Airbnb para un período. |
| **Anuncio / propiedad / departamento** | La misma unidad: cada alojamiento publicado. |
""")
