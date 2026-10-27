"""Agent de veille (smolagents CodeAgent + Claude via LiteLLM).

L'agent dispose d'un outil de recherche web et est prompté pour identifier les
sorties LLM / IA notables de la semaine, puis produire une synthèse structurée
en markdown, prête à être envoyée sur Teams.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import re
import time

from smolagents import CodeAgent, LiteLLMModel


def _try_import(name: str):
    try:
        return getattr(__import__("smolagents", fromlist=[name]), name)
    except (ImportError, AttributeError):  # pragma: no cover - selon version smolagents
        return None


# Backends de recherche disponibles selon la version de smolagents.
_GoogleSearchTool = _try_import("GoogleSearchTool")      # Serper / SerpApi (Google)
_ApiWebSearchTool = _try_import("ApiWebSearchTool")      # Brave Search API
_WebSearchTool = _try_import("WebSearchTool")            # Exa (engine="exa") / DDG / Bing
_DuckDuckGoSearchTool = _try_import("DuckDuckGoSearchTool")  # scraping DDG (secours)

logger = logging.getLogger(__name__)

# Jeton renvoyé par l'agent lorsqu'il n'a rien de significatif à publier
# (ou que la recherche web est inexploitable). Sert de signal déterministe
# pour NE PAS publier sur Teams — voir `is_publishable`.
NO_REPORT_SENTINEL = "NO_NOTABLE_NEWS"

# Marqueurs textuels typiques d'un rapport « d'échec » que l'on ne veut jamais
# publier (au cas où l'agent rédigerait quand même une prose au lieu du jeton).
_FAILURE_MARKERS = (
    "no results found",
    "aucun résultat",
    "aucune source",
    "impossible à compléter",
    "impossible de compléter",
    "impossible de produire",
    "impossible à produire",
    "rapport incomplet",
    "indisponibilité des sources",
    "n'a retourné aucun",
    "ne peut être produit",
    "ne peut s'appuyer",
    "absence de données",
)


def _select_search_tool():
    """Choisit le backend de recherche selon les clés d'API présentes.

    Les API dédiées (Serper/Brave/Exa) sont fiables depuis la CI. Le scraping
    DuckDuckGo est bloqué par rate-limiting sur les IP partagées des runners
    GitHub (cause des rapports vides d'octobre 2026) et ne sert que de dernier
    recours. Il suffit donc de définir UNE de ces variables d'environnement
    pour fiabiliser la recherche : SERPER_API_KEY, SERPAPI_API_KEY,
    BRAVE_API_KEY ou EXA_API_KEY.
    """
    if os.getenv("SERPER_API_KEY") and _GoogleSearchTool:
        logger.info("Recherche : Serper (Google).")
        return _GoogleSearchTool(provider="serper")
    if os.getenv("SERPAPI_API_KEY") and _GoogleSearchTool:
        logger.info("Recherche : SerpApi (Google).")
        return _GoogleSearchTool(provider="serpapi")
    if os.getenv("BRAVE_API_KEY") and _ApiWebSearchTool:
        logger.info("Recherche : Brave Search API.")
        return _ApiWebSearchTool()
    if os.getenv("EXA_API_KEY") and _WebSearchTool:
        logger.info("Recherche : Exa.")
        return _WebSearchTool(engine="exa")

    logger.warning(
        "Recherche : DuckDuckGo sans clé d'API — PEU FIABLE depuis la CI "
        "(rate-limiting). Définis SERPER_API_KEY / BRAVE_API_KEY / EXA_API_KEY "
        "pour une recherche fiable."
    )
    if _DuckDuckGoSearchTool:
        return _DuckDuckGoSearchTool()
    if _WebSearchTool:
        return _WebSearchTool()
    raise RuntimeError("Aucun outil de recherche disponible dans smolagents.")


def _make_search_tool(max_retries: int = 4, base_delay: float = 1.5):
    """Instancie le backend de recherche choisi et enrobe `forward` de retries.

    Un backoff exponentiel (1.5s, 3s, 6s, 12s) absorbe les échecs transitoires
    (rate-limiting, erreurs réseau) quel que soit le moteur retenu.
    """
    tool = _select_search_tool()
    original_forward = tool.forward

    def forward_with_retries(*args, **kwargs):
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                return original_forward(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - on relaie après épuisement
                last_exc = exc
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Recherche en échec (tentative %d/%d) : %s — retry dans %.0fs.",
                        attempt + 1,
                        max_retries,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    tool.forward = forward_with_retries
    return tool


def _build_prompt() -> str:
    today = _dt.date.today()
    week_start = today - _dt.timedelta(days=7)
    return f"""Tu es une cellule de veille technologique spécialisée en IA et grands modèles de langage (LLM).

Période couverte : du {week_start.isoformat()} au {today.isoformat()} (les 7 derniers jours).

Objectif : identifier les sorties / annonces NOTABLES de la semaine dans l'écosystème LLM & IA.
Cela inclut : nouveaux modèles ou versions (Anthropic, OpenAI, Google, Meta, Mistral, xAI, DeepSeek, Qwen…),
frameworks et outils marquants, releases open-source significatives, annonces de recherche importantes.

Méthode :
1. Effectue plusieurs recherches web ciblées (ex. "LLM releases this week", "new AI model {today.year}",
   noms des principaux labos + "announcement"). Varie les requêtes.
2. Filtre le bruit : ne garde que ce qui est réellement daté de la semaine écoulée et significatif.
   Ignore les articles génériques, les listicles marketing et le contenu non daté.
3. Déduplique : un même événement rapporté par plusieurs sources = une seule entrée.
4. Vérifie la plausibilité des dates ; en cas de doute sur la fraîcheur, écarte l'item.

Produis UNIQUEMENT un rapport final en markdown, structuré ainsi :

## 🛰️ Veille IA / LLM — semaine du {week_start.isoformat()}

**TL;DR** : 2-3 phrases sur les faits marquants de la semaine.

### Sorties & annonces notables
- **[Nom]** — description en 1-2 phrases. _Source : <url>_
(3 à 8 entrées maximum, les plus pertinentes)

### À surveiller
- Signaux faibles ou annonces à confirmer (optionnel, 0 à 3 items).

RÈGLE IMPORTANTE — absence de résultats :
Si l'outil de recherche ne renvoie AUCUN résultat exploitable (erreurs « No results found »,
rate-limiting, contenu non pertinent), OU si tu ne trouves rien de réellement notable et sourcé
pour la période, alors NE RÉDIGE PAS de rapport expliquant l'absence de données.
Dans ce cas, renvoie EXACTEMENT ce jeton, seul, sans autre texte :
{NO_REPORT_SENTINEL}
Ne l'utilise que dans ce cas ; il empêchera toute publication d'un message inutile.

