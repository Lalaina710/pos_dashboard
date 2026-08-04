/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

class PosDashboard extends Component {
    static template = "pos_dashboard.PosDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            data: {
                daily_ca: [],
                top_products: [],
                ca_by_pos: [],
                compare_months: null,
                budget_vs_actual: null,
                active_sessions: [],
            },
            // Filtres dynamiques
            filters: {
                chart_days: 7,
                recent_days: 30,
                top_products_limit: 10,
                date_from: '',
                date_to: '',
                pos_config_id: 0,
                user_id: 0,
            },
            // Données des listes déroulantes
            pos_configs: [],
            users: [],
            // Panneau filtres visible/masqué
            showFilters: false,
            // Auto-refresh
            autoRefreshInterval: 0,
            // Dernière mise à jour
            lastUpdate: '',
            // Erreur de chargement (distincte d'une periode sans vente)
            loadError: '',
            // Dark mode
            darkMode: localStorage.getItem('pos_dashboard_dark') === 'true',
        });
        this._refreshTimer = null;

        onWillStart(async () => {
            await this.loadFiltersData();
            await this.loadConfig();
            await this.loadData();
        });

        onMounted(() => {
            this._startAutoRefresh();
        });

        onWillUnmount(() => {
            this._stopAutoRefresh();
        });
    }

    async loadConfig() {
        try {
            const config = await this.orm.call(
                'pos.dashboard.config', 'get_config', []
            );
            this.state.filters.chart_days = config.chart_days;
            this.state.filters.recent_days = config.recent_days;
            this.state.filters.top_products_limit = config.top_products_limit;
            this.state.autoRefreshInterval = config.auto_refresh_interval;
        } catch (e) {
            console.warn("Config non disponible, valeurs par défaut utilisées");
        }
    }

    async loadFiltersData() {
        try {
            const data = await rpc("/pos_dashboard/filters_data", {});
            this.state.pos_configs = data.pos_configs || [];
            this.state.users = data.users || [];
        } catch (e) {
            console.warn("Impossible de charger les filtres:", e);
        }
    }

    async loadData() {
        this.state.loading = true;
        this.state.loadError = '';
        try {
            const filters = { ...this.state.filters };
            // Nettoyer les filtres vides
            if (!filters.pos_config_id) delete filters.pos_config_id;
            if (!filters.user_id) delete filters.user_id;
            if (!filters.date_from) delete filters.date_from;
            if (!filters.date_to) delete filters.date_to;

            const data = await rpc("/pos_dashboard/data", { filters });
            // Un payload absent ou incomplet (403 du controleur, 500, proxy qui
            // renvoie du vide) doit etre traite comme une ERREUR. Sans ce test,
            // le catch ci-dessous remplissait des zeros et l'ecran devenait
            // indiscernable d'une periode sans vente — le symptome meme que la
            // correction cote /direction devait eliminer.
            if (!data || data.open_sessions_count === undefined) {
                throw new Error("Payload incomplet");
            }
            this.state.data = data;
            this.state.lastUpdate = new Date().toLocaleTimeString("fr-FR");
        } catch (e) {
            console.error("POS Dashboard error:", e);
            this.state.loadError = "Données PdV indisponibles (accès refusé ou "
                + "erreur serveur). Ce n'est pas une période sans vente.";
            this.state.data = {
                open_sessions_count: 0,
                orders_today_count: 0,
                ca_today: 0,
                avg_basket: 0,
                ca_month: 0,
                qty_month: 0,
                orders_month_count: 0,
                returns_today_count: 0,
                distinct_partners: 0,
                daily_ca: [],
                chart_period: '',
                total_orders_recent: 0,
                total_ca_recent: 0,
                top_products: [],
                top_products_period: '',
                ca_by_pos: [],
                compare_months: null,
                budget_vs_actual: null,
                active_sessions: [],
            };
        }
        this.state.loading = false;
    }

    // --- Gestion des filtres ---

    toggleFilters() {
        this.state.showFilters = !this.state.showFilters;
    }

    onFilterChange(field, ev) {
        const value = ev.target.value;
        if (['chart_days', 'recent_days', 'top_products_limit',
             'pos_config_id', 'user_id'].includes(field)) {
            this.state.filters[field] = parseInt(value) || 0;
        } else {
            this.state.filters[field] = value;
        }
    }

    applyFilters() {
        this.loadData();
    }

    toggleTheme() {
        this.state.darkMode = !this.state.darkMode;
        localStorage.setItem('pos_dashboard_dark', this.state.darkMode);
    }

    resetFilters() {
        this.state.filters = {
            chart_days: 7,
            recent_days: 30,
            top_products_limit: 10,
            date_from: '',
            date_to: '',
            pos_config_id: 0,
            user_id: 0,
        };
        this.loadData();
    }

    // --- Auto-refresh ---

    onRefreshIntervalChange(ev) {
        this.state.autoRefreshInterval = parseInt(ev.target.value) || 0;
        this._startAutoRefresh();
    }

    _startAutoRefresh() {
        this._stopAutoRefresh();
        const interval = this.state.autoRefreshInterval;
        if (interval > 0) {
            this._refreshTimer = setInterval(() => this.loadData(), interval * 1000);
        }
    }

    _stopAutoRefresh() {
        if (this._refreshTimer) {
            clearInterval(this._refreshTimer);
            this._refreshTimer = null;
        }
    }

    // --- Formatage et helpers ---

    formatCurrency(amount) {
        if (!amount && amount !== 0) return "0,00";
        return Number(amount).toLocaleString("fr-FR", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    formatQty(qty) {
        if (!qty && qty !== 0) return "0,000";
        return Number(qty).toLocaleString("fr-FR", {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3,
        });
    }

    // Modified by: odoo-frontend agent — 2026-07-28 — Colonne PdV principal top produits
    formatShare(share) {
        if (!share) return "";
        return Number(share).toLocaleString("fr-FR", {
            maximumFractionDigits: 1,
        }) + "%";
    }

    // Une part > 100 % n'est pas une erreur de calcul. Cause la plus frequente :
    // retours sur un autre PdV. Non plafonnee, mise en evidence.
    shareTitle(share) {
        if (share > 100) {
            return "Part supérieure au total net du produit "
                + "(le plus souvent : retours sur un autre PdV)";
        }
        return undefined;
    }

    formatQtyMonth(qty) {
        if (!qty && qty !== 0) return "0";
        return Number(qty).toLocaleString("fr-FR", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2,
        });
    }

    getBarHeight(total) {
        const maxTotal = Math.max(
            ...this.state.data.daily_ca.map((d) => d.total),
            1
        );
        return Math.max((total / maxTotal) * 150, 4);
    }

    // --- Graphiques groupes : comparatif M/M-1 et CA vs budget ---
    // Modified by: odoo-frontend agent — 2026-07-31
    //
    // Meme rendu que la page /direction, obtenu autrement : ici le template OWL
    // pose la structure et ces helpers ne calculent que des nombres. La regle
    // de densite est DETERMINISTE des deux cotes (un libelle de jour tous les 5,
    // categories toujours affichees et tronquees en CSS) — c'est ce qui garantit
    // que les deux ecrans montrent exactement les memes libelles, alors que
    // /direction dispose d'un moteur de mesure de texte et pas ce widget.
    // Avec deux series, aucune valeur ne tient au-dessus des barres : les
    // valeurs exactes sont dans l'infobulle de groupe et la ligne de synthese.
    // Helpers plutot que des expressions JS dans le template : le compilateur
    // d'expressions d'OWL reecrit les identifiants du template, on ne lui
    // confie ni `typeof`, ni litteral objet, ni acces optionnel.
    isNum(value) {
        return typeof value === "number" && !Number.isNaN(value);
    }

    // Titre construit en JS plutot qu'ecrit dans le template.
    // Modified by: odoo-frontend agent — 2026-08-02
    // QWeb extrait CHAQUE noeud de texte separement pour la traduction : dans
    // `Top <t t-esc="..."/> produits`, "Top" formait a lui seul un terme
    // traduisible, et sa traduction francaise dans le catalogue Odoo est
    // "Haut" — l'ecran affichait "Haut 10 produits". Un t-esc ne produit aucun
    // noeud traduisible : la segmentation ne peut plus s'appliquer, quel que
    // soit le catalogue de langue installe.
    topProductsTitle() {
        return `Top ${this.state.filters.top_products_limit} produits`;
    }

    comparePeriodLabel() {
        const cmp = this.state.data.compare_months;
        return cmp ? cmp.period_label || "" : "";
    }

    budgetPeriodLabel() {
        const budget = this.state.data.budget_vs_actual;
        return budget ? budget.period_label || "" : "";
    }

    // --- Etat du mois de reference ---
    // Modified by: odoo-frontend agent — 2026-08-03
    //
    // Etat replie en un seul mot a partir des DEUX booleens que le serveur
    // affirme : 'past' (clos), 'current' (en cours), 'future' (a venir). Le
    // frontend ne le deduit jamais de dates — la regle d'ancrage (le mois ou
    // tombe la FIN de la periode filtree) vit cote serveur, et deux ecrans
    // consomment ce meme payload : la dupliquer ici la ferait deriver a la
    // premiere correction.
    //
    // Deux booleens et non un seul : un mois A VENIR n'est ni clos ni en cours,
    // et c'est un cas atteignable (le filtre de date accepte une periode
    // future). Les deux a faux = mois en cours.
    //
    // L'ordre des tests fait foi : 'past' l'emporterait sur une combinaison
    // contradictoire que le serveur n'emet pas — c'est le repli le plus sur, il
    // n'annonce aucun rythme.
    //
    // Un payload anterieur au contrat n'a aucune des deux cles et retombe sur
    // 'current', qui est le comportement historique — meme discipline de garde
    // d'ecart de deploiement que has_budget / has_any_budget. Identique, mot
    // pour mot, a monthState() dans direction_dashboard.js.
    monthState(primary, fallback) {
        for (const o of [primary, fallback]) {
            if (!o) {
                continue;
            }
            if (o.is_closed_month === true) return "past";
            if (o.is_future_month === true) return "future";
            if (o.is_closed_month === false || o.is_future_month === false) {
                return "current";
            }
        }
        return "current";
    }

    // Etat du mois du COMPARATIF : ce bloc porte sa propre cle, il ne retombe
    // pas sur celle du budget.
    compareMonthState() {
        return this.monthState(this.state.data.compare_months, null);
    }

    // Etat du mois du BUDGET. Les deux blocs sont ancres sur le MEME mois par
    // construction : on prefere la cle du bloc budget et on retombe sur celle
    // du comparatif.
    budgetMonthState() {
        return this.monthState(
            this.state.data.budget_vs_actual, this.state.data.compare_months);
    }

    // Libelle du total du mois de reference dans le comparatif. Le template
    // echappe (t-esc), ces deux methodes renvoient donc du texte brut.
    //   - en cours : « juin 2026 à date (12 j) »     — inchange
    //   - clos     : « mai 2026 (mois complet) »     — 100 % ecoule, pas « a date »
    //   - a venir  : « juillet 2026 (mois à venir) » — 0 j, le total vaut 0
    cmpCurrentLabel(cmp) {
        const state = this.compareMonthState();
        if (state === "past") return cmp.current_label + " (mois complet)";
        if (state === "future") return cmp.current_label + " (mois à venir)";
        return cmp.current_label + " à date (" + cmp.elapsed_days + " j)";
    }

    // Libelle de la BASE de comparaison — les memes jours du mois precedent.
    //   - en cours : « mai 2026 — mêmes 12 jours »  — inchange, le compte est exact
    //   - clos     : « avril 2026 — jours équivalents »
    //   - a venir  : « août 2026 — aucun jour comparé »
    //
    // Le compte de jours DISPARAIT sur un mois clos, il ne peut pas y etre
    // juste : elapsed_days y vaut la longueur du mois de REFERENCE, pas celle
    // du mois compare. « avril 2026 — mêmes 31 jours » sur un mois qui en
    // compte 30 est donc une phrase fausse — tolerable tant qu'elle ne
    // s'affichait qu'au dernier jour du mois, plus du tout depuis que filtrer
    // un mois passe la rend permanente. « jours équivalents » dit la seule
    // chose vraie dans tous les cas : on compare les memes NUMEROS de jour, et
    // la note du serveur precise deja qu'un jour sans equivalent n'est pas
    // trace.
    //
    // Aucun calcul cote client : le libelle cesse d'annoncer un compte plutot
    // que d'en annoncer un autre.
    //
    // Sur un mois a venir il n'y a aucun jour compare : « mêmes 0 jours » se
    // lirait comme un bug, alors que le total de 0 est exact.
    // Modified by: odoo-frontend agent — 2026-08-04 — compte de jours plus long que M-1
    // Le compte disparait AUSSI sur un mois en cours des qu'il ne peut pas
    // decrire les deux mois : elapsed_days est un jour du mois de REFERENCE, et
    // le mois precedent peut etre plus court. Le 31/03 annonçait « février 2026
    // — mêmes 31 jours » sur un mois qui en compte 28 ; les 29, 30 et 31/05,
    // « avril 2026 — mêmes 31 jours » sur un mois de 30. Meme mensonge que sur
    // un mois clos, meme reponse — et pas un Math.min : plafonner le compte
    // reparerait le libelle de la BASE tout en laissant celui du mois de
    // reference (« à date (31 j) ») annoncer un autre nombre, soit deux comptes
    // differents pour une seule comparaison.
    // Identique, mot pour mot, a cmpBasisLabel() dans direction_dashboard.js.
    cmpBasisLabel(cmp) {
        const state = this.compareMonthState();
        if (state === "past") return cmp.previous_label + " — jours équivalents";
        if (state === "future") return cmp.previous_label + " — aucun jour comparé";
        if (!this.cmpDayCountFits(cmp)) {
            return cmp.previous_label + " — jours équivalents";
        }
        return cmp.previous_label + " — mêmes " + cmp.elapsed_days + " jours";
    }

    // Le compte de jours ecoules du mois de reference decrit-il aussi le mois
    // precedent ? previous_month_days ABSENT = backend anterieur au contrat : on
    // garde le rendu historique plutot que d'effacer un compte exact dans le cas
    // courant — meme discipline de garde d'ecart de deploiement que has_budget.
    cmpDayCountFits(cmp) {
        if (cmp.previous_month_days === undefined
            || cmp.previous_month_days === null) {
            return true;
        }
        return cmp.elapsed_days <= cmp.previous_month_days;
    }

    // Modified by: odoo-frontend agent — 2026-08-04 — « complet » sur un mois en cours
    // Le total de reference de fin de mois porte sur le mois ENTIER — sauf quand
    // le mois precedent est le mois EN COURS, cas atteignable des que le filtre
    // vise un mois futur : avec date_to au 15/09 un 3 aout, le mois de reference
    // est septembre et son precedent est aout, en cours. « août 2026 complet »
    // s'affichait alors a cote de trois jours de chiffre d'affaires, pendant que
    // la note du serveur disait juste en dessous que le jour en cours est partiel.
    //
    // Aucun compte de jours dans le libelle « à date » : les jours ecoules du
    // mois EN COURS ne sont pas au contrat ici (elapsed_days decrit le mois de
    // reference, qui est un AUTRE mois).
    //
    // TROISIEME cas, trouve en executant le rendu et non signale : quand le mois
    // de reference est A VENIR, son precedent ne peut jamais etre clos — il est
    // soit le mois en cours, soit lui aussi a venir. Filtrer jusqu'au 15/10 un
    // 3 aout donne M = octobre et M-1 = septembre, et l'ecran affichait
    // « septembre 2026 complet — 0,00 » : un mois entier a zero, pour un mois qui
    // n'a pas commence.
    //
    // Le second test porte sur `false` EXPLICITE, pas sur l'absence : avec un
    // backend qui annonce deja is_future_month mais pas encore
    // previous_is_current_month, on ne peut pas distinguer les deux cas, et
    // « mois à venir » colle a un total non nul serait pire que « complet ». La
    // cle absente garde donc le rendu historique.
    // Identique, mot pour mot, a cmpPreviousFullLabel() dans direction_dashboard.js.
    cmpPreviousFullLabel(cmp) {
        if (cmp.previous_is_current_month === true) {
            return cmp.previous_label + " à date";
        }
        if (this.compareMonthState() === "future"
            && cmp.previous_is_current_month === false) {
            return cmp.previous_label + " (mois à venir)";
        }
        return cmp.previous_label + " complet";
    }

    // --- Badge d'ecart : le sens ancre dans du texte ---
    // Modified by: odoo-frontend agent — 2026-08-04
    // La FLECHE etait le seul porteur du SENS : elle dit qu'on monte ou qu'on
    // descend, jamais lequel des deux mois le fait. Le lecteur devait le deduire
    // d'un ordre de mots — et l'ecran en presentait trois (l'en-tete, les
    // chiffres de synthese, les barres), dont un a l'envers. Le libelle explicite
    // ne se deduit d'aucun ordre : il NOMME le mois qui evolue puis sa reference.
    // Textes identiques, mot pour mot, a deltaBadge() / deltaTitle() dans
    // direction_dashboard.js.

    // Les deux mois compares, NOMMES dans le sens du calcul : le mois de
    // reference d'abord, sa base ensuite. La source en est le serveur
    // (delta_label) — les deux ecrans consomment le meme payload, deux
    // formulations finiraient par diverger.
    //
    // delta_label est TOUJOURS une chaine non vide des que compare_months existe,
    // y compris quand delta_pct est nul : il nomme le sens de la mesure, il
    // n'affirme pas qu'il y en a une. Il ne peut donc pas servir de test
    // d'existence du badge — c'est isNum(delta_pct) qui tranche.
    //
    // A defaut (JS servi face a un serveur anterieur au contrat) on compose des
    // deux libelles deja au contrat, A L'IDENTIQUE sur les deux ecrans et mot
    // pour mot comme le serveur : l'ancrage du sens est precisement ce qui
    // manquait, mieux vaut une phrase composee des memes mots que pas de phrase
    // du tout. Ce repli n'est atteignable qu'en deploiement partiel.
    cmpEvolutionLabel(cmp) {
        if (cmp.delta_label) {
            return cmp.delta_label;
        }
        if (cmp.current_label && cmp.previous_label) {
            return cmp.current_label + " par rapport à " + cmp.previous_label;
        }
        return "";
    }

    cmpDeltaClass(cmp) {
        if (!this.isNum(cmp.delta_pct)) return "cmp-delta-na";
        return cmp.delta_pct >= 0 ? "cmp-delta-up" : "cmp-delta-down";
    }

    cmpDeltaText(cmp) {
        if (!this.isNum(cmp.delta_pct)) return "—";
        return (cmp.delta_pct >= 0 ? "▲ +" : "▼ ")
            + this.formatPct(cmp.delta_pct) + " %";
    }

    // Le taux est repete apres l'evolution nommee : role="img" fait lire le
    // libelle A LA PLACE du contenu du badge, et une evolution sans sa valeur
    // n'apprendrait rien de plus que la fleche qu'elle remplace.
    //
    // Taux absent (total du mois precedent nul) : le badge affiche « — », qui ne
    // veut rien dire lu a voix haute. Le libelle dit alors pourquoi il n'y a pas
    // de chiffre — meme traitement que « — » et « s. o. » dans le tableau budget.
    //
    // `false` et non "" quand il n'y a rien a dire : OWL retire alors l'attribut
    // (meme convention que shareTitle()), le badge est rendu exactement comme
    // avant — une garde d'ecart de deploiement ne doit rien changer de visible.
    cmpDeltaTitle(cmp) {
        const evolution = this.cmpEvolutionLabel(cmp);
        if (!evolution) return false;
        if (!this.isNum(cmp.delta_pct)) {
            return evolution + " : évolution non calculable";
        }
        return evolution + " : " + (cmp.delta_pct >= 0 ? "+" : "")
            + this.formatPct(cmp.delta_pct) + " %";
    }

    // Sans role, un aria-label pose sur un <span> est ignore par une partie des
    // lecteurs d'ecran ; il n'est donc pose qu'avec lui, et disparait avec lui.
    cmpDeltaRole(cmp) {
        return this.cmpDeltaTitle(cmp) ? "img" : false;
    }

    cmpScaleMax(rows, keys) {
        let max = 0;
        for (const row of rows || []) {
            for (const key of keys) {
                if (typeof row[key] === "number" && row[key] > max) {
                    max = row[key];
                }
            }
        }
        return max || 1;
    }

    // Enveloppes sans argument : le template n'a ainsi aucun litteral tableau a
    // faire compiler par OWL (cf. isNum plus haut). Echelle commune aux deux
    // series — deux echelles independantes rendraient la comparaison fausse.
    compareScaleMax() {
        const cmp = this.state.data.compare_months;
        return this.cmpScaleMax(cmp ? cmp.days : [], ["current", "previous"]);
    }

    cmpBarHeight(value, max) {
        if (typeof value !== "number") {
            return 0;
        }
        return Math.max(Math.round((value / (max || 1)) * 150), value > 0 ? 4 : 2);
    }

    // Valeur abregee — meme regle que fmtChartCompact() de direction_dashboard.
    formatCompact(value) {
        const n = Number(value) || 0;
        const a = Math.abs(n);
        const opts = { minimumFractionDigits: 1, maximumFractionDigits: 1 };
        if (a >= 1e9) return (n / 1e9).toLocaleString("fr-FR", opts) + " Md";
        if (a >= 1e6) return (n / 1e6).toLocaleString("fr-FR", opts) + " M";
        if (a >= 1e4) return (n / 1e3).toLocaleString("fr-FR", opts) + " k";
        return this.formatCurrency(n);
    }

    formatPct(value, digits = 1) {
        if (value === null || value === undefined) {
            return "—";
        }
        return Number(value).toLocaleString("fr-FR", { maximumFractionDigits: digits });
    }

    // Un libelle tous les 5 jours + les deux bornes : reperes naturels d'un axe
    // 1..31, stables quelle que soit la largeur.
    cmpShowDay(day, total) {
        return day === 1 || day === total || day % 5 === 0;
    }

    // Un tick sur deux est "mineur" : sous 768px, 31 tranches ne laissent qu'une
    // dizaine de pixels par groupe et les libelles se chevauchent. Le CSS masque
    // les mineurs a cette largeur. Meme regle que dans direction_dashboard.js.
    cmpDayLabelClass(day, total) {
        if (!this.cmpShowDay(day, total) || day === 1 || day === total) {
            return "bar-label";
        }
        return day % 10 === 0 ? "bar-label" : "bar-label cmp-tick-minor";
    }

    // Texte identique, mot pour mot, a celui produit par groupedBarChart() dans
    // direction_dashboard.js — y compris l'ordre des series, qui suit l'ordre
    // des barres (M-1 puis M) et non celui des chiffres de synthese.
    cmpDayTitle(day, compare) {
        const parts = [`Jour ${day.day}`];
        parts.push(`${compare.previous_label} : ` + (
            typeof day.previous === "number"
                ? this.formatCurrency(day.previous)
                : "non applicable"
        ));
        parts.push(`${compare.current_label} : ` + (
            typeof day.current === "number"
                ? this.formatCurrency(day.current)
                : "non applicable"
        ));
        if (typeof day.current === "number" && typeof day.previous === "number"
            && day.previous) {
            const pct = ((day.current - day.previous) / day.previous) * 100;
            parts.push(`écart : ${pct >= 0 ? "+" : ""}${this.formatPct(pct)} %`);
        }
        return parts.join(" · ");
    }

    // --- CA realise vs budget : jauge d'atteinte, une ligne par PdV ---
    // Modified by: odoo-frontend agent — 2026-08-02
    // Textes identiques, mot pour mot, a ceux produits par direction_dashboard.js :
    // les deux ecrans rendent le meme payload.

    // --- CA realise vs budget : jauge, une ligne par PdV ---
    // Modified by: odoo-frontend agent — 2026-08-02
    //
    // DEUX informations par jauge SUR UN MOIS EN COURS, et c'est delibere : le
    // CHIFFRE est l'avancement dans le budget du MOIS, la COULEUR est le rythme
    // (realise rapporte au budget PRORATISE a date). L'avancement seul
    // afficherait 40 % en rouge le 12 du mois pour un PdV dans les temps ; le
    // rythme seul ferait disparaitre la progression vers l'objectif mensuel. La
    // legende sous le tableau, calculee cote serveur, explique les deux.
    //
    // Modified by: odoo-frontend agent — 2026-08-03 — mois clos / mois a venir
    // Sur un mois CLOS les deux se confondent : le mois est ecoule a 100 %, donc
    // budget_todate == budget_month et pct_todate == pct_month. Continuer
    // d'afficher un « rythme » laisserait croire a un prorata qui n'a plus lieu
    // d'etre, et « a date » a une date d'arret qui n'existe pas. Le chiffre
    // d'atteinte reste, et la COULEUR des jauges par PdV reste juste sans rien
    // changer (elle derive de pct_todate, qui vaut alors l'atteinte finale) : le
    // verdict par point de vente ne disparait pas avec le badge de synthese.
    // Sur un mois A VENIR rien n'a couru : budget_todate vaut 0 et pct_todate
    // est nul cote serveur. Aucun NaN ni infini n'est possible ici, tous les
    // taux arrivent deja gardes ; ce sont les LIBELLES qui doivent cesser de
    // promettre une mesure.
    // Textes identiques, mot pour mot, a ceux de direction_dashboard.js : les
    // deux ecrans rendent le meme payload.

    // La couleur porte le rythme : elle ne peut pas en etre le SEUL vecteur.
    // Le rythme chiffre est donc dans l'infobulle et dans le libelle
    // d'accessibilite, lisibles sans percevoir la couleur.
    // Ecart signe : le "+" explicite evite de lire une avance comme un retard.
    // Sortie identique a fmtPct() de direction_dashboard.js : "12,3 %" ou "—".
    // formatPct() seul rend "—", et un site d'appel qui concatene " %" derriere
    // produit "— %", qui n'est pas une valeur. A n'utiliser que la ou le taux
    // peut manquer ; sous une garde isNum(), formatPct() + " %" reste correct.
    budgetPct(value) {
        return this.isNum(value) ? this.formatPct(value) + " %" : "—";
    }

    // La couleur porte le rythme : elle ne peut pas en etre le SEUL vecteur.
    // Le rythme chiffre est donc dans l'infobulle et dans le libelle
    // d'accessibilite, lisibles sans percevoir la couleur.
    // Ecart signe : le "+" explicite evite de lire une avance comme un retard.
    //
    // pct_todate peut manquer alors que pct_month existe : le budget a date est
    // le budget du mois proratise, et le prorata est ~0 dans les premieres
    // minutes du 1er du mois — budget_todate arrondi a 0, donc pas de taux de
    // rythme. Le libelle disait alors "rythme : — %".
    //
    // Modified by: odoo-frontend agent — 2026-08-03 — mois clos / mois a venir
    // TROIS formulations, une par etat du mois de reference — l'infobulle porte
    // le rythme chiffre, elle ne peut donc pas continuer d'en annoncer un la ou
    // il n'en existe plus :
    //   - en cours : avancement · rythme · ecart a date          — inchange
    //   - clos     : avancement · ecart (final, plus « a date ») — le rythme se
    //                confond avec l'avancement, le repeter n'apprend rien
    //   - a venir  : avancement · rien a mesurer                 — budget_todate
    //                vaut 0, un « écart : +0,00 » se lirait comme un resultat
    // Identique, mot pour mot, a gaugeLabel() dans direction_dashboard.js.
    budgetGaugeLabel(row) {
        const state = this.budgetMonthState();
        const avancement = this.budgetPct(row.pct_month) + " du budget du mois";
        if (state === "future") {
            return avancement + " · mois à venir, aucun rythme à mesurer";
        }
        const ecart = row.actual - row.budget_todate;
        const signe = (ecart >= 0 ? "+" : "") + this.formatCurrency(ecart);
        if (state === "past") {
            return avancement + " · écart : " + signe;
        }
        return avancement + " · rythme : " + this.budgetPct(row.pct_todate)
            + " du budget à date · écart à date : " + signe;
    }

    // « Réalisé à date (12 j / 30) » n'a de sens que sur un mois en cours : le
    // mois clos est ecoule en entier, le mois a venir n'a pas commence. Le
    // compteur de jours disparait donc avec le « a date » — « 0 j / 30 » se
    // lirait comme une panne de collecte plutot que comme un mois non commence.
    budgetActualLabel(bud) {
        const state = this.budgetMonthState();
        if (state === "past") {
            return "Réalisé " + bud.month_label + " (mois complet)";
        }
        if (state === "future") {
            return "Réalisé " + bud.month_label + " (mois à venir)";
        }
        return "Réalisé à date (" + bud.elapsed_days + " j / " + bud.month_days + ")";
    }

    // Les DEUX elements « a date » de la synthese — le badge de rythme et le
    // budget proratise — ne sont rendus que sur un mois EN COURS. Hors de ce cas
    // ils ne mesurent plus rien : sur un mois clos ils repetent l'atteinte et le
    // budget plein deja affiches a cote, sur un mois a venir ils valent 0 et
    // « rythme — ». Le badge neutre d'atteinte, lui, est rendu A L'IDENTIQUE
    // dans les trois cas — y compris son « — du budget » SANS « % ».
    //
    // monthState() normalise tout etat inconnu en 'current' : un payload
    // anterieur au contrat garde donc le rendu historique, badge de rythme
    // compris.
    budgetShowPace() {
        return this.budgetMonthState() === "current";
    }

    // Le REMPLISSAGE est plafonne a 100 % — une jauge ne deborde pas de son
    // rail. Le POURCENTAGE affiche a cote ne l'est pas : au-dela de l'objectif
    // on lit "104 %". Meme parti pris que le badge de part du Top produits.
    budgetGaugeWidth(row) {
        if (!this.isNum(row.pct_month)) {
            return 0;
        }
        return Math.min(Math.max(row.pct_month, 0), 100).toFixed(1);
    }

    // La couleur reste pilotee par pct_todate dans les trois etats du mois, sans
    // condition : sur un mois clos il vaut l'atteinte finale (prorata a 100 %),
    // sur un mois a venir il est nul et le repli 'cell-muted' rend une jauge
    // grise — ce qui est exact quand aucun rythme n'est mesurable.
    budgetPaceClass(row) {
        if (!this.isNum(row.pct_todate)) {
            return "cell-muted";
        }
        if (row.pct_todate >= 100) return "bud-ok";
        return row.pct_todate >= 80 ? "bud-mid" : "bud-low";
    }

    // --- Budget : etat du bloc et trois rendus de ligne ---
    // Modified by: odoo-frontend agent — 2026-08-03 — has_budget + statut 'forbidden'
    //                                              + taux absent rendu "—" et non "— %"
    // Helpers plutot que des expressions dans le template : le compilateur OWL
    // reecrit les identifiants, on ne lui confie ni acces optionnel ni litteral
    // objet. Textes et regles identiques, mot pour mot, a ceux de
    // direction_dashboard.js — les deux ecrans rendent le meme payload.

    // Message et tableau sont INDEPENDANTS, parce que le serveur les combine :
    // le message accompagne des lignes bien remplies des que les objectifs sont
    // indisponibles (module absent, droits manquants, lecture en erreur), et il
    // arrive seul quand il n'y a rien a lister (filtre caissier actif). Les
    // conditionner l'un a l'autre perdait, selon le sens, soit l'explication
    // soit le realise du mois par PdV.
    // Le test sur status ne sert qu'au repli local, pour un 'forbidden' arrive
    // sans message ; un payload anterieur au contrat n'a pas de status et garde
    // l'ancien comportement, pilote par le seul message.
    budgetHasState(bud) {
        return Boolean(bud.message || (bud.status && bud.status !== "ok"));
    }

    // Payload sans status (backend anterieur au contrat) ET message non vide :
    // l'ancien code s'arretait la, message seul. On garde ce rendu A
    // L'IDENTIQUE le temps d'un deploiement partiel — une garde d'ecart n'a
    // d'interet que si elle ne change rien de visible. Des que le backend
    // annonce un status, la regle du contrat s'applique et le tableau
    // accompagne le message.
    budgetShowTable(bud) {
        if (!bud.rows || !bud.rows.length) {
            return false;
        }
        return Boolean(bud.status) || !bud.message;
    }

    // Ni message ni lignes : ne pas laisser la section vide.
    budgetShowFallback(bud) {
        return !this.budgetHasState(bud) && !this.budgetShowTable(bud);
    }

    // Les objectifs sont-ils lisibles ET presents ? Deux choses distinctes que
    // le serveur separe : le statut dit si on a pu les lire, has_any_budget
    // s'il y en a. Dans les deux cas contraires les totaux de budget valent 0 —
    // non parce que l'objectif est nul, mais parce qu'il est INCONNU. Afficher
    // "Budget du mois : 0,00" la-dessus serait le meme mensonge que celui qu'on
    // corrige au niveau de la ligne, en plus gros.
    //
    // has_any_budget ABSENT = payload anterieur au contrat : on retombe sur
    // l'absence de message, qui est exactement le signal dont disposait
    // l'ancien code ("message vide = il y a quelque chose a afficher"). Le
    // tenir pour "lisible" par defaut affichait un "Budget du mois : 0,00" la
    // ou l'ancien n'affichait aucune synthese.
    budgetReadable(bud) {
        if (bud.status && bud.status !== "ok") {
            return false;
        }
        if (bud.has_any_budget === undefined || bud.has_any_budget === null) {
            return !bud.message;
        }
        return Boolean(bud.has_any_budget);
    }

    // Quatre statuts au contrat — 'missing' (module absent), 'error' (donnees
    // illisibles), 'forbidden' (pas le droit de les lire), 'ok' — et, en statut
    // 'ok', un message du serveur ("aucun budget saisi pour le mois", "aucun
    // PdV visible") : cinq situations qui ne veulent pas dire la meme chose et
    // ne doivent donc pas se ressembler. L'icone porte la difference de nature.
    // 'forbidden' est deliberement discret (cadenas, pas de rouge) : c'est une
    // habilitation manquante, pas une panne.
    budgetStateIcon(bud) {
        if (bud.status === "missing") return "fa-puzzle-piece";
        if (bud.status === "error") return "fa-exclamation-triangle";
        if (bud.status === "forbidden") return "fa-lock";
        return "fa-info-circle";
    }

    // Seul etat colore : une panne technique doit se distinguer d'un ecran
    // vide. bud-low est le jeton de texte rouge deja defini par la feuille de
    // style — aucune classe nouvelle, donc rien a repercuter cote CSS ni dans
    // le <style> inline de direction_dashboard/controllers/main.py.
    budgetStateClass(bud) {
        return bud.status === "error" ? "bud-low" : "";
    }

    // Le TEXTE n'est jamais recalcule ici quand le serveur en envoie un : les
    // deux ecrans rendent le meme payload, une formulation par ecran finirait
    // par diverger. Le repli local ne sert qu'au cas ou le serveur n'envoie
    // rien — notamment 'forbidden', dont le message est facultatif au contrat.
    budgetStateText(bud) {
        if (bud.message) return bud.message;
        if (bud.status === "missing") return "Module budget non installé.";
        if (bud.status === "error") return "Budgets indisponibles.";
        if (bud.status === "forbidden") return "Budgets réservés à la direction.";
        return "Aucun budget à afficher.";
    }

    // TROIS rendus de ligne distincts, et c'est le point de la correction :
    //   - pas d'objectif saisi          : "—"      + colonne Budget vide
    //   - objectif saisi, taux non fini : "s. o."  + colonne Budget "0,00"
    //   - objectif mesurable            : jauge + pourcentage
    // C'est has_budget qui tranche, PAS la veracite de budget_month. Un
    // objectif saisi a 0 (cas metier reel : PdV ferme sur le mois) EST un
    // objectif, et 0,00 est son montant. Le test precedent portait sur le
    // montant : ce PdV affichait "—" et l'infobulle "Aucun budget saisi", qui
    // niait une saisie existante. pct_month reste nul dans ce cas (un realise
    // > 0 rapporte a 0 n'a pas de pourcentage fini), il ne peut donc pas servir
    // a distinguer les deux.
    // has_budget fait foi des qu'il est present, meme a faux. Sa seule ABSENCE
    // signifie un backend anterieur au contrat : on retombe alors sur
    // l'ancienne regle plutot que de declarer TOUS les PdV sans objectif — ce
    // serait le meme mensonge que celui qu'on corrige, applique a la liste
    // entiere. Meme repli que hasTarget() dans direction_dashboard.js.
    budgetHasTarget(row) {
        if (row.has_budget === undefined || row.has_budget === null) {
            return this.isNum(row.pct_month);
        }
        return Boolean(row.has_budget);
    }

    budgetShowGauge(row) {
        return this.budgetHasTarget(row) && this.isNum(row.pct_month);
    }

    budgetShowFlat(row) {
        return this.budgetHasTarget(row) && !this.isNum(row.pct_month);
    }

    // Pourquoi cette ligne n'a pas d'objectif : la reponse depend du STATUT du
    // bloc, pas de la ligne — has_budget vaut faux partout des que la lecture a
    // echoue. "Aucun objectif saisi" serait faux quand les objectifs existent
    // mais ne sont pas lisibles ; c'est le meme type de mensonge que celui
    // corrige sur l'objectif a 0, et il se lirait comme une invitation a aller
    // saisir un budget qui l'est deja.
    budgetNoTargetTitle() {
        const bud = this.state.data.budget_vs_actual;
        const status = bud ? bud.status : null;
        if (status === "forbidden") return "Budget non lisible avec vos droits";
        if (status === "error") return "Budget non lisible : données illisibles";
        if (status === "missing") return "Module budget non installé";
        return "Aucun objectif saisi pour ce point de vente";
    }

    budgetZeroTitle(row) {
        return "Objectif de " + this.formatCurrency(row.budget_month)
            + " pour le mois — aucun taux d'atteinte n'est calculable · réalisé : "
            + this.formatCurrency(row.actual);
    }

    hasActiveFilters() {
        const f = this.state.filters;
        return f.date_from || f.date_to || f.pos_config_id || f.user_id
            || f.chart_days !== 7 || f.recent_days !== 30;
    }

    formatDatetime(dt) {
        if (!dt) return '';
        const d = new Date(dt);
        return d.toLocaleString("fr-FR", {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    openOrdersToday() {
        const today = new Date();
        const todayStr = today.toISOString().split('T')[0];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Commandes aujourd'hui",
            res_model: "pos.order",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [
                ["date_order", ">=", todayStr + " 00:00:00"],
                ["date_order", "<=", todayStr + " 23:59:59"],
            ],
            target: "current",
        });
    }

    openReturnsToday() {
        const today = new Date();
        const todayStr = today.toISOString().split('T')[0];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Retours aujourd'hui",
            res_model: "pos.order",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [
                ["date_order", ">=", todayStr + " 00:00:00"],
                ["date_order", "<=", todayStr + " 23:59:59"],
                ["amount_total", "<", 0],
            ],
            target: "current",
        });
    }

    openSessions() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Sessions ouvertes",
            res_model: "pos.session",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [["state", "=", "opened"]],
            target: "current",
        });
    }

    openMonthOrders() {
        const now = new Date();
        const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
        const monthStartStr = monthStart.toISOString().split('T')[0];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Commandes du mois",
            res_model: "pos.order",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [
                ["date_order", ">=", monthStartStr + " 00:00:00"],
            ],
            target: "current",
        });
    }
}

registry.category("actions").add("pos_dashboard.PosDashboard", PosDashboard);
