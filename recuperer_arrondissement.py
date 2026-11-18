
from pathlib import Path
import json
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]

DOSSIER_SORTIE = ROOT_DIR / "data" / "geographie"
FICHIER_SORTIE = DOSSIER_SORTIE / "arrondissements_lyon.geojson"

CODE_LYON = "69123"

CODES_ATTENDUS = {
    "69381", "69382", "69383",
    "69384", "69385", "69386",
    "69387", "69388", "69389"
}

URL_API = "https://geo.api.gouv.fr/communes"


def recuperer_arrondissements():
    parametres = {
        "codeParent": CODE_LYON,
        "type": "arrondissement-municipal",
        "format": "geojson",
        "geometry": "contour"
    }

    print("Récupération des contours de Lyon...")

    reponse = requests.get(
        URL_API,
        params=parametres,
        timeout=60
    )
    reponse.raise_for_status()

    geojson = reponse.json()

    features = geojson.get("features", [])

    codes_recuperes = {
        feature["properties"]["code"]
        for feature in features
    }

    codes_manquants = CODES_ATTENDUS - codes_recuperes
    codes_inattendus = codes_recuperes - CODES_ATTENDUS

    if codes_manquants or codes_inattendus:
        raise ValueError(
            f"Codes manquants : {sorted(codes_manquants)}\n"
            f"Codes inattendus : {sorted(codes_inattendus)}"
        )

    if len(features) != 9:
        raise ValueError(
            f"Nombre de géométries inattendu : {len(features)}"
        )

    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)

    with FICHIER_SORTIE.open("w", encoding="utf-8") as fichier:
        json.dump(geojson, fichier, ensure_ascii=False)

    print("\nRécupération terminée.")

    for feature in sorted(
        features,
        key=lambda f: f["properties"]["code"]
    ):
        proprietes = feature["properties"]
        print(f"{proprietes['code']} : {proprietes['nom']}")

    print(f"\nNombre d'arrondissements : {len(features)}")
    print(f"Fichier enregistré : {FICHIER_SORTIE}")


if __name__ == "__main__":
    recuperer_arrondissements()
