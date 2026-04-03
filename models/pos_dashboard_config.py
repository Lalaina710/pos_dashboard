from odoo import models, fields, api


class PosDashboardConfig(models.Model):
    _name = 'pos.dashboard.config'
    _description = 'Configuration Tableau de bord POS'

    name = fields.Char(default='Configuration Dashboard POS', required=True)
    chart_days = fields.Integer(
        string='Jours graphique CA',
        default=7,
        help='Nombre de jours affichés dans le graphique de chiffre d\'affaires',
    )
    recent_days = fields.Integer(
        string='Jours statistiques récentes',
        default=30,
        help='Période pour le calcul des statistiques récentes',
    )
    top_products_limit = fields.Integer(
        string='Limite top produits',
        default=10,
        help='Nombre de produits affichés dans le classement',
    )
    auto_refresh_interval = fields.Selection([
        ('0', 'Désactivé'),
        ('30', '30 secondes'),
        ('60', '1 minute'),
        ('120', '2 minutes'),
        ('300', '5 minutes'),
    ], string='Rafraîchissement auto', default='0')
    company_id = fields.Many2one(
        'res.company', string='Société',
        default=lambda self: self.env.company,
    )

    @api.model
    def get_config(self):
        """Retourne la config active ou les valeurs par défaut."""
        config = self.search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if config:
            return {
                'chart_days': config.chart_days,
                'recent_days': config.recent_days,
                'top_products_limit': config.top_products_limit,
                'auto_refresh_interval': int(config.auto_refresh_interval),
            }
        return {
            'chart_days': 7,
            'recent_days': 30,
            'top_products_limit': 10,
            'auto_refresh_interval': 0,
        }
