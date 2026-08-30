# CartIA Legal

Agente RAG de investigación jurídica para abogados y estudios jurídicos de Argentina.
Responde consultas de derecho argentino fundadas en un corpus propio de normativa,
jurisprudencia y doctrina, citando siempre la fuente que respalda cada afirmación.

## Arquitectura

Monorepo con cuatro servicios:

| Servicio     | Rol                                                                              | Puerto | Hosting            |
| ------------ | -------------------------------------------------------------------------------- | ------ | ------------------ |
| `ui/`        | Chat estilo ChatGPT con streaming y dictado por voz                              | 3000   | Vercel             |
| `backend/`   | Workflow RAG en LangGraph, auth JWT, conversaciones, transcripción               | 8000   | Cloud Run          |
| `rag/`       | Retrieval híbrido sobre pgvector: devuelve los chunks más relevantes como context | 8002   | Cloud Run (privado)|
| `rag-loader/`| Ingesta on-demand: reindex completo o documento individual                        | 8003   | Cloud Run Job / local |

`shared/` es un paquete Python (`cartia-shared`) con los DTOs, los enums del dominio
legal, el cliente de embeddings y el DDL del índice vectorial. Vive ahí porque tanto `rag`
como `rag-loader` tienen que coincidir exactamente en modelo de embeddings,
dimensionalidad y nombres de tabla: si divergen, el retrieval se degrada en silencio.

```
        ┌──────────┐   HTTPS/SSE   ┌───────────┐   HTTP interno   ┌────────┐
        │    ui    │ ────────────► │  backend  │ ───────────────► │  rag   │
        │ (Vercel) │ ◄──────────── │ (LangGraph)│ ◄─────────────── │        │
        └──────────┘   tokens      └───────────┘   chunks         └────┬───┘
                                                                       │ SQL
                                        ┌──────────────┐               ▼
                                        │  rag-loader  │ ───────► Postgres + pgvector
                                        │  (on-demand) │           (Cloud SQL / Neon)
                                        └──────────────┘
```

La UI habla solo con el backend. El backend es el único que consulta el servicio RAG, y el
servicio RAG el único dueño del esquema del índice. El rag-loader escribe ese índice.

### Stack

| Área              | Elección                                                                     |
| ----------------- | ---------------------------------------------------------------------------- |
| Vector store      | pgvector sobre Postgres (HNSW, distancia coseno, 1536 dimensiones)           |
| Embeddings        | `gemini-embedding-001`, normalizados L2 del lado del cliente                 |
| LLM               | Gemini (Google AI Studio), un modelo distinto por nodo del grafo             |
| Orquestación      | LangGraph                                                                    |
| Backend           | FastAPI + SQLModel + Alembic, `uv` como gestor de dependencias                |
| Frontend          | Next.js (App Router) + Tailwind v4 + TanStack Query + Zustand                 |
| Entorno local     | Tilt sobre Kubernetes                                                        |
| CI/CD             | GitHub Actions → Cloud Run vía Workload Identity Federation, y Vercel        |

## El workflow RAG

El grafo de LangGraph vive en `backend/app/graphs/legal_rag.py`.

```
     START
       │
       ▼
  guardrails ──(no es derecho argentino)──►  reject ──► END
       │
       ▼
    rewrite      consulta coloquial ──► 1-3 consultas técnicas de búsqueda
       │
       ▼
   retrieve ◄────────────────┐          llama al servicio RAG y fusiona multi-query
       │                     │
       ▼                     │
     grade ──(insuficiente)──┘ broaden: suelta los filtros y duplica el top_k
       │
       ▼
   generate ──► END           respuesta en streaming con citas numeradas
```

**`guardrails` es el primer nodo, a propósito.** Rechazar antes de reescribir, embeddear,
buscar y generar evita gastar tokens del modelo grande en consultas fuera de alcance, y
deja registrado el motivo del rechazo en la tabla `messages`. Tiene dos capas: una
determinística contra intentos de override de instrucciones (no depende de que el modelo
"se acuerde" de resistirlos) y una de clasificación con LLM sobre pertinencia al derecho
argentino. Ante error de la API el clasificador admite la consulta: una falla transitoria
no debería dejar el producto inutilizable.

`rewrite` traduce la consulta al registro del foro ("me echaron" → "despido sin justa
causa") y preserva textualmente los literales que la consulta traiga ("art. 245 LCT",
"Ley 27.401"), porque de esos literales depende la rama léxica de la búsqueda.

