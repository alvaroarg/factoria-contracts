#!/usr/bin/env python3
"""Cupo de correcciones y reviews del piloto OpenCode.

La review inicial no es una corrección ni una re-review. Tras
``CHANGES_REQUESTED`` caben como máximo ``MAX_CORRECTIONS`` correcciones,
cada una seguida de una re-review nueva. ``MAX_RE_REVIEWS`` es ese cupo de
re-reviews. El total de reviews es la inicial más las re-reviews.

Estos enteros son el límite efectivo. Un tope más bajo (el piloto anterior
de 1 corrección y 1 re-review, o un techo de 3 reviews totales) no se aplica.

Los textos del orquestador, del prompt, del contrato y de la documentación
operativa tienen que publicar las mismas marcas. ``verificar_textos`` lo
comprueba sin llamar al modelo.

``decidir_tras_review`` no ejecuta el bucle de la factoría. Recibe un
veredicto y unos contadores y devuelve ``aceptar``, ``corregir`` o
``bloquear``. Quien reanuda al builder y lanza la re-review es el
orquestador, siguiendo ``factory-orchestrator.md`` y ``pilot-prompt.md``.
``guarded_run.py`` no llama a esta función. El control determinista que sí
corre antes de inferir es ``verificar_textos``, desde ``check_config.py``.

Rutas de esta plantilla, no las del checkout de producto. El producto
(LicitacionesScrapping PR #63, commit 467995a) resuelve los mismos archivos
desde la raíz del repo: ``.opencode/``, ``contracts/PORTABLE-CONTRACT.md`` y
``automation/opencode/docs/``. Aquí el paquete OpenCode vive en
``multiprovider/opencode``, ``MIGRACION.md`` y
``PRUEBAS-Y-ARRANQUE-LIMPIO.md`` están en esa raíz (no en ``docs/``), el
contrato portable está en ``multiprovider/contracts/`` y el workflow piloto
superado entra en el preflight para que no quede un tope distinto.
"""
from pathlib import Path

# Correcciones tras CHANGES_REQUESTED. La implementación inicial no cuenta.
MAX_CORRECTIONS = 3
# Re-reviews. La review inicial no cuenta.
MAX_RE_REVIEWS = 3
# Review inicial + re-reviews.
MAX_TOTAL_REVIEWS = 1 + MAX_RE_REVIEWS

MARCA_CORRECCIONES = f"MAX_CORRECTIONS={MAX_CORRECTIONS}"
MARCA_REREVIEWS = f"MAX_RE_REVIEWS={MAX_RE_REVIEWS}"
MARCA_TOTAL = f"MAX_TOTAL_REVIEWS={MAX_TOTAL_REVIEWS}"
RUTA_CUPO = "automation/opencode/review_budget.py"

ACEPTAR = "aceptar"
CORREGIR = "corregir"
BLOQUEAR = "bloquear"

_VEREDICTOS = ("PASS", "CHANGES_REQUESTED", "BLOCKED")

_OPENCODE = "multiprovider/opencode"

ARCHIVOS_CON_CUPO = (
    f"{_OPENCODE}/.opencode/agents/factory-orchestrator.md",
    f"{_OPENCODE}/automation/opencode/pilot-prompt.md",
    "multiprovider/contracts/PORTABLE-CONTRACT.md",
    f"{_OPENCODE}/MIGRACION.md",
    f"{_OPENCODE}/PRUEBAS-Y-ARRANQUE-LIMPIO.md",
    f"{_OPENCODE}/.github/workflows/opencode-factory.yml",
    f"{_OPENCODE}/.github/workflows/opencode-factory-PILOT.yml",
)

# Frases que volvían a imponer un tope de 1 corrección o de 1 re-review.
PROHIBIDAS = {
    f"{_OPENCODE}/.opencode/agents/factory-orchestrator.md": (
        "ONE NEW reviewer",
        "allow **one** correction",
        "policy is suspended",
        "at most ONE",
    ),
    f"{_OPENCODE}/automation/opencode/pilot-prompt.md": (
        "automatic re-attempts",
        "ONE NEW reviewer",
        "obtain one independent",
    ),
    f"{_OPENCODE}/.github/workflows/opencode-factory-PILOT.yml": (
        "(max 3 rounds)",
        "ONE NEW reviewer",
    ),
}

# Topes que este cambio no mueve, y la frase de correcciones de Cursor.
CONSERVADAS = (
    ("multiprovider/contracts/PORTABLE-CONTRACT.md", "Up to 3 corrections occur on the same branch/PR."),
    (f"{_OPENCODE}/.github/workflows/opencode-factory.yml", "timeout-minutes: 355"),
    (f"{_OPENCODE}/.github/workflows/opencode-factory.yml", "--no-edit-seconds 900"),
    (f"{_OPENCODE}/.github/workflows/opencode-factory.yml", "--total-seconds 20400"),
    (f"{_OPENCODE}/.github/workflows/opencode-factory.yml", "--max-reported-input-tokens 5000000"),
    (f"{_OPENCODE}/.github/workflows/opencode-factory.yml", "max-parallel: 3"),
    (f"{_OPENCODE}/.github/workflows/opencode-factory.yml", 'default: "3"'),
)


