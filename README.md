# Tableau de bord Point de Vente (POS Dashboard)

Module Odoo 18 — Dashboard POS dynamique avec KPI en temps reel, filtres interactifs et configuration par societe.

**Auteur :** SOPROMER  
**Version :** 18.0.2.0.0  
**Licence :** LGPL-3  
**Dependance :** `point_of_sale`

---

## Fonctionnalites

### KPI en temps reel (8 indicateurs)

| Indicateur | Description |
|---|---|
| **Sessions ouvertes** | Nombre de sessions POS actuellement ouvertes |
| **Commandes aujourd'hui** | Nombre total de commandes passees aujourd'hui |
| **CA aujourd'hui** | Chiffre d'affaires cumule de la journee en cours |
| **Panier moyen** | Montant moyen par commande aujourd'hui |
| **CA ce mois** | Chiffre d'affaires cumule du mois en cours |
| **Commandes ce mois** | Nombre total de commandes du mois en cours |
| **Retours** | Nombre de retours (commandes a montant negatif) aujourd'hui |
| **Clients servis** | Nombre de clients distincts servis aujourd'hui |

Chaque carte KPI est **cliquable** et ouvre la liste filtree des enregistrements correspondants (commandes, sessions ou retours).

### Graphique du chiffre d'affaires quotidien

- Graphique en barres du CA quotidien (montant total par jour)
- Periode configurable : **7, 14 ou 30 jours**
- Resume en haut a droite : total commandes et CA sur la periode stats

### Top produits

- Classement des produits les plus vendus par chiffre d'affaires
- Colonnes : Rang, Produit, Quantite vendue, CA
- Mise en evidence des 3 premiers (badge dore)
- Nombre de produits configurable (par defaut : 10)
- Periode basee sur le filtre "Periode stats"

### Moyens de paiement

- Repartition des paiements par mode (especes, carte bancaire, cheque, etc.)
- Colonnes : Mode de paiement, Montant, % du total
- Barre de progression visuelle pour chaque pourcentage
- Basee sur la periode stats configuree

### Sessions actives

- Liste des sessions POS actuellement ouvertes
- Colonnes : Session, Caissier, Point de vente, Date d'ouverture
- Nombre de sessions affiche dans le titre de la section

---

## Filtres dynamiques

Le panneau de filtres s'ouvre via le bouton **Filtres** dans l'en-tete du dashboard.

| Filtre | Description |
|---|---|
| **Date debut** | Filtrer les commandes a partir de cette date |
| **Date fin** | Filtrer les commandes jusqu'a cette date |
| **Point de vente** | Filtrer par configuration POS (liste dynamique) |
| **Caissier** | Filtrer par utilisateur ayant passe des commandes (liste dynamique) |
| **Jours graphique** | Nombre de jours affiches dans le graphique (7/14/30) |
| **Periode stats** | Periode pour les statistiques recentes et top produits (7/30/60/90 jours) |

- Un **point bleu** apparait sur le bouton Filtres quand des filtres sont actifs
- Bouton **Appliquer** pour lancer la recherche
- Bouton **Reinitialiser** pour revenir aux valeurs par defaut

---

## Rafraichissement automatique

Le selecteur dans l'en-tete permet de configurer le rafraichissement automatique :

- **Off** -- rafraichissement manuel uniquement
- **30 secondes**
- **1 minute**
- **2 minutes**
- **5 minutes**

L'heure de la derniere mise a jour est affichee a cote des controles.

---

## Installation

### Prerequis

- Odoo 18 Community ou Enterprise
- Module `point_of_sale` (Point de Vente) installe et configure

### Etapes

1. Copier le dossier `pos_dashboard` dans le repertoire des addons personnalises :

   ```
   cp -r pos_dashboard /chemin/vers/odoo18/custom-addons/
   ```

2. Mettre a jour la liste des modules dans Odoo :

   **Applications > Mettre a jour la liste des applications**

3. Rechercher et installer le module :

   **Applications > Rechercher "Tableau de bord Point de Vente" > Installer**

4. Ou via la ligne de commande :

   ```bash
   python odoo-bin -d ma_base -u pos_dashboard --stop-after-init
   ```

### Mise a jour

Pour mettre a jour apres modification :

```bash
python odoo-bin -d ma_base -u pos_dashboard --stop-after-init
```

---

## Configuration

### Acceder a la configuration

**Point de Vente > Configuration > Config. Dashboard**

> Seuls les **Responsables Dashboard PdV** (groupe `pos_dashboard.group_pos_dashboard_manager`) peuvent modifier la configuration.

### Parametres disponibles

| Parametre | Par defaut | Description |
|---|---|---|
| Jours graphique CA | 7 | Nombre de jours dans le graphique en barres |
| Jours statistiques recentes | 30 | Periode pour le calcul des top produits et moyens de paiement |
| Limite top produits | 10 | Nombre de produits affiches dans le classement |
| Rafraichissement auto | Desactive | Intervalle de mise a jour automatique |
| Societe | Societe courante | Configuration par societe (multi-societe) |

### Multi-societe

Chaque societe peut avoir sa propre configuration. Le dashboard charge automatiquement la configuration de la societe active de l'utilisateur.

---

## Droits d'acces

