"""Runner de desarrollo para Windows.

psycopg async no funciona con el ProactorEventLoop (default de asyncio en Windows).
En produccion y en Tilt el servicio corre en Linux, donde no aplica. Para correrlo
local en Windows: `uv run python run_dev.py`.
"""

import asyncio
import sys

import uvicorn

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8002, reload=True)
