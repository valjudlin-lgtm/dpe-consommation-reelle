# Contribuer au projet

Merci de votre aide ! Ce guide explique comment travailler à plusieurs sans se marcher dessus.

## Principe

La branche **`main`** contient toujours une version **qui fonctionne**. On ne travaille jamais directement dessus : chacun crée **sa propre branche**, y fait ses modifications, puis propose de les intégrer via une **Pull Request**.

## Étapes

### 1. Récupérer le projet (une seule fois)

```bash
git clone https://github.com/valjudlin-lgtm/dpe-consommation-reelle.git
cd dpe-consommation-reelle
```

Puis télécharger les données et les placer dans ce dossier (voir la section « Reproduire l'analyse » du README).

### 2. Partir de la dernière version

```bash
git checkout main
git pull
```

### 3. Créer sa branche

Un nom court qui dit ce qu'on fait :

```bash
git checkout -b analyse/ecarts-par-classe
```

| Préfixe | Usage | Exemple |
|---|---|---|
| `nettoyage/` | préparation des données | `nettoyage/doublons-dpe` |
| `analyse/` | statistiques, graphiques | `analyse/ecarts-par-classe` |
| `modele/` | modélisation | `modele/modele-mixte` |
| `docs/` | documentation | `docs/rapport-final` |

### 4. Travailler et enregistrer

```bash
git add 01_preparation_donnees.Rmd
git commit -m "Ajoute le retrait des DPE remplacés"
git push -u origin nettoyage/doublons-dpe
```

**Messages de commit** : une phrase courte, au présent, qui dit *ce que fait* la modification.
Bon : `Ajoute le filtre sur la surface habitable`. À éviter : `modifs`, `test`, `ça marche`.

### 5. Ouvrir une Pull Request

Sur GitHub, cliquer sur **Compare & pull request**, puis décrire :
- ce qui a été fait ;
- les choix effectués (seuils, filtres) et pourquoi ;
- l'effet sur les effectifs (nombre de lignes avant / après).

## Règles du projet

1. **Ne jamais versionner les données** : les fichiers `.csv` sont ignorés automatiquement (`.gitignore`).
2. **Ne pas envoyer son propre chemin `setwd()`** : modifiez-le chez vous pour travailler, mais remettez celui de `main` avant de faire `git add`, sinon chaque contributeur écrasera le chemin des autres. *(Amélioration prévue : passer à des chemins relatifs pour supprimer ce problème.)*
3. **Le document doit se générer avec Knit sans erreur** avant chaque Pull Request.
4. **Commenter le pourquoi, pas seulement le comment** : un filtre sans justification est inutilisable dans le rapport.
5. **Toute étape qui retire des lignes est notée** dans `docs/journal_nettoyage.md`.
