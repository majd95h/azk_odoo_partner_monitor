# models/partner_status_history.py
from odoo import models, fields

class PartnerStatusHistory(models.Model):
    _name = 'azk.partner.status.history'
    _description = 'Partner Status History'

    partner_id = fields.Many2one('azk.partner.partner', required=True, ondelete='cascade')
    old_status = fields.Selection([
        ('gold','Gold'),
        ('silver','Silver'),
        ('ready','Ready'),
    ], string='Previous Status', required=True)
    new_status = fields.Selection([
        ('gold','Gold'),
        ('silver','Silver'),
        ('ready','Ready'),
    ], string='New Status', required=True)
    change_date = fields.Date(string='Change Date', default=fields.Date.context_today)
    change_type = fields.Selection([
        ('initial','Initial'),
        ('promoted','Promoted'),
        ('demoted','Demoted'),
    ], string='Change Type', required=True)
