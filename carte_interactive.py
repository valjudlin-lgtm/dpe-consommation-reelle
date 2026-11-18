
import json
from pathlib import Path

import folium
import polars as pl
import streamlit as st

# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[1]

FICHIER_SOURCE = (
    ROOT_DIR / "data" / "processed" / "dpe_geocode.csv"
)

FICHIER_GEOJSON = (
    ROOT_DIR / "data" / "geographie" / "arrondissements_lyon.geojson"
)

SEPARATEUR_CSV = ","

CLASSES_DPE = ["A", "B", "C", "D", "E", "F", "G"]

CODES_ARRONDISSEMENTS = [
    "69381", "69382", "69383",
    "69384", "69385", "69386",
    "69387", "69388", "69389"
]

COULEURS_DPE = {
    "A": "#009B55",
    "B": "#50B848",
    "C": "#B5D334",
    "D": "#FEE500",
    "E": "#F6A000",
    "F": "#ED6A23",
    "G": "#E30613"
}

COULEUR_NEUTRE = "#A0A0A0"

CENTRE_CARTE = [45.7640, 4.8357]
ZOOM_INITIAL = 12


# ============================================================
# 2. CHARGEMENT DES DONNEES
# ============================================================

@st.cache_data
def charger_donnees() -> pl.DataFrame:
    """
    Charge les colonnes nécessaires depuis le fichier CSV.
    """

    colonnes_requises = [
        "code_insee_ban",
        "etiquette_dpe"
    ]

    donnees = pl.scan_csv(
        FICHIER_SOURCE,
        separator=SEPARATEUR_CSV,
        infer_schema=False
    )

    colonnes_disponibles = donnees.collect_schema().names()

    colonnes_manquantes = (
        set(colonnes_requises) - set(colonnes_disponibles)
    )

    if colonnes_manquantes:
        raise ValueError(
            "Colonnes absentes du fichier source : "
            f"{sorted(colonnes_manquantes)}"
        )

    return donnees.select(colonnes_requises).collect()


@st.cache_data
def charger_geojson() -> dict:
    """
    Charge les contours géographiques des arrondissements.
    """

    with FICHIER_GEOJSON.open(
        "r",
        encoding="utf-8"
    ) as fichier:
        geojson = json.load(fichier)

    return geojson


# ============================================================
# 3. NORMALISATION DES DONNEES
# ============================================================

def normaliser_donnees(
    donnees: pl.DataFrame
) -> pl.DataFrame:
    """
    Normalise les codes INSEE et les étiquettes DPE.
    """

    return donnees.with_columns([
        pl.col("code_insee_ban")
        .str.strip_chars(),

        pl.col("etiquette_dpe")
        .str.strip_chars()
        .str.to_uppercase()
    ])


# ============================================================
# 4. AGREGATION DES DPE PAR ARRONDISSEMENT
# ============================================================

def agreger_dpe(
    donnees: pl.DataFrame
) -> pl.DataFrame:
    """
    Calcule les effectifs A à G, les DPE exclus,
    le total exploitable et l'étiquette dominante.
    """

    donnees_arrondissements = donnees.filter(
        pl.col("code_insee_ban").is_in(
            CODES_ARRONDISSEMENTS
        )
    )

    # Comptage de tous les DPE présents dans chaque arrondissement.
    agregats = (
        donnees_arrondissements
        .group_by("code_insee_ban")
        .agg([
            pl.len().alias("total_dpe"),

            *[
                (
                    pl.col("etiquette_dpe") == classe
                )
                .sum()
                .alias(classe)
                for classe in CLASSES_DPE
            ]
        ])
    )

    # Création d'une base contenant systématiquement les 9 arrondissements.
    statistiques = (
        pl.DataFrame({
            "code_insee_ban": CODES_ARRONDISSEMENTS
        })
        .join(
            agregats,
            on="code_insee_ban",
            how="left"
        )
        .with_columns([
            pl.col("total_dpe").fill_null(0),
            *[
                pl.col(classe).fill_null(0)
                for classe in CLASSES_DPE
            ]
        ])
        .with_columns([
            pl.sum_horizontal(
                *[
                    pl.col(classe)
                    for classe in CLASSES_DPE
                ]
            ).alias("total_exploitable")
        ])
        .with_columns([
            (
                pl.col("total_dpe")
                - pl.col("total_exploitable")
            ).alias("total_exclu")
        ])
    )

    # Détermination de l'étiquette dominante.
    etiquettes_dominantes = []

    for ligne in statistiques.iter_rows(named=True):

        effectifs = {
            classe: ligne[classe]
            for classe in CLASSES_DPE
        }

        maximum = max(effectifs.values())

        if maximum == 0:
            dominante = "Aucune donnée"

        else:
            classes_maximales = [
                classe
                for classe, effectif in effectifs.items()
                if effectif == maximum
            ]

            if len(classes_maximales) > 1:
                dominante = "Égalité"
            else:
                dominante = classes_maximales[0]

        etiquettes_dominantes.append(dominante)

    statistiques = statistiques.with_columns(
        pl.Series(
            "etiquette_dominante",
            etiquettes_dominantes
        )
    )

    return statistiques.sort("code_insee_ban")


