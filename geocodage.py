
"""
Géocodage des DPE à partir de leur adresse BAN.

Entrée :
    data/processed/dpe_fusionne.csv

Sortie :
    data/processed/dpe_geocode.csv

Cache :
    data/processed/geocodage_cache.csv
"""

import argparse
import logging
import time
from pathlib import Path

import polars as pl
import requests

# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[1]

DOSSIER_DATA = ROOT_DIR / "data" / "processed"

FICHIER_SOURCE = DOSSIER_DATA / "dpe_fusionne.csv"
FICHIER_SORTIE = DOSSIER_DATA / "dpe_geocode.csv"
FICHIER_CACHE = DOSSIER_DATA / "geocodage_cache.csv"

COLONNE_ADRESSE = "adresse_ban"

API_URL = "https://data.geopf.fr/geocodage/search"

SEUIL_SCORE = 0.70

TIMEOUT = 20
NB_TENTATIVES = 3
DELAI_REQUETE = 0.1
FREQUENCE_SAUVEGARDE = 20

COLONNES_RESULTAT = [
    "latitude",
    "longitude",
    "score_geocodage",
    "statut_geocodage",
    "libelle_geocodage",
]

SCHEMA_CACHE = {
    "adresse_cle": pl.String,
    "latitude": pl.String,
    "longitude": pl.String,
    "score_geocodage": pl.String,
    "statut_geocodage": pl.String,
    "libelle_geocodage": pl.String,
}

# ============================================================
# 2. CONFIGURATION DES LOGS
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


# ============================================================
# 3. OUTILS
# ============================================================

def resoudre_chemin(chemin):
    """Résout un chemin relatif depuis la racine du projet."""

    chemin = Path(chemin)

    if chemin.is_absolute():
        return chemin

    return ROOT_DIR / chemin

def normaliser_adresse(adresse):
    """Normalise une adresse pour identifier les doublons."""

    if adresse is None:
        return ""

    return " ".join(str(adresse).lower().split())


def resultat_vide(statut):
    """Construit un résultat sans coordonnées."""

    return {
        "latitude": "",
        "longitude": "",
        "score_geocodage": "",
        "statut_geocodage": statut,
        "libelle_geocodage": "",
    }


# ============================================================
# 4. GESTION DU CACHE
# ============================================================

def charger_cache(chemin_cache):
    """Charge les résultats de géocodage déjà disponibles."""

    if not chemin_cache.exists():
        logger.info("Aucun cache existant.")
        return {}

    cache_df = pl.read_csv(
        chemin_cache,
        separator=";",
        schema_overrides=SCHEMA_CACHE,
        infer_schema=False,
    )

    cache = {}

    for ligne in cache_df.iter_rows(named=True):

        cle = ligne["adresse_cle"]

        if cle:
            cache[cle] = {
                colonne: ligne[colonne]
                for colonne in COLONNES_RESULTAT
            }

    logger.info("%s adresses chargées depuis le cache.", len(cache))

    return cache


def sauvegarder_cache(cache, chemin_cache):
    """Enregistre les résultats dans le cache."""

    chemin_cache.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    cache_df = pl.DataFrame(
        [
            {
                "adresse_cle": adresse,
                **resultat,
            }
            for adresse, resultat in cache.items()
        ],
        schema=SCHEMA_CACHE,
    )

    cache_df.write_csv(
        chemin_cache,
        separator=";",
    )


# ============================================================
# 5. GEOCODAGE
# ============================================================

def geocoder_adresse(adresse, session):
    """Interroge l'API de géocodage de la Géoplateforme."""

    params = {
        "q": adresse,
        "index": "address",
        "limit": 1,
    }

    for tentative in range(1, NB_TENTATIVES + 1):

        try:

            response = session.get(
                API_URL,
                params=params,
                timeout=TIMEOUT,
            )

            if response.status_code == 429:
                delai = int(
                    response.headers.get("Retry-After", 5)
                )
                logger.warning(
                    "Limite API atteinte. Attente de %s secondes.",
                    delai,
                )
                time.sleep(delai)
                continue

            if response.status_code >= 500:
                raise requests.HTTPError(
                    f"Erreur serveur HTTP {response.status_code}"
                )

            response.raise_for_status()

            data = response.json()
            features = data.get("features", [])

            if not features:
                return resultat_vide("non_trouvee")

            feature = features[0]

            coordinates = feature.get(
                "geometry", {}
            ).get("coordinates", [])

            if len(coordinates) < 2:
                return resultat_vide("non_trouvee")

            # GeoJSON : longitude puis latitude
            longitude, latitude = coordinates[:2]

            properties = feature.get("properties", {})

            score = properties.get("score")

            if score is not None:
                score = float(score)

            if score is not None and score >= SEUIL_SCORE:
                statut = "geocodee"
            else:
                statut = "incertaine"

            return {
                "latitude": latitude,
                "longitude": longitude,
                "score_geocodage": score if score is not None else "",
                "statut_geocodage": statut,
                "libelle_geocodage": properties.get("label", ""),
            }

        except (
            requests.RequestException,
            ValueError,
            TypeError,
            KeyError,
        ) as erreur:

            logger.warning(
                "Tentative %s/%s échouée pour '%s' : %s",
                tentative,
                NB_TENTATIVES,
                adresse,
                erreur,
            )

            if tentative < NB_TENTATIVES:
                time.sleep(2 ** tentative)

    return resultat_vide("erreur_api")


# ============================================================
# 6. TRAITEMENT PRINCIPAL
# ============================================================

