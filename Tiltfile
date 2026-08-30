# -*- mode: Python -*-
#
# Entorno local completo de CartIA Legal sobre Kubernetes.
#
#   En el cluster:  postgres (pgvector) · rag · backend · ui
#   Como proceso local: rag-loader
#
# El rag-loader corre fuera del cluster a proposito: los documentos a ingestar viven en el
# disco del abogado, y montar un directorio del host dentro del cluster es fragil (sobre
# todo en Windows). Como proceso local lee `rag-loader/documents/` directo y escribe en
# Postgres por el port-forward, que es exactamente como va a correr en produccion.
#
# Recursos manuales (se disparan con el boton de Tilt, no corren solos):
#   rag-loader:ingest   -> ingesta incremental de DOCUMENTS_DIR
#   rag-loader:reindex  -> borra el indice y lo reconstruye
#   backend:migrate     -> alembic upgrade head

load("ext://uibutton", "cmd_button", "location")

allow_k8s_contexts(["docker-desktop", "kind-kind", "minikube", "rancher-desktop", "orbstack"])

# --------------------------------------------------------------------- configuracion

ENV_FILE = ".env"

def read_env_file(path):
    """Parsea un .env a diccionario. Se hace en Starlark para que sea portable."""
    if not os.path.exists(path):
        fail(
            "Falta el archivo {}. Copialo desde .env.example y completá GOOGLE_API_KEY: ".format(path)
            + "cp .env.example .env"
        )
    values = {}
    for line in str(read_file(path)).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values

env = read_env_file(ENV_FILE)

def required(key):
    value = env.get(key, "")
    if not value:
        fail("{} está vacío en {}. Es obligatorio para levantar el entorno.".format(key, ENV_FILE))
    return value

GOOGLE_API_KEY = required("GOOGLE_API_KEY")
POSTGRES_PASSWORD = env.get("POSTGRES_PASSWORD", "cartia-local")
JWT_SECRET = env.get("JWT_SECRET", "jwt-secret-solo-para-desarrollo-local-0123456789")
INTERNAL_TOKEN = env.get("INTERNAL_TOKEN", "token-interno-local")
EMBEDDING_DIMENSIONS = env.get("EMBEDDING_DIMENSIONS", "1536")

# Los servicios del cluster resuelven Postgres por el nombre del Service; los procesos
# locales, por el port-forward.
DB_URL_CLUSTER = "postgresql+psycopg://cartia:{}@postgres:5432/cartia".format(POSTGRES_PASSWORD)
DB_URL_LOCAL = "postgresql+psycopg://cartia:{}@localhost:5432/cartia".format(POSTGRES_PASSWORD)

# --------------------------------------------------------------------- secret compartido

k8s_yaml(
    encode_yaml(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "cartia-secrets"},
            "type": "Opaque",
            "stringData": {
                "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
                "DATABASE_URL": DB_URL_CLUSTER,
                "GOOGLE_API_KEY": GOOGLE_API_KEY,
                "JWT_SECRET": JWT_SECRET,
                "INTERNAL_TOKEN": INTERNAL_TOKEN,
                "EMBEDDING_DIMENSIONS": EMBEDDING_DIMENSIONS,
            },
        }
    )
)

# El Secret no pertenece a ningun workload, asi que sin esto Tilt lo agrupa en
# "uncategorized".
k8s_resource(
    new_name="secrets",
    objects=["cartia-secrets:secret"],
    labels=["infra"],
)

# --------------------------------------------------------------------- postgres

k8s_yaml("infra/k8s/postgres.yaml")
k8s_resource(
    "postgres",
    port_forwards=["5432:5432"],
    labels=["infra"],
)

# --------------------------------------------------------------------- rag

docker_build(
    "cartia-rag",
    context=".",
    dockerfile="rag/Dockerfile",
    only=["rag/", "shared/"],
    live_update=[
        sync("./rag/app", "/app/app"),
        sync("./shared/cartia_shared", "/shared/cartia_shared"),
    ],
)

k8s_yaml("infra/k8s/rag.yaml")
k8s_resource(
    "rag",
    port_forwards=["8002:8002"],
    resource_deps=["postgres"],
    labels=["servicios"],
)

# --------------------------------------------------------------------- backend