# ============================================================
# 5. DIAGNOSTIC DES DONNEES HORS PERIMETRE
# ============================================================

def calculer_donnees_hors_perimetre(
    donnees: pl.DataFrame
) -> dict:
    """
    Compte les DPE qui ne correspondent pas aux 9 arrondissements.
    """

    return {
        "lyon_commune": donnees.filter(
            pl.col("code_insee_ban") == "69123"
        ).height,

        "code_manquant": donnees.filter(
            pl.col("code_insee_ban").is_null()
        ).height,

        "autres_codes": donnees.filter(
            pl.col("code_insee_ban").is_not_null()
            & ~pl.col("code_insee_ban").is_in(
                CODES_ARRONDISSEMENTS + ["69123"]
            )
        ).height
    }


# ============================================================
# 6. ASSOCIATION DES STATISTIQUES AU GEOJSON
# ============================================================

def enrichir_geojson(
    geojson: dict,
    statistiques: pl.DataFrame
) -> dict:
    """
    Ajoute les statistiques DPE aux propriétés de chaque polygone.
    """

    statistiques_par_code = {
        ligne["code_insee_ban"]: ligne
        for ligne in statistiques.iter_rows(named=True)
    }

    codes_geojson = {
        feature["properties"]["code"]
        for feature in geojson["features"]
    }

    codes_attendus = set(CODES_ARRONDISSEMENTS)

    if codes_geojson != codes_attendus:
        raise ValueError(
            "Les codes INSEE du GeoJSON ne correspondent "
            "pas aux neuf arrondissements attendus."
        )

    for feature in geojson["features"]:

        code = feature["properties"]["code"]

        if feature.get("geometry") is None:
            raise ValueError(
                f"Géométrie absente pour le code {code}"
            )

        statistiques_arrondissement = (
            statistiques_par_code[code]
        )

        feature["properties"].update(
            statistiques_arrondissement
        )

    return geojson


# ============================================================
# 7. CREATION DE LA CARTE
# ============================================================

def creer_carte() -> folium.Map:
    """
    Initialise la carte centrée sur Lyon.
    """

    return folium.Map(
        location=CENTRE_CARTE,
        zoom_start=ZOOM_INITIAL,
        tiles="OpenStreetMap"
    )


def obtenir_couleur_dominante(etiquette: str) -> str:
    """
    Retourne la couleur associée à l'étiquette dominante.
    """

    return COULEURS_DPE.get(
        etiquette,
        COULEUR_NEUTRE
    )


def ajouter_arrondissements(
    carte: folium.Map,
    geojson: dict
) -> folium.Map:
    """
    Ajoute les neuf polygones et leurs infobulles.
    """

    def style_function(feature):

        etiquette = feature["properties"][
            "etiquette_dominante"
        ]

        couleur = obtenir_couleur_dominante(
            etiquette
        )

        return {
            "fillColor": couleur,
            "color": "#333333",
            "weight": 2,
            "fillOpacity": 0.70
        }

    def highlight_function(feature):

        return {
            "weight": 4,
            "color": "#222222",
            "fillOpacity": 0.90
        }

    champs = [
        "nom",
        "total_exploitable",
        "total_exclu",
        "A", "B", "C", "D", "E", "F", "G",
        "etiquette_dominante"
    ]

    alias = [
        "Arrondissement :",
        "DPE exploitables :",
        "DPE exclus :",
        "DPE A :",
        "DPE B :",
        "DPE C :",
        "DPE D :",
        "DPE E :",
        "DPE F :",
        "DPE G :",
        "Étiquette dominante :"
    ]

    folium.GeoJson(
        data=geojson,
        name="Arrondissements de Lyon",
        style_function=style_function,
        highlight_function=highlight_function,
        tooltip=folium.GeoJsonTooltip(
            fields=champs,
            aliases=alias,
            localize=True,
            sticky=True,
            labels=True
        )
    ).add_to(carte)

    return carte


# ============================================================
# 8. LEGENDE
# ============================================================