def traiter_csv(chemin_source, chemin_sortie, chemin_cache):

    # --------------------------------------------------------
    # Lecture du fichier source
    # --------------------------------------------------------

    if not chemin_source.exists():
        raise FileNotFoundError(
            f"Fichier source introuvable : {chemin_source}"
        )

    logger.info("Lecture du fichier : %s", chemin_source)


    df = pl.read_csv(
        chemin_source,
        separator=',',
        infer_schema=False,
        encoding="utf8",
    )

    if COLONNE_ADRESSE not in df.columns:
        raise ValueError(
            f"La colonne '{COLONNE_ADRESSE}' "
            "est absente du fichier."
        )

    nombre_lignes = df.height

    logger.info("Nombre de lignes : %s", nombre_lignes)

    # --------------------------------------------------------
    # Préparation des adresses
    # --------------------------------------------------------

    df = df.with_columns(
        pl.col(COLONNE_ADRESSE)
        .cast(pl.String)
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
        .str.to_lowercase()
        .alias("adresse_cle")
    )

    adresses = (
        df.select("adresse_cle")
        .unique(maintain_order=True)
        .filter(
            (pl.col("adresse_cle") != "")
            & pl.col("adresse_cle").is_not_null()
        )
        .get_column("adresse_cle")
        .to_list()
    )

    logger.info("Adresses distinctes : %s", len(adresses))

    # --------------------------------------------------------
    # Chargement du cache
    # --------------------------------------------------------

    cache = charger_cache(chemin_cache)

    adresses_a_geocoder = [
        adresse
        for adresse in adresses
        if adresse not in cache
    ]

    logger.info(
        "Adresses déjà en cache : %s",
        len(adresses) - len(adresses_a_geocoder),
    )

    logger.info(
        "Nouvelles adresses à géocoder : %s",
        len(adresses_a_geocoder),
    )

    # --------------------------------------------------------
    # Géocodage des nouvelles adresses
    # --------------------------------------------------------

    with requests.Session() as session:

        session.headers.update({
            "User-Agent": "Projet-tutore-DPE/1.0"
        })

        for numero, adresse in enumerate(
            adresses_a_geocoder,
            start=1,
        ):

            logger.info(
                "[%s/%s] Géocodage : %s",
                numero,
                len(adresses_a_geocoder),
                adresse,
            )

            resultat = geocoder_adresse(
                adresse,
                session,
            )

            # Les erreurs API ne sont pas mises en cache
            if resultat["statut_geocodage"] != "erreur_api":
                cache[adresse] = resultat

            # Sauvegarde régulière
            if numero % FREQUENCE_SAUVEGARDE == 0:
                sauvegarder_cache(cache, chemin_cache)

            time.sleep(DELAI_REQUETE)

    sauvegarder_cache(cache, chemin_cache)

    # --------------------------------------------------------
    # Construction de la table de correspondance
    # --------------------------------------------------------

    correspondances = pl.DataFrame(
        [
            {
                "adresse_cle": adresse,
                **resultat,
            }
            for adresse, resultat in cache.items()
        ],
        schema={
            "adresse_cle": pl.String,
            "latitude": pl.String,
            "longitude": pl.String,
            "score_geocodage": pl.String,
            "statut_geocodage": pl.String,
            "libelle_geocodage": pl.String,
        },
    )

    # --------------------------------------------------------
    # Jointure avec le fichier initial
    # --------------------------------------------------------

    # Suppression des anciennes colonnes de géocodage
    df = df.drop(
        [
            colonne
            for colonne in COLONNES_RESULTAT
            if colonne in df.columns
        ]
    )

    df = df.join(
        correspondances,
        on="adresse_cle",
        how="left",
    )

    # Identification des adresses absentes
    df = df.with_columns(
        pl.when(
            pl.col("adresse_cle").is_null()
            | (pl.col("adresse_cle") == "")
        )
        .then(pl.lit("adresse_absente"))
        .otherwise(pl.col("statut_geocodage"))
        .alias("statut_geocodage")
    )

    df = df.drop("adresse_cle")

    # --------------------------------------------------------
    # Contrôle et export
    # --------------------------------------------------------

    if df.height != nombre_lignes:
        raise RuntimeError(
            "Le nombre de lignes a changé après la jointure."
        )

    chemin_sortie.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.write_csv(
        chemin_sortie,
        separator=',',
    )

    # --------------------------------------------------------
    # Bilan
    # --------------------------------------------------------

    logger.info("========== BILAN DU GEOCODAGE ==========")

    bilan = (
        df.group_by("statut_geocodage")
        .len()
        .sort("len", descending=True)
    )

    print(bilan)

    logger.info("Nombre de lignes initiales : %s", nombre_lignes)
    logger.info("Nombre de lignes finales : %s", df.height)

    logger.info("Fichier enrichi : %s", chemin_sortie)
    logger.info("Cache : %s", chemin_cache)


# ============================================================
# 7. EXECUTION
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Géocodage des DPE à partir de leur adresse BAN."
    )

    parser.add_argument(
        "--source",
        type=Path,
        default=FICHIER_SOURCE,
        help="Fichier CSV fusionné.",
    )

    parser.add_argument(
        "--sortie",
        type=Path,
        default=FICHIER_SORTIE,
        help="Fichier CSV enrichi.",
    )

    parser.add_argument(
        "--cache",
        type=Path,
        default=FICHIER_CACHE,
        help="Fichier de cache.",
    )

    args = parser.parse_args()

    traiter_csv(
        resoudre_chemin(args.source),
        resoudre_chemin(args.sortie),
        resoudre_chemin(args.cache),
    )


if __name__ == "__main__":
    main()