`grade` evalúa si los chunks alcanzan para fundar la respuesta. Si no, `broaden` reintenta
una vez sin filtros y con el doble de candidatos. Si el segundo intento tampoco alcanza, se
responde de todos modos pero con instrucciones explícitas de admitir qué no se pudo
determinar, en lugar de completar con conocimiento general.

### Por qué la búsqueda es híbrida

`rag/app/services/retrieval.py` corre dos búsquedas en paralelo y fusiona los rankings con
Reciprocal Rank Fusion:

- **Vectorial** (HNSW sobre `pgvector`): cubre las preguntas parafraseadas.
- **Léxica** (`tsvector` en español): cubre los literales. En derecho, "art. 245 LCT" o
  "Fallos 340:1163" son identificadores exactos que el espacio semántico no distingue de
  forma confiable de sus vecinos.

RRF combina ambos sin tener que calibrar scores que están en escalas distintas.

### Por qué el chunking es sensible a la estructura

En normativa, la unidad semántica es el artículo, no la ventana de N caracteres. Un
abogado pregunta qué dice el art. 245, y un chunk que corta ese artículo al medio no
alcanza para responder. `rag-loader/app/services/chunking.py` detecta la estructura
(`ARTÍCULO n`, `TÍTULO`, `CAPÍTULO`), parte por artículo, agrupa artículos cortos
consecutivos, subdivide los largos repitiendo la referencia en cada parte, y arrastra el
título vigente como encabezado del chunk. Si el documento no tiene estructura de artículos
—un fallo, doctrina, un contrato— cae a partición por párrafo con overlap.

Cada chunk se embeddea con el título del documento y su referencia estructural como
prefijo. Sin eso, un chunk que dice "el plazo será de treinta días" es indistinguible
entre la LCT y el CCyC.

## Correr local

### Requisitos

