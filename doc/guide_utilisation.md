# Guide d'utilisation -- Tableau de bord Point de Vente

## Table des matieres

1. [Acceder au dashboard](#1-accéder-au-dashboard)
2. [Comprendre les KPI](#2-comprendre-les-kpi)
3. [Utiliser les filtres](#3-utiliser-les-filtres)
4. [Configurer le rafraichissement automatique](#4-configurer-le-rafraîchissement-automatique)
5. [Naviguer vers les commandes et sessions](#5-naviguer-vers-les-commandes-et-sessions)
6. [Lire le graphique du chiffre d'affaires](#6-lire-le-graphique-du-chiffre-daffaires)
7. [Analyser les top produits](#7-analyser-les-top-produits)
8. [Analyser les moyens de paiement](#8-analyser-les-moyens-de-paiement)
9. [Surveiller les sessions actives](#9-surveiller-les-sessions-actives)
10. [Configurer les parametres par defaut](#10-configurer-les-paramètres-par-défaut)
11. [Droits d'acces](#11-droits-daccès)
12. [Cas d'usage courants](#12-cas-dusage-courants)

---

## 1. Acceder au dashboard

1. Ouvrir le menu principal **Point de Vente**
2. Cliquer sur **Tableau de bord** (premier element du menu)

Le dashboard se charge et affiche les donnees en temps reel.

> **Note :** L'acces au dashboard necessite le groupe "Utilisateur Dashboard PdV" au minimum. Les responsables Point de Vente y ont acces automatiquement.

---

## 2. Comprendre les KPI

Les 8 cartes en haut du dashboard affichent les indicateurs principaux :

### Cartes de la journee

- **Sessions ouvertes** -- Nombre de sessions POS actuellement ouvertes. Permet de savoir combien de caisses sont operationnelles a l'instant T.
- **Commandes aujourd'hui** -- Nombre total de commandes enregistrees depuis minuit. Donne une idee du volume de la journee.
- **CA aujourd'hui** (en DH) -- Chiffre d'affaires cumule de la journee. Somme des montants totaux de toutes les commandes du jour.
- **Panier moyen** (en DH) -- Montant moyen par commande aujourd'hui. Calcule comme CA aujourd'hui divise par le nombre de commandes.

### Cartes du mois

- **CA ce mois** (en DH) -- Chiffre d'affaires cumule depuis le 1er du mois en cours.
- **Commandes ce mois** -- Nombre total de commandes depuis le 1er du mois.

### Cartes d'alerte

- **Retours aujourd'hui** -- Nombre de commandes dont le montant total est negatif (retours, avoirs). Permet de detecter un taux de retour anormal.
- **Clients servis** -- Nombre de clients distincts (partenaires) ayant passe au moins une commande aujourd'hui. Mesure la frequentation avec identification client.

### Interaction

Cliquer sur les cartes suivantes ouvre la **liste filtree** correspondante :

| Carte | Action au clic |
|---|---|
| Sessions ouvertes | Liste des sessions POS en etat "ouvert" |
| Commandes aujourd'hui | Liste des commandes POS du jour |
| CA ce mois / Commandes ce mois | Liste des commandes du mois en cours |
| Retours aujourd'hui | Liste des commandes du jour avec montant negatif |

---

## 3. Utiliser les filtres

### Ouvrir le panneau

Cliquer sur le bouton **Filtres** dans l'en-tete du dashboard. Un panneau apparait avec les options suivantes :

### Filtres disponibles

#### Date debut / Date fin
- Permet de restreindre les donnees a une **periode precise**
- Filtre sur la date de commande (`date_order`) des commandes POS
- Exemple : voir uniquement les commandes de mars 2026

#### Point de vente
- Liste deroulante contenant toutes les configurations POS existantes
- Permet de voir le dashboard **d'un magasin ou d'une caisse specifique**
- "-- Tous --" affiche les donnees de tous les points de vente

#### Caissier
- Liste deroulante contenant tous les utilisateurs ayant passe des commandes
- Permet de voir le dashboard **du point de vue d'un caissier**
- "-- Tous --" affiche les donnees de tous les caissiers

#### Jours graphique
- **7 jours** -- vue courte, ideale pour le suivi quotidien
- **14 jours** -- vue bi-hebdomadaire
- **30 jours** -- vue mensuelle

#### Periode stats
- Determine la periode pour le calcul des top produits, moyens de paiement et du resume affiche en haut du graphique ("30j: X cmd / Y DH")
- **7 jours** -- cette semaine
- **30 jours** -- ce mois (par defaut)
- **60 jours** -- 2 mois
- **90 jours** -- trimestre

### Appliquer les filtres

1. Configurer les filtres souhaites
2. Cliquer sur **Appliquer**
3. Le dashboard se recharge avec les donnees filtrees
4. Un **point bleu** apparait sur le bouton Filtres pour indiquer que des filtres sont actifs

### Reinitialiser

Cliquer sur **Reinitialiser** pour revenir aux valeurs par defaut et recharger toutes les donnees.

---

## 4. Configurer le rafraichissement automatique

### Depuis le dashboard

Le selecteur **Auto** dans l'en-tete permet de choisir l'intervalle :

| Option | Usage recommande |
|---|---|
| **Off** | Travail ponctuel, consultation rapide |
| **30 secondes** | Suivi en temps reel sur ecran de caisse |
| **1 minute** | Supervision active du magasin |
| **2 minutes** | Suivi regulier |
| **5 minutes** | Affichage permanent sur ecran mural ou back-office |

### Depuis la configuration

Le responsable peut definir l'intervalle par defaut dans la configuration (voir section 10).

### Rafraichissement manuel

Le bouton **Actualiser** (icone de rafraichissement) force un rechargement immediat a tout moment.

L'heure de la derniere mise a jour est affichee a gauche des controles.

---

## 5. Naviguer vers les commandes et sessions

### Depuis les cartes KPI

| Carte | Destination |
|---|---|
| **Sessions ouvertes** | Vue liste des sessions POS ouvertes |
| **Commandes aujourd'hui** | Vue liste des commandes du jour |
| **CA ce mois** | Vue liste des commandes depuis le 1er du mois |
| **Commandes ce mois** | Vue liste des commandes depuis le 1er du mois |
| **Retours aujourd'hui** | Vue liste des retours du jour (montant < 0) |

Depuis ces vues liste Odoo standard, vous pouvez trier, filtrer, regrouper, exporter, ou ouvrir chaque enregistrement en detail.

---

## 6. Lire le graphique du chiffre d'affaires

### Les barres

- Chaque barre represente un jour
- La hauteur indique le **chiffre d'affaires total** de ce jour-la
- La valeur exacte est affichee au-dessus de chaque barre
- La date est affichee en dessous (format jj/mm)

### Le resume

En haut a droite du graphique :
- **X cmd** -- nombre total de commandes sur la periode stats
- **Y DH** -- chiffre d'affaires total sur la periode stats

### Interpreter

- Des barres regulieres indiquent une activite commerciale stable
- Des barres a zero signalent des jours sans vente (fermeture, jour ferie, etc.)
- Une tendance a la hausse indique une progression des ventes
- Une chute soudaine peut signaler un probleme (caisse fermee, panne, etc.)
- Comparer les jours de semaine entre eux pour identifier les pics d'activite

---

## 7. Analyser les top produits

La section "Top produits" se trouve dans la colonne droite du dashboard :

### Lecture du tableau

| Colonne | Description |
|---|---|
| **#** | Rang du produit (les 3 premiers ont un badge dore) |
| **Produit** | Nom du produit |
| **Qte vendue** | Quantite totale vendue sur la periode |
| **CA** | Chiffre d'affaires genere par ce produit (en DH) |

### Parametres

- Le classement est base sur le CA (du plus eleve au plus faible)
- Le nombre de produits affiches depend du parametre **Limite top produits** (defaut : 10)
- La periode depend du filtre **Periode stats** (defaut : 30 jours)

### Utilisation

- Identifier les produits les plus rentables
- Detecter les produits phares de la semaine ou du mois
- Comparer les performances entre differents points de vente en utilisant le filtre POS

---

## 8. Analyser les moyens de paiement

La section "Moyens de paiement" se trouve dans la colonne gauche, sous le graphique :

### Lecture du tableau

| Colonne | Description |
|---|---|
| **Mode de paiement** | Nom du mode (Especes, Carte bancaire, Cheque, etc.) |
| **Montant** | Montant total encaisse par ce mode (en DH) |
| **% du total** | Part de ce mode dans le total des encaissements, avec barre visuelle |

### Utilisation

- Connaitre la repartition especes / carte / autres modes
- Verifier que les montants especes correspondent au contenu des caisses
- Identifier les tendances (augmentation des paiements par carte, etc.)
- Analyser par point de vente en combinant avec le filtre POS

---

## 9. Surveiller les sessions actives

La section "Sessions actives" se trouve dans la colonne droite, sous les top produits :

### Lecture du tableau

| Colonne | Description |
|---|---|
| **Session** | Identifiant de la session POS |
| **Caissier** | Utilisateur qui a ouvert la session |
| **Point de vente** | Configuration POS associee |
| **Ouverture** | Date et heure d'ouverture de la session |

### Utilisation

- Verifier quelles caisses sont operationnelles
- Identifier les sessions ouvertes depuis trop longtemps (oubli de cloture)
- Savoir quel caissier est sur quelle caisse
- Le compteur dans le titre indique le nombre total de sessions ouvertes

---

## 10. Configurer les parametres par defaut

> Reserve aux **Responsables Dashboard PdV** (ou Responsables Point de Vente par heritage)

### Acceder a la configuration

**Point de Vente > Configuration > Config. Dashboard**

### Creer une configuration

1. Cliquer sur **Nouveau**
2. Remplir les parametres :
   - **Jours graphique CA** -- nombre de jours par defaut dans le graphique (defaut : 7)
   - **Jours statistiques recentes** -- periode de calcul des top produits et moyens de paiement (defaut : 30)
   - **Limite top produits** -- combien de produits afficher dans le classement (defaut : 10)
   - **Rafraichissement auto** -- intervalle par defaut (Desactive / 30s / 1min / 2min / 5min)
   - **Societe** -- la societe concernee (visible uniquement en multi-societe)
3. Cliquer sur **Enregistrer**

### Multi-societe

Si vous gerez plusieurs societes, creez une configuration distincte pour chacune. Le dashboard chargera automatiquement la configuration correspondant a la societe active de l'utilisateur.

### Pas de configuration ?

Si aucune configuration n'existe pour la societe, le dashboard utilise les valeurs par defaut :
- 7 jours pour le graphique
- 30 jours pour les stats
- 10 produits dans le classement
- Pas d'auto-refresh

---

## 11. Droits d'acces

### Groupes dedies

Le module cree deux groupes dans la categorie **Dashboard Point de Vente** :

| Groupe | Droits |
|---|---|
| **Utilisateur Dashboard PdV** | Acces en lecture au dashboard et a la configuration |
| **Responsable Dashboard PdV** | Acces complet a la configuration (creation, modification, suppression) |

### Heritage automatique

- **Responsable Dashboard PdV** implique automatiquement **Utilisateur Dashboard PdV**
- **Responsable Point de Vente** (groupe standard Odoo POS) implique automatiquement **Responsable Dashboard PdV**

En pratique : tout manager POS a automatiquement acces complet au dashboard sans configuration supplementaire. Pour donner acces a un simple caissier, il suffit de lui attribuer le groupe "Utilisateur Dashboard PdV".

### Attribution des droits

1. Aller dans **Parametres > Utilisateurs**
2. Ouvrir la fiche de l'utilisateur
3. Dans la section **Dashboard Point de Vente**, selectionner le niveau d'acces :
   - *Vide* -- aucun acces au dashboard
   - **Utilisateur Dashboard PdV** -- acces en consultation
   - **Responsable Dashboard PdV** -- acces complet

---

## 12. Cas d'usage courants

### Suivi en temps reel en magasin

1. Ouvrir le dashboard sur un ecran dedie (back-office ou tablette)
2. Configurer l'auto-refresh a **30 secondes** ou **1 minute**
3. Surveiller les KPI en continu : CA, commandes, sessions ouvertes
4. Le dashboard se met a jour automatiquement sans intervention

### Analyse de caisse

1. Ouvrir les filtres
2. Selectionner le **caissier** dans la liste deroulante
3. Cliquer sur **Appliquer**
4. Le dashboard affiche uniquement les donnees de ce caissier
5. Verifier le CA, le nombre de commandes et le panier moyen
6. Consulter les moyens de paiement pour verifier les encaissements

### Bilan journalier

1. Ouvrir le dashboard en fin de journee
2. Consulter les KPI du jour : CA, commandes, retours, clients servis
3. Verifier les moyens de paiement pour preparer la cloture de caisse
4. Consulter les top produits pour identifier les meilleures ventes du jour (mettre la periode stats a 1 jour si besoin)
5. Verifier qu'aucune session n'est restee ouverte par erreur

### Comparaison de points de vente

1. Ouvrir les filtres
2. Selectionner un **point de vente** dans la liste deroulante
3. Cliquer sur **Appliquer**
4. Noter les KPI affiches (CA, commandes, panier moyen)
5. Repeter l'operation pour un autre point de vente
6. Comparer les performances entre les deux magasins

### Analyse mensuelle

1. Ouvrir les filtres
2. Definir **Date debut** = 01/03/2026, **Date fin** = 31/03/2026
3. Mettre **Jours graphique** a 30
4. Mettre **Periode stats** a 30 jours
5. Cliquer sur **Appliquer**
6. Le dashboard affiche la vue complete du mois de mars
7. Analyser le graphique pour identifier les tendances et les jours forts

### Suivi des retours

1. Surveiller la carte **Retours aujourd'hui** au fil de la journee
2. Si le chiffre augmente, cliquer sur la carte pour voir la liste des retours
3. Examiner chaque retour pour verifier sa legitimite
4. Utiliser le filtre caissier pour identifier si les retours sont concentres sur une caisse

---

## Raccourcis et interactions

Le dashboard utilise les interactions souris standard d'Odoo :
- **Clic** sur une carte KPI -- ouvre la liste filtree correspondante
- **Clic** sur le bouton Filtres -- ouvre/ferme le panneau de filtres
- **F5** ou bouton Actualiser -- rafraichir les donnees
- **Selecteur auto-refresh** -- active le rechargement periodique
