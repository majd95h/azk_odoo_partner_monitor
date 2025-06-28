import logging
import re
import requests
import time
import random
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# --- HTTP SESSION WITH FAST RETRIES ---
def get_retry_session():
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    retry = Retry(
        total=2,                # Fewer retries for speed
        read=2,
        connect=2,
        backoff_factor=0.5,     # Faster backoff for retries
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    # Custom User-Agent to reduce block risk
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (compatible; OdooPartnerBot/1.0; +https://yourdomain.example)'
    })
    return session

RETRY_SESSION = get_retry_session()

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
    project_size_bucket = fields.Selection(
        selection=[
            ('<5', '<5'),
            ('5-10', '5-10'),
            ('11-25', '11-25'),
            ('25+', '25+')
        ],
        string='Project Size Bucket',
        compute='_compute_project_size_bucket',
        store=True
    )

    @api.depends('average_project_size')
    def _compute_project_size_bucket(self):
        for record in self:
            size = record.average_project_size or 0
            if size >= 25:
                record.project_size_bucket = '25+'
            elif size >= 11:
                record.project_size_bucket = '11-25'
            elif size >= 5:
                record.project_size_bucket = '5-10'
            else:
                record.project_size_bucket = '<5'

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

    def _get_country_slug_and_id(self, country_name):
        url = 'https://www.odoo.com/partners'
        try:
            time.sleep(random.uniform(0.1, 0.5))  # Speed: minimal delay
            resp = RETRY_SESSION.get(url, timeout=20)
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

    def _get_max_pages(self, base_url):
        try:
            time.sleep(random.uniform(0.1, 0.5))  # Speed: minimal delay
            resp = RETRY_SESSION.get(base_url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            pages = [int(a.text.strip()) for a in soup.select('ul.pagination li a') if a.text.strip().isdigit()]
            return max(pages) if pages else 1
        except Exception as e:
            _logger.error("Pagination detection failed: %s", e)
            return 1

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
            time.sleep(random.uniform(0.1, 0.5))  # Speed: minimal delay
            resp = RETRY_SESSION.get(url, timeout=20)
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
        config = self.env['ir.config_parameter'].sudo()
        fetch_mode = config.get_param('azk_odoo_partner_monitor.partner_fetch_mode', 'all')

        base_url, pages = self._determine_pages(fetch_mode, config)
        if not pages:
            _logger.warning("No pages to fetch.")
            return

        use_amp = '?' in base_url
        url_for = lambda p: f"{base_url}/page/{p}" if not use_amp else f"{base_url}&page={p}" if p > 1 else base_url

        thread_count = min(len(pages), 12)  # SPEED: up to 12 threads
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
        for partner in self.search([]):
            active_count = self.env['azk.partner.reference'].search_count([
                ('partner_id', '=', partner.id),
                ('active', '=', True),
            ])
            if active_count != partner.total_references_count:
                partner.write({'to_reprocess_references': True})
                _logger.info("Partner %s marked for reprocess due to mismatch.", partner.name)

    def _parse_single_partner_page(self, soup):
        try:
            country_name = "Unknown"
            address_span = soup.select_one('span[itemprop="streetAddress"]')
            if address_span:
                parts = re.split(r'<br\s*/?>', str(address_span), flags=re.IGNORECASE)
                if parts:
                    last_part = BeautifulSoup(parts[-1], 'html.parser').get_text(strip=True)
                    if last_part:
                        country_name = last_part

            retention_rate = 0.0
            stat_size_div = soup.select_one('div.stat_size')
            if stat_size_div:
                retention_span = stat_size_div.find(string=re.compile(r'\d+\s*%'))
                if retention_span:
                    match = re.search(r'(\d+)', retention_span)
                    if match:
                        retention_rate = float(match.group(1))

            largest_project_size = 0
            average_project_size = 0.0
            if stat_size_div:
                largest_tag = stat_size_div.find('span', string=re.compile('Largest', re.IGNORECASE))
                if largest_tag and largest_tag.next_sibling:
                    largest_text = largest_tag.next_sibling.strip()
                    match = re.search(r'(\d+)', largest_text)
                    if match:
                        largest_project_size = int(match.group(1))

                average_tag = stat_size_div.find('span', string=re.compile('Average', re.IGNORECASE))
                if average_tag and average_tag.next_sibling:
                    average_text = average_tag.next_sibling.strip()
                    match = re.search(r'(\d+(?:\.\d+)?)', average_text)
                    if match:
                        average_project_size = float(match.group(1))

            total_references_count = 0
            stat_ref_div = soup.select_one('div.stat_ref')
            if stat_ref_div:
                heading = stat_ref_div.find(string=re.compile(r'References\s*-\s*\d+', re.IGNORECASE))
                if heading:
                    match = re.search(r'(\d+)', heading)
                    if match:
                        total_references_count = int(match.group(1))

            return {
                'country_name': country_name,
                'retention_rate': retention_rate,
                'largest_project_size': largest_project_size,
                'average_project_size': average_project_size,
                'total_references_count': total_references_count,
            }

        except Exception as e:
            _logger.exception("Failed to parse single partner page: %s", e)
            return {}

    @api.model
    def cron_reprocess_flagged_partners(self):
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
                time.sleep(random.uniform(0.1, 0.5))  # Speed: minimal delay
                response = RETRY_SESSION.get(partner.partner_url, timeout=20)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                data = self._parse_single_partner_page(soup)
                if not data:
                    _logger.error("Empty result for %s", partner.partner_url)
                    continue

                country_name = data.pop('country_name', None)
                if country_name:
                    country = self.env['azk.partner.country'].sudo().search([('name', '=', country_name)], limit=1)
                    if not country:
                        country = self.env['azk.partner.country'].sudo().create({'name': country_name})
                    data['country_id'] = country.id

                partner.write(data)
                partner.to_reprocess_references = False
                _logger.info("Successfully reprocessed partner: %s", partner.name)

            except Exception as e:
                _logger.exception("Failed to reprocess %s: %s", partner.name, e)