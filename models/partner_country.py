import logging
from odoo import models, fields, api
from .partner_monitor_mixin import PartnerMonitorMixin
_logger = logging.getLogger(__name__)


class PartnerCountry(models.Model, PartnerMonitorMixin):
    _name = 'azk.partner.country'
    _description = 'Country of Odoo Partner'

    name = fields.Char(string='Country Name', required=True)
    active = fields.Boolean(default=True)
    partner_ids = fields.One2many(
        'azk.partner.partner',
        'country_id',
        string='Partners'
    )
    total_partner_count = fields.Integer(
        string='Total Partners',
        compute='_compute_counts',
        store=True
    )
    to_reprocess_partners = fields.Boolean(string='To Reprocess', default=False)
    slug = fields.Char(string="Country Slug")
    odoo_country_id = fields.Char(string="Odoo Country ID")

    @api.depends('partner_ids')
    def _compute_counts(self):
        for rec in self:
            rec.total_partner_count = len(rec.partner_ids)

    @api.model
    def cron_validate_countries(self):
        try:
            Partner = self.env['azk.partner.partner']
            for country in self.search([]):
                actual_count = Partner.search_count([('country_id', '=', country.id)])
                if actual_count != country.total_partner_count:
                    country.write({
                        'to_reprocess_partners': True,
                        'total_partner_count': actual_count,
                    })
                    _logger.info(
                        "Country %s flagged for reprocess (was %s, now %s)",
                        country.name, country.total_partner_count, actual_count
                    )
                else:
                    # reset flag if counts match
                    if country.to_reprocess_partners:
                        country.to_reprocess_partners = False
        except Exception as e:
            self._post_cron_error('cron_validate_countries', str(e))
            _logger.exception("Error in cron_validate_countries")

    @api.model
    def cron_reprocess_flagged_countries(self):
        params = self.env['ir.config_parameter'].sudo()
        partner = self.env['azk.partner.partner']
        flagged = self.search([('to_reprocess_partners', '=', True)])

        for country in flagged:
            try:
                # Set temporary parameters
                params.set_param('azk_odoo_partner_monitor.partner_fetch_mode', 'specific_c')
                params.set_param('azk_odoo_partner_monitor.partner_country_id', str(country.id))

                # Fetch and update partner data for the country
                partner.fetch_partner_data()

                # Clear reprocess flag
                country.to_reprocess_partners = False
                _logger.info("Reprocessed country %s", country.name)

            finally:
                # Always clear parameters to avoid side effects
                params.unlink_param('azk_odoo_partner_monitor.partner_fetch_mode')
                params.unlink_param('azk_odoo_partner_monitor.partner_country_id')
