# Modified by: odoo-frontend agent — 2026-04-13 — Fix timezone, perf graphique
from odoo import fields, http
from odoo.http import request
from datetime import timedelta, datetime
import pytz
from werkzeug.exceptions import Forbidden


class PosDashboardController(http.Controller):

    @http.route('/pos_dashboard/data', type='json', auth='user')
    def get_dashboard_data(self, **kwargs):
        if not request.env.user.has_group('pos_dashboard.group_pos_dashboard_user'):
            raise Forbidden("Accès non autorisé au dashboard PdV")

        PosOrder = request.env['pos.order']
        PosSession = request.env['pos.session']
        PosOrderLine = request.env['pos.order.line']

        # Récupérer les paramètres dynamiques (filtres du frontend)
        filters = kwargs.get('filters', {})
        chart_days = filters.get('chart_days', 7)
        recent_days = filters.get('recent_days', 30)
        top_products_limit = filters.get('top_products_limit', 10)
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')

        # Convert date_from/date_to to UTC boundaries (user timezone)
        _ftz = pytz.timezone(request.env.user.tz or 'Indian/Antananarivo')
        if date_from and len(date_from) == 10:
            _df_local = _ftz.localize(datetime.strptime(date_from, '%Y-%m-%d'))
            date_from = _df_local.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
        if date_to and len(date_to) == 10:
            _dt_local = _ftz.localize(datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
            date_to = _dt_local.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
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
            date_domain.append(('date_order', '<=', date_to))

        # --- KPI Cards ---

        # 1. Sessions ouvertes
        session_domain = [('state', '=', 'opened')]
        if pos_config_id:
            session_domain.append(('config_id', '=', pos_config_id))
        open_sessions_count = PosSession.search_count(session_domain)

        # Dates du jour
        _tz = pytz.timezone(request.env.user.tz or 'Indian/Antananarivo')
        _now_local = fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(_tz)
        _today_local_start = _now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        _today_local_end = _now_local.replace(hour=23, minute=59, second=59, microsecond=0)
        today_start = _today_local_start.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
        today_end = _today_local_end.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
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
        month_start = _today_local_start.replace(day=1).astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
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

        # 6b. Quantite totale ce mois (somme qty sur les memes orders que ca_month)
        month_order_ids = [o['id'] for o in orders_month]
        if month_order_ids:
            qty_month_groups = PosOrderLine.read_group(
                [('order_id', 'in', month_order_ids)],
                fields=['qty:sum'],
                groupby=[],
            )
            qty_month = qty_month_groups[0].get('qty', 0) if qty_month_groups else 0
        else:
            qty_month = 0

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

        # --- Graphique CA quotidien (optimisé read_group) ---
        now = fields.Datetime.now()
        date_chart_start = (now - timedelta(days=chart_days - 1)).strftime('%Y-%m-%d 00:00:00')
        chart_domain = base_domain + [('date_order', '>=', date_chart_start)]
        chart_groups = PosOrder.read_group(
            chart_domain,
            fields=['amount_total:sum', 'date_order'],
            groupby=['date_order:day'],
        )
        user_tz = pytz.timezone(request.env.user.tz or 'Indian/Antananarivo')
        chart_by_date = {}
        for g in chart_groups:
            rng = g.get('__range', {}).get('date_order:day', {})
            from_str = rng.get('from', '')
            if from_str:
                utc_dt = datetime.strptime(from_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
                local_dt = utc_dt.astimezone(user_tz)
                day_key = local_dt.strftime('%Y-%m-%d')
                chart_by_date[day_key] = {
                    'total': round(g.get('amount_total', 0), 2),
                    'count': g.get('__count', 0),
                }
        daily_ca = []
        now_local = now.replace(tzinfo=pytz.utc).astimezone(user_tz)
        for i in range(chart_days - 1, -1, -1):
            day = now_local - timedelta(days=i)
            day_label = day.strftime('%d/%m')
            day_key = day.strftime('%Y-%m-%d')
            data = chart_by_date.get(day_key, {})
            daily_ca.append({
                'date': day_label,
                'total': data.get('total', 0),
                'count': data.get('count', 0),
            })

        # --- Statistiques période récente ---
        date_n_ago = fields.Datetime.now() - timedelta(days=recent_days)
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

        # --- CA par PdV (aujourd'hui par défaut, ou période filtrée) ---
        ca_pos_domain = base_domain[:]
        if date_domain:
            ca_pos_domain += date_domain
        else:
            ca_pos_domain += [
                ('date_order', '>=', today_start),
                ('date_order', '<=', today_end),
            ]
        ca_by_pos = []
        pos_groups = PosOrder.read_group(
            ca_pos_domain,
            fields=['config_id', 'amount_total', 'date_order'],
            groupby=['date_order:day', 'config_id'],
            orderby='date_order:day desc, amount_total desc',
            lazy=False,
        )

        # Pre-compute total qty sold per (day_key, config_id)
        qty_by_key = {}
        scope_orders = PosOrder.search_read(
            ca_pos_domain,
            fields=['id', 'date_order', 'config_id'],
        )
        scope_order_ids = [o['id'] for o in scope_orders]
        qty_by_order = {}
        if scope_order_ids:
            line_qty_groups = PosOrderLine.read_group(
                [('order_id', 'in', scope_order_ids)],
                fields=['order_id', 'qty:sum'],
                groupby=['order_id'],
            )
            for lg in line_qty_groups:
                if lg.get('order_id'):
                    qty_by_order[lg['order_id'][0]] = lg.get('qty', 0) or 0
        for o in scope_orders:
            if not o.get('config_id'):
                continue
            dt = o['date_order']
            if isinstance(dt, str):
                dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
            local_dt = pytz.utc.localize(dt).astimezone(user_tz) \
                if dt.tzinfo is None else dt.astimezone(user_tz)
            day_key = local_dt.strftime('%Y-%m-%d')
            key = (day_key, o['config_id'][0])
            qty_by_key[key] = qty_by_key.get(key, 0) + qty_by_order.get(o['id'], 0)

        total_ca_pos = sum(g['amount_total'] for g in pos_groups)
        for g in pos_groups:
            if g['config_id']:
                amount = g['amount_total']
                count = g.get('__count', 0)
                pct = round((amount / total_ca_pos * 100), 1) if total_ca_pos else 0
                avg_basket_pos = round(amount / count, 2) if count else 0
                rng = g.get('__range', {}).get('date_order:day', {})
                from_str = rng.get('from', '')
                day_str = ''
                day_key = ''
                if from_str:
                    utc_dt = datetime.strptime(from_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
                    local_dt = utc_dt.astimezone(user_tz)
                    day_str = local_dt.strftime('%d/%m/%Y')
                    day_key = local_dt.strftime('%Y-%m-%d')
                cfg_id = g['config_id'][0]
                total_qty = qty_by_key.get((day_key, cfg_id), 0)
                ca_by_pos.append({
                    'id': cfg_id,
                    'name': g['config_id'][1],
                    'date': day_str,
                    'amount': round(amount, 2),
                    'count': count,
                    'avg_basket': avg_basket_pos,
                    'total_qty': round(total_qty, 3),
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
            'qty_month': round(qty_month, 3),
            'orders_month_count': orders_month_count,
            'returns_today_count': returns_today_count,
            'distinct_partners': distinct_partners,
            'daily_ca': daily_ca,
            'total_orders_recent': total_orders_recent,
            'total_ca_recent': round(total_ca_recent, 2),
            'top_products': top_products,
            'ca_by_pos': ca_by_pos,
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