def ajouter_legende(
    carte: folium.Map
) -> folium.Map:
    """
    Ajoute la légende des couleurs DPE.
    """

    contenu = """
    <div style="
        position: fixed;
        bottom: 30px;
        right: 20px;
        z-index: 9999;
        background-color: white;
        padding: 12px;
        border: 1px solid #999;
        border-radius: 6px;
        font-size: 13px;
        box-shadow: 0 1px 5px rgba(0,0,0,0.3);
    ">
        <b>Étiquette DPE dominante</b>
        <br><br>
    """

    for classe, couleur in COULEURS_DPE.items():

        contenu += f"""
        <div style="margin-bottom: 4px;">
            <span style="
                display: inline-block;
                width: 13px;
                height: 13px;
                background-color: {couleur};
                margin-right: 6px;
                vertical-align: middle;
            "></span>
            {classe}
        </div>
        """

    contenu += f"""
        <hr style="margin: 7px 0;">
        <div>
            <span style="
                display: inline-block;
                width: 13px;
                height: 13px;
                background-color: {COULEUR_NEUTRE};
                margin-right: 6px;
                vertical-align: middle;
            "></span>
            Égalité / aucune donnée
        </div>
    </div>
    """

    carte.get_root().html.add_child(
        folium.Element(contenu)
    )

    return carte


# ============================================================
# 9. INTERFACE STREAMLIT
# ============================================================

def afficher_indicateurs(
    statistiques: pl.DataFrame,
    donnees_hors_perimetre: dict
):
    """
    Affiche les indicateurs généraux sous la carte.
    """

    total_dpe = statistiques["total_dpe"].sum()

    total_exploitable = (
        statistiques["total_exploitable"].sum()
    )

    total_exclu = statistiques["total_exclu"].sum()

    st.subheader("Bilan des DPE")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "DPE dans les 9 arrondissements",
        f"{total_dpe:,}".replace(",", " ")
    )

    col2.metric(
        "DPE exploitables",
        f"{total_exploitable:,}".replace(",", " ")
    )

    col3.metric(
        "DPE exclus",
        f"{total_exclu:,}".replace(",", " ")
    )

    st.caption(
        "Les DPE exclus correspondent aux étiquettes "
        "absentes ou non reconnues parmi les neuf arrondissements."
    )

    st.subheader("Données hors périmètre")

    st.write(
        f"- Code INSEE 69123 (commune de Lyon) : "
        f"{donnees_hors_perimetre['lyon_commune']:,} DPE"
        .replace(",", " ")
    )

    st.write(
        f"- Code INSEE manquant : "
        f"{donnees_hors_perimetre['code_manquant']:,} DPE"
        .replace(",", " ")
    )

    st.write(
        f"- Autres codes INSEE : "
        f"{donnees_hors_perimetre['autres_codes']:,} DPE"
        .replace(",", " ")
    )


# ============================================================
# 10. PROGRAMME PRINCIPAL
# ============================================================

def main():

    st.set_page_config(
        page_title="Cartographie des DPE",
        page_icon="🏠",
        layout="wide"
    )

    st.title("Cartographie interactive des DPE")
    st.subheader("Lyon — neuf arrondissements municipaux")

    try:

        # Chargement.
        with st.spinner("Chargement des données..."):

            donnees = charger_donnees()
            geojson = charger_geojson()

        # Normalisation.
        with st.spinner("Normalisation des données..."):

            donnees = normaliser_donnees(donnees)

        # Agrégation.
        with st.spinner("Agrégation des DPE par arrondissement..."):

            statistiques = agreger_dpe(donnees)

        # Diagnostic hors périmètre.
        donnees_hors_perimetre = (
            calculer_donnees_hors_perimetre(donnees)
        )

        # Association des statistiques aux contours.
        geojson = enrichir_geojson(
            geojson,
            statistiques
        )

        # Création de la carte.
        with st.spinner("Construction de la carte..."):

            carte = creer_carte()

            carte = ajouter_arrondissements(
                carte,
                geojson
            )

            carte = ajouter_legende(carte)

        # Affichage.
        st.subheader("Répartition géographique des étiquettes DPE")

        carte_html = carte.get_root().render()

        st.components.v1.html(
            carte_html,
            height=750,
            scrolling=False
        )

        # Indicateurs.
        afficher_indicateurs(
            statistiques,
            donnees_hors_perimetre
        )

        # Tableau statistique.
        with st.expander("Consulter les statistiques détaillées"):

            st.dataframe(
                statistiques,
                use_container_width=True,
                hide_index=True
            )

        st.success("Cartographie générée avec succès.")

    except FileNotFoundError as erreur:

        st.error(
            f"Fichier introuvable : {erreur.filename}"
        )

    except Exception as erreur:  # noqa: BLE001

        st.error(
            f"Erreur lors de la génération de la carte : {erreur}"
        )


if __name__ == "__main__":
    main()
