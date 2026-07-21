"""Agent de veille (smolagents CodeAgent + Claude via LiteLLM).

L'agent dispose d'un outil de recherche web et est prompté pour identifier les
sorties LLM / IA notables de la semaine, puis produire une synthèse structurée
en markdown, prête à être envoyée sur Teams.
"""

from __future__ import annotations

import datetime as _dt
import logging

from smolagents import CodeAgent, LiteLLMModel

try:
    # Nom actuel de l'outil de recherche web fourni par smolagents.
    from smolagents import WebSearchTool as _SearchTool
except ImportError:  # pragma: no cover - compat versions plus anciennes
    from smolagents import DuckDuckGoSearchTool as _SearchTool

logger = logging.getLogger(__name__)


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

Si tu ne trouves rien de significatif, dis-le explicitement plutôt que d'inventer.
Le rapport doit être concis, factuel, et chaque affirmation doit s'appuyer sur une source trouvée.
Utilise `final_answer(<markdown>)` pour renvoyer le rapport."""


def run_veille(model_id: str, api_key: str, max_steps: int = 12) -> str:
    """Exécute l'agent de veille et renvoie le rapport markdown final."""
    model = LiteLLMModel(model_id=model_id, api_key=api_key)
    agent = CodeAgent(
        tools=[_SearchTool()],
        model=model,
        max_steps=max_steps,
    )

    logger.info("Lancement de l'agent de veille (modèle=%s, max_steps=%d).", model_id, max_steps)
    result = agent.run(_build_prompt())
    report = str(result).strip()

    if not report:
        raise RuntimeError("L'agent a renvoyé un rapport vide.")

    logger.info("Rapport généré (%d caractères).", len(report))
    return report
