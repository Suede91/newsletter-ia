# Cellule de veille technologique autonome — MVP V1

Agent qui, une fois par semaine, effectue une veille sur les sorties LLM / IA
notables, produit une synthèse structurée et l'envoie sur un canal Microsoft
Teams via Incoming Webhook.

Stack : [smolagents](https://github.com/huggingface/smolagents) (`CodeAgent`) +
Claude (API Anthropic, via LiteLLM) + recherche web + webhook Teams, schedulé
par GitHub Actions (cron hebdo).

Voir [PROJECT_BRIEF.md](PROJECT_BRIEF.md) pour le contexte et les décisions.

## Structure

```
main.py                     # Orchestrateur : agent → Teams → log
veille/
  agent.py                  # CodeAgent smolagents + prompt de veille
  teams.py                  # Envoi du rapport via Incoming Webhook Teams
.github/workflows/veille.yml # Scheduling hebdomadaire (cron lundi 07:00 UTC)
requirements.txt
.env.example                # Modèle de configuration (copier vers .env)
```

## Installation locale

```bash
python -m venv .venv
# Windows PowerShell : .venv\Scripts\Activate.ps1
# macOS / Linux      : source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # puis remplir les valeurs
```

Variables (voir `.env.example`) :

| Variable             | Rôle                                                    |
|----------------------|---------------------------------------------------------|
| `ANTHROPIC_API_KEY`  | Clé API Anthropic                                       |
| `TEAMS_WEBHOOK_URL`  | URL de l'Incoming Webhook du canal Teams cible          |
| `MODEL_ID`           | Modèle Claude (format LiteLLM), déf. `anthropic/claude-sonnet-5` |
| `AGENT_MAX_STEPS`    | Budget d'étapes de l'agent (contrôle du coût), déf. 15  |
| `SERPER_API_KEY`     | **Recherche web fiable** (Serper/Google). À défaut : `BRAVE_API_KEY` ou `EXA_API_KEY`. Sans clé → DuckDuckGo, bloqué en CI |

### Recherche web (important)

L'agent choisit automatiquement son moteur selon la clé présente :
`SERPER_API_KEY` → `BRAVE_API_KEY` → `EXA_API_KEY` → DuckDuckGo (secours).
**Depuis GitHub Actions, DuckDuckGo (scraping) est bloqué** par rate-limiting sur
les IP partagées des runners → l'agent ne trouve rien et ne publie rien. Définis
donc **une** clé d'API de recherche. Recommandé : [Serper](https://serper.dev)
(résultats Google, free tier généreux, inscription sans carte).

## Lancement

```bash
python main.py
```

Le script génère le rapport, le logge (donc jamais perdu même si l'envoi
échoue), puis le POST sur Teams en vérifiant le status code.

Codes de sortie : `0` succès · `1` échec génération agent · `2` échec envoi Teams.

## Scheduling (GitHub Actions)

Le workflow tourne chaque lundi à 07:00 UTC et est aussi déclenchable
manuellement (`workflow_dispatch`). Configurer dans les paramètres du repo :

- **Secrets** : `TEAMS_WEBHOOK_URL`, `SERPER_API_KEY` (recherche fiable). L'auth
  Anthropic passe par la fédération OIDC (identité de charge), pas par un secret.
- **Variables** (optionnel) : `MODEL_ID`, `AGENT_MAX_STEPS`

## Points de vigilance (V1)

- **Coût** : tester le coût réel d'un run avant de valider le cron. `AGENT_MAX_STEPS`
  borne le nombre d'étapes.
- **Bruit / doublons** : le prompt filtre et déduplique ; itérer dessus si besoin.
  Une mémoire simple (JSON des items déjà couverts) pourra être ajoutée en V2.
- **Rien plutôt qu'un message inutile** : si la recherche échoue (rate-limiting)
  ou qu'aucune actualité notable n'est trouvée, l'agent renvoie le jeton
  `NO_NOTABLE_NEWS` et `is_publishable()` bloque l'envoi. Un rapport n'est publié
  que s'il ne contient aucun marqueur d'échec et cite ≥ 2 URLs sources.
  La recherche est en plus enrobée de retries/backoff pour absorber les échecs
  transitoires. Résultat : le run reste vert, mais **rien n'est posté** sur Teams.
- **Échec webhook** : le status code est toujours vérifié et loggé ; le rapport
  est loggé avant l'envoi.

## Évolution (V2, hors scope)

Découpage en 3 agents (Collecteur / Analyste / Rédacteur) orchestrés par un
Supervisor (LangGraph) + mémoire vectorielle anti-doublons. À n'implémenter
qu'une fois la V1 stable.
