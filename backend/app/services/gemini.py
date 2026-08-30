"""Fabrica de modelos Gemini, uno por rol del grafo.

Cada nodo tiene requisitos distintos: el guardrail necesita latencia minima y
temperatura 0, el reescritor de consultas algo de flexibilidad, y la generacion final el
modelo mas capaz. Separarlos permite ajustar costo y calidad nodo por nodo.
"""

from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from ..core.settings import get_settings


def _build(model: str, temperature: float, max_tokens: int | None = None) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.google_api_key,
        temperature=temperature,
        max_output_tokens=max_tokens,
        # El guardrail y el grader deben fallar de forma visible, no colgarse.
        timeout=60,
        max_retries=2,
    )


@lru_cache
def guardrail_model() -> ChatGoogleGenerativeAI:
    return _build(get_settings().gemini_guardrail_model, temperature=0.0)


@lru_cache
def rewrite_model() -> ChatGoogleGenerativeAI:
    return _build(get_settings().gemini_rewrite_model, temperature=0.2)


@lru_cache
def grader_model() -> ChatGoogleGenerativeAI:
    return _build(get_settings().gemini_rewrite_model, temperature=0.0)


@lru_cache
def answer_model() -> ChatGoogleGenerativeAI:
    return _build(get_settings().gemini_answer_model, temperature=0.25)
