# Modified by: odoo-frontend agent — 2026-04-13 — Fix timezone, perf graphique
# Modified by: odoo-frontend agent — 2026-07-28 — Colonne PdV principal top produits
# Modified by: odoo-frontend agent — 2026-07-28 — Corrections QA/secu : bornes filtres
#   client, double borne basse periode, denominateur part PdV
# Modified by: odoo-frontend agent — 2026-07-31 — Comparatif M/M-1 + CA vs budget
# Modified by: odoo-frontend agent — 2026-08-01 — Contrat budget fige + rythme
# Modified by: odoo-backend agent — 2026-08-03 — Corrections revue code du lot
#   budget : statut 'forbidden' (bascule ACL), budget a 0 discernable d'un
#   budget absent, borne volumetrique de la fenetre recente, neutralisation du
#   bloc budget sous filtre caissier, rythme intra-journalier, total a date
# Modified by: odoo-backend agent — 2026-08-03 — Changement de specification :
#   le comparatif M/M-1 et le bloc budget SUIVENT desormais le filtre de date
#   (ancrage sur le mois de la date de fin), prorata decline sur mois
#   passe/courant/futur, libelles « hors filtre de date » supprimes
# Modified by: odoo-backend agent — 2026-08-03 — Corrections de libelle du lot
#   d'ancrage (aucun calcul touche) : period_label du comparatif remis dans
#   l'ordre « M vs M-1 », ancrage textuel du delta (delta_label),
#   previous_is_current_month expose, note du budget sur mois a venir
from odoo import fields, http
from odoo.exceptions import AccessError
from odoo.http import request
from datetime import timedelta, datetime
import calendar
import logging
import pytz
from werkzeug.exceptions import Forbidden

_logger = logging.getLogger(__name__)

# Libelles de mois : le dashboard est monolingue francais (tous les autres
# libelles de ce controleur le sont deja). Une dependance a babel/format_date
# ferait dependre le rendu de la langue de l'utilisateur, alors que les deux
# frontends qui consomment ce payload sont ecrits en dur en francais.
_MONTHS_FR = (
    'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
)


def _month_label(day):
    """'2026-07-01' -> 'juillet 2026'."""
    return '%s %d' % (_MONTHS_FR[day.month - 1], day.year)


