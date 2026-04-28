# Déploiement — Allianz Renewables Atlas

> Étapes manuelles pour Mancef. Le déploiement Streamlit Community Cloud demande une
> authentification navigateur — Claude Code ne peut donc pas le faire en autonome.

## 1. Pré-requis

- Compte GitHub avec le repo `mancef/allianz-renewables-atlas` (public).
- Compte Streamlit Community Cloud lié au même GitHub : <https://share.streamlit.io>.
- Compte Copernicus Data Space Ecosystem (gratuit) : <https://dataspace.copernicus.eu/>.

## 2. Secrets GitHub Actions (cron hebdo)

Le workflow `.github/workflows/refresh-data.yml` re-run `scripts/precompute_all.py`
chaque lundi 06:00 UTC. Pour que les images Sentinel se rafraîchissent, ajouter dans
**GitHub → Settings → Secrets and variables → Actions** :

| Nom | Valeur |
|---|---|
| `COPERNICUS_USERNAME` | email Copernicus |
| `COPERNICUS_PASSWORD` | mot de passe Copernicus |

Sans ces secrets, le cron tourne quand même mais skip Sentinel (cf. `PRECOMPUTE_FAILURES.md`).

## 3. Déploiement Streamlit Community Cloud

1. Aller sur <https://share.streamlit.io>, se connecter via GitHub.
2. **New app** → choisir le repo `mancef/allianz-renewables-atlas`, branche `main`.
3. **Main file path** : `src/app.py`.
4. **Advanced settings → Python version** : 3.11.
5. **Advanced settings → Secrets** (TOML) :

   ```toml
   COPERNICUS_USERNAME = "..."
   COPERNICUS_PASSWORD = "..."
   ```

   Ces secrets ne sont nécessaires que si on veut re-fetcher Sentinel à la volée
   depuis l'app. En pratique, les images sont pré-calculées et committées dans
   `data/parks/<id>/sentinel.png` — l'app n'a donc pas besoin des creds en runtime.

6. **Deploy**. L'URL finale est typiquement `https://<slug>.streamlit.app`.

## 4. Mail à l'analyste Allianz

Template dans `README.md` § "Mail à l'analyste". Remplacer `[URL Streamlit]` et
`[URL GitHub]` par les vraies URLs avant envoi.

## 5. Mise à jour des données

- **Manuelle** : `python scripts/precompute_all.py` (avec `.env` rempli) puis
  `git add data/parks/ && git commit && git push`.
- **Automatique** : le cron GitHub Actions s'en occupe chaque lundi.
- **Re-cartographie** : éditer `data/parks_index.yaml`, vérifier `pytest tests/`,
  re-run le précompute.

## 6. Souveraineté (variante institutionnelle)

Pour un déploiement Allianz interne, remplacer Streamlit Community Cloud par :

- **Self-hosted** : Docker image + Allianz private cloud (DORA-compliant).
- **Stockage** : data/parks/ servi via S3-compatible interne (Allianz IT).
- **Secrets** : Vault Allianz au lieu de GitHub Secrets.

Voir page **About** de l'app pour les considérations DORA / RGPD.
