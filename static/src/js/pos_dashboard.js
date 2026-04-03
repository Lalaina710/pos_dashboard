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
            data: {},
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
        try {
            const filters = { ...this.state.filters };
            // Nettoyer les filtres vides
            if (!filters.pos_config_id) delete filters.pos_config_id;
            if (!filters.user_id) delete filters.user_id;
            if (!filters.date_from) delete filters.date_from;
            if (!filters.date_to) delete filters.date_to;

            this.state.data = await rpc("/pos_dashboard/data", { filters });
            this.state.lastUpdate = new Date().toLocaleTimeString("fr-FR");
        } catch (e) {
            console.error("POS Dashboard error:", e);
            this.state.data = {
                open_sessions_count: 0,
                orders_today_count: 0,
                ca_today: 0,
                avg_basket: 0,
                ca_month: 0,
                orders_month_count: 0,
                returns_today_count: 0,
                distinct_partners: 0,
                daily_ca: [],
                total_orders_recent: 0,
                total_ca_recent: 0,
                top_products: [],
                payment_methods: [],
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
        if (!qty) return "0";
        return Math.round(qty).toLocaleString("fr-FR");
    }

    getBarHeight(total) {
        const maxTotal = Math.max(
            ...this.state.data.daily_ca.map((d) => d.total),
            1
        );
        return Math.max((total / maxTotal) * 150, 4);
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