class PosDashboardController(http.Controller):

    @staticmethod
    def _bounded_int(value, default, minimum, maximum):
        """Borne un entier issu du payload client.

        Le frontend envoie ces valeurs telles quelles : sans borne, une valeur
        non numerique fait une 500 (timedelta(days='abc')) et une valeur enorme
        fait exploser la taille des requetes (DoS worker par un utilisateur
        authentifie). Les bornes sont larges : elles couvrent toutes les options
        de l'UI et toute valeur raisonnable de pos.dashboard.config.
        """
        try:
            value = int(value)
        except (TypeError, ValueError, OverflowError):
            # OverflowError : json.loads de CPython accepte Infinity, et
            # int(float('inf')) leve OverflowError, pas ValueError
            return default
        return min(max(value, minimum), maximum)

    @staticmethod
    def _period_label(start_local, end_local, has_end_filter, suffix=''):
        """Libelle de periode — mecanisme unique pour tout l'ecran.

        Toutes les sections filtrables (graphique, stats recentes, top produits)
        derivent leur libelle d'ici : une seule regle, pas une source de verite
        par section. Le suffixe porte la granularite / la troncature du graphique.
        """
        if has_end_filter:
            label = 'du %s au %s' % (
                start_local.strftime('%d/%m/%Y'), end_local.strftime('%d/%m/%Y'),
            )
        else:
            label = "du %s à aujourd'hui" % start_local.strftime('%d/%m/%Y')
        return (label + suffix) if suffix else label

    # ------------------------------------------------------------------
    # Budget PdV — POINT D'ANCRAGE UNIQUE vers le module sopromer_pos_budget
    # Modified by: odoo-frontend agent — 2026-07-31
    # Modified by: odoo-frontend agent — 2026-08-01 — contrat fige
    # ------------------------------------------------------------------
    # Contrat (sopromer_pos_budget/README.md, « Contrat d'acces pour le
    # tableau de bord ») :
    #     budget.pos.line._get_budget_map(date_from, date_to, config_ids=None)
    #         -> {(config_id, date(AAAA, MM, 1)): float}
    # Tout ce qui touche a ce module est confine ici : un seul endroit a
    # corriger si le contrat bouge.
    _BUDGET_MODEL = 'budget.pos.line'

    @staticmethod
    def _normalize_budget(raw, month_first):
        """{(config_id, date(AAAA,MM,1)): montant} -> {config_id: montant}.

        Renvoie None si la forme n'est pas celle du contrat : mieux vaut
        afficher "budgets indisponibles" que des montants attribues au mauvais
        PdV, ou un bloc vide qui se lirait "aucun budget saisi".

        Le mois de la cle est un `date`, PAS une chaine : date(2026, 7, 1) et
        '2026-07' n'ont ni la meme valeur ni le meme hash. Comparer a une
        chaine ne ferait correspondre aucune cle et viderait le bloc SANS
        lever d'erreur — d'ou le garde-fou sur les cles ignorees plus bas.
        """
        if not isinstance(raw, dict):
            return None
        out = {}
        skipped = 0
        for key, value in raw.items():
            if not isinstance(key, (tuple, list)) or len(key) != 2:
                return None
            cfg_id, key_month = key[0], key[1]
            if key_month != month_first:
                # Une seule borne a ete demandee : un autre mois signale un
                # changement de contrat, on ne l'agrege pas en silence.
                skipped += 1
                continue
            try:
                out[int(cfg_id)] = out.get(int(cfg_id), 0.0) + float(value or 0)
            except (TypeError, ValueError):
                return None
        if raw and not out and skipped:
            # Le module a renvoye des lignes, aucune ne correspond au mois
            # demande : le type de la cle a change (date -> datetime, par
            # exemple). Un mapping vide serait indiscernable de "rien de saisi".
            _logger.warning(
                "pos_dashboard : %s a renvoye %d cle(s) dont aucune pour %s "
                "(type de cle mois : %s)", 'budget.pos.line', skipped,
                month_first, type(next(iter(raw))[1]).__name__)
            return None
        return out

    @classmethod
    def _get_pos_budget(cls, month_first, config_ids=None):
        """Budget de CA par PdV pour UN mois. Retourne (statut, mapping).

        Statuts : 'missing' (module non installe), 'forbidden' (installe, mais
        l'utilisateur n'a pas l'habilitation de lecture), 'error' (installe et
        habilite, mais illisible ou hors contrat), 'ok' (mapping exploitable,
        vide s'il n'y a aucun budget saisi). Le frontend rend un message
        distinct pour chacun : "aucun budget saisi", "reserve a la direction"
        et "budgets illisibles" ne veulent pas dire la meme chose pour la
        direction.

        config_ids : None = tous les PdV lisibles. Une LISTE VIDE veut dire
        "aucun PdV" et renvoie {} — ne jamais passer [] pour dire "tous".

        Aucune exception ne remonte : le dashboard PdV doit continuer de
        fonctionner meme si le module de budget est absent ou casse.

        Depuis sopromer_pos_budget 18.0.1.1.0, la lecture n'est plus donnee a
        group_pos_dashboard_user mais au groupe dedie group_pos_budget_reader
        (arbitrage direction : le budget n'est pas une donnee d'exploitation).
        Un utilisateur du dashboard qui n'a pas ce groupe leve donc un
        AccessError, qui est une DECISION D'HABILITATION et pas une panne :
        il est attrape AVANT Exception, rendu comme 'forbidden', et n'est pas
        logge en warning — le cas est nominal pour les ~39 responsables PdV, et
        l'auto-refresh du dashboard noierait les logs a chaque tour.
        """
        env = request.env
        if cls._BUDGET_MODEL not in env:
            return 'missing', {}
        try:
            model = env[cls._BUDGET_MODEL]
            # _normalize_month est le constructeur de cle OFFICIEL du module :
            # c'est lui qui fixe le type exact du mois dans les cles renvoyees.
            # Reconstruire cette cle a la main est le piege documente cote
            # module — date_order groupe par mois donne un datetime, et
            # datetime(2026,7,1) != date(2026,7,1) (hash different) : aucune
            # cle ne correspondrait et le bloc s'afficherait vide, sans erreur.
            month_key = model._normalize_month(month_first)
            # Bornes identiques = ce seul mois (un budget est retenu des que
            # son mois chevauche la periode).
            raw = model._get_budget_map(
                month_first, month_first, config_ids=config_ids)
            # L'exploitation du retour est DANS le try : hors du try, la
            # promesse "aucune exception ne remonte" ne couvrait pas
            # _normalize_budget, qui itere et caste des donnees venues d'un
            # module optionnel.
            mapping = cls._normalize_budget(raw, month_key)
        except AccessError:
            _logger.debug(
                "pos_dashboard : %s non lisible par %s (habilitation), bloc "
                "budget masque", cls._BUDGET_MODEL, env.user.login)
            return 'forbidden', {}
        except Exception:
            _logger.warning(
                "pos_dashboard : lecture de %s impossible, budget ignore",
                cls._BUDGET_MODEL, exc_info=True)
            return 'error', {}
        if mapping is None:
            _logger.warning(
                "pos_dashboard : retour de %s._get_budget_map non conforme au "
                "contrat, budget ignore", cls._BUDGET_MODEL)
            return 'error', {}
        return 'ok', mapping

    @http.route('/pos_dashboard/data', type='json', auth='user')
    def get_dashboard_data(self, **kwargs):
        if not request.env.user.has_group('pos_dashboard.group_pos_dashboard_user'):
            raise Forbidden("Accès non autorisé au dashboard PdV")

        PosOrder = request.env['pos.order']
        PosSession = request.env['pos.session']
        PosOrderLine = request.env['pos.order.line']

        # Récupérer les paramètres dynamiques (filtres du frontend)
        filters = kwargs.get('filters', {})
        chart_days = self._bounded_int(filters.get('chart_days'), 7, 1, 90)
        recent_days = self._bounded_int(filters.get('recent_days'), 30, 1, 365)
        top_products_limit = self._bounded_int(filters.get('top_products_limit'), 10, 1, 200)
        # Fuseau et instant de reference : calcules UNE fois pour toute la methode
        user_tz = pytz.timezone(request.env.user.tz or 'Indian/Antananarivo')
        now = fields.Datetime.now()
        now_local = now.replace(tzinfo=pytz.utc).astimezone(user_tz)

        # UNE seule representation des filtres date : ce qui n'a pas ete parse
        # n'existe pas. Auparavant has_date_from portait sur la chaine brute
        # tandis que le domaine ORM recevait cette meme chaine non parsee : un
        # date_to='2026-03-31 23:59:59' force en JSON-RPC filtrait bien les
        # commandes MAIS n'alimentait pas window_end_local, ramenant d'un coup
        # les trois defauts corriges par ce lot (+ 500 possible au cast PG).
        date_from = None
        date_to = None
        date_from_local_dt = None
        date_to_local_dt = None
        _raw_from = filters.get('date_from')
        _raw_to = filters.get('date_to')
        # isinstance avant len() : un date_from=123 leverait TypeError sur len(int)
        # AVANT d'entrer dans le try, et une liste de 10 elements passerait le
        # test de longueur pour casser dans strptime.
        #
        # Annee bornee a [1900, 2999] : '%Y-%m-%d' accepte l'annee 1 comme
        # l'annee 9999, et ces extremes font DEBORDER l'arithmetique de dates en
        # aval — (date(1, 1, 1) - timedelta(days=1)) leve OverflowError, donc
        # une 500 sur une route auth='user' a partir d'un payload forge. Deux
        # calculs y sont exposes : la borne d'etendue a 366 jours, et surtout le
        # mois precedent du comparatif, qui derive desormais de date_to. Hors
        # bornes = date ignoree, exactement comme une date illisible : la regle
        # de ce bloc est « ce qui n'a pas ete parse n'existe pas ». Les bornes
        # sont larges : aucune donnee PdV plausible ne tombe en dehors.
        _min_year, _max_year = 1900, 2999
        if isinstance(_raw_from, str) and len(_raw_from) == 10:
            try:
                _parsed = datetime.strptime(_raw_from, '%Y-%m-%d')
                if _min_year <= _parsed.year <= _max_year:
                    date_from_local_dt = user_tz.localize(_parsed)
            except (ValueError, TypeError):
                date_from_local_dt = None
        if isinstance(_raw_to, str) and len(_raw_to) == 10:
            try:
                _parsed = datetime.strptime(_raw_to, '%Y-%m-%d')
                if _min_year <= _parsed.year <= _max_year:
                    date_to_local_dt = user_tz.localize(
                        _parsed.replace(hour=23, minute=59, second=59))
            except (ValueError, TypeError):
                date_to_local_dt = None

        # Fin de fenetre commune a toutes les sections filtrables : date_to si
        # fourni, sinon maintenant. Les fenetres glissantes par defaut s'ancrent
        # dessus et JAMAIS sur now : sinon un date_to seul (sans date_from)
        # donnerait une borne basse posterieure a la borne haute (ensemble vide).
        window_end_local = date_to_local_dt or now_local

        # Plafond d'etendue. Rendre la borne basse conditionnelle (fix periode
        # passee) a supprime le seul garde-fou volumetrique : un date_from a
        # 1970 ferait travailler search_read + search + read_group + le SQL brut
        # sur tout l'historique. Le plafond de points borne le RENDU, pas le SQL.
        max_span_days = 366
        period_clamped = False
        if date_from_local_dt:
            _earliest = (window_end_local - timedelta(days=max_span_days)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            if date_from_local_dt < _earliest:
                date_from_local_dt = _earliest
                period_clamped = True
        clamp_suffix = ' · limité à 12 mois' if period_clamped else ''

        if date_from_local_dt:
            date_from = date_from_local_dt.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
        if date_to_local_dt:
            date_to = date_to_local_dt.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
        has_date_from = bool(date_from_local_dt)

        # Coercition par _bounded_int : un dict ou une liste passes en id
        # atterrissaient tels quels dans le domaine ORM (erreur psycopg2 -> 500).
        # Une valeur non coercible retombe sur 0, donc filtre absent.
        _pg_int_max = 2 ** 31 - 1
        pos_config_id = self._bounded_int(filters.get('pos_config_id'), 0, 0, _pg_int_max)
        user_id = self._bounded_int(filters.get('user_id'), 0, 0, _pg_int_max)

        # Construire le domaine de base à partir des filtres
        base_domain = []
        if pos_config_id:
            base_domain.append(('config_id', '=', pos_config_id))
        if user_id:
            base_domain.append(('user_id', '=', user_id))

        # Domaine temporel — bati uniquement sur les dates reellement parsees
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

        # Dates du jour (now_local calcule en tete de methode)
        _today_local_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        _today_local_end = now_local.replace(hour=23, minute=59, second=59, microsecond=0)
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

        # --- Graphique CA (granularite adaptative, nombre de points borne) ---
        if has_date_from and date_from_local_dt:
            chart_start_local = date_from_local_dt
        else:
            chart_start_local = (
                window_end_local - timedelta(days=chart_days - 1)
            ).replace(hour=0, minute=0, second=0, microsecond=0)

        chart_domain = base_domain + date_domain
        if not has_date_from:
            chart_domain += [(
                'date_order', '>=',
                chart_start_local.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S'),
            )]

        # Une etendue de 6 mois ne se trace pas comme 7 jours : la granularite
        # s'adapte pour que le nombre de points reste lisible et borne.
        span_days = (window_end_local.date() - chart_start_local.date()).days + 1
        if span_days <= 31:
            granularity, gran_suffix = 'day', ''
        elif span_days <= 182:
            granularity, gran_suffix = 'week', ' · par semaine'
        else:
            granularity, gran_suffix = 'month', ' · par mois'

        def _bucket_key(local_dt):
            """Cle de regroupement, identique cote read_group et cote iteration."""
            if granularity == 'day':
                return local_dt.strftime('%Y-%m-%d')
            if granularity == 'week':
                # Normalise sur le lundi : les tranches d'Odoo sont espacees de 7
                # jours, la normalisation reste injective quel que soit le
                # premier jour de semaine configure
                return (local_dt - timedelta(days=local_dt.weekday())).strftime('%Y-%m-%d')
            return local_dt.strftime('%Y-%m')

        chart_groups = PosOrder.read_group(
            chart_domain,
            fields=['amount_total:sum', 'date_order'],
            groupby=['date_order:%s' % granularity],
        )
        chart_by_date = {}
        for g in chart_groups:
            rng = g.get('__range', {}).get('date_order:%s' % granularity, {})
            from_str = rng.get('from', '')
            if from_str:
                utc_dt = datetime.strptime(from_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
                local_dt = utc_dt.astimezone(user_tz)
                bucket = chart_by_date.setdefault(
                    _bucket_key(local_dt), {'total': 0, 'count': 0},
                )
                bucket['total'] = round(bucket['total'] + (g.get('amount_total', 0) or 0), 2)
                bucket['count'] += g.get('__count', 0)

        # Generation des tranches (les vides comprises : un jour sans vente doit
        # rester visible comme une barre a zero)
        # Iteration sur des dates nues : ajouter un timedelta a un datetime pytz
        # peut deriver d'une heure au passage d'un changement d'heure et decaler
        # une tranche. Madagascar n'a pas de DST, d'autres fuseaux si.
        buckets = []
        end_date = window_end_local.date()
        if granularity == 'month':
            cursor = chart_start_local.date().replace(day=1)
            while cursor <= end_date:
                buckets.append((cursor.strftime('%Y-%m'), cursor.strftime('%m/%Y')))
                cursor = (cursor.replace(day=28) + timedelta(days=7)).replace(day=1)
        else:
            step = 7 if granularity == 'week' else 1
            cursor = chart_start_local.date()
            if granularity == 'week':
                cursor = cursor - timedelta(days=cursor.weekday())
            while cursor <= end_date:
                buckets.append((_bucket_key(cursor), cursor.strftime('%d/%m')))
                cursor = cursor + timedelta(days=step)

        # Plafond dur, defense en profondeur uniquement. Depuis le clamp
        # d'etendue a 366 j, le maximum REEL atteignable est 31 points (31 j en
        # granularite jour) : 32-182 j passent en semaine (<= 27 points) et
        # 183-367 j en mois (<= 14 : le clamp autorise 367 jours inclusifs, qui
        # peuvent toucher 14 mois calendaires, ex 31/12/2025 -> 01/01/2027).
        # C'est ce clamp qui regle la lisibilite a la source ; overflow-x cote
        # CSS absorbe le residu.
        max_points = 40
        truncated = len(buckets) > max_points
        if truncated:
            buckets = buckets[-max_points:]

        daily_ca = []
        for key, label in buckets:
            data = chart_by_date.get(key, {})
            daily_ca.append({
                'date': label,
                'total': data.get('total', 0),
                'count': data.get('count', 0),
            })

        chart_period = self._period_label(
            chart_start_local, window_end_local, bool(date_to_local_dt),
            suffix=gran_suffix + (
                ' · %s derniers points' % max_points if truncated else ''
            ) + clamp_suffix,
        )

        # --- Statistiques période récente ---
        # Cette fenetre est la seule de l'ecran dont les ids de commandes sont
        # MATERIALISES (search_read ci-dessous), puis reinjectes dans un
        # read_group et dans le SQL brut du PdV dominant. Sa taille gouverne
        # donc a elle seule la volumetrie de tout ce bloc : elle doit rester
        # bornee, quelle que soit l'etendue demandee par les filtres.
        recent_domain = base_domain + date_domain
        # Etendue maximale de la fenetre. Plancher a 31 jours : avec le seul
        # recent_days (defaut 30), un filtre sur un mois de 31 jours perdrait
        # son premier jour et le libelle annoncerait "du 02/03", ce qui se lit
        # comme un bug. Au-dela, c'est le reglage utilisateur qui commande,
        # exactement comme sur l'ecran non filtre.
        recent_span_days = max(recent_days, 31)
        recent_truncated = False
        if not has_date_from:
            # date_domain porte deja une borne basse quand date_from est fourni.
            # Les cumuler ANDait deux '>=' : la borne effective devenait le max des
            # deux, et une periode passee (ex 01/03 -> 31/03 avec recent_days=30)
            # donnait un ensemble vide silencieux, KPI du haut restant remplis.
            # Normalise a minuit comme chart_start_local : sans ca le libelle
            # annonce "du 28/06" pour une fenetre demarrant le 28/06 a 14h30.
            # Consequence assumee : la fenetre passe de N x 24h glissantes a N
            # jours calendaires (elargissement de quelques heures, jamais moins).
            recent_start_local = (
                window_end_local - timedelta(days=recent_days)
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            recent_domain += [(
                'date_order', '>=',
                recent_start_local.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S'),
            )]
        else:
            recent_start_local = date_from_local_dt
            # Borne volumetrique restauree. Le point CRITIQUE est l'ancrage :
            # cette borne se calcule sur window_end_local (fin de la periode
            # filtree), JAMAIS sur now. C'est l'ancrage sur now qui produisait
            # l'ecran vide silencieux corrige precedemment — pour une periode
            # passee, "now - recent_days" tombe APRES la fin de la periode et
            # ANDait un ensemble vide. Ancree sur la fin de fenetre, la borne
            # est toujours a l'interieur de la periode : une periode passee
            # rend ses donnees, seule son ETENDUE est rognee.
            _recent_floor = (
                window_end_local - timedelta(days=recent_span_days)
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            if recent_start_local < _recent_floor:
                recent_start_local = _recent_floor
                recent_truncated = True
                recent_domain += [(
                    'date_order', '>=',
                    recent_start_local.astimezone(pytz.utc).strftime(
                        '%Y-%m-%d %H:%M:%S'),
                )]
        # Compromis assume : on borne la FENETRE plutot que de supprimer la
        # materialisation des ids (jointure sur la sous-requete du Query ORM).
        # La liste d'ids est ce qui garantit que le read_group et le SQL brut
        # d'en dessous ne voient que des commandes deja passees par les regles
        # d'enregistrement de pos.order (cf. "NB ACL" plus bas) ; deplacer cette
        # garantie dans du SQL compose changerait le perimetre de securite d'un
        # bloc deja audite. La semantique du bloc ("statistiques periode
        # recente", "top produits recents") autorise la borne, et le libelle
        # de periode la rend visible a l'ecran.
        # Un seul passage : search_read renvoie deja les ids, le PosOrder.search()
        # qui suivait rejouait la meme requete complete pour rien
        recent_orders = PosOrder.search_read(
            recent_domain,
            fields=['id', 'amount_total'],
        )
        total_orders_recent = len(recent_orders)
        total_ca_recent = sum(o['amount_total'] for o in recent_orders)

        # --- Top produits ---
        recent_order_ids = [o['id'] for o in recent_orders]
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
                        # PdV dominant (rempli plus bas, '' / 0 si indeterminable)
                        'top_pos': '',
                        'top_pos_share': 0.0,
                    })

        # --- PdV principal par produit du top ---
        # Modified by: odoo-frontend agent — 2026-07-28 — Colonne PdV principal top produits
        # Une seule agregation produit x config sur EXACTEMENT les memes lignes que
        # top_products (recent_order_ids).
        # NB ACL : ces ids de commandes sont passes par l'ORM, donc par les regles
        # de pos.order. Le raccourci "donc les lignes aussi" ne vaut que parce que
        # pos_order_line.company_id est un related STOCKE de la commande : ne pas
        # generaliser ce SQL a un modele dont les regles ne derivent pas du parent.
        # pos.order.line n'a pas de config_id : read_group ne peut pas grouper par
        # chemin relationnel, d'ou le SQL groupe unique (evite un N+1 par produit).
        if top_products:
            top_product_ids = [p['id'] for p in top_products]
            request.env.flush_all()
            request.env.cr.execute(
                """
                SELECT l.product_id, o.config_id, SUM(l.qty) AS qty
                  FROM pos_order_line l
                  JOIN pos_order o ON o.id = l.order_id
                 WHERE l.order_id IN %s
                   AND l.product_id IN %s
                   AND o.config_id IS NOT NULL
                 GROUP BY l.product_id, o.config_id
                """,
                (tuple(recent_order_ids), tuple(top_product_ids)),
            )
            qty_by_product = {}
            seen_config_ids = set()
            for product_id, cfg_id, qty in request.env.cr.fetchall():
                qty_by_product.setdefault(product_id, []).append((cfg_id, float(qty or 0)))
                seen_config_ids.add(cfg_id)
            config_names = {}
            if seen_config_ids:
                # search_read : les regles d'enregistrement filtrent silencieusement
                # (pas d'AccessError si un PdV n'est pas visible par l'utilisateur)
                config_names = {
                    c['id']: c['name']
                    for c in request.env['pos.config'].search_read(
                        [('id', 'in', list(seen_config_ids))], fields=['name'],
                    )
                }
            for prod in top_products:
                entries = qty_by_product.get(prod['id'], [])
                if not entries:
                    continue
                # Denominateur = la qte AFFICHEE dans la colonne d'a cote, pas une
                # somme recalculee depuis le SQL. Les deux coincident aujourd'hui,
                # mais ancrer sur la valeur affichee rend structurel l'invariant
                # "le % se rapporte au chiffre de la ligne" : si un filtre est un
                # jour ajoute d'un seul cote, le % devient faux au lieu de mentir
                # silencieusement. Le IS NOT NULL du SQL reste une garde defensive.
                total_qty = prod['qty'] or 0
                if total_qty <= 0:
                    # Qte nette nulle ou negative (retours) : pas de PdV dominant
                    continue
                # Departage stable : plus grande qte, puis plus petit id de config
                best_cfg_id, best_qty = max(entries, key=lambda e: (e[1], -e[0]))
                if best_qty <= 0:
                    continue
                cfg_name = config_names.get(best_cfg_id, '')
                if not cfg_name:
                    # PdV filtre par les record rules : ne pas divulguer sa part,
                    # le ratio de concentration est deja une information
                    continue
                prod['top_pos'] = cfg_name
                # Pas de plafond a 100 : une part > 100 % signale qu'un autre PdV est
                # en retour net sur la periode. C'est une anomalie que la direction
                # doit voir, le frontend la met en evidence (badge + title).
                prod['top_pos_share'] = round(best_qty / total_qty * 100, 1)

        # Periode REELLEMENT couverte par top_products / stats recentes. Meme
        # mecanisme que le graphique (_period_label), mais valeur distincte : sans
        # filtre date les deux fenetres par defaut different (chart_days vs
        # recent_days). Une cle unique mentirait sur l'ecran non filtre.
        top_products_period = self._period_label(
            recent_start_local, window_end_local, bool(date_to_local_dt),
            suffix=clamp_suffix + (
                ' · %d derniers jours de la période' % recent_span_days
                if recent_truncated else ''
            ),
        )

        # --- CA par PdV (aujourd'hui par défaut, ou période filtrée) ---
        # Meme regle que recent_domain : la fenetre par defaut (1 jour) s'ancre
        # sur la fin de fenetre, jamais sur aujourd'hui. Sans borne basse, un
        # date_to seul declenchait un search_read sur TOUT l'historique PdV,
        # puis un read_group sur toutes leurs lignes, puis une boucle Python —
        # atteignable en remplissant le seul champ "Date fin".
        ca_pos_domain = base_domain[:]
        if has_date_from:
            ca_pos_domain += date_domain
            ca_pos_start_local = date_from_local_dt
        else:
            ca_pos_start_local = window_end_local.replace(
                hour=0, minute=0, second=0, microsecond=0)
            ca_pos_domain += [(
                'date_order', '>=',
                ca_pos_start_local.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S'),
            )]
            ca_pos_domain += [(
                'date_order', '<=',
                date_to or today_end,
            )]
        ca_pos_period = self._period_label(
            ca_pos_start_local, window_end_local, bool(date_to_local_dt),
            suffix=clamp_suffix,
        )
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

        # --- Comparatif M/M-1 et CA vs budget ---
        # Modified by: odoo-frontend agent — 2026-07-31
        # Modified by: odoo-backend agent — 2026-08-03 — ces deux blocs SUIVENT
        #   desormais le filtre de date (changement de specification client)
        #
        # ANCRAGE (regle tranchee par le client, a ne pas reinterpreter) : le
        # mois de reference M est le mois dans lequel tombe la date de FIN de la
        # periode filtree ; il est compare au mois calendaire PRECEDENT M-1.
        # Toujours DEUX MOIS COMPLETS, jamais une demi-periode :
        #     01/06 -> 30/06 : mai vs juin      01/03 -> 30/06 : mai vs juin
        #     15/06 -> 30/06 : mai vs juin      01/06 -> 10/06 : mai vs juin
        #     aucun filtre   : mois courant vs mois precedent (inchange)
        #
        # window_end_local porte deja exactement cette semantique (date_to si
        # fourni, sinon maintenant), d'ou l'ancrage dessus et non sur now_local.
        # CAS date_from SANS date_to : la periode court jusqu'a maintenant, donc
        # le mois d'ancrage est le mois COURANT — identique au cas sans filtre.
        # Rien d'absurde : la fin de la periode EST aujourd'hui, et la regle
        # « mois de la date de fin » s'applique telle quelle. Consequence
        # assumee : « du 01/01 a aujourd'hui » et « aucun filtre » comparent les
        # deux memes mois. Un date_to SEUL ancre sur le mois de date_to, meme
        # regle. Le libelle de periode dit dans tous les cas quels mois sont
        # compares, donc l'ecran ne peut pas laisser croire autre chose.
        #
        # VOLUMETRIE : la fenetre agregee reste bornee a deux mois calendaires
        # (<= 62 jours) quelle que soit l'etendue du filtre pose. date_domain
        # n'est DELIBEREMENT pas ajoute ici : un filtre de 366 jours elargirait
        # sinon cette agregation. Les filtres PdV et caissier, eux, s'appliquent
        # — ils sont portes par base_domain.
        #
        # UNE seule agregation sert les deux blocs : un read_group (jour x PdV)
        # sur la fenetre "1er de M-1 -> fin de M". Le comparatif s'obtient en
        # sommant sur les PdV, le realise par PdV en sommant sur les jours de M.
        # Deux read_group auraient rescanne deux fois pos_order, qui est la
        # seule partie couteuse ici.
        today_date = now_local.date()
        cur_month_first = today_date.replace(day=1)
        anchor_month_first = window_end_local.date().replace(day=1)
        prev_month_first = (anchor_month_first - timedelta(days=1)).replace(day=1)
        anchor_month_days = calendar.monthrange(
            anchor_month_first.year, anchor_month_first.month)[1]
        prev_month_days = calendar.monthrange(
            prev_month_first.year, prev_month_first.month)[1]
        anchor_month_last = anchor_month_first.replace(day=anchor_month_days)

        # Etat du mois d'ancrage — TROIS cas, pas deux : le filtre peut porter
        # sur un mois A VENIR, qui n'est ni clos ni en cours. C'est le serveur
        # qui tranche et non le frontend : lui faire comparer des dates
        # dupliquerait la regle d'ancrage dans les deux ecrans qui consomment ce
        # payload, et les ferait deriver a la premiere correction.
        #
        # month_state reste INTERNE : le payload expose deux booleens
        # (is_closed_month, is_future_month), affirmes par le serveur. « Ni l'un
        # ni l'autre » = mois en cours ; le frontend n'a donc rien a deriver, et
        # surtout aucune date a comparer.
        if anchor_month_last < today_date:
            month_state = 'past'
        elif anchor_month_first > today_date:
            month_state = 'future'
        else:
            month_state = 'current'
        is_closed_month = month_state == 'past'
        is_future_month = month_state == 'future'

        # localize() et non replace(tzinfo=...) : seul localize() choisit le bon
        # decalage a une bascule d'heure d'ete. Madagascar n'en a pas, mais ce
        # controleur suit le fuseau de l'utilisateur, pas celui du serveur.
        cmp_start = user_tz.localize(
            datetime.combine(prev_month_first, datetime.min.time())
        ).astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
        if month_state == 'current':
            # Borne haute STRICTEMENT inchangee sur le cas sans filtre, qui est
            # celui de l'ecran par defaut : today_end, deja calcule dans le
            # fuseau de l'utilisateur en tete de methode.
            cmp_end = today_end
        else:
            cmp_end = user_tz.localize(
                datetime.combine(
                    anchor_month_last, datetime.max.time()
                ).replace(microsecond=0)
            ).astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')

        cmp_groups = PosOrder.read_group(
            base_domain + [
                ('date_order', '>=', cmp_start),
                ('date_order', '<=', cmp_end),
            ],
            fields=['config_id', 'amount_total', 'date_order'],
            groupby=['date_order:day', 'config_id'],
            lazy=False,
        )
        ca_by_local_day = {}
        actual_by_config = {}
        budget_config_names = {}
        for g in cmp_groups:
            rng = g.get('__range', {}).get('date_order:day', {})
            from_str = rng.get('from', '')
            if not from_str:
                continue
            local_day = datetime.strptime(
                from_str, '%Y-%m-%d %H:%M:%S'
            ).replace(tzinfo=pytz.utc).astimezone(user_tz).date()
            amount = g.get('amount_total', 0) or 0
            # += et non = : a une bascule d'heure, deux tranches UTC peuvent
            # retomber sur la meme date locale (meme raison que le graphique).
            ca_by_local_day[local_day] = ca_by_local_day.get(local_day, 0) + amount
            if (anchor_month_first <= local_day <= anchor_month_last
                    and g.get('config_id')):
                cfg_id = g['config_id'][0]
                actual_by_config[cfg_id] = actual_by_config.get(cfg_id, 0) + amount
                budget_config_names[cfg_id] = g['config_id'][1]

        # Nombre de jours de M deja advenus. Sert de base au « meme nombre de
        # jours » du mois precedent et au prorata du budget.
        #   - mois PASSE  : le mois entier, il est ecoule a 100 %,
        #   - mois COURANT: jour du mois d'aujourd'hui (comportement inchange),
        #   - mois FUTUR  : 0, aucun jour n'a couru.
        if month_state == 'past':
            elapsed_day_count = anchor_month_days
        elif month_state == 'future':
            elapsed_day_count = 0
        else:
            elapsed_day_count = today_date.day

        # Mois de longueurs differentes : l'axe couvre le plus long des deux.
        # Une case sans equivalent vaut None, JAMAIS 0 :
        #   - jour non encore advenu (13 -> 31 quand on est le 12),
        #   - jour inexistant du mois compare (31 quand il en compte 30).
        # Un 0 se lirait "ce jour-la on n'a rien vendu", ce qui serait faux. Le
        # frontend ne trace aucune barre pour une valeur nulle.
        #
        # Le test « jour advenu » porte sur la DATE REELLE et non plus sur un
        # numero de jour compare a today_day : depuis l'ancrage sur la periode
        # filtree, M n'est plus forcement le mois courant, et M-1 peut lui-meme
        # l'etre (filtre pose sur un mois a venir). L'ancienne forme, appliquee
        # au seul mois courant, aurait trace a 0 les jours a venir de M-1.
        def _compare_day_value(month_first, month_days, day_num):
            if day_num > month_days:
                return None
            day = month_first.replace(day=day_num)
            if day > today_date:
                return None
            return round(ca_by_local_day.get(day, 0), 2)

        compare_days = []
        for day_num in range(1, max(anchor_month_days, prev_month_days) + 1):
            compare_days.append({
                'day': day_num,
                'current': _compare_day_value(
                    anchor_month_first, anchor_month_days, day_num),
                'previous': _compare_day_value(
                    prev_month_first, prev_month_days, day_num),
            })

        total_current = round(sum(
            d['current'] for d in compare_days if d['current'] is not None), 2)
        # Base de comparaison honnete : les MEMES jours du mois precedent.
        # Comparer 12 jours de juillet aux 30 jours de juin afficherait un
        # effondrement qui n'existe pas. Le total complet de M-1 reste renvoye
        # a part, comme reference de fin de mois.
        total_previous_same = round(sum(
            d['previous'] for d in compare_days
            if d['previous'] is not None and d['day'] <= elapsed_day_count), 2)
        total_previous_full = round(sum(
            d['previous'] for d in compare_days if d['previous'] is not None), 2)
        delta_pct = None
        if total_previous_same:
            delta_pct = round(
                (total_current - total_previous_same) / total_previous_same * 100, 1)

        # Un filtre de date est pose des qu'UNE des deux bornes a ete parsee :
        # date_to seul deplace l'ancrage tout autant que date_from.
        date_filter_active = bool(date_from_local_dt or date_to_local_dt)
        anchor_month_label = _month_label(anchor_month_first)

        compare_notes = []
        if anchor_month_days != prev_month_days:
            compare_notes.append(
                "les deux mois n'ont pas le même nombre de jours : "
                "un jour sans équivalent n'est pas tracé")
        if month_state == 'future':
            compare_notes.append(
                "%s n'a pas encore commencé : aucun réalisé à comparer"
                % anchor_month_label)
        # Le mois en cours peut etre l'un OU l'autre des deux mois traces : M
        # dans le cas nominal, mais M-1 quand le filtre porte sur un mois a
        # venir. La note vaut dans les deux cas — elle explique les jours non
        # traces, quelle que soit la serie a laquelle ils appartiennent.
        if cur_month_first in (anchor_month_first, prev_month_first):
            if today_date.day < calendar.monthrange(
                    today_date.year, today_date.month)[1]:
                compare_notes.append(
                    "les jours non encore advenus du mois en cours ne sont "
                    "pas tracés")
            compare_notes.append("le jour en cours est partiel")
        if date_filter_active:
            # Le cas le plus deroutant est un filtre plus large ou plus etroit
            # qu'un mois (01/03 -> 30/06, ou 01/06 -> 10/06) : la comparaison
            # porte quand meme sur deux mois pleins. Le dire evite de lire les
            # totaux comme ceux de la periode filtree.
            compare_notes.append(
                "la comparaison porte sur deux mois complets, pas sur "
                "l'étendue exacte de la période filtrée")

        prev_month_label = _month_label(prev_month_first)
        # Suffixe commun au libelle de periode : il dit d'ou vient le couple de
        # mois des qu'une borne de date a ete posee.
        compare_period_suffix = (
            " · d'après la fin de la période filtrée" if date_filter_active else '')

        compare_months = {
            'current_label': anchor_month_label,
            'previous_label': prev_month_label,
            'days': compare_days,
            'total_current': total_current,
            'total_previous_same': total_previous_same,
            'total_previous_full': total_previous_full,
            'delta_pct': delta_pct,
            'elapsed_days': elapsed_day_count,
            'current_month_days': anchor_month_days,
            'previous_month_days': prev_month_days,
            # Etat du mois de reference, AFFIRME par le serveur. Expose ICI
            # aussi (et pas seulement sur le bloc budget) parce que chaque bloc
            # doit etre lisible seul, et parce que le frontend en a besoin pour
            # les memes raisons : « à date » et « mêmes N jours » n'ont pas de
            # sens sur un mois clos, ou N vaut le mois entier. DEUX booleens et
            # non un : un mois a venir n'est ni clos ni en cours. Les deux faux
            # = mois en cours ; le frontend n'a rien a deriver.
            'is_closed_month': is_closed_month,
            'is_future_month': is_future_month,
            # M-1 EST-IL LE MOIS EN COURS ? Depuis l'ancrage sur la periode
            # filtree, oui c'est possible : un filtre pose sur un mois a venir
            # fait de M-1 le mois courant (date_to au 15/09 le 3 aout -> M =
            # septembre, M-1 = aout). Le total complet de M-1 n'est alors PAS
            # un mois complet, et l'etiqueter « complet » ferait lire 3 jours de
            # CA comme un mois entier — a deux lignes de la note « le jour en
            # cours est partiel », qui dit le contraire.
            # AFFIRME par le serveur, meme regle que is_closed_month /
            # is_future_month : le frontend a INTERDICTION de le deriver. Il ne
            # se deduit d'ailleurs pas des deux autres — sur un mois d'ancrage
            # en cours, M-1 est toujours clos, et les deux booleens sont faux
            # dans les deux situations.
            'previous_is_current_month': prev_month_first == cur_month_first,
            # Le libelle nomme les mois REELLEMENT compares, dans l'ordre
            # « M vs M-1 » — celui de la ligne de chiffres ET celui que mesure
            # delta_pct. L'ordre chronologique inverse (M-1 vs M) faisait lire
            # au delta le sens oppose : « juillet vs aout · ▼ -96,6 % » se
            # comprenait « juillet en baisse », alors que c'est aout qui est
            # bas. Trois elements du meme ecran doivent enoncer le meme ordre.
            # (L'axe du graphique, lui, reste chronologique : c'est un axe de
            # temps, et sa legende nomme ses deux series.)
            # Il portait « hors filtre de date » : cette mention affirmait
            # exactement le contraire du comportement actuel, elle devait
            # disparaitre partout.
            'period_label': '%s vs %s%s' % (
                anchor_month_label, prev_month_label, compare_period_suffix),
            # Ancrage TEXTUEL du delta, pour titre / aria-label du badge.
            # Sans lui, le sens de l'evolution n'est porte que par une fleche :
            # aucun lecteur (ni aucun lecteur d'ecran) ne peut dire QUEL mois
            # monte ou descend. Enonce le sens de la mesure — delta_pct compare
            # bien le mois d'ancrage AU mois precedent, jamais l'inverse.
            'delta_label': '%s par rapport à %s' % (
                anchor_month_label, prev_month_label),
            'note': ' · '.join(compare_notes),
        }

        # --- CA realise vs budget du mois ---
        # Le budget n'a AUCUNE dimension caissier : il est defini par point de
        # vente. Or base_domain porte le filtre caissier et alimente cmp_groups,
        # donc actual_by_config : avec « Caissier = X », le realise ne compte que
        # les ventes de X, face a un budget reste plein PdV. Le taux d'atteinte
        # s'effondre mecaniquement (de l'ordre de 8 % au lieu de 95 %), tous les
        # PdV passent au rouge et le tri « qui decroche » ne classe plus que du
        # bruit. On NEUTRALISE donc le bloc plutot que d'afficher une
        # comparaison fausse — le message et le libelle de periode disent
        # pourquoi, sinon l'absence de donnees se lirait comme une panne.
        # Le comparatif M/M-1 ci-dessus n'est PAS concerne : les deux mois
        # subissent le meme filtre, le rapport entre eux reste honnete.
        budget_off_cashier = bool(user_id)
        if budget_off_cashier:
            # Statut 'ok' et non un 5e statut : le contrat n'en compte que
            # quatre, et « rien a afficher + message » est deja la convention
            # de ce bloc (cas "aucun budget saisi"). L'appel au module de
            # budget est economise, il ne servirait a rien.
            budget_status, budget_map = 'ok', {}
            budget_ids = set()
        else:
            # config_ids : liste NON VIDE ou None. Passer [] demanderait "aucun
            # PdV" au module de budget et renverrait {} — le bloc afficherait
            # "aucun budget saisi" en permanence.
            # Meme ancrage que le comparatif (decision client) : le budget
            # interroge est celui du mois de fin de periode filtree, pas celui
            # du mois courant. Filtre juin -> objectif de juin contre realise
            # de juin, les deux issus du meme anchor_month_first.
            budget_status, budget_map = self._get_pos_budget(
                anchor_month_first, [pos_config_id] if pos_config_id else None)

            budget_ids = set(actual_by_config) | set(budget_map)
            if pos_config_id:
                budget_ids &= {pos_config_id}
        missing_names = [i for i in budget_ids if i not in budget_config_names]
        if missing_names:
            # search_read : les regles d'enregistrement filtrent silencieusement.
            # Un PdV budgete mais invisible pour cet utilisateur n'apparaitra
            # pas — c'est voulu, on ne divulgue pas son objectif de CA.
            for cfg in request.env['pos.config'].search_read(
                    [('id', 'in', missing_names)], fields=['name']):
                budget_config_names[cfg['id']] = cfg['name']
        # Le module ne prorate PAS : le montant renvoye est le budget PLEIN
        # du mois. Comparer 12 jours de realise a un budget mensuel plein donne
        # un taux d'atteinte de ~40 % qui ne veut rien dire et que la direction
        # lirait comme une alerte — exactement le piege deja corrige sur le
        # comparatif M-1. Le budget est donc PRORATISE en jours CALENDAIRES
        # (les PdV ouvrent tous les jours ; des jours ouvres fausseraient le
        # taux), et la regle de prorata est affichee a l'ecran : un taux
        # d'atteinte dont on ignore la base est pire qu'inutile.
        #
        # Depuis l'ancrage sur la periode filtree, le mois compare n'est plus
        # forcement le mois en cours : le prorata se decline en TROIS cas.
        #
        # 1. Mois PASSE — il est ecoule a 100 %. Prorater n'a plus aucun sens :
        #    budget_todate vaut le budget PLEIN du mois, donc pct_todate ==
        #    pct_month, et « atteinte » et « rythme » se confondent. Continuer
        #    d'afficher un rythme laisserait croire a un calcul qui n'a plus
        #    lieu d'etre — d'ou is_closed_month, expose au frontend pour qu'il
        #    change ses libelles sans refaire ce raisonnement de son cote.
        # 2. Mois COURANT — comportement inchange. Le jour en cours COURT, il
        #    n'est pas ecoule : le compter pour un jour plein (today_day /
        #    jours du mois) exigeait 3/31 du budget le 3 aout a 09 h alors que
        #    2,4 jours seulement avaient couru, et une journee entiere des le
        #    1er a 00 h 05. Tous les PdV etaient donc structurellement un jour
        #    en retard — badge rouge chaque matin. On compte les jours REVOLUS
        #    plus la fraction ecoulee du jour courant, dans le fuseau de
        #    l'utilisateur (now_local), pas celui du serveur.
        # 3. Mois FUTUR — le filtre peut porter sur un mois a venir : 0 %
        #    ecoule, donc budget_todate a 0 et AUCUN taux a date. La division
        #    par zero est impossible : pace_ratio a pour denominateur le nombre
        #    de jours du mois (jamais nul), et tous les taux qui derivent de
        #    budget_todate sont deja gardes (`if budget_todate else None`), ce
        #    qui rend None et non l'infini. Meme garde que dans les premieres
        #    minutes du 1er du mois, ou le ratio vaut deja ~0.
        if month_state == 'past':
            elapsed_days_frac = float(anchor_month_days)
        elif month_state == 'future':
            elapsed_days_frac = 0.0
        else:
            elapsed_seconds = (
                now_local.hour * 3600 + now_local.minute * 60 + now_local.second)
            elapsed_days_frac = (
                elapsed_day_count - 1 + elapsed_seconds / 86400.0)
        pace_ratio = elapsed_days_frac / float(anchor_month_days)
        budget_rows = []
        for cfg_id in budget_ids:
            name = budget_config_names.get(cfg_id)
            if not name:
                continue
            actual = round(actual_by_config.get(cfg_id, 0), 2)
            # « Objectif saisi a 0 » et « aucun objectif saisi » donnaient tous
            # deux un montant de 0 et un pourcentage a None : indiscernables
            # cote frontend, qui affichait "Aucun budget saisi" sur un PdV dont
            # l'objectif de 0 est justement une saisie volontaire (PdV ferme sur
            # le mois — invariant protege cote module par
            # test_zero_amount_allowed). Le contrat du module ABSENTE les mois
            # non budgetes du mapping au lieu d'y mettre 0 : c'est exactement
            # cette distinction que porte has_budget, et lui seul. Le 0 ci-
            # dessous reste une valeur interne pour le cas "absent".
            has_budget = cfg_id in budget_map
            budget_month = round(budget_map.get(cfg_id, 0), 2)
            budget_todate = round(budget_month * pace_ratio, 2)
            budget_rows.append({
                'id': cfg_id,
                'name': name,
                'actual': actual,
                # Seul discriminant entre "objectif de 0" et "pas d'objectif" :
                # les deux montants et les deux pourcentages sont identiques.
                'has_budget': has_budget,
                # Deux budgets, nommes sans ambiguite : celui de la periode
                # ecoulee (base du taux d'atteinte) et celui du mois entier
                # (l'objectif, qui ne bouge pas).
                'budget_todate': budget_todate,
                'budget_month': budget_month,
                # None des que le denominateur est nul — objectif absent comme
                # objectif saisi a 0. Un realise > 0 contre un objectif de 0 n'a
                # pas de pourcentage fini, et 0/0 n'en a pas davantage : mieux
                # vaut ne rien afficher qu'un infini ou un 0 % faux. C'est
                # has_budget qui dit lequel des deux cas on regarde.
                'pct_todate': round(
                    actual / budget_todate * 100, 1) if budget_todate else None,
                'pct_month': round(
                    actual / budget_month * 100, 1) if budget_month else None,
            })
        budget_has_any = any(r['has_budget'] for r in budget_rows)
        budget_total_actual = round(sum(r['actual'] for r in budget_rows), 2)
        budget_total_month = round(sum(r['budget_month'] for r in budget_rows), 2)
        # Somme de la COLONNE affichee, et non re-prorata du total mensuel :
        # round(somme) et somme(arrondis) different, et "Budget a date" est
        # affiche a cote de la colonne qu'il resume. Une synthese qui n'est pas
        # la somme de sa colonne se lit comme une erreur de calcul.
        budget_total_todate = round(sum(r['budget_todate'] for r in budget_rows), 2)
        budget_total_pct_todate = round(
            budget_total_actual / budget_total_todate * 100, 1
        ) if budget_total_todate else None
        budget_total_pct_month = round(
            budget_total_actual / budget_total_month * 100, 1
        ) if budget_total_month else None
        # Tri par taux d'atteinte CROISSANT : les PdV qui decrochent en tete.
        # Les autres blocs de l'ecran classent par montant decroissant ("qui
        # pese le plus"), mais la question de celui-ci est "qui est en retard" —
        # et comme la liste defile, son haut est la seule partie vue a coup sur.
        # Les PdV sans budget n'ont pas de taux : ils ferment la liste sans en
        # disparaitre. Ceux dont l'objectif saisi vaut 0 n'en ont pas davantage
        # (denominateur nul) et les rejoignent en fin de liste : has_budget
        # reste le seul moyen de les distinguer, y compris a l'affichage.
        budget_rows.sort(key=lambda r: (
            r['pct_todate'] is None, r['pct_todate'] or 0, -r['actual'], r['name'],
        ))

        # Message d'indisponibilite calcule ICI et non dans les frontends : les
        # deux ecrans (widget OWL et page /direction) rendent le meme payload,
        # une formulation par ecran finirait par diverger. Message vide = il y a
        # quelque chose a afficher.
        #
        # « Aucun budget saisi » ne doit pas couvrir « aucun PdV visible » : des
        # PdV budgetes peuvent avoir ete ecartes juste au-dessus par les regles
        # d'enregistrement de pos.config (`if not name: continue`). L'ancien
        # message designait alors la mauvaise cause et envoyait la direction
        # verifier une saisie pourtant faite.
        budgeted_hidden = bool(
            (set(budget_map) & budget_ids) - {r['id'] for r in budget_rows})
        if budget_off_cashier:
            budget_message = ("Comparaison au budget désactivée : un filtre "
                              "caissier est actif, or le budget est défini par "
                              "point de vente, sans dimension caissier.")
        elif budget_status == 'missing':
            budget_message = ("Module budget non installé — aucun objectif "
                              "de CA à comparer.")
        elif budget_status == 'forbidden':
            # Les lignes restent construites dans ce cas (le realise seul, aucun
            # montant de budget) par coherence avec 'missing', et parce que rien
            # n'y fuit. Le frontend actuel ne les exploite pas : il remplace tout
            # le bloc par son rendu cadenas des que le statut vaut 'forbidden'.
            # C'est donc du calcul mort cote serveur — assume, pas un oubli : le
            # supprimer ferait dependre la forme du payload du rendu d'un
            # frontend, alors que deux ecrans consomment ce meme payload.
            budget_message = "Budgets réservés à la direction."
        elif budget_status == 'error':
            budget_message = ("Budgets indisponibles : le module est présent "
                              "mais ses données n'ont pas pu être lues.")
        elif budget_has_any:
            budget_message = ''
        elif budgeted_hidden:
            budget_message = ("Aucun budget à afficher pour %s : les budgets "
                              "saisis portent sur des points de vente auxquels "
                              "vous n'avez pas accès." % anchor_month_label)
        else:
            budget_message = "Aucun budget saisi pour %s." % anchor_month_label

        # Legende du taux, declinee sur les trois etats du mois. Sur un mois
        # clos, parler de « rythme » ou de « budget proratisé » decrirait un
        # calcul qui n'a plus lieu d'etre ; sur un mois a venir, il n'y a
        # simplement rien a proratiser.
        if month_state == 'past':
            budget_note = ("%s est clos : le mois est écoulé à 100 %%, le "
                           "pourcentage est donc le taux d'atteinte du budget "
                           "du mois entier — il n'y a plus d'avance ni de "
                           "retard de rythme à lire" % anchor_month_label)
        elif month_state == 'future':
            # « aucun taux d'atteinte » etait FAUX et contredisait l'ecran :
            # pct_month vaut bien 0.0 sur un mois a venir (realise nul face a un
            # objectif saisi) et le badge affiche « 0 % du budget » juste
            # au-dessus de cette note. Ce qui n'existe pas sur un mois non
            # commence, c'est le RYTHME : budget_todate vaut 0, donc pct_todate
            # vaut None. C'est ce manque-la qu'il faut nommer.
            budget_note = ("%s n'a pas commencé : aucun budget à date, donc "
                           "aucun rythme à mesurer — le pourcentage affiché est "
                           "le taux d'atteinte de l'objectif du mois entier"
                           % anchor_month_label)
        else:
            budget_note = ("le pourcentage est la part du budget du mois déjà "
                           "réalisée ; sa couleur indique l'avance ou le retard "
                           "sur le budget proratisé à %s/%d jours écoulés · le "
                           "jour en cours est compté au prorata de l'heure"
                           % (('%.1f' % elapsed_days_frac).replace('.', ','),
                              anchor_month_days))

        budget_period_suffix = ''
        if month_state == 'past':
            budget_period_suffix = ' · mois clos'
        elif month_state == 'future':
            budget_period_suffix = ' · mois à venir'
        if budget_off_cashier:
            budget_period_suffix += ' · non comparable avec un filtre caissier'

        budget_vs_actual = {
            'status': budget_status,
            'message': budget_message,
            'month_label': anchor_month_label,
            'rows': budget_rows,
            # Vrai des qu'AU MOINS UNE ligne affichee porte un objectif saisi,
            # fut-il de 0. Le frontend s'en sert pour choisir entre "afficher
            # la colonne budget" et "afficher le message" — le total mensuel ne
            # pouvait pas jouer ce role : un unique PdV budgete a 0 le laisse a
            # 0 et faisait basculer tout le bloc sur "aucun budget saisi".
            'has_any_budget': budget_has_any,
            'total_count': len(budget_rows),
            'total_actual': budget_total_actual,
            'total_budget_todate': budget_total_todate,
            'total_budget_month': budget_total_month,
            'total_pct_todate': budget_total_pct_todate,
            'total_pct_month': budget_total_pct_month,
            'elapsed_days': elapsed_day_count,
            'month_days': anchor_month_days,
            # Etat du mois compare, AFFIRME par le serveur. Le frontend en a
            # besoin pour CHOISIR SES LIBELLES : sur un mois clos, « Réalisé à
            # date (30 j / 30) » et « % du rythme attendu » decrivent un calcul
            # qui n'a plus lieu d'etre. Le frontend a INTERDICTION de les
            # deriver — deux ecrans consomment ce payload et divergeraient a la
            # premiere correction. Les deux faux = mois en cours.
            'is_closed_month': is_closed_month,
            'is_future_month': is_future_month,
            # Deux choses a dire sur un mois EN COURS, parce que chaque jauge
            # porte alors DEUX informations : le chiffre (avancement dans le
            # budget du mois) et sa couleur (avance ou retard sur le budget
            # proratise a date). Sans cette legende, un "40 %" en vert le 12 du
            # mois se lirait comme une incoherence. La regle de prorata y figure :
            # un taux dont on ignore la base est pire qu'inutile. Meme
            # formulation que le comparatif pour le jour partiel — les deux blocs
            # se lisent l'un apres l'autre.
            # Sur un mois CLOS ou A VENIR, cette legende serait fausse : il n'y a
            # plus (ou pas encore) de prorata, donc plus qu'UNE information.
            'note': budget_note,
            # Le libelle ne porte plus « hors filtre de date » : ce bloc SUIT
            # desormais le filtre. Il nomme le mois compare, dit s'il est clos ou
            # a venir (le pourcentage ne se lit pas pareil), et signale le seul
            # filtre que ce bloc ne suit toujours pas — le caissier, faute de
            # dimension caissier dans le budget.
            'period_label': anchor_month_label + budget_period_suffix,
        }

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
            'chart_period': chart_period,
            'total_orders_recent': total_orders_recent,
            'total_ca_recent': round(total_ca_recent, 2),
            'top_products': top_products,
            'top_products_period': top_products_period,
            'ca_by_pos': ca_by_pos,
            'ca_by_pos_period': ca_pos_period,
            'compare_months': compare_months,
            'budget_vs_actual': budget_vs_actual,
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
