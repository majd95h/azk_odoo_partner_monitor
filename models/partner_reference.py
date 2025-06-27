from odoo import models, fields

class PartnerReference(models.Model):
    _name = 'azk.partner.reference'
    _description = 'Partner Reference'

    partner_id = fields.Many2one('azk.partner.partner', required=True, ondelete='cascade')
    reference_count = fields.Char(required=True)
    active = fields.Boolean(default=True)
    change_date = fields.Datetime(default=fields.Datetime.now)