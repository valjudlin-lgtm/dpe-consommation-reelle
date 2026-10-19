# Le DPE reflète-t-il la consommation électrique réelle ?

**Confrontation des Diagnostics de Performance Énergétique (ADEME) aux consommations électriques mesurées par Enedis**

![R](https://img.shields.io/badge/R-data.table-276DC3?logo=r&logoColor=white)
![Statut](https://img.shields.io/badge/statut-en%20cours-orange)
![Open Data](https://img.shields.io/badge/données-open%20data-2ea44f)

Projet réalisé dans le cadre de l'[Open Data University](https://www.data.gouv.fr/topics/diagnostics-de-performance-energetique), défi proposé par **Enedis**, au sein du Master 2 Statistique & Science des données de l'Université Grenoble Alpes.

---

## Contexte

Le DPE classe chaque logement de **A à G** selon sa consommation d'énergie. Il sert de base à des politiques publiques majeures : interdiction progressive de la location des « passoires thermiques » (F et G), aides à la rénovation, valorisation des biens immobiliers.

Pourtant, la consommation affichée par le DPE **n'est pas mesurée** : elle est **calculée** par une méthode conventionnelle (3CL) qui suppose une météo standard et un occupant moyen.

## Questions de recherche

1. **La consommation électrique estimée par le DPE est-elle proche de la consommation réellement mesurée ?**
2. **Quel gain réel (kWh/an, €/an) apporte le passage d'une classe DPE à une autre ?**
3. **Quelle part des écarts s'explique par le bâtiment, et quelle part par les modes de vie ?**

## Démarche par territoires

| Phase | Territoire | Objectif | Statut |
|---|---|---|---|
| 1 | **Lyon** (territoire pilote) | Construire et valider la méthode | en cours |
| 2 | Autres grandes villes | Tester la robustesse (formats d'adresses, abréviations locales) | à venir |
| 3 | **France entière** | Résultats nationaux | à venir |

## Données

| Source | Contenu | Rôle |
|---|---|---|
| [DPE Logements existants (ADEME)](https://www.data.gouv.fr/datasets/dpe-logements-existants-depuis-juillet-2021) | Un diagnostic par logement depuis juillet 2021 | Consommation **estimée** |
| [DPE Logements neufs (ADEME)](https://www.data.gouv.fr/datasets/dpe-logements-neufs-depuis-juillet-2021) | Idem, logements neufs | Consommation **estimée** |
| [Consommation annuelle résidentielle par adresse (Enedis)](https://www.data.gouv.fr/datasets/consommation-annuelle-residentielle-par-adresse) | Consommation électrique annuelle moyenne par adresse (≥ 10 logements), 2019–2025 | Consommation **mesurée** |

Les données ne sont pas versionnées (voir « Reproduire l'analyse »).

## Méthodologie

```
 DPE existants ─┐
                ├─► harmonisation des colonnes ─► empilement ─┐
 DPE neufs ─────┘                                              │
                                                               ├─► adresse normalisée ─► filtrage ─► dédoublonnage ─► jointure
 Enedis ─────────► harmonisation des colonnes ─────────────────┘
```

**Principaux choix méthodologiques**

- **Appariement par adresse normalisée** : minuscules, sans accents, abréviations développées (`crs` → `cours`), compléments de numéro unifiés (`91 b` → `91bis`), chiffres en lettres, articles retirés. Le taux d'appariement est mesuré après chaque amélioration.
- **Énergie finale électrique uniquement** : le DPE est comparé à Enedis sur la seule électricité, en énergie finale (`_ef`), et non en énergie primaire (`_ep`) qui sert au calcul de l'étiquette.
- **Appartements uniquement** : les DPE « immeuble » et « maison » sont exclus (incompatibles avec une moyenne Enedis par logement).
- **Analyses séparées selon le mode de chauffage** : un logement chauffé au gaz consomme peu d'électricité quelle que soit sa classe.

## Résultats intermédiaires — Lyon (territoire pilote)

| Indicateur | Valeur |
|---|---|
| DPE importés | 226 922 |
| Adresses Enedis | ≈ 13 700 |
| Adresses Enedis appariées à au moins un DPE | **≈ 91 %** (81 % avec une normalisation simple) |
| Adresses non appariées situées sur une rue connue côté DPE | ≈ 54 % (absence de DPE au numéro, et non erreur d'appariement) |

Détail des étapes et des effectifs : [`docs/journal_nettoyage.md`](docs/journal_nettoyage.md).

## Structure du dépôt

```
.
├── 01_preparation_donnees.Rmd       # import, harmonisation, appariement, filtrage
├── docs/
│   └── journal_nettoyage.md # décisions et effectifs à chaque étape
├── CONTRIBUTING.md          # comment contribuer (branches, Pull Requests)
└── README.md
```

## Reproduire l'analyse

1. Cloner le dépôt : `git clone https://github.com/valjudlin-lgtm/dpe-consommation-reelle.git`
2. Télécharger les trois fichiers ci-dessus (filtrés sur la commune de Lyon) et les placer dans le dossier du dépôt, sous les noms :
   - `dpe03existant.csv`
   - `dpe02neuf.csv`
   - `consommation-annuelle-residentielle-par-adresse (1).csv`
3. Dans `01_preparation_donnees.Rmd`, remplacer le chemin des `setwd()` par celui de votre dossier.
4. Ouvrir le fichier dans RStudio et cliquer sur **Knit**.

## Feuille de route

- [x] Import et harmonisation des trois sources
- [x] Normalisation des adresses et mesure du taux d'appariement
- [x] Filtrage des DPE (type de bâtiment, surface)
- [ ] Dédoublonnage (copies exactes, DPE remplacés, DPE générés depuis un DPE immeuble)
- [ ] Calcul de la consommation électrique estimée par DPE (énergie finale)
- [ ] Agrégation Enedis 2022–2025 et jointure (une ligne par adresse / par logement)
- [ ] Analyse descriptive des écarts DPE / réel, par classe et mode de chauffage
- [ ] Modélisation : régression puis modèle mixte (logements imbriqués dans les adresses)
- [ ] Chemins relatifs et code commune dans la clé d'adresse, pour passer à plusieurs villes
- [ ] Extension à d'autres villes, puis à la France entière
- [ ] Publication d'une réutilisation sur data.gouv.fr

## Limites connues

- Enedis ne publie que des **moyennes par adresse** (≥ 10 logements) : la consommation réelle d'un appartement donné n'est pas observable, et les maisons individuelles sont exclues.
- Les DPE ne couvrent que les logements **vendus ou loués depuis 2021** : l'échantillon n'est pas représentatif de l'ensemble du parc.
- Le DPE couvre 5 usages (chauffage, eau chaude, refroidissement, éclairage, auxiliaires) alors qu'Enedis mesure **toute** l'électricité (électroménager et cuisson inclus).
- Le dictionnaire d'abréviations a été construit sur Lyon et devra être enrichi pour d'autres territoires.

## Auteur

**Keevson Val** — Master 2 Statistique & Science des données, Université Grenoble Alpes
[GitHub](https://github.com/valjudlin-lgtm) · [LinkedIn](https://www.linkedin.com/in/keevson-judlin-val-095baa2b5)

Données sous [Licence Ouverte 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/).