Sinon, le rapport doit être concis, factuel, et chaque entrée notable doit citer une URL source réelle
trouvée pendant tes recherches. N'invente jamais de source ni de date.
Utilise `final_answer(<markdown ou {NO_REPORT_SENTINEL}>)` pour renvoyer ta réponse."""


def _sanitize_report(report: str) -> str:
    """Nettoie le rapport final.

    Si l'agent atteint `max_steps` sans appel propre à `final_answer`, smolagents
    peut renvoyer le littéral de code `final_answer(<markdown>)`. On retire alors
    ce wrapper pour n'envoyer que le markdown.
    """
    text = report.strip()
    if text.startswith("final_answer("):
        text = text[len("final_answer(") :].strip()
        # Retire la parenthèse fermante de l'appel si elle est en fin de chaîne.
        if text.endswith(")"):
            text = text[:-1].strip()
        # Retire d'éventuels guillemets triples/simples entourant le contenu.
        for quote in ('"""', "'''", '"', "'"):
            if text.startswith(quote) and text.endswith(quote) and len(text) >= 2 * len(quote):
                text = text[len(quote) : -len(quote)].strip()
                break
    return text


def is_publishable(report: str, min_sources: int = 2) -> tuple[bool, str]:
    """Décide si un rapport mérite d'être publié sur Teams.

    On préfère ne RIEN publier plutôt qu'un message non pertinent. Un rapport
    est jugé publiable seulement s'il :
      - n'est pas vide et n'est pas le jeton `NO_REPORT_SENTINEL` ;
      - ne contient aucun marqueur d'échec (`_FAILURE_MARKERS`) ;
      - cite au moins `min_sources` URLs réelles (preuve d'entrées sourcées).

    Renvoie (publiable, raison) — `raison` explicite le rejet le cas échéant.
    """
    text = report.strip()
    if not text:
        return False, "rapport vide"
    if NO_REPORT_SENTINEL in text:
        return False, "l'agent signale aucune actualité notable (jeton NO_NOTABLE_NEWS)"

    lowered = text.lower()
    for marker in _FAILURE_MARKERS:
        if marker in lowered:
            return False, f"marqueur d'échec détecté : {marker!r}"

    n_sources = len(re.findall(r"https?://", text))
    if n_sources < min_sources:
        return False, f"trop peu de sources ({n_sources} < {min_sources})"

    return True, "ok"


def run_veille(model_id: str, max_steps: int = 12) -> str:
    """Exécute l'agent de veille et renvoie le rapport markdown final.

    L'authentification Anthropic n'est pas passée explicitement : litellm la
    résout depuis l'environnement, soit `ANTHROPIC_API_KEY` (en-tête x-api-key),
    soit `ANTHROPIC_AUTH_TOKEN` (en-tête Authorization: Bearer, fédération OIDC).
    """
    model = LiteLLMModel(model_id=model_id)
    agent = CodeAgent(
        tools=[_make_search_tool()],
        model=model,
        max_steps=max_steps,
    )

    logger.info("Lancement de l'agent de veille (modèle=%s, max_steps=%d).", model_id, max_steps)
    result = agent.run(_build_prompt())
    report = _sanitize_report(str(result))

    if not report:
        raise RuntimeError("L'agent a renvoyé un rapport vide.")

    logger.info("Rapport généré (%d caractères).", len(report))
    return report
