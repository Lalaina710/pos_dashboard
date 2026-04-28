{
    'name': 'Tableau de bord Point de Vente',
    'version': '18.0.2.2.1',
    'category': 'Point of Sale',
    'summary': 'Dashboard POS dynamique avec KPI, filtres et configuration',
    'description': 'Tableau de bord interactif pour le suivi du Point de Vente avec filtres dynamiques, rafraîchissement auto et configuration.',
    'author': 'SOPROMER',
    'depends': ['point_of_sale'],
    'data': [
        'security/pos_dashboard_groups.xml',
        'security/ir.model.access.csv',
        'views/pos_dashboard_config_views.xml',
        'views/pos_dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pos_dashboard/static/src/css/pos_dashboard.css',
            'pos_dashboard/static/src/xml/pos_dashboard.xml',
            'pos_dashboard/static/src/js/pos_dashboard.js',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
