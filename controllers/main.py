# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class PartnerDashboardController(http.Controller):
    @http.route('/azk/dashboard/partner_data', type='json', auth='user')
    def partner_data(self, status_filter=None):
        domain = []
        if status_filter:
            domain.append(('current_status', '=', status_filter))
        groups = request.env['azk.partner.partner'].sudo().read_group(
            domain,
            ['id:count', 'current_status', 'country_id'],
            ['country_id', 'current_status'],
            lazy=False
        )
        stats = {}
        for g in groups:
            country = g['country_id'][1]
            status = g['current_status']
            stats.setdefault(country, {'gold': 0, 'silver': 0, 'ready': 0})
            stats[country][status] = g['__count']
        sorted_stats = sorted(stats.items(), key=lambda x: sum(x[1].values()), reverse=True)
        return {
            'top5': sorted_stats[:5],
            'bottom5': sorted_stats[-5:],
        }

    @http.route('/azk/dashboard/project_size_data', type='json', auth='user')
    def project_size_data(self, status_filter=None):
        domain = []
        if status_filter:
            domain.append(('current_status', '=', status_filter))
        partners = request.env['azk.partner.partner'].sudo().search(domain)
        buckets = {}
        for p in partners:
            country = p.country_id.name or 'Unknown'
            size = p.average_project_size or 0
            if size < 5:
                b = '<5'
            elif size <= 10:
                b = '5-10'
            elif size <= 25:
                b = '11-25'
            else:
                b = '25+'
            buckets.setdefault(country, {'<5': 0, '5-10': 0, '11-25': 0, '25+': 0})
            buckets[country][b] += 1
        sorted_buckets = sorted(buckets.items(), key=lambda x: sum(x[1].values()), reverse=True)
        return {
            'top5': sorted_buckets[:5],
            'bottom5': sorted_buckets[-5:],
        }