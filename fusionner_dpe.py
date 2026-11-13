
"""Fusionne les fichiers DPE neuf et existant en un seul CSV.

Les fichiers sources sont conservés sans modification.
Les colonnes des deux fichiers sont alignées automatiquement.
Une colonne 'source' permet d'identifier l'origine de chaque ligne.
"""

from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

RACINE_PROJET = Path(__file__).resolve().parent.parent

FICHIER_NEUF = RACINE_PROJET / "data" / "raw" / "Lyon" / "dpe02neuf.csv"
FICHIER_EXISTANT = RACINE_PROJET / "data" / "raw" / "Lyon" / "dpe03existant.csv"

DOSSIER_SORTIE = RACINE_PROJET / "data" / "processed"
FICHIER_SORTIE = DOSSIER_SORTIE / "dpe_fusionne.csv"
FICHIER_BILAN = DOSSIER_SORTIE / "bilan_colonnes.csv"

COLONNE_SOURCE = "source"


# ---------------------------------------------------------------------
# Read + prep fichier source
# ---------------------------------------------------------------------

def lire_source(chemin: Path) -> pl.DataFrame:
    """Lit un CSV, normalise ses noms de colonnes et identifie sa source."""

    if not chemin.is_file():
        raise FileNotFoundError(
            f"Fichier source introuvable : {chemin}"
        )

    df = pl.read_csv(
        chemin,
        infer_schema_length=None,
    )

    # Supprimer les espaces en début et fin des noms de colonnes.
    # Les fichiers bruts restent inchangés.
    noms_normalises = [nom.strip() for nom in df.columns]

    # Vérifier qu'aucun nom n'est dupliqué après normalisation.
    if len(noms_normalises) != len(set(noms_normalises)):
        raise ValueError(
            f"Noms de colonnes dupliqués après normalisation "
            f"dans {chemin.name}."
        )

    df.columns = noms_normalises

    # Éviter d'écraser une éventuelle colonne source existante.
    if COLONNE_SOURCE in df.columns:
        raise ValueError(
            f"La colonne '{COLONNE_SOURCE}' existe déjà "
            f"dans {chemin.name}."
        )

    # Ajouter le nom du fichier d'origine.
    df = df.with_columns(
        pl.lit(chemin.name).alias(COLONNE_SOURCE)
    )

    return df

def generer_bilan_colonnes(
    df_neuf: pl.DataFrame,
    df_existant: pl.DataFrame,
    df_fusionne: pl.DataFrame,
) -> pl.DataFrame:
    """Analyse les colonnes et leur taux de valeurs manquantes."""

    colonnes_neuf = set(df_neuf.columns) - {COLONNE_SOURCE}
    colonnes_existant = set(df_existant.columns) - {COLONNE_SOURCE}

    colonnes = sorted(colonnes_neuf | colonnes_existant)

    rapport = []

    for colonne in colonnes:
        presente_neuf = colonne in colonnes_neuf
        presente_existant = colonne in colonnes_existant

        if presente_neuf and presente_existant:
            statut = "commune"
        elif presente_neuf:
            statut = "specifique_neuf"
        else:
            statut = "specifique_existant"

        # Valeurs manquantes dans chaque source.
        manquants_neuf = (
            df_neuf[colonne].null_count()
            if presente_neuf
            else df_neuf.height
        )

        manquants_existant = (
            df_existant[colonne].null_count()
            if presente_existant
            else df_existant.height
        )

        # Valeurs manquantes dans le fichier fusionné.
        manquants_total = df_fusionne[colonne].null_count()

        taux_neuf = manquants_neuf / df_neuf.height * 100
        taux_existant = manquants_existant / df_existant.height * 100
        taux_total = manquants_total / df_fusionne.height * 100

        rapport.append({
            "colonne": colonne,
            "presente_neuf": presente_neuf,
            "presente_existant": presente_existant,
            "statut": statut,

            "nb_lignes_neuf": df_neuf.height,
            "nb_manquants_neuf": manquants_neuf,
            "taux_manquant_neuf_pct": round(taux_neuf, 2),

            "nb_lignes_existant": df_existant.height,
            "nb_manquants_existant": manquants_existant,
            "taux_manquant_existant_pct": round(taux_existant, 2),

            "nb_lignes_total": df_fusionne.height,
            "nb_manquants_total": manquants_total,
            "taux_manquant_total_pct": round(taux_total, 2),
        })

    return pl.DataFrame(rapport)


