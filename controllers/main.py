from odoo import http
from odoo.http import request
from datetime import datetime, timedelta
from werkzeug.exceptions import Forbidden


class PosDashboardController(http.Controller):

    @http.route('/pos_dashboard/data', type='json', auth='user')
    def get_dashboard_data(self, **kwargs):
        if not request.env.user.has_group('pos_dashboard.group_pos_dashboard_user'):
            raise Forbidden("Accès non autorisé au dashboard PdV")

        PosOrder = request.env['pos.order']
        PosSession = request.env['pos.session']
        PosPayment = request.env['pos.payment']
        PosOrderLine = request.env['pos.order.line']

        # Récupérer les paramètres dynamiques (filtres du frontend)
        filters = kwargs.get('filters', {})
        chart_days = filters.get('chart_days', 7)
        recent_days = filters.get('recent_days', 30)
        top_products_limit = filters.get('top_products_limit', 10)
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        pos_config_id = filters.get('pos_config_id')
        user_id = filters.get('user_id')

        # Construire le domaine de base à partir des filtres
        base_domain = []
        if pos_config_id:
            base_domain.append(('config_id', '=', pos_config_id))
        if user_id:
            base_domain.append(('user_id', '=', user_id))

        # Domaine temporel pour les filtres date
        date_domain = []
        if date_from:
            date_domain.append(('date_order', '>=', date_from))
        if date_to:
            date_domain.append(('date_order', '<=', date_to + ' 23:59:59'))

        # --- KPI Cards ---

        # 1. Sessions ouvertes
        session_domain = [('state', '=', 'opened')]
        if pos_config_id:
            session_domain.append(('config_id', '=', pos_config_id))
        open_sessions_count = PosSession.search_count(session_domain)

        # Dates du jour
        today_start = datetime.now().replace(hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
        today_end = datetime.now().replace(hour=23, minute=59, second=59).strftime('%Y-%m-%d %H:%M:%S')
        today_domain = base_domain + [
            ('date_order', '>=', today_start),
            ('date_order', '<=', today_end),
        ]

        # 2. Commandes aujourd'hui
        orders_today_count = PosOrder.search_count(today_domain)

        # 3. CA aujourd'hui
        orders_today = PosOrder.search_read(
            today_domain,
            fields=['amount_total'],
        )
        ca_today = sum(o['amount_total'] for o in orders_today)

        # 4. Panier moyen
        avg_basket = ca_today / orders_today_count if orders_today_count else 0

        # Dates du mois
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
        month_domain = base_domain + [
            ('date_order', '>=', month_start),
            ('date_order', '<=', today_end),
        ]

        # 5. CA ce mois
        orders_month = PosOrder.search_read(
            month_domain,
            fields=['amount_total'],
        )
        ca_month = sum(o['amount_total'] for o in orders_month)

        # 6. Commandes ce mois
        orders_month_count = len(orders_month)

        # 7. Retours aujourd'hui
        returns_today_count = PosOrder.search_count(
            today_domain + [('amount_total', '<', 0)]
        )

        # 8. Clients servis aujourd'hui
        orders_with_partner = PosOrder.search_read(
            today_domain + [('partner_id', '!=', False)],
            fields=['partner_id'],
        )
        distinct_partners = len(set(o['partner_id'][0] for o in orders_with_partner if o['partner_id']))

        # --- Graphique CA quotidien ---
        daily_ca = []
        for i in range(chart_days - 1, -1, -1):
            day = datetime.now() - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
            day_end = day.replace(hour=23, minute=59, second=59).strftime('%Y-%m-%d %H:%M:%S')
            domain = base_domain + [
                ('date_order', '>=', day_start),
                ('date_order', '<=', day_end),
            ]
            day_orders = PosOrder.search_read(domain, fields=['amount_total'])
            day_total = sum(o['amount_total'] for o in day_orders)
            day_count = len(day_orders)
            daily_ca.append({
                'date': day.strftime('%d/%m'),
                'total': round(day_total, 2),
                'count': day_count,
            })

        # --- Statistiques période récente ---
        date_n_ago = datetime.now() - timedelta(days=recent_days)
        recent_domain = base_domain + date_domain + [
            ('date_order', '>=', date_n_ago.strftime('%Y-%m-%d %H:%M:%S')),
        ]
        recent_orders = PosOrder.search_read(
            recent_domain,
            fields=['amount_total'],
        )
        total_orders_recent = len(recent_orders)
        total_ca_recent = sum(o['amount_total'] for o in recent_orders)

        # --- Top produits ---
        recent_order_ids = PosOrder.search(recent_domain).ids
        top_products = []
        if recent_order_ids:
            line_groups = PosOrderLine.read_group(
                [('order_id', 'in', recent_order_ids)],
                fields=['product_id', 'qty', 'price_subtotal_incl'],
                groupby=['product_id'],
                orderby='price_subtotal_incl desc',
                limit=top_products_limit,
            )
            for g in line_groups:
                if g['product_id']:
                    top_products.append({
                        'id': g['product_id'][0],
                        'product': g['product_id'][1],
                        'qty': g['qty'],
                        'ca': round(g['price_subtotal_incl'], 2),
                    })

        # --- Moyens de paiement ---
        payment_methods = []
        if recent_order_ids:
            payment_groups = PosPayment.read_group(
                [('pos_order_id', 'in', recent_order_ids)],
                fields=['payment_method_id', 'amount'],
                groupby=['payment_method_id'],
                orderby='amount desc',
            )
            total_payments = sum(g['amount'] for g in payment_groups)
            for g in payment_groups:
                if g['payment_method_id']:
                    pct = round((g['amount'] / total_payments * 100), 1) if total_payments else 0
                    payment_methods.append({
                        'id': g['payment_method_id'][0],
                        'method': g['payment_method_id'][1],
                        'amount': round(g['amount'], 2),
                        'pct': pct,
                    })

        # --- Sessions actives ---
        active_sessions = PosSession.search_read(
            session_domain,
            fields=['name', 'user_id', 'config_id', 'start_at'],
            order='start_at desc',
        )

        # Config pour le frontend
        config = request.env['pos.dashboard.config'].get_config()

        # Devise de la société
        currency = request.env.company.currency_id
        currency_info = {
            'symbol': currency.symbol or '',
            'position': currency.position or 'after',
        }

        return {
            'currency': currency_info,
            'open_sessions_count': open_sessions_count,
            'orders_today_count': orders_today_count,
            'ca_today': round(ca_today, 2),
            'avg_basket': round(avg_basket, 2),
            'ca_month': round(ca_month, 2),
            'orders_month_count': orders_month_count,
            'returns_today_count': returns_today_count,
            'distinct_partners': distinct_partners,
            'daily_ca': daily_ca,
            'total_orders_recent': total_orders_recent,
            'total_ca_recent': round(total_ca_recent, 2),
            'top_products': top_products,
            'payment_methods': payment_methods,
            'active_sessions': active_sessions,
            'config': config,
        }

    @http.route('/pos_dashboard/filters_data', type='json', auth='user')
    def get_filters_data(self):
        """Retourne les données pour les listes déroulantes des filtres."""
        if not request.env.user.has_group('pos_dashboard.group_pos_dashboard_user'):
            raise Forbidden("Accès non autorisé au dashboard PdV")

        # Points de vente
        pos_configs = request.env['pos.config'].search_read(
            [],
            fields=['name'],
            order='name',
        )
        config_list = [
            {'id': c['id'], 'name': c['name']}
            for c in pos_configs
        ]

        # Caissiers ayant des commandes
        users = request.env['pos.order'].read_group(
            [('user_id', '!=', False)],
            fields=['user_id'],
            groupby=['user_id'],
        )
        user_list = [
            {'id': u['user_id'][0], 'name': u['user_id'][1]}
            for u in users if u['user_id']
        ]

        return {
            'pos_configs': config_list,
            'users': user_list,
        }
