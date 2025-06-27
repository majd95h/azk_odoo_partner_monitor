from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    partner_fetch_mode = fields.Selection([
        ('all', 'All Partners'),
        ('first', 'First Page'),
        ('specific', 'Specific Page'),
        ('specific_c', 'Specific Country'),
    ], string="Partner Fetch Mode", default='all',
       config_parameter='azk_odoo_partner_monitor.partner_fetch_mode')

    partner_fetch_page = fields.Integer(
        string="Partner Fetch Page",
        config_parameter='azk_odoo_partner_monitor.partner_fetch_page'
    )

    partner_country_id = fields.Many2one(
    'res.country', string="Specific Country (Odoo Country)",
    config_parameter='azk_odoo_partner_monitor.partner_country_id')

    partner_monitor_error_user_id = fields.Many2one(
        'res.users',
        string="Partner Monitor Error Receiver User",
        config_parameter='azk_odoo_partner_monitor.error_recipient_user_id',
        help="The user who will be notified in chat when a cron fails."
    )

    @api.onchange('partner_fetch_mode')
    def _onchange_partner_fetch_mode(self):
        if self.partner_fetch_mode != 'specific':
            self.partner_fetch_page = False
        if self.partner_fetch_mode != 'specific_c':
            self.partner_country_id = False