### Groupes dedies

Le module definit ses propres groupes de securite dans la categorie **Dashboard Point de Vente** :

| Groupe | Description |
|---|---|
| **Utilisateur Dashboard PdV** | Acces en lecture au dashboard et a la configuration |
| **Responsable Dashboard PdV** | Acces complet (lecture, creation, modification, suppression de la configuration) |

### Heritage automatique

- Le groupe **Responsable Dashboard PdV** implique automatiquement le groupe **Utilisateur Dashboard PdV**
- Le groupe **Responsable Point de Vente** (`point_of_sale.group_pos_manager`) implique automatiquement le groupe **Responsable Dashboard PdV**

Ainsi, tout responsable POS a automatiquement acces complet au dashboard sans configuration supplementaire.

### Matrice des droits

| Groupe | Voir le dashboard | Voir la config | Modifier la config |
|---|---|---|---|
| Utilisateur Dashboard PdV | Oui | Oui (lecture) | Non |
| Responsable Dashboard PdV | Oui | Oui | Oui |
| Responsable Point de Vente | Oui | Oui | Oui (herite) |

---

## Architecture technique

```
pos_dashboard/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   └── main.py                  # Endpoints RPC
├── models/
│   ├── __init__.py
│   └── pos_dashboard_config.py  # Modele de configuration
├── security/
│   ├── ir.model.access.csv      # Droits d'acces
│   └── pos_dashboard_groups.xml # Groupes de securite
├── static/src/
│   ├── css/pos_dashboard.css    # Styles
│   ├── js/pos_dashboard.js      # Composant OWL
│   └── xml/pos_dashboard.xml    # Template OWL
├── views/
│   ├── pos_dashboard_views.xml        # Menu + Action client
│   └── pos_dashboard_config_views.xml # Vues configuration
├── doc/
│   └── guide_utilisation.md     # Guide detaille
└── README.md
```

### Endpoints API

| Route | Type | Description |
|---|---|---|
| `/pos_dashboard/data` | JSON (POST) | Donnees du dashboard avec filtres |
| `/pos_dashboard/filters_data` | JSON (POST) | Listes pour les selecteurs de filtres (points de vente, caissiers) |

### Parametres de `/pos_dashboard/data`

```json
{
  "filters": {
    "chart_days": 7,
    "recent_days": 30,
    "top_products_limit": 10,
    "date_from": "2026-01-01",
    "date_to": "2026-03-31",
    "pos_config_id": 2,
    "user_id": 5
  }
}
```

### Reponse de `/pos_dashboard/data`

```json
{
  "open_sessions_count": 3,
  "orders_today_count": 47,
  "ca_today": 12540.50,
  "avg_basket": 266.82,
  "ca_month": 89320.00,
  "orders_month_count": 312,
  "returns_today_count": 1,
  "distinct_partners": 28,
  "daily_ca": [{"date": "27/03", "total": 1850.00, "count": 12}],
  "total_orders_recent": 245,
  "total_ca_recent": 67800.00,
  "top_products": [{"product": "Produit A", "qty": 150, "ca": 4500.00}],
  "payment_methods": [{"method": "Especes", "amount": 35000.00, "pct": 52.3}],
  "active_sessions": [{"name": "POS/001", "user_id": [2, "Admin"], "config_id": [1, "Magasin Principal"], "start_at": "2026-04-03 08:00:00"}],
  "config": {"chart_days": 7, "recent_days": 30, "top_products_limit": 10, "auto_refresh_interval": 0}
}
```

### Reponse de `/pos_dashboard/filters_data`

```json
{
  "pos_configs": [{"id": 1, "name": "Magasin Principal"}, {"id": 2, "name": "Magasin Annexe"}],
  "users": [{"id": 2, "name": "Admin"}, {"id": 5, "name": "Caissier 1"}]
}
```

### Technologies

- **Frontend :** OWL 2 (framework reactif Odoo), Bootstrap 5
- **Backend :** Odoo 18 HTTP Controllers, ORM
- **Modeles interroges :** `pos.order`, `pos.session`, `pos.payment`, `pos.order.line`, `pos.config`

---

## Depannage

| Probleme | Solution |
|---|---|
| Le dashboard ne s'affiche pas | Verifier que le module `point_of_sale` est installe. Vider le cache navigateur (Ctrl+Maj+Suppr). |
| Erreur "Acces non autorise au dashboard PdV" | Verifier que l'utilisateur a le groupe "Utilisateur Dashboard PdV" au minimum. |
| Les filtres point de vente / caissier sont vides | Normal si aucune commande POS n'existe encore dans le systeme. |
| L'auto-refresh ne fonctionne pas | Verifier que la valeur est differente de "Off" dans le selecteur. |
| Les donnees ne correspondent pas | Cliquer sur "Actualiser" pour forcer un rechargement. Verifier les filtres actifs (point bleu). |
| Le menu "Config. Dashboard" n'apparait pas | Ce menu est reserve aux Responsables Dashboard PdV. Verifier les droits de l'utilisateur. |
| Les montants affichent 0 | Verifier qu'il existe des commandes POS dans la periode concernee. Verifier les filtres de date. |

---

## Licence

Ce module est distribue sous licence [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.html).
