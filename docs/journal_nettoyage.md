# Journal de nettoyage

Chaque étape qui retire des lignes est notée ici, avec sa justification, **pour chaque territoire traité**. 

## Règles communes à tous les territoires

| Étape | Règle | Justification |
|---|---|---|
| Import | `clean_names()` sur chaque fichier avant empilement | Les DPE existants et neufs n'écrivent pas leurs colonnes exactement pareil |
| Type de bâtiment | Appartements uniquement | DPE « immeuble » (consommation de tout l'immeuble) et « maison » (absentes d'Enedis) incompatibles avec une moyenne par logement |
| Surface | Entre 9 et 250 m² | 9 m² = minimum d'un logement décent ; au-delà de 250 m², valeurs rares et souvent erronées |
| Copies exactes | Une ligne par `numero_dpe` | Même DPE enregistré plusieurs fois |
| DPE remplacés | Retrait des DPE cités dans `numero_dpe_remplace` | On garde la version la plus récente |

---

## Lyon (territoire pilote)

### DPE

| # | Étape | DPE restants | Retirés |
|---|---|---|---|
| 0 | Import (existants + neufs) | 226 922 | — |
| 1 | Appartements uniquement | 219 331 | 7 591 |
| 2 | Surface entre 9 et 250 m² | 218 991 | 340 |
| 3 | Copies exactes retirées | *à compléter* | |
| 4 | DPE remplacés retirés | *à compléter* | |

### Appariement des adresses

| Version de la normalisation | Adresses Enedis appariées | Non appariées |
|---|---|---|
| Minuscules, accents, code postal retiré | 81,3 % | 2 664 |
| + compléments de numéro (bis, ter) et abréviations (crs, av…) | 88,1 % | 1 630 |
| + chiffres en lettres et articles retirés | 91,2 % | 1 201 |



Sur les adresses non appariées, environ 54 % sont situées sur une rue présente côté DPE : il n'existe simplement aucun DPE à ce numéro.

### Points d'attention

- **173 avenue Barthélémy Buyer** : 1 558 DPE pour environ 375 logements selon Enedis. Hypothèse : DPE d'appartements générés à partir d'un DPE immeuble et diagnostics refaits. À vérifier avec `methode_application_dpe`.
- **Années Enedis 2022 et 2023** : environ 4 000 lignes de moins que les autres années. Cause non identifiée.