# ---------------------------------------------------------------------
# Fusion et contrôles
# ---------------------------------------------------------------------

def main() -> None:
    """Exécute la fusion, vérifie le résultat et écrit le CSV final."""

    # Ne jamais écraser un résultat existant.
    if FICHIER_SORTIE.exists():
        raise FileExistsError(
            f"Le fichier de sortie existe déjà : {FICHIER_SORTIE}\n"
            "Archive-le, déplace-le ou supprime-le avant de relancer."
        )

    df_neuf = lire_source(FICHIER_NEUF)
    df_existant = lire_source(FICHIER_EXISTANT)

    # Effectifs de référence
    nb_neuf = df_neuf.height
    nb_existant = df_existant.height
    nb_attendu = nb_neuf + nb_existant

    # Concaténation verticale :
    # - union des colonnes ;
    # - valeurs nulles si une colonne est absente d'une source ;
    # - harmonisation des types compatibles.
    df_fusionne = pl.concat(
        [df_neuf, df_existant],
        how="diagonal_relaxed",
    )

    # Check nb total ligne
    if df_fusionne.height != nb_attendu:
        raise RuntimeError(
            f"Nombre de lignes incorrect : {df_fusionne.height}, "
            f"attendu : {nb_attendu}."
        )

    # Check provenance lignes
    repartition = (
        df_fusionne
        .group_by(COLONNE_SOURCE)
        .len()
    )

    effectifs = {
        ligne[COLONNE_SOURCE]: ligne["len"]
        for ligne in repartition.iter_rows(named=True)
    }

    effectifs_attendus = {
        FICHIER_NEUF.name: nb_neuf,
        FICHIER_EXISTANT.name: nb_existant,
    }

    if effectifs != effectifs_attendus:
        raise RuntimeError(
            "La répartition des lignes par source est incorrecte.\n"
            f"Attendu : {effectifs_attendus}\n"
            f"Obtenu : {effectifs}"
        )

    # Créer le dossier de sortie si nécessaire.
    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)

    # Écrire le fichier fusionné.
    df_fusionne.write_csv(FICHIER_SORTIE)

    # Relire le CSV pour vérifier le fichier réellement écrit.
    df_verification = pl.read_csv(
        FICHIER_SORTIE,
        infer_schema_length=None,
    )

    if (
        df_verification.height != df_fusionne.height
        or df_verification.width != df_fusionne.width
    ):
        raise RuntimeError(
            "La vérification du fichier écrit a échoué : "
            "les dimensions ne correspondent pas."
        )

    # Vérifier également la provenance après relecture.
    repartition_verification = (
        df_verification
        .group_by(COLONNE_SOURCE)
        .len()
    )

    effectifs_verification = {
        ligne[COLONNE_SOURCE]: ligne["len"]
        for ligne in repartition_verification.iter_rows(named=True)
    }

    if effectifs_verification != effectifs_attendus:
        raise RuntimeError(
            "La provenance des lignes diffère après relecture du CSV."
        )

    # Résumé final.
    print("\nFusion terminée avec succès.")
    print(f"Fichier généré : {FICHIER_SORTIE.relative_to(RACINE_PROJET)}")
    print(f"Lignes issues du neuf : {nb_neuf:,}".replace(",", " "))
    print(
        f"Lignes issues de l'existant : {nb_existant:,}".replace(",", " ")
    )
    print(f"Total des lignes : {df_verification.height:,}".replace(",", " "))
    print(f"Nombre de colonnes : {df_verification.width}")
    print("Contrôles de structure et de provenance : OK")

    # Générer le bilan des colonnes et des valeurs manquantes.
    df_bilan = generer_bilan_colonnes(
        df_neuf,
        df_existant,
        df_fusionne,
    )

    df_bilan.write_csv(FICHIER_BILAN)

    # Afficher une synthèse dans le terminal.
    print("\nBilan des colonnes :")
    print(f"Colonnes communes : {(df_bilan['statut'] == 'commune').sum()}")
    print(
        "Colonnes spécifiques au neuf : "
        f"{(df_bilan['statut'] == 'specifique_neuf').sum()}"
    )
    print(
        "Colonnes spécifiques à l'existant : "
        f"{(df_bilan['statut'] == 'specifique_existant').sum()}"
    )

    print(f"\nBilan détaillé généré : {FICHIER_BILAN.relative_to(RACINE_PROJET)}")


if __name__ == "__main__":
    main()
