"""Orchestrateur de la cellule de veille (MVP V1).

Enchaîne : chargement config → run agent → envoi Teams → log du résultat.
Conçu pour être lancé manuellement en local ou via GitHub Actions (cron hebdo).
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from veille.agent import run_veille
from veille.teams import send_to_teams

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("veille.main")


def _get_env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        logger.error("Variable d'environnement manquante : %s", name)
        sys.exit(1)
    return value or ""


def main() -> int:
    load_dotenv()

    # Auth Anthropic : soit une clé classique (ANTHROPIC_API_KEY, en-tête
    # x-api-key, usage local via .env), soit un access token de fédération
    # OIDC/WIF (ANTHROPIC_AUTH_TOKEN, en-tête Authorization: Bearer, CI GitHub).
    # litellm résout automatiquement l'un ou l'autre depuis l'environnement.
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("ANTHROPIC_AUTH_TOKEN"):
        logger.error(
            "Auth Anthropic manquante : définir ANTHROPIC_API_KEY (clé) "
            "ou ANTHROPIC_AUTH_TOKEN (access token OIDC/WIF)."
        )
        sys.exit(1)

    webhook_url = _get_env("TEAMS_WEBHOOK_URL", required=True)
    model_id = _get_env("MODEL_ID", default="anthropic/claude-sonnet-5")
    max_steps = int(_get_env("AGENT_MAX_STEPS", default="15"))

    # 1. Génération du rapport par l'agent.
    try:
        report = run_veille(model_id=model_id, max_steps=max_steps)
    except Exception:
        logger.exception("Échec de la génération du rapport par l'agent.")
        return 1

    logger.info("----- Rapport généré -----\n%s\n--------------------------", report)

    # 2. Envoi sur Teams (étape séparée, vérifiée et loggée).
    try:
        send_to_teams(webhook_url, report)
    except Exception:
        logger.exception("Échec de l'envoi du rapport sur Teams.")
        # Le rapport a déjà été loggé ci-dessus : il n'est pas perdu.
        return 2

    logger.info("Veille terminée avec succès.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
