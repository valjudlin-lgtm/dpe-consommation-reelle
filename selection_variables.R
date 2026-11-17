# =============================================================================
#  Sélection des variables — fonctions réutilisables (Lyon, autres villes, France)
#  Projet DPE × Enedis — Open Data University
#
#  Le protocole complet est décrit dans le document
#  « Protocole de sélection des variables — Projet DPE ».
#
#  Étape 1 : audit_variables() et paires_redondantes()   -> règles R4, R5, R6
#  Étape 3 : comparer_modeles()                           -> BIC sur modèles emboîtés
#            selection_stabilite()                        -> Lasso + stabilité
#
#  Aucune fonction ne contient de nom de ville : on les applique à n'importe
#  quel territoire, et on compare les résultats entre territoires.
# =============================================================================

library(data.table)
library(glmnet)    # install.packages("glmnet") une seule fois


# ---- Outils ----------------------------------------------------------------

# Une case vide "" compte comme manquante, au même titre que NA
est_manquant <- function(x) {
  is.na(x) | (is.character(x) & trimws(as.character(x)) == "")
}

# V de Cramér : lien entre deux variables qualitatives (0 = aucun, 1 = parfait)
cramer_v <- function(x, y) {
  tab <- table(x, y)
  if (min(dim(tab)) < 2) return(NA_real_)
  chi2 <- suppressWarnings(chisq.test(tab, correct = FALSE)$statistic)
  as.numeric(sqrt(chi2 / (sum(tab) * (min(dim(tab)) - 1))))
}

# Rapport de corrélation (êta) : lien entre une variable numérique et une qualitative
eta <- function(num, cat) {
  moy_g <- tapply(num, cat, mean)
  n_g   <- tapply(num, cat, length)
  sqrt(sum(n_g * (moy_g - mean(num))^2) / sum((num - mean(num))^2))
}


# ---- Étape 1 : règles R4 (disponibilité) et R5 (variabilité) -----------------
# Les seuils sont des paramètres : on les fixe une fois pour tout le projet.
audit_variables <- function(dt, variables, seuil_na = 40, seuil_dominance = 99) {
  res <- rbindlist(lapply(variables, function(v) {
    x  <- dt[[v]]
    ok <- !est_manquant(x)
    dominance <- if (any(ok)) 100 * max(table(x[ok])) / sum(ok) else NA_real_
    data.table(
      variable               = v,
      type                   = class(x)[1],
      pct_na                 = round(100 * mean(!ok), 1),
      pct_modalite_dominante = round(dominance, 1),
      n_modalites            = uniqueN(x[ok])
    )
  }))
  res[, decision := fcase(
    pct_na > seuil_na,                         "Écartée (R4) : trop de manquants",
    pct_modalite_dominante >= seuil_dominance, "Écartée (R5) : quasi constante",
    default =                                  "Retenue"
  )]
  res[order(decision, -pct_na)]
}


# ---- Étape 1 : règle R6 (redondance) ----------------------------------------
# Spearman (numérique-numérique), V de Cramér (quali-quali), êta (numérique-quali).
# Sur la France entière, on calcule sur un échantillon (n_max lignes) : largement
# suffisant pour mesurer un lien, et beaucoup plus rapide.
paires_redondantes <- function(dt, variables, seuil = 0.9, n_max = 2e5, graine = 2026) {
  if (nrow(dt) > n_max) {
    set.seed(graine)
    dt <- dt[sample(.N, n_max)]
  }
  paires <- combn(variables, 2, simplify = FALSE)
  res <- rbindlist(lapply(paires, function(p) {
    x  <- dt[[p[1]]]
    y  <- dt[[p[2]]]
    ok <- !est_manquant(x) & !est_manquant(y)
    x <- x[ok]; y <- y[ok]
    lien <- if (length(x) < 10) {
      NA_real_
    } else if (is.numeric(x) && is.numeric(y)) {
      abs(cor(x, y, method = "spearman"))
    } else if (is.numeric(x)) {
      eta(x, as.character(y))
    } else if (is.numeric(y)) {
      eta(y, as.character(x))
    } else {
      cramer_v(as.character(x), as.character(y))
    }
    data.table(variable_1 = p[1], variable_2 = p[2], lien = round(lien, 2))
  }))
  res[!is.na(lien) & lien >= seuil][order(-lien)]
}


# ---- Étape 3a : BIC sur modèles emboîtés -------------------------------------
# M0 : ajustement seul ; M1 : + variable(s) d'intérêt ; M2 : + interaction.
# La variable à expliquer est passée en log (consommation asymétrique).
# Le meilleur modèle a le PLUS PETIT BIC ; un écart > 10 = preuve très forte.
comparer_modeles <- function(dt, y, ajustement, interet,
                             interaction_avec = NULL, poids = NULL) {
  colonnes <- unique(c(y, ajustement, interet, interaction_avec, poids))
  d <- na.omit(dt[, ..colonnes])
  d <- d[get(y) > 0]                       # le log exige des valeurs positives
  w <- if (is.null(poids)) NULL else d[[poids]]

  f0 <- reformulate(ajustement, response = sprintf("log(%s)", y))
  f1 <- update(f0, paste(". ~ . +", paste(interet, collapse = " + ")))
  modeles <- list(
    "M0 : ajustement seul"      = lm(f0, data = d, weights = w),
    "M1 : + variable d'intérêt" = lm(f1, data = d, weights = w)
  )
  if (!is.null(interaction_avec)) {
    f2 <- update(f1, paste(". ~ . +", interet[1], ":", interaction_avec))
    modeles[["M2 : + interaction"]] <- lm(f2, data = d, weights = w)
  }

  tableau <- data.table(
    modele    = names(modeles),
    n         = nrow(d),
    BIC       = sapply(modeles, BIC),
    R2_ajuste = sapply(modeles, function(m) summary(m)$adj.r.squared)
  )
  tableau[, delta_BIC := BIC - min(BIC)]
  # Test du rapport de vraisemblance M0 contre M1 (en complément du BIC)
  tableau[, p_valeur_vs_precedent := c(NA, sapply(2:length(modeles), function(i)
    anova(modeles[[i - 1]], modeles[[i]])$`Pr(>F)`[2]))]
  list(tableau = tableau[], modeles = modeles)
}