def _entero(nombre, valor):
    """Rechaza bool: en Python ``bool`` es subclase de ``int``."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValueError(f"{nombre} debe ser int")
    return valor


def decidir_tras_review(
    veredicto,
    correcciones_previas,
    indice_review,
    *,
    max_corrections=None,
    max_re_reviews=None,
):
    """Decide si la story se acepta, se corrige o se bloquea.

    No reanuda sesiones ni lanza reviewers. Clasifica un veredicto ya emitido.

    Args:
        veredicto: ``PASS``, ``CHANGES_REQUESTED`` o ``BLOCKED``.
        correcciones_previas: Correcciones ya aplicadas antes de esta review.
            La implementación inicial no cuenta. La review inicial llega con 0.
        indice_review: Review que acaba de terminar, empezando en 1.
            1 es la inicial. 2, 3 y 4 son las re-reviews de los ciclos 1, 2 y 3.
        max_corrections: Cupo de correcciones. Por defecto ``MAX_CORRECTIONS``.
            El argumento existe para demostrar en tests que un tope más bajo
            bloquea antes; el piloto usa el valor del módulo.
        max_re_reviews: Cupo de re-reviews. Por defecto ``MAX_RE_REVIEWS``.
            El total de reviews de esa llamada es ``1 + max_re_reviews``.

    Returns:
        ``aceptar``, ``corregir`` o ``bloquear``.

    Raises:
        ValueError: Veredicto desconocido o contadores que no son enteros
        válidos (negativos, review 0 o bool).

    Una secuencia válida cumple ``correcciones_previas == indice_review - 1``.
    Si no se cumple, el resultado es ``bloquear``: un contador desfasado no
    abre un ciclo de más. ``PASS`` dentro del cupo acepta, también en la
    cuarta review. ``CHANGES_REQUESTED`` abre otra corrección solo si queda
    corrección, queda re-review y la review siguiente cabe en el total. Con
    el cupo publicado, eso ocurre en las reviews 1, 2 y 3, y deja de ocurrir
    en la review 4.
    """
    if not isinstance(veredicto, str) or veredicto.strip() not in _VEREDICTOS:
        raise ValueError("veredicto debe ser PASS, CHANGES_REQUESTED o BLOCKED")
    veredicto = veredicto.strip()
    correcciones_previas = _entero("correcciones_previas", correcciones_previas)
    indice_review = _entero("indice_review", indice_review)
    if correcciones_previas < 0 or indice_review < 1:
        raise ValueError("contadores fuera de rango")
    max_corrections = MAX_CORRECTIONS if max_corrections is None else _entero(
        "max_corrections", max_corrections
    )
    max_re_reviews = MAX_RE_REVIEWS if max_re_reviews is None else _entero(
        "max_re_reviews", max_re_reviews
    )
    if max_corrections < 0 or max_re_reviews < 0:
        raise ValueError("el cupo no puede ser negativo")
    max_total = 1 + max_re_reviews

    if veredicto == "BLOCKED":
        return BLOQUEAR
    if correcciones_previas != indice_review - 1:
        return BLOQUEAR
    if indice_review > max_total or correcciones_previas > max_corrections:
        return BLOQUEAR
    if veredicto == "PASS":
        return ACEPTAR
    re_reviews_hechas = indice_review - 1
    siguiente_review = indice_review + 1
    if (
        correcciones_previas < max_corrections
        and re_reviews_hechas < max_re_reviews
        and siguiente_review <= max_total
    ):
        return CORREGIR
    return BLOQUEAR


def texto_respeta_cupo(texto, prohibidas=()):
    """Devuelve los desajustes de un texto respecto al cupo publicado.

    Args:
        texto: Contenido ya leído.
        prohibidas: Frases que no pueden seguir presentes.

    Returns:
        Lista de mensajes. Vacía si el texto publica las tres marcas, la ruta
        del módulo y ninguna frase prohibida.
    """
    errores = []
    for marca in (MARCA_CORRECCIONES, MARCA_REREVIEWS, MARCA_TOTAL, RUTA_CUPO):
        if marca not in texto:
            errores.append(f"falta {marca}")
    for frase in prohibidas:
        if frase in texto:
            errores.append(f"sigue vigente {frase!r}")
    return errores


def verificar_textos(root):
    """Comprueba que contrato, prompt, workflow y docs publican el mismo cupo.

    Args:
        root: Raíz del repositorio de contratos (la que contiene ``multiprovider/``).

    Raises:
        ValueError: Falta una marca, sigue una frase del tope antiguo o se ha
        perdido un tope de tiempo, de selección o la frase de correcciones de
        Cursor.
    """
    raiz = Path(root)
    errores = []
    for relativo in ARCHIVOS_CON_CUPO:
        texto = (raiz / relativo).read_text(encoding="utf-8")
        for mensaje in texto_respeta_cupo(texto, PROHIBIDAS.get(relativo, ())):
            errores.append(f"{relativo}: {mensaje}")
    for relativo, frase in CONSERVADAS:
        texto = (raiz / relativo).read_text(encoding="utf-8")
        if frase not in texto:
            errores.append(f"{relativo}: falta el tope conservado {frase!r}")
    if errores:
        raise ValueError("cupo de review desalineado: " + "; ".join(errores))