- Docker Desktop con Kubernetes habilitado (o kind / minikube / Rancher Desktop / OrbStack)
- [Tilt](https://docs.tilt.dev/install.html) y `kubectl`
- [uv](https://docs.astral.sh/uv/) y Node 22+
- Una API key de [Google AI Studio](https://aistudio.google.com/apikey)

### Levantar el entorno

```bash
cp .env.example .env
# Completar GOOGLE_API_KEY en .env

tilt up
```

Tilt levanta Postgres con pgvector, el servicio RAG, el backend y la UI en el cluster, y
corre las migraciones de Alembic y la creación del esquema del índice como tareas locales.

| Servicio | URL                            |
| -------- | ------------------------------ |
| UI       | http://localhost:3000          |
| Backend  | http://localhost:8000/docs     |
| RAG      | http://localhost:8002/docs     |
| Postgres | localhost:5432 (`cartia`)      |

**El rag-loader corre como proceso local, no en el cluster.** Los documentos a ingestar
viven en el disco del estudio, y montar un directorio del host dentro del cluster es
frágil (sobre todo en Windows). Como proceso local lee `rag-loader/documents/` directo y
escribe en Postgres por el port-forward.

### Cargar documentos

#### Scraper de normas oficiales

El loader incluye un scraper que baja normas nacionales desde fuentes oficiales y las
deja clasificadas por materia, listas para ingestar:

1. **Catálogo**: baja la base InfoLEG publicada en
   [datos.jus.gob.ar](https://datos.jus.gob.ar/dataset/base-de-datos-legislativos-infoleg)
   (Ministerio de Justicia, actualización mensual). Trae por norma: tipo, número,
   organismo, fechas de sanción y Boletín Oficial, observaciones y la URL directa al
   texto vigente.
2. **Clasificación**: cada norma cae en una carpeta por materia (`laboral/`,
   `civil-comercial/`, `consumo/`, `procesal/`, `penal/`, `tributario/`, etc.) con un
   mapa curado para las normas más consultadas (LCT, CCCyC, CPCCN, LGS...) y reglas por
   keywords para el resto. Lo que no clasifica va a `otros/` para revisión, nunca se
   descarta.
3. **Descarga**: el texto vigente se baja de InfoLEG con delay entre requests, User-Agent
   identificable y cache en disco. Se guarda como `.txt` limpio más un sidecar
   `.meta.json` con toda la metadata oficial, incluido el **estado de vigencia**
   (`vigente` / `parcialmente_vigente` / `derogada`, inferido de las observaciones del
   catálogo).

```bash
cd rag-loader

# 1. Bajar el catálogo (una vez; se reusa entre corridas)
uv run cartia-loader scrape-catalog

# 2. Preview: cuántas normas caerían en cada carpeta, sin descargar
uv run cartia-loader scrape-list
uv run cartia-loader scrape-list --materia laboral --materia consumo

# 3. Descargar (escribe en documents/<materia>/)
uv run cartia-loader scrape --materia laboral --materia civil-comercial --limit 100
uv run cartia-loader scrape --anio-desde 2000            # todo, desde 2000
uv run cartia-loader scrape --incluir-derogadas          # también las derogadas

# 4. Ingestar lo descargado
uv run cartia-loader ingest .
```

Las corridas son idempotentes: un manifiesto (`documents/_catalogo/manifest.json`)
registra qué se bajó, y `--force` fuerza la re-descarga. Las normas derogadas quedan
marcadas con `estado` y el backend las excluye del retrieval por defecto
(`RETRIEVAL_EXCLUIR_DEROGADAS=false` para cambiarlo); en la UI las citas muestran un
badge de vigencia.

#### Documentos propios

Poné los archivos en `rag-loader/documents/` (soporta `.pdf`, `.docx`, `.txt`, `.md`,
`.html`) y disparalos desde la UI de Tilt, o por CLI:

```bash
cd rag-loader

# Dry-run: metadata inferida y chunks, sin escribir en la base ni llamar a la API.
# Es la forma barata de calibrar el chunking contra un documento nuevo.
uv run cartia-loader inspect "leyes/ley-20744-lct.pdf"

# Ingesta incremental de todo el directorio (saltea lo que no cambió)
uv run cartia-loader ingest .

# Un solo documento, con metadata explícita
uv run cartia-loader ingest "fallos/csjn-recurso.pdf" \
  --doc-type fallo --jurisdiction nacional --organo CSJN --anio 2024

# Reindex completo: BORRA el índice y lo reconstruye
uv run cartia-loader reindex

# Qué hay cargado
uv run cartia-loader status
```

Desde Tilt, los mismos comandos están como recursos manuales: `rag-loader:ingest`,
`rag-loader:reindex`, `rag-loader:status`, más dos botones en la vista del recurso `rag`.

#### Metadata

La metadata es lo que después permite filtrar el retrieval por jurisdicción, fuero, tipo
de norma o rango de años. El loader la infiere del nombre del archivo y del encabezado, y
se puede corregir con dos niveles de override, en orden de precedencia creciente:

- `_meta.json` en un directorio: aplica a todos los documentos de esa carpeta.
- `<archivo>.pdf.meta.json`: aplica a ese documento.
- Flags del CLI: ganan sobre todo lo anterior.

```json
{
  "doc_type": "convenio_colectivo",
  "jurisdiction": "nacional",
  "fuero": "laboral",
  "organo": "Ministerio de Trabajo",
  "anio": 2024,
  "estado": "vigente"
}
```

`estado` admite `vigente`, `parcialmente_vigente` y `derogada`. Si no se informa queda
en NULL ("sin dato"), que es distinto de vigente: el filtro de vigencia del retrieval
solo excluye lo que está explícitamente derogado.

Verificá siempre con `inspect` antes de una ingesta grande: un PDF escaneado sin capa de
texto falla de forma explícita (necesita OCR, que este pipeline no hace).

## El dictado por voz

`ui/lib/useVoiceInput.ts` usa dos estrategias y elige en runtime:

1. **Web Speech API** cuando el browser la expone (Chrome, Edge, Safari): transcribe en
   vivo, sin costo y sin latencia al final.
2. **MediaRecorder + `POST /transcribe`** como fallback (Firefox, o cuando
   `SpeechRecognition` falla): graba el audio y lo transcribe con Gemini al soltar.

El endpoint de transcripción sesga el prompt hacia vocabulario jurídico argentino, que es
donde los transcriptores genéricos fallan más: devuelve "LCT" y no "elecé té", "artículo
245" y no "artículo doscientos cuarenta y cinco".

## Deploy

### Bootstrap de GCP (una sola vez)

```bash
export GCP_PROJECT_ID=mi-proyecto
export GITHUB_REPO=usuario/cartia-legal
bash infra/gcp/bootstrap.sh
```

El script habilita las APIs, crea el repositorio de Artifact Registry, una service account
de runtime por servicio (permisos mínimos: si se compromete el backend, no queda con los
permisos del loader, que puede borrar el índice completo) y configura Workload Identity
Federation con una condición sobre `assertion.repository`, para que ningún otro repositorio
de GitHub pueda obtener credenciales del proyecto. **No se usan claves JSON de service
account en ningún momento.** Al final imprime los valores exactos a cargar en GitHub.

### Base de datos

Cloud SQL para Postgres (o Neon) con la extensión `vector`. Un solo Postgres sirve a los
dos esquemas: las tablas de la aplicación (`users`, `conversations`, `messages`) las
maneja Alembic desde el backend, y las del índice (`rag_documents`, `rag_chunks`) las crea
el rag-loader con `cartia-loader init-schema`.

### Workflows

| Workflow                 | Dispara con                              | Destino                        |
| ------------------------ | ---------------------------------------- | ------------------------------ |
| `ci.yml`                 | todo PR y push a `main`                  | ruff + pytest + build de la UI |
| `deploy-backend.yml`     | cambios en `backend/**` o `shared/**`    | Cloud Run (público)            |
| `deploy-rag.yml`         | cambios en `rag/**` o `shared/**`        | Cloud Run (privado)            |
| `deploy-rag-loader.yml`  | cambios en `rag-loader/**` o `shared/**` | Cloud Run Job                  |
| `deploy-ui.yml`          | cambios en `ui/**`                       | Vercel (preview en PR)         |

Un cambio en `shared/**` dispara los tres deploys de Python, porque los tres lo tienen
como dependencia.

El deploy del backend corre `alembic upgrade head` **antes** del deploy: si la migración
falla, la revisión vieja sigue sirviendo tráfico con un esquema que le sirve.

El servicio RAG se despliega con `--no-allow-unauthenticated`. El backend lo invoca con un
ID token del metadata server (`backend/app/services/gcp_identity.py`) más el header
`X-Internal-Token`: dos capas, una de infraestructura y una de aplicación.

### Configuración de GitHub

En el environment `Production`:

**Variables**

```
GCP_PROJECT_ID  GCP_REGION  GAR_REPOSITORY  GCP_WIF_PROVIDER  GCP_DEPLOY_SA
BACKEND_RUNTIME_SERVICE_ACCOUNT  RAG_RUNTIME_SERVICE_ACCOUNT
RAG_LOADER_RUNTIME_SERVICE_ACCOUNT
RAG_SERVICE_URL  CORS_ORIGINS  NEXT_PUBLIC_API_URL  EMBEDDING_DIMENSIONS
```

**Secrets**

```
BACKEND_DATABASE_URL  RAG_DATABASE_URL  JWT_SECRET  GOOGLE_API_KEY  INTERNAL_TOKEN
VERCEL_TOKEN  VERCEL_ORG_ID  VERCEL_PROJECT_ID
LANGSMITH_API_KEY (opcional)
```

El proyecto de Vercel tiene que tener **Root Directory** = `ui`.

`RAG_SERVICE_URL`, `CORS_ORIGINS` y `NEXT_PUBLIC_API_URL` dependen de las URLs que Cloud
Run genera, así que se completan después del primer deploy.

## Desarrollo

```bash
# Backend
cd backend && uv sync --group dev && uv run ruff check . && uv run pytest -q
uv run alembic revision --autogenerate -m "descripcion"

# RAG
cd rag && uv sync --group dev && uv run ruff check .

# RAG loader
cd rag-loader && uv sync --group dev && uv run ruff check . && uv run pytest -q

# UI
cd ui && npm ci && npm run typecheck && npm run lint && npm run build
```

Los tests cubren las dos piezas donde un bug es silencioso y caro: el chunker (si parte mal
los artículos, el retrieval empeora sin que nada falle) y la capa determinística del
guardrail (la única parte verificable sin red).

## Notas

- **`EMBEDDING_DIMENSIONS` no se cambia en caliente.** Los vectores viejos dejan de ser
  comparables con los nuevos: cambiarla obliga a un reindex completo. HNSW en pgvector
  soporta hasta 2000 dimensiones. `gemini-embedding-001` sólo devuelve vectores
  normalizados en su dimensionalidad nativa (3072), así que para cualquier valor menor la
  normalización L2 la hace `shared/cartia_shared/embeddings.py`.
- **Los documentos nunca se versionan.** `rag-loader/documents/**` está en `.gitignore`:
  puede haber expedientes con datos de clientes.
- **Los tokens de la UI viven en `localStorage`**, lo que los expone a XSS. Para producción
  conviene migrar a cookies `httpOnly` emitidas por el backend; el store de Zustand ya
  está aislado detrás de una interfaz (`ui/lib/auth.ts`) para que el cambio no toque los
  componentes.