# ---- Étape 3b et 3c : Lasso avec variables forcées + sélection par stabilité --
# - forcees    : le jeu d'ajustement + la variable d'intérêt, jamais pénalisés
# - candidates : les variables « utiles », que le Lasso peut retirer
# Le niveau de pénalité (lambda.1se) est choisi UNE fois par validation croisée
# sur tout l'échantillon, puis réutilisé sur B demi-échantillons : c'est ce qui
# rend la méthode assez rapide pour la France entière.
selection_stabilite <- function(dt, y, forcees, candidates,
                                B = 100, fraction = 0.5, seuil = 0.7, graine = 2026) {
  colonnes <- unique(c(y, forcees, candidates))
  d <- na.omit(dt[, ..colonnes])
  d <- d[get(y) > 0]

  # Une variable qualitative à une seule modalité ferait planter model.matrix
  utiles_ici <- c(forcees, candidates)[sapply(c(forcees, candidates),
                                              function(v) uniqueN(d[[v]]) > 1)]
  mm   <- model.matrix(reformulate(utiles_ici), data = d)
  X    <- mm[, -1, drop = FALSE]
  appartenance <- utiles_ici[attr(mm, "assign")[-1]]   # colonne -> variable d'origine
  pf   <- ifelse(appartenance %in% forcees, 0, 1)      # 0 = jamais retirée
  yv   <- log(d[[y]])

  set.seed(graine)
  lambda <- cv.glmnet(X, yv, penalty.factor = pf, nfolds = 5)$lambda.1se

  cand_ici  <- intersect(candidates, utiles_ici)
  selection <- matrix(FALSE, B, length(cand_ici), dimnames = list(NULL, cand_ici))
  for (b in seq_len(B)) {
    idx  <- sample(nrow(d), floor(fraction * nrow(d)))
    fit  <- glmnet(X[idx, ], yv[idx], penalty.factor = pf, lambda = lambda)
    beta <- as.numeric(coef(fit))[-1]
    for (v in cand_ici) selection[b, v] <- any(beta[appartenance == v] != 0)
  }

  data.table(
    variable            = cand_ici,
    frequence_selection = round(colMeans(selection), 2)
  )[, retenue := frequence_selection >= seuil][order(-frequence_selection)]
}


# =============================================================================
#  Exemple d'utilisation sur le tableau A (une ligne par adresse)
#  Les noms de colonnes sont ceux de la section « Tableau A » du Rmd.
# =============================================================================
if (FALSE) {   # mettre TRUE pour exécuter

  # Étape 1
  candidates_dpe <- c("surface_habitable_logement", "periode_construction",
                      "annee_construction", "typologie_logement",
                      "type_energie_principale_chauffage",
                      "type_generateur_chauffage_principal",
                      "type_energie_principale_ecs", "type_installation_chauffage",
                      "numero_etage_appartement", "qualite_isolation_enveloppe")
  candidates_dpe <- intersect(candidates_dpe, names(dpe))
  audit_variables(dpe, candidates_dpe)
  paires_redondantes(dpe, candidates_dpe)

  # Étape 3a : l'étiquette apporte-t-elle quelque chose au-delà de l'ajustement ?
  tableau_a[, chauffage_electrique := chauffage_mode == "Électricité"]
  res <- comparer_modeles(
    tableau_a,
    y                = "conso_reelle_kwh",
    ajustement       = c("surface_moy", "chauffage_mode", "periode_mode"),
    interet          = "etiquette_mode",
    interaction_avec = "chauffage_electrique",
    poids            = "nb_logements"
  )
  res$tableau
  summary(res$modeles[[2]])      # coefficients : exp(coef) - 1 = écart en %

  # Étape 3b-c : quelles variables « utiles » ajouter ?
  selection_stabilite(
    tableau_a,
    y          = "conso_reelle_kwh",
    forcees    = c("surface_moy", "chauffage_mode", "periode_mode", "etiquette_mode"),
    candidates = c("part_F_G", "part_dpe_generes", "taux_couverture")
  )

  # Réutilisabilité : la même boucle sur plusieurs territoires
  # resultats <- rbindlist(lapply(c("lyon", "grenoble", "marseille"), function(t) {
  #   tab <- fread(file.path("data", t, "tableau_a_adresses.csv"))
  #   cbind(territoire = t, comparer_modeles(tab, ...)$tableau)
  # }))
}
