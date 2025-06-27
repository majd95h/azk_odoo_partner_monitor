import logging
import re
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class PartnerPartner(models.Model):
    _name = 'azk.partner.partner'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Odoo Official Partner'

    name = fields.Char(string='Partner Name', required=True, tracking=True)
    partner_url = fields.Char(string='Profile URL')
    current_status = fields.Selection([
        ('gold', 'Gold'),
        ('silver', 'Silver'),
        ('ready', 'Ready'),
    ], string='Status', default='ready', tracking=True)
    country_id = fields.Many2one('azk.partner.country', string='Country', tracking=True)
    first_seen_on = fields.Date(string='First Seen On', default=fields.Date.context_today, readonly=True)
    retention_rate = fields.Float(string='Retention Rate')
    total_references_count = fields.Integer(string='Total References')
    largest_project_size = fields.Integer(string='Largest Project Size')
    average_project_size = fields.Float(string='Average Project Size')
    to_reprocess_references = fields.Boolean(string='To Reprocess References', default=False)

    status_history_ids = fields.One2many('azk.partner.status.history', 'partner_id', string='Status History')
    reference_ids = fields.One2many('azk.partner.reference', 'partner_id', string='Reference History')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('first_seen_on', fields.Date.context_today(self))
        return super().create(vals_list)

    def write(self, vals):
        today = fields.Date.context_today(self)
        for partner in self:
            # Track status changes
            if 'current_status' in vals and vals['current_status'] != partner.current_status:
                old_status = partner.current_status
                new_status = vals['current_status']
                change_type = (
                    'initial' if not old_status else
                    'promoted' if ['ready', 'silver', 'gold'].index(new_status) >
                                   ['ready', 'silver', 'gold'].index(old_status)
                    else 'demoted'
                )
                self.env['azk.partner.status.history'].create({
                    'partner_id': partner.id,
                    'old_status': old_status,
                    'new_status': new_status,
                    'change_date': today,
                    'change_type': change_type,
                })

            # Track reference count changes
            if 'total_references_count' in vals and vals['total_references_count'] != partner.total_references_count:
                self.env['azk.partner.reference'].create({
                    'partner_id': partner.id,
                    'reference_count': str(vals['total_references_count']),
                    'active': True,
                    'change_date': fields.Datetime.now(),
                })

        return super().write(vals)

    # Utility: Determine slug and ID for specific country
    def _get_country_slug_and_id(self, country_name):
        url = 'https://www.odoo.com/partners'
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.select('a[href*="/partners/country/"]'):
                if a.get_text(strip=True).lower() == country_name.lower():
                    match = re.search(r'/country/([a-z0-9\-]+)-(\d+)', a['href'])
                    if match:
                        return match.group(1), match.group(2)
        except Exception as e:
            _logger.error("Failed to fetch country slug/id for %s: %s", country_name, e)
        return None, None

    # Utility: Determine number of pages
    def _get_max_pages(self, base_url):
        try:
            resp = requests.get(base_url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            pages = [int(a.text.strip()) for a in soup.select('ul.pagination li a') if a.text.strip().isdigit()]
            return max(pages) if pages else 1
        except Exception as e:
            _logger.error("Pagination detection failed: %s", e)
            return 1

    # Extract a single partner's data
    def _parse_partner_card(self, soup_item):
        try:
            name = soup_item.select_one('h5 span').text.strip()
            profile_url = f"https://www.odoo.com{soup_item.get('href')}"
            badge = soup_item.select_one('h5 .badge')
            status = 'gold' if badge and 'gold' in badge.text.lower() else \
                     'silver' if badge and 'silver' in badge.text.lower() else 'ready'
            country = soup_item.select_one('#o_wcrm_partners_address span')
            country_name = country.text.strip() if country else 'Unknown'
            retention_span = soup_item.select_one('div.mb-2 small span')
            retention = float(retention_span.text.strip()) if retention_span else 0.0
            ref_div = soup_item.select_one('div.col-md-3.stat_ref > div')
            ref_count = int(re.search(r'(\d+)', ref_div.text.strip()).group(1)) if ref_div else 0

            largest, average = 0, 0.0
            for tag in soup_item.select('small.text-muted'):
                text = tag.text.strip()
                if text.startswith('Average Project'):
                    match = re.search(r'(\d+(?:\.\d+)?)', text)
                    average = float(match.group(1)) if match else 0.0
                elif text.startswith('Large Project'):
                    match = re.search(r'(\d+)', text)
                    largest = int(match.group(1)) if match else 0

            return (name, {
                'partner_url': profile_url,
                'current_status': status,
                'country_name': country_name,
                'retention_rate': retention,
                'total_references_count': ref_count,
                'largest_project_size': largest,
                'average_project_size': average,
            })
        except Exception as e:
            _logger.warning("Failed to parse partner item: %s", e)
            return None

    def _scrape_page(self, url):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            return [
                parsed for card in soup.select('a.text-decoration-none.row.p-2.text-black')
                if (parsed := self._parse_partner_card(card))
            ]
        except Exception as e:
            _logger.error("Error scraping %s: %s", url, e)
            return []

    def _determine_pages(self, mode, config):
        """Determine URL and pages to fetch based on fetch mode setting."""
        base_url = 'https://www.odoo.com/partners?country_all=1'
        if mode == 'all':
            return base_url, list(range(1, self._get_max_pages(base_url) + 1))
        if mode == 'first':
            return base_url, [1]
        if mode == 'specific':
            page = int(config.get_param('azk_odoo_partner_monitor.partner_fetch_page', '1'))
            return base_url, [page]
        if mode == 'specific_c':
            country_id = config.get_param('azk_odoo_partner_monitor.partner_country_id')
            country = self.env['res.country'].browse(int(country_id)) if country_id else None
            if not country.exists():
                _logger.error("Invalid country ID: %s", country_id)
                return base_url, []
            slug, num_id = self._get_country_slug_and_id(country.name)
            if not slug:
                _logger.error("No slug found for %s", country.name)
                return base_url, []
            country_url = f"https://www.odoo.com/partners/country/{slug}-{num_id}"
            return country_url, list(range(1, self._get_max_pages(country_url) + 1))
        _logger.error("Unknown fetch mode: %s", mode)
        return base_url, []

    def fetch_partner_data(self):
        """Main cron to fetch all partners depending on configuration mode."""
        config = self.env['ir.config_parameter'].sudo()
        fetch_mode = config.get_param('azk_odoo_partner_monitor.partner_fetch_mode', 'all')

        base_url, pages = self._determine_pages(fetch_mode, config)
        if not pages:
            _logger.warning("No pages to fetch.")
            return

        use_amp = '?' in base_url
        url_for = lambda p: f"{base_url}/page/{p}" if not use_amp else f"{base_url}&page={p}" if p > 1 else base_url

        thread_count = 4 if fetch_mode == 'all' else min(len(pages), 8)
        _logger.info("Fetching %d pages using %d threads...", len(pages), thread_count)

        scraped = []
        with ThreadPoolExecutor(max_workers=thread_count) as pool:
            futures = [pool.submit(self._scrape_page, url_for(p)) for p in pages]
            for future in as_completed(futures):
                scraped.extend(future.result() or [])

        _logger.info("Scraped %d partner records", len(scraped))
        self._upsert_partner_records(scraped)

    def _upsert_partner_records(self, records):
        country_model = self.env['azk.partner.country'].sudo()
        existing = {p.name: p for p in self.search([('name', 'in', [r[0] for r in records])])}
        for name, data in records:
            country_name = data.pop('country_name', None)
            if country_name:
                country = country_model.search([('name', '=', country_name)], limit=1)
                if not country:
                    country = country_model.create({'name': country_name})
                data['country_id'] = country.id
            if name in existing:
                existing[name].write(data)
            else:
                self.create([{'name': name, **data}])

    @api.model
    def cron_validate_partners(self):
        """Cron to check if any partner's reference count has changed."""
        for partner in self.search([]):
            active_count = self.env['azk.partner.reference'].search_count([
                ('partner_id', '=', partner.id),
                ('active', '=', True),
            ])
            if active_count != partner.total_references_count:
                partner.write({'to_reprocess_references': True})
                _logger.info("Partner %s marked for reprocess due to mismatch.", partner.name)

    def _parse_single_partner_page(self, partner_url):
        """
        Parse a single partner profile page to extract detailed partner data.
        Returns a tuple (partner_name, data_dict).
        """
        try:
            response = requests.get(partner_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Partner name
            name_tag = soup.select_one('h1')
            partner_name = name_tag.text.strip() if name_tag else None
            if not partner_name:
                _logger.warning("No name found in %s", partner_url)
                return None, {}

            # Country: extract from last <br> inside address block
            country = 'Unknown'
            address_block = soup.select_one('span[itemprop="streetAddress"]')
            if address_block and '<br>' in str(address_block):
                parts = str(address_block).split('<br>')
                country = BeautifulSoup(parts[-1], 'html.parser').text.strip()

            # Total References
            total_refs = 0
            ref_div = soup.select_one('div.stat_ref')
            if ref_div:
                header = ref_div.select_one('div.mt-3')
                if header and 'References' in header.text:
                    match = re.search(r'(\d+)', header.text)
                    if match:
                        total_refs = int(match.group(1))

            # Largest & Average Project Size
            largest = 0
            average = 0.0
            size_div = soup.select_one('div.stat_size')
            if size_div:
                largest_tag = size_div.find(string=re.compile('Largest:'))
                if largest_tag:
                    match = re.search(r'(\d+)', largest_tag)
                    if match:
                        largest = int(match.group(1))

                average_tag = size_div.find(string=re.compile('Average:'))
                if average_tag:
                    match = re.search(r'(\d+(?:\.\d+)?)', average_tag)
                    if match:
                        average = float(match.group(1))

            # Retention Rate
            retention_value = 0.0
            if size_div:
                retention_text = size_div.find(string=re.compile(r'\d+\s*%'))
                if retention_text:
                    match = re.search(r'(\d+)', retention_text)
                    if match:
                        retention_value = float(match.group(1))

            # Status (from badge)
            badge = soup.select_one('span.badge')
            badge_text = badge.text.lower().strip() if badge else ''
            if 'gold' in badge_text:
                status = 'gold'
            elif 'silver' in badge_text:
                status = 'silver'
            else:
                status = 'ready'

            return partner_name, {
                'partner_url': partner_url,
                'current_status': status,
                'country_name': country,
                'retention_rate': retention_value,
                'total_references_count': total_refs,
                'largest_project_size': largest,
                'average_project_size': average,
            }

        except Exception as e:
            _logger.error("Failed to parse %s: %s", partner_url, e)
            return None, {}

    @api.model
    def cron_reprocess_flagged_partners(self):
        """
        Re-scrape only the partners flagged for reprocessing
        and update their information.
        """
        flagged = self.search([('to_reprocess_references', '=', True)])
        if not flagged:
            _logger.info("No partners flagged for reprocessing.")
            return

        _logger.info("Reprocessing %d flagged partners...", len(flagged))

        for partner in flagged:
            if not partner.partner_url:
                _logger.warning("Partner '%s' has no partner_url. Skipping.", partner.name)
                continue

            try:
                # Fetch HTML content
                response = requests.get(partner.partner_url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                # Parse detailed partner data from page
                data = self._parse_single_partner_page(soup)
                if not data:
                    _logger.error("Empty result for %s", partner.partner_url)
                    continue

                # Link country if found
                country_name = data.pop('country_name', None)
                if country_name:
                    country = self.env['azk.partner.country'].sudo().search([('name', '=', country_name)], limit=1)
                    if not country:
                        country = self.env['azk.partner.country'].sudo().create({'name': country_name})
                    data['country_id'] = country.id

                # Update partner record
                partner.write(data)
                partner.to_reprocess_references = False
                _logger.info("Successfully reprocessed partner: %s", partner.name)

            except Exception as e:
                _logger.exception("Failed to reprocess %s: %s", partner.name, e)

