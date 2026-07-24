"""Envoi du rapport de veille sur un canal Microsoft Teams via Incoming Webhook.

On utilise le format MessageCard (legacy "connector card"), largement supporté
par les Incoming Webhooks Teams et suffisant pour un simple message texte/markdown.
L'envoi est volontairement une étape séparée du run de l'agent (plus simple et
plus fiable pour la V1) : on vérifie systématiquement le status code et on logge.
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

# Teams tronque les MessageCard très volumineux ; on borne la taille du texte.
_MAX_TEXT_LEN = 24000


def send_to_teams(
    webhook_url: str,
    report_markdown: str,
    title: str = "🛰️ Veille IA / LLM — synthèse hebdomadaire",
    timeout: int = 30,
) -> None:
    """POST le rapport sur le canal Teams cible.

    Lève une exception si l'URL est absente ou si Teams renvoie une erreur, afin
    que l'orchestrateur (`main.py`) puisse logger l'échec sans le rendre silencieux.
    """
    if not webhook_url:
        raise ValueError("TEAMS_WEBHOOK_URL est vide : impossible d'envoyer le rapport.")

    text = report_markdown.strip()
    if len(text) > _MAX_TEXT_LEN:
        logger.warning("Rapport tronqué de %d à %d caractères pour Teams.", len(text), _MAX_TEXT_LEN)
        text = text[:_MAX_TEXT_LEN] + "\n\n_(…tronqué)_"

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": title,
        "sections": [
            {
                "activityTitle": title,
                "text": text,
                "markdown": True,
            }
        ],
    }

    response = requests.post(webhook_url, json=payload, timeout=timeout)

    # Un Incoming Webhook Teams classique renvoie 200 ("1") ; un flux Power
    # Automate ("Workflows") renvoie 202 Accepted. On accepte donc tout 2xx.
    if not (200 <= response.status_code < 300):
        raise RuntimeError(
            f"Échec de l'envoi Teams (status {response.status_code}): {response.text[:500]}"
        )

    logger.info("Rapport envoyé sur Teams (status %s).", response.status_code)
