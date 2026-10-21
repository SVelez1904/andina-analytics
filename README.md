# andina_analytics

Análisis, pronóstico, IA y dashboard del negocio de arriendo de corto plazo.
Es el "cerebro" que trabaja **encima** de los datos que carga `andina_lab`.

---

## Índice

1. [Cómo encaja con andina_lab](#1-cómo-encaja-con-andina_lab)
2. [Estructura de carpetas](#2-estructura-de-carpetas)
3. [Instalación (una sola vez)](#3-instalación-una-sola-vez)
4. [Rutina: qué hacer cuando llegan datos nuevos](#4-rutina-qué-hacer-cuando-llegan-datos-nuevos)
5. [Pronóstico de ocupación](#5-pronóstico-de-ocupación)
6. [Clasificación de reviews con IA](#6-clasificación-de-reviews-con-ia)
7. [Reporte semanal](#7-reporte-semanal)
8. [Dashboard (Streamlit)](#8-dashboard-streamlit)
9. [Tablas y vistas del esquema `analitica`](#9-tablas-y-vistas-del-esquema-analitica)
10. [Seguridad y privacidad](#10-seguridad-y-privacidad)
11. [Costos de la IA](#11-costos-de-la-ia)
12. [Solución de problemas](#12-solución-de-problemas)
13. [Limitaciones conocidas e ideas para después](#13-limitaciones-conocidas-e-ideas-para-después)
14. [Referencia rápida de comandos](#14-referencia-rápida-de-comandos)

---

## 1. Cómo encaja con andina_lab

```
 Stays / Airbnb (Excel descargados)
            │
            ▼
 ┌──────────────────────────┐        usuario: stays (dueño)
 │ andina_lab  (Django)     │  ───►  esquema public
 │ importa, limpia, valida  │        tablas: reservas, avaliaciones, dim_propiedades,
 └──────────────────────────┘                hechos_airbnb_conversion, ...
                                     vistas: vw_kpis_*, vw_reviews_*, vw_scorecard_mensual,
                                             vw_controles_calidad, ...
            │  (solo lectura)
            ▼
 ┌──────────────────────────┐        usuario: analitica_app
 │ andina_analytics (este)  │  ───►  esquema analitica
 │ pronóstico, IA, reporte, │        pronósticos, temas de reviews, reportes
 │ dashboard                │
 └──────────────────────────┘
            │
            ▼
   Dashboard (navegador) · PDF semanal
```

| | andina_lab | andina_analytics |
|---|---|---|
| Para qué | **Poblar** la base: importar y limpiar | **Analizar**: pronosticar, clasificar, reportar, mostrar |
| Usuario de la base | `stays` (puede todo) | `analitica_app` (lee `public`, escribe solo en `analitica`) |
| Se usa | Cada vez que descargas un Excel | Después de importar, y para mirar el dashboard |

Los dos usan **la misma base Postgres** que corre en Docker. andina_analytics **nunca modifica**
tus tablas de negocio: si algo sale mal aquí, tus datos de andina_lab no se tocan.

**Qué se actualiza solo y qué no:**

- Las **vistas** de andina_lab (`vw_kpis_*`, `vw_reviews_*`, scorecard, controles) se calculan al
  momento de consultarlas: apenas importas, ya están al día.
- El **pronóstico** es una "foto" de un día: hay que volver a calcularlo (`--guardar`).
- La **clasificación de reviews** solo procesa las reviews nuevas cuando la corres.
- El **reporte** se genera cuando lo pides.

---

## 2. Estructura de carpetas

```
andina_analytics/
├── .env.example            plantilla de configuración (copiar a .env)
├── .env                    TU configuración: claves. Nunca se sube a Git
├── requirements.txt        librerías de Python
├── sql/
│   └── esquema_analitica.sql   crea el usuario analitica_app, el esquema analitica, tablas y vistas
├── analitica/              la lógica (se ejecuta con python -m analitica.<módulo>)
│   ├── config.py           lee el .env
│   ├── db.py               conexión a Postgres
│   ├── pronostico.py       pronóstico de ocupación e ingresos
│   ├── reviews_ia.py       clasificación de comentarios con Claude Haiku
│   └── reporte.py          reporte semanal HTML / PDF
├── app/                    dashboard Streamlit
│   ├── Inicio.py           portada (resumen)
│   ├── comun.py            colores, formatos y conexión compartidos
│   └── pages/
│       ├── 1_Ocupacion.py
│       ├── 2_Reviews.py
│       ├── 3_Conversion.py
│       └── 4_Reporte.py
├── .streamlit/config.toml  colores del dashboard
├── reportes/               aquí quedan los PDF/HTML generados
└── tests/                  pruebas automáticas (pytest)
```

---

## 3. Instalación (una sola vez)

Requisitos: Docker con la base de andina_lab corriendo, Python 3.11 o más nuevo y `psql`.

### 3.1 Entorno de Python

```bash
cd ~/andina_analytics
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`source .venv/bin/activate` hay que hacerlo **cada vez que abres una terminal nueva** para trabajar
en este proyecto (el prompt muestra `(.venv)` cuando está activo).

Para que el reporte salga en PDF, weasyprint necesita librerías del sistema:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0        # Ubuntu / Debian / WSL
sudo dnf install pango                                    # Fedora
```

Sin ellas el reporte se genera igual, pero solo en HTML.

### 3.2 Usuario y esquema de análisis

Inventa una clave **nueva** para `analitica_app` (distinta a la de `stays`) y ejecuta con el usuario
`stays` (te pedirá la clave de `stays`, la del `.env` de andina_lab):

```bash
psql -h localhost -U stays -d stays -v analitica_pass='LA-CLAVE-NUEVA' -f sql/esquema_analitica.sql
```

Qué hace:

- Crea el usuario `analitica_app` con esa clave.
- Le da permiso de **lectura** sobre todo el esquema `public`, **excepto** `dim_hospedes`,
  `vw_reservas_analisis` (tienen datos de huéspedes) y las tablas de usuarios de Django.
- Crea el esquema `analitica` con sus tablas y vistas (ver sección 9).

Se puede volver a ejecutar cuando quieras: no borra datos. Sirve para cambiar la clave o si
aparece un error de permisos.

### 3.3 Archivo `.env`

```bash
cp .env.example .env
nano .env
```

| Variable | Qué poner |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME` | Normalmente `localhost`, `5432`, `stays` |
| `ANALITICA_DB_USER` | `analitica_app` |
| `ANALITICA_DB_PASSWORD` | **La misma clave** que pusiste en `analitica_pass` |
| `ANTHROPIC_API_KEY` | Opcional. Vacío = sin IA (ver sección 11) |
| `CLAUDE_MODELO_REVIEWS`, `CLAUDE_MODELO_REPORTE` | Dejar `claude-haiku-4-5-20251001` |
| `CONFIABLE_DESDE` | `2026-05-16` (ver sección 5) |

Guarda con Ctrl+O, Enter y sal con Ctrl+X.

### 3.4 Comprobar que todo funciona

```bash
pytest -q                          # 10 pruebas, no necesitan la base
python -m analitica.pronostico     # debe mostrar el pronóstico de 3 meses
```

---

## 4. Rutina: qué hacer cuando llegan datos nuevos

### Paso 1 · andina_lab (cargar)

```bash
cd ~/andina_lab && source .venv/bin/activate
python manage.py importar_reservas data/reservas/ARCHIVO.xlsx
python manage.py importar_avaliaciones data/reviews/ARCHIVO.xlsx
python manage.py importar_conversion_airbnb data/conversion/plantilla_conversion_airbnb.xlsx   # 1 vez al mes
```

Consejo: al exportar reservas de Stays, usa un rango que **cubra las llegadas futuras** (no solo
las reservas creadas esta semana). Así se actualizan también cambios de fecha y cancelaciones.

### Paso 2 · andina_analytics (analizar)

```bash
cd ~/andina_analytics && source .venv/bin/activate
python -m analitica.pronostico --guardar     # SIEMPRE después de importar reservas
python -m analitica.reviews_ia               # si hay reviews nuevas y tienes API key
python -m analitica.reporte                  # opcional: genera el PDF semanal
python -m analitica.subir_bigquery           # SIEMPRE al final: copia los datos al dashboard
```

### Paso 3 · Mirar

El dashboard lee de **BigQuery** (no de Postgres): abre la app publicada en Streamlit Cloud, o en tu
computador:

```bash
streamlit run app/Inicio.py
```

Se abre en http://localhost:8501. Para cerrarlo, Ctrl+C en esa terminal.
El dashboard guarda los datos 5 minutos en memoria: si no ves un cambio, espera o usa el menú
⋮ → *Clear cache* y recarga.

### Frecuencia sugerida

| Qué | Cuándo |
|---|---|
| Importar reservas + pronóstico `--guardar` | 1-2 veces por semana (el dashboard avisa si el pronóstico tiene más de 7 días) |
| Importar reviews + `reviews_ia` | Cuando bajes el Excel de reviews |
| Conversión de Airbnb | 1 vez al mes (los últimos 30 días cerrados) |
| Reporte | 1 vez por semana (por ejemplo, el lunes) |
| `--backtest` | 1 vez al mes, para ver si el pronóstico sigue acertando |

---

## 5. Pronóstico de ocupación

`python -m analitica.pronostico`

### Cómo funciona (método "pickup")

Para cada propiedad y cada noche de los próximos 3 meses:

- Si la noche **ya está reservada** → cuenta 1.
- Si está **libre** → cuenta la probabilidad de que se venda a tiempo, según cuántos días faltan.

```
pronóstico del mes = noches ya reservadas + Σ (noches libres × probabilidad según anticipación)
```

**La probabilidad se aprende de tus propias reservas.** Mira, en el pasado, todas las noches que
estaban libres a X días de distancia, y cuenta cuántas terminaron vendiéndose. Por ejemplo, con tus
datos la curva quedó así:

| Días que faltan | 0-2 | 3-6 | 7-13 | 14-20 | 21-29 | 30+ |
|---|---|---|---|---|---|---|
| Prob. de que una noche libre se venda | ~7 % | ~31 % | ~46 % | ~53 % | ~58 % | ~62 % |

Luego cada propiedad se ajusta con un **factor propio**: si en los últimos 120 días vendió más
(o menos) de lo que la curva general esperaba, su probabilidad sube (o baja). Con pocos datos el
factor se acerca a 1 (suavizado), para no exagerar.

El **ingreso pronosticado** = ingreso de lo ya reservado + noches probables × ADR promedio de la
propiedad en los últimos 90 días, en la moneda de cada propiedad (CLP o BRL).

### Qué fecha usa como "hoy"

Por defecto, el día en que lo corres. Cuenta como "ya reservada" cualquier reserva creada hasta
ese mismo día (incluidas las que importaste hoy).

### Por qué `CONFIABLE_DESDE = 2026-05-16`

Las reservas migradas a Stays aparecen todas "creadas" el 15-05-2026, aunque se hicieron antes.
Eso confundiría el cálculo de anticipación, así que la curva solo aprende de reservas creadas
desde el 16-05-2026. Con el tiempo habrá más historia y será más precisa.

### Opciones

| Comando | Qué hace |
|---|---|
| `python -m analitica.pronostico` | Muestra el pronóstico en pantalla (no guarda) |
| `python -m analitica.pronostico --guardar` | Además lo guarda para el dashboard y el reporte |
| `python -m analitica.pronostico --meses 6` | Pronostica 6 meses en vez de 3 |
| `python -m analitica.pronostico --fecha-corte 2026-09-01` | "Como si hoy fuera" esa fecha |
| `python -m analitica.pronostico --csv pronostico.csv` | Exporta a CSV para Excel |
| `python -m analitica.pronostico --backtest` | Mide el error en meses pasados |

### Cómo leer el backtest

Pronostica cada mes cerrado como si fuera el día 1 y el día 15, y lo compara con lo que realmente
pasó. Muestra dos errores:

- **Error del pronóstico**: cuánto se equivocó el modelo.
- **Error sin pronóstico**: cuánto te equivocarías mirando solo lo ya reservado.

En las pruebas: ~9 puntos de ocupación por propiedad con el modelo, contra ~20-22 sin él.

### Dónde se guarda

- `analitica.pronostico_ocupacion`: una fila por propiedad y mes, por cada fecha de corte.
- `analitica.pronostico_noches`: una fila por propiedad y noche futura (reservada o no, y su probabilidad).

Si lo corres varias veces el mismo día, la foto de ese día se reemplaza. Las fotos de días
anteriores se conservan (sirven para comparar después).

---

## 6. Clasificación de reviews con IA

`python -m analitica.reviews_ia` · requiere `ANTHROPIC_API_KEY`

### Qué hace

Lee cada review que tenga comentario (público o privado) y le pide a **Claude Haiku** que extraiga
los temas concretos que menciona. Por cada tema guarda:

| Campo | Ejemplo |
|---|---|
| `tema` | limpieza, ropa_de_cama, mantenimiento, equipamiento, cocina, bano, climatizacion, wifi_tv, privacidad, ruido, seguridad, check_in, comunicacion, ubicacion, precio_valor, exactitud, espacio, vista, externo, otro |
| `sentimiento` | positivo (elogio) · negativo (queja) · neutro (sugerencia amable) |
| `severidad` | 1 = detalle · 2 = molestia clara · 3 = grave (higiene, seguridad, algo que no funcionó en toda la estadía). Solo quejas/sugerencias |
| `cita` | La frase textual del huésped (máx. 25 palabras, en su idioma) |
| `fuente` | publico o privado |
| `accion_sugerida` | Acción operativa concreta, ej. "Revisar presión del agua caliente" |

- `externo` = problemas que no dependen de ti (clima, cortes de luz, obras). No cuentan como pendientes.
- Si la review es solo un elogio general ("todo excelente") se marca como revisada sin temas.
- La IA no inventa causas: si una nota es 4 sin explicación, no genera tema.

### Opciones

| Comando | Qué hace |
|---|---|
| `python -m analitica.reviews_ia --dry-run --limite 3` | Muestra exactamente qué se enviaría. **No gasta** |
| `python -m analitica.reviews_ia --limite 5` | Clasifica solo 5 (para probar) |
| `python -m analitica.reviews_ia` | Clasifica todas las que faltan |
| `python -m analitica.reviews_ia --reclasificar` | Vuelve a clasificar todas (reemplaza los temas) |

Al terminar muestra cuántos tokens usó y el costo aproximado en dólares.

### Para qué sirve

- **Pendientes por propiedad** (`vw_pendientes_propiedad`): quejas de los últimos 90 días ordenadas
  por **prioridad = suma de severidades**. Una queja grave pesa 3; un detalle, 1. Si se repite en
  varias reviews, sube.
- **Fortalezas** (`vw_fortalezas_propiedad`): lo que más elogian; úsalo en título y descripción del anuncio.
- Ambas aparecen en la página **Reviews** del dashboard y en el reporte.

### Criticidad de reviews (viene de andina_lab, no de la IA)

| Estado | Regla |
|---|---|
| 🔴 Crítico | Promedio acumulado < 4,80, **o** promedio 3 meses < 4,70, **o** alguna review ≤ 3 este mes |
| 🟠 Alerta | Acumulado < 4,90, **o** 3 meses < 4,85 |
| 🟢 OK | El resto |
| ⚪ Sin datos suficientes | Menos de 3 reviews |

---

## 7. Reporte semanal

`python -m analitica.reporte`

### Contenido

1. **Resumen** y **Acciones de la semana** (texto).
2. Desempeño del último mes cerrado: ocupación, ADR, RevPAR por mercado y por propiedad.
3. Pronóstico de los próximos meses (usa el último `--guardar`; avisa si está viejo).
4. Noches libres en los próximos 21 días.
5. Reviews: estado por propiedad y pendientes según los comentarios.
6. Conversión de Airbnb: última captura y cuello de botella de cada propiedad.
7. Controles de calidad de datos que están en "REVISAR".

### ¿Quién escribe el texto?

- **Con API key**: Claude Haiku redacta el resumen y las acciones **usando solo las cifras de las
  tablas** (recibe un resumen numérico, no tus datos crudos). Al pie se indica el modelo.
- **Sin API key** o con `--sin-ia`: el texto se arma con reglas fijas (mismas tablas, redacción más simple).

Las tablas y cifras **siempre** salen de la base, nunca de la IA.

### Dónde queda

- Archivo: `reportes/reporte_AAAA-MM-DD.pdf` (y `.html`).
- Historial: tabla `analitica.reportes` y página **Reporte** del dashboard (desde ahí también se descarga).

### Opciones

| Comando | Qué hace |
|---|---|
| `python -m analitica.reporte` | Genera con IA si hay clave |
| `python -m analitica.reporte --sin-ia` | Sin llamar a la API |
| `python -m analitica.reporte --sin-pdf` | Solo HTML |
| `python -m analitica.reporte --no-guardar` | No lo registra en el historial |
| `python -m analitica.reporte --fecha-corte 2026-10-06` | Reporte "al" día indicado |

---

## 8. Dashboard (Streamlit)

`streamlit run app/Inicio.py` → http://localhost:8501

El dashboard **lee de BigQuery**. Postgres sigue siendo tu base de trabajo: ahí importa andina_lab y ahí
escriben el pronóstico, la clasificación de reviews y el reporte. `python -m analitica.subir_bigquery`
copia a BigQuery solo las tablas y vistas que usa el dashboard (lista `OBJETOS` en ese archivo), cada schema
a un dataset con el mismo nombre (`public`, `analitica`). Usa el usuario `analitica_app`, así que los datos
personales de huéspedes nunca salen de tu computador.

### 8.1 Primera vez en BigQuery

```bash
gcloud auth application-default login                 # tu usuario de Google, una vez
# en el .env: GCP_PROJECT=tu-proyecto-id
python -m analitica.subir_bigquery --dry-run          # revisa qué se va a subir
python -m analitica.subir_bigquery
```

Con este volumen, BigQuery queda dentro de la capa gratuita (10 GB de almacenamiento y 1 TB de consultas al
mes; las cargas no se cobran). Igual conviene crear una alerta de presupuesto de USD 1 en Facturación.

### 8.2 Publicar en Streamlit Community Cloud

1. Cuenta de servicio **solo de lectura** para la app:
   ```bash
   P=tu-proyecto-id
   gcloud iam service-accounts create streamlit-lector --project=$P
   gcloud projects add-iam-policy-binding $P --member=serviceAccount:streamlit-lector@$P.iam.gserviceaccount.com --role=roles/bigquery.dataViewer
   gcloud projects add-iam-policy-binding $P --member=serviceAccount:streamlit-lector@$P.iam.gserviceaccount.com --role=roles/bigquery.jobUser
   gcloud iam service-accounts keys create llave-streamlit.json --iam-account=streamlit-lector@$P.iam.gserviceaccount.com
   ```
2. En share.streamlit.io → **Create app**: repositorio, rama `master`, *Main file path* `app/Inicio.py`.
3. **Advanced settings → Secrets**: pega el contenido de `.streamlit/secrets.toml.example` con los valores
   de `llave-streamlit.json`. Después **borra** el JSON de tu computador (nunca lo subas a Git).
4. Configura el inicio de sesión (8.3). Con eso la app puede quedar pública en **Settings → Sharing**:
   igual solo entran cuentas del dominio de Andina Group.

### 8.3 Inicio de sesión con Google (gratis)

El dashboard pide ingresar con Google (`st.login`) y solo deja pasar correos de `dominios_permitidos`.
Si falta la configuración, la app no muestra datos.

1. En Google Cloud (mismo proyecto) → **APIs y servicios → Pantalla de consentimiento de OAuth**:
   tipo **Interno** si el proyecto pertenece a la organización de Google Workspace de Andina Group
   (así Google ya rechaza cuentas de fuera); si no, **Externo** y publícala.
2. **Credenciales → Crear credenciales → ID de cliente de OAuth → Aplicación web**. En *URIs de
   redireccionamiento autorizados* agrega `https://tu-app.streamlit.app/oauth2callback` (y
   `http://localhost:8501/oauth2callback` para probar en tu computador).
3. En Streamlit Cloud → **Settings → Secrets**, agrega `dominios_permitidos` y la sección `[auth]` de
   `.streamlit/secrets.toml.example` con el *client_id*, *client_secret* y un `cookie_secret` aleatorio.

En tu computador puedes saltarte el login con `SIN_LOGIN=1 streamlit run app/Inicio.py`.

La app muestra los datos de la última subida (`_cargado_en` en cada tabla). En la nube, la página **Reporte**
solo muestra y descarga; los reportes se generan en tu computador y se suben con `subir_bigquery`
(si generas desde el dashboard local, se suben solos).

| Página | Qué muestra |
|---|---|
| **Inicio** | Último mes cerrado por mercado (ocupación, ADR, RevPAR con variación vs. mes anterior); propiedades en Crítico/Alerta; pronóstico de los próximos meses; noches libres de los próximos 7 días; aviso si hay controles de datos para revisar |
| **Ocupación** | Evolución mensual por mercado; ranking de propiedades por mes; pronóstico por propiedad (azul oscuro = ya reservado, azul claro = lo que se espera vender); mapa de calor de los próximos 21 días (gris = reservada, azul claro = libre y con poca probabilidad → necesita precio o promoción) |
| **Reviews** | Estado y criticidad; nota general mes a mes por propiedad (línea punteada = 4,80); notas por categoría de los últimos 3 meses; temas de los comentarios (quejas vs. elogios), pendientes con citas y acciones, fortalezas |
| **Conversión** | Embudo de Airbnb de la última captura: visibilidad (1ª página) → atractivo (búsqueda→anuncio) → cierre (anuncio→reserva), con ✅/⚠️ frente a la referencia y el cuello de botella; tendencia por propiedad; acciones registradas |
| **Reporte** | Historial y descargas; en tu computador, además, botón para generar el reporte de hoy |

Cada gráfico tiene debajo **"Ver tabla"** con los números exactos (se puede descargar a CSV desde la tabla).

ADR y RevPAR se muestran **por mercado y en su moneda** (CLP para Chile, BRL para Brasil); nunca se mezclan en un mismo eje.

---

## 9. Tablas y vistas del esquema `analitica`

Las puedes consultar en pgAdmin → base `stays` → Schemas → `analitica`.

| Objeto | Tipo | Contenido |
|---|---|---|
| `review_temas` | tabla | Un tema por fila (ver sección 6). Se borra solo si se borra la review |
| `vw_review_temas_detalle` | vista | Temas + fecha, propiedad y nota de la review |
| `vw_temas_mensual` | vista | Conteo de elogios/quejas/sugerencias por propiedad, mes y tema |
| `vw_pendientes_propiedad` | vista | Quejas de los últimos 90 días por propiedad y tema, con prioridad, citas y acciones |
| `vw_fortalezas_propiedad` | vista | Elogios por propiedad y tema, con citas |
| `pronostico_ocupacion` | tabla | Pronóstico por fecha de corte, propiedad y mes |
| `vw_pronostico_actual` | vista | Solo el último pronóstico guardado, con % reservado y % pronosticado |
| `pronostico_noches` | tabla | Pronóstico noche a noche |
| `vw_noches_en_riesgo` | vista | Noches **libres** de los próximos 21 días del último pronóstico, con su probabilidad |
| `reportes` | tabla | Historial de reportes: texto, cifras (JSON), modelo de IA, tokens, archivo |

Ejemplos útiles en pgAdmin:

```sql
-- Qué corregir primero en cada propiedad
SELECT propiedad, tema, menciones, prioridad, acciones_sugeridas
FROM analitica.vw_pendientes_propiedad
ORDER BY prioridad DESC;

-- Noches libres esta semana, de la menos a la más probable de venderse
SELECT propiedad, fecha, dia_semana, probabilidad
FROM analitica.vw_noches_en_riesgo
WHERE dias_para_la_noche <= 6
ORDER BY probabilidad;

-- Cómo cambió el pronóstico de un mes entre dos fechas de corte
SELECT fecha_corte, SUM(noches_pronostico) / SUM(disponibles) AS ocupacion_pronostico
FROM analitica.pronostico_ocupacion
WHERE mes = '2026-11-01'
GROUP BY fecha_corte ORDER BY fecha_corte;
```

---

## 10. Seguridad y privacidad

- **Usuario con permisos mínimos**: `analitica_app` solo lee `public` y escribe en `analitica`.
  No puede modificar reservas, propiedades ni nada de andina_lab.
- **Sin datos personales**: `analitica_app` no puede leer `dim_hospedes`, `vw_reservas_analisis`
  ni las tablas de usuarios de Django.
- **A la IA nunca se envían** nombres de huéspedes, códigos de reserva ni datos de contacto.
  A `reviews_ia` le llega: nombre del anuncio, notas y comentarios. Al reporte: cifras agregadas.
  Usa `--dry-run` para verlo tú misma.
- **El `.env` no se sube a Git** (está en `.gitignore`), igual que los Excel y los reportes.
- No pegues claves (de la base o de la API) en chats ni correos. Si se filtró una:
  - Clave de la base → vuelve a ejecutar `esquema_analitica.sql` con una nueva y actualiza el `.env`.
  - API key → bórrala en platform.claude.com y crea otra.

---

## 11. Costos de la IA

Todo funciona **sin** API key, excepto `reviews_ia`. Si la quieres:

1. Crea una cuenta en https://platform.claude.com (es aparte de la suscripción de Claude.ai).
2. *Billing*: carga crédito y, si quieres, pon un **límite de gasto mensual**.
3. *API Keys*: crea una clave (empieza con `sk-ant-`; se muestra una sola vez).
4. Pégala en el `.env` como `ANTHROPIC_API_KEY=sk-ant-...`.
5. Prueba: `python -m analitica.reviews_ia --limite 5`.

Costo aproximado con Haiku:

| Tarea | Costo |
|---|---|
| Clasificar ~500 reviews | < 1 USD (una sola vez; después solo las nuevas) |
| Un reporte semanal | < 0,01 USD |

---

## 12. Solución de problemas

| Mensaje / síntoma | Causa | Solución |
|---|---|---|
| `password authentication failed for user "analitica_app"` | La clave del `.env` no coincide con la de `analitica_pass` | Corrige `ANALITICA_DB_PASSWORD` en `.env` (sin espacios al final). Si no la recuerdas, vuelve a ejecutar `esquema_analitica.sql` con una nueva |
| `Connection refused` / "No me pude conectar a la base" | Docker o el contenedor de Postgres está apagado | Inicia Docker y el contenedor (`docker start <nombre>`) |
| `permission denied for table ...` | Una tabla/vista nueva de andina_lab sin permisos | Vuelve a ejecutar `esquema_analitica.sql` |
| `relation "public.vw_..." does not exist` | Falta ejecutar un `.sql` de andina_lab | Ejecuta en andina_lab `vw_kpis.sql`, `vw_reviews.sql`, `vw_scorecard.sql`, `controles_calidad.sql` (en ese orden) |
| `ModuleNotFoundError: No module named 'analitica'` | No estás en la carpeta del proyecto o falta activar el entorno | `cd ~/andina_analytics && source .venv/bin/activate` |
| `streamlit: command not found` | Entorno no activado | `source .venv/bin/activate` |
| El dashboard no muestra lo recién importado | Pronóstico no recalculado o caché | `python -m analitica.pronostico --guardar` y luego ⋮ → *Clear cache* |
| Las noches reservadas no coinciden con Stays | Reservas no importadas, rango de exportación corto o estado no considerado | Revisa en pgAdmin la tabla `reservas` de esa propiedad y `vw_fct_noches` (consultas abajo) |
| `Falta ANTHROPIC_API_KEY` | No hay clave de IA | Normal si no la tienes; usa `--sin-ia` en el reporte |
| El reporte sale solo en HTML | Faltan librerías de weasyprint | Ver sección 3.1 |
| Una propiedad que ya no operas baja la ocupación | Sigue contando como disponible | Ponle `fecha_baja` en `propiedad_fechas` (andina_lab) |

Verificar las reservas de una propiedad en pgAdmin (como `stays`):

```sql
SELECT r.id_reserva, r.numero_registro, r.data_criacao, r.data_chegada, r.data_checkout,
       r.numero_noites, r.status_reserva, r.data_cancelamento
FROM reservas r
JOIN dim_propiedades p ON p.id_interno = r.id_propriedade
WHERE p.nome_anuncio = 'ENCINA 1101'
  AND r.data_checkout > '2026-10-01' AND r.data_chegada < '2026-11-01'
ORDER BY r.data_chegada;

SELECT n.fecha, n.vendida, n.fecha_reserva
FROM vw_fct_noches n
JOIN dim_propiedades p ON p.id_interno = n.id_propriedade
WHERE p.nome_anuncio = 'ENCINA 1101'
  AND n.fecha BETWEEN '2026-10-01' AND '2026-10-31'
ORDER BY n.fecha;
```

---

## 13. Limitaciones conocidas e ideas para después

**Limitaciones actuales**

- El pronóstico **no considera temporada**: diciembre-febrero (y feriados) pueden salir bajos.
- No conoce **bloqueos** del calendario (el Excel de reservas de Stays no los trae): los ve como noches libres.
- No anticipa **cancelaciones** futuras.
- Historia corta: aprende desde el 16-05-2026.
- La conversión de Airbnb depende de tu captura manual mensual.
- Si borras y vuelves a crear `vw_reservas_analisis` en andina_lab, vuelve a ejecutar
  `esquema_analitica.sql` para que `analitica_app` siga sin acceso a ella.

**Ideas para siguientes versiones**

- Estacionalidad en el pronóstico cuando haya 12 meses de historia confiable.
- Cargar bloqueos desde Stays o PriceLabs.
- Sugerencias de precio para noches en riesgo (cruzando con PriceLabs).
- Script `actualizar.sh` que corra toda la rutina con un comando.
- Programar el reporte para que se genere solo cada lunes.

---

## 14. Referencia rápida de comandos

```bash
# Siempre primero
cd ~/andina_analytics && source .venv/bin/activate

# Rutina
python -m analitica.pronostico --guardar
python -m analitica.reviews_ia
python -m analitica.reporte
python -m analitica.subir_bigquery
streamlit run app/Inicio.py

# Diagnóstico
python -m analitica.pronostico --backtest
python -m analitica.reviews_ia --dry-run --limite 3
pytest -q

# Volver a aplicar permisos / cambiar clave
psql -h localhost -U stays -d stays -v analitica_pass='CLAVE' -f sql/esquema_analitica.sql
```