# Cellule de veille technologique autonome — Brief projet

## Objectif

Construire un agent qui, une fois par semaine (déclenchement automatique), effectue une veille sur les sorties LLM / IA notables de la semaine, produit une synthèse structurée, et l'envoie sur un canal Microsoft Teams via webhook.

Cible : un MVP fonctionnel et fiable, pas une architecture multi-agents complète dès le départ. On complexifie seulement une fois que la V1 tourne de façon stable.

---

## Contexte & décisions déjà prises

- **Framework agent** : smolagents (Hugging Face). Choisi pour sa simplicité — l'agent génère du vrai code Python pour orchestrer ses actions plutôt que des appels JSON, ce qui donne un raisonnement lisible et un code court.
- **Modèle** : Claude (via l'API Anthropic), appelé depuis smolagents avec un wrapper LiteLLM ou l'intégration native si disponible.
- **Protocole d'accès aux outils** : MCP si des tools MCP existants sont disponibles (ex. GitHub MCP server) ; sinon tools custom smolagents classiques (fonctions Python décorées `@tool`) pour la V1, sans complexifier avec MCP si ce n'est pas nécessaire.
- **Livraison du rapport** : Microsoft Teams via **Incoming Webhook** (pas besoin de l'API Graph complète pour un simple envoi de message).
- **Déclenchement périodique** : GitHub Actions avec un trigger `schedule` (cron), pour éviter d'avoir à gérer une infra serveur dédiée.

---

## Architecture cible (V1 — un seul agent)

```
GitHub Actions (cron hebdo)
        ↓
   Agent unique (smolagents)
        ↓ tool: recherche web
        ↓ tool: (optionnel) recherche GitHub releases
        ↓ raisonnement : filtrer, dédupliquer, synthétiser
        ↓
   Rapport structuré (texte/markdown)
        ↓
   Webhook Teams → canal cible
```

### Évolution future (V2, hors scope MVP)
Découper en 3 agents spécialisés (Collecteur / Analyste / Rédacteur) orchestrés par un Supervisor (LangGraph), avec mémoire vectorielle pour éviter les doublons d'une semaine sur l'autre. Ne pas implémenter tant que la V1 n'est pas stable.

---

## Étapes du MVP (ordre recommandé)

1. **Setup du repo** : structure Python simple, `requirements.txt` (smolagents, requests, éventuellement litellm), `.env` pour les secrets (clé API Anthropic, URL webhook Teams).
2. **Agent de base** : un `CodeAgent` smolagents avec un tool de recherche web (ex. `DuckDuckGoSearchTool` fourni nativement par smolagents), prompté pour identifier les sorties LLM notables de la semaine.
3. **Tool d'envoi Teams** : fonction Python qui POST un payload `MessageCard` (ou `Adaptive Card`) vers l'URL du webhook Teams. Peut être un tool custom appelé par l'agent en fin de run, ou une étape séparée du script (plus simple et plus fiable — recommandé pour la V1).
4. **Script d'orchestration** (`main.py`) : lance l'agent, récupère le résultat, l'envoie sur Teams, logge le résultat (succès/échec).
5. **Scheduling** : workflow GitHub Actions (`.github/workflows/veille.yml`) avec `on: schedule: cron: ...` (chaque lundi matin), qui exécute `main.py` avec les secrets injectés via GitHub Secrets.
6. **Fiabilité** : gestion des erreurs autour de l'appel webhook (si échec, logger clairement / envisager un fallback email), et un budget de tokens/coût raisonnable (limiter `max_steps` de l'agent).

---

## Points de vigilance identifiés

- **Bruit dans la recherche web** : filtrer les résultats non pertinents demande un prompt bien calibré côté agent — prévoir des itérations sur le prompt.
- **Doublons semaine après semaine** : pour la V1, on peut accepter ce défaut mineur ; une mémoire simple (fichier JSON avec les items déjà couverts) peut être ajoutée rapidement si besoin.
- **Coûts API** : tester le coût réel d'un run avant de valider le scheduling automatique.
- **Rate limits** sur la recherche web si l'agent multiplie les requêtes.
- **Échec silencieux du webhook** : toujours vérifier le status code de la requête POST et logger.

---

## Ce que Claude Code doit faire

Aider à implémenter ce MVP étape par étape dans l'ordre ci-dessus, en commençant par la structure du repo et l'agent de base, avant de passer au webhook Teams et au scheduling GitHub Actions.