docker_build(
    "cartia-backend",
    context=".",
    dockerfile="backend/Dockerfile",
    only=["backend/", "shared/"],
    live_update=[
        sync("./backend/app", "/app/app"),
        sync("./shared/cartia_shared", "/shared/cartia_shared"),
    ],
)

k8s_yaml("infra/k8s/backend.yaml")
k8s_resource(
    "backend",
    port_forwards=["8000:8000"],
    resource_deps=["postgres", "rag"],
    labels=["servicios"],
)

# --------------------------------------------------------------------- ui

docker_build(
    "cartia-ui",
    context=".",
    dockerfile="ui/Dockerfile.dev",
    only=["ui/"],
    ignore=["ui/.next/", "ui/node_modules/"],
    live_update=[
        # `package.json` no se sincroniza: si cambian las dependencias hay que rebuildear.
        fall_back_on(["./ui/package.json", "./ui/package-lock.json"]),
        sync("./ui/app", "/app/app"),
        sync("./ui/components", "/app/components"),
        sync("./ui/lib", "/app/lib"),
        sync("./ui/public", "/app/public"),
    ],
)

k8s_yaml("infra/k8s/ui.yaml")
k8s_resource(
    "ui",
    port_forwards=["3000:3000"],
    resource_deps=["backend"],
    labels=["servicios"],
)

# --------------------------------------------------------------------- procesos locales

UV = "uv run --directory {}"

local_resource(
    "backend:migrate",
    cmd="{} alembic upgrade head".format(UV.format("backend")),
    env={"DATABASE_URL": DB_URL_LOCAL},
    resource_deps=["postgres"],
    labels=["tareas"],
)

LOADER_ENV = {
    "DATABASE_URL": DB_URL_LOCAL,
    "GOOGLE_API_KEY": GOOGLE_API_KEY,
    "INTERNAL_TOKEN": INTERNAL_TOKEN,
    "EMBEDDING_DIMENSIONS": EMBEDDING_DIMENSIONS,
    "DOCUMENTS_DIR": "./documents",
}

local_resource(
    "rag-loader:init-schema",
    cmd="{} cartia-loader init-schema".format(UV.format("rag-loader")),
    env=LOADER_ENV,
    resource_deps=["postgres"],
    labels=["tareas"],
)

# Ingesta incremental: solo procesa lo que cambio desde la ultima corrida.
local_resource(
    "rag-loader:ingest",
    cmd="{} cartia-loader ingest .".format(UV.format("rag-loader")),
    env=LOADER_ENV,
    resource_deps=["rag-loader:init-schema"],
    trigger_mode=TRIGGER_MODE_MANUAL,
    auto_init=False,
    labels=["tareas"],
)

# Reindex completo: BORRA el indice y lo reconstruye desde cero.
local_resource(
    "rag-loader:reindex",
    cmd="{} cartia-loader reindex --yes".format(UV.format("rag-loader")),
    env=LOADER_ENV,
    resource_deps=["postgres"],
    trigger_mode=TRIGGER_MODE_MANUAL,
    auto_init=False,
    labels=["tareas"],
)

local_resource(
    "rag-loader:status",
    cmd="{} cartia-loader status".format(UV.format("rag-loader")),
    env=LOADER_ENV,
    resource_deps=["rag-loader:init-schema"],
    trigger_mode=TRIGGER_MODE_MANUAL,
    auto_init=False,
    labels=["tareas"],
)

# Botones en la vista del recurso `rag`, para no tener que buscar los recursos manuales.
cmd_button(
    name="ingest-documentos",
    resource="rag",
    argv=["sh", "-c", "cd rag-loader && uv run cartia-loader ingest ."],
    text="Ingestar documentos nuevos",
    icon_name="upload_file",
    location=location.RESOURCE,
)

cmd_button(
    name="reindex-corpus",
    resource="rag",
    argv=["sh", "-c", "cd rag-loader && uv run cartia-loader reindex --yes"],
    text="Reindexar todo el corpus",
    icon_name="autorenew",
    requires_confirmation=True,
    location=location.RESOURCE,
)

print(
    """
CartIA Legal levantado.

  UI          http://localhost:3000
  Backend     http://localhost:8000/docs
  RAG         http://localhost:8002/docs
  Postgres    localhost:5432 (cartia/cartia)

Para cargar documentos: ponelos en rag-loader/documents/ y disparen el recurso
`rag-loader:ingest` desde la UI de Tilt (o `tilt trigger rag-loader:ingest`).
"""
)
