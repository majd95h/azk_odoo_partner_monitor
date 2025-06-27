/** @odoo-module **/
import { Component, onWillStart, onMounted, useState } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { loadJS, AssetsLoadingError } from '@web/core/assets';

class PartnerDashboard extends Component {
    setup() {
        this.orm = useService('orm');
        this.state = useState({
            statusFilter: '',
            countryFilter: '',
            yearFilter: '',
            availableCountries: [],
            availableYears: []
        });

        onWillStart(async () => {
            try {
                await loadJS('https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js');
            } catch (error) {
                if (!(error instanceof AssetsLoadingError)) {
                    throw error;
                }
                console.error('Chart.js loading failed');
            }
            await this.fetchFilterOptions();
        });

        onMounted(() => {
            this.loadAndRender();
        });
    }

    async fetchFilterOptions() {
        try {
            console.log('Fetching countries...');

            // Option 1: Get all countries from res.country
            this.state.availableCountries = await this.orm.searchRead(
                'azk.partner.country',
                [],
                ['id', 'name'],
                { order: 'name ASC', limit: 1000 } // Increase limit if needed
            );

            console.log('Countries fetched:', this.state.availableCountries);
        } catch (countryError) {
            console.error('Failed to fetch countries', countryError);

            // Fallback: Manual country list
            this.state.availableCountries = [
                {id: 1, name: 'United States'},
                {id: 2, name: 'Canada'},
                // Add other countries as needed
            ];
        }

        try {
            console.log('Fetching years...');

            // Get distinct years using readGroup
            const yearGroups = await this.orm.readGroup(
                'azk.partner.partner',
                [['first_seen_on', '!=', null]],
                ['first_seen_on'],
                ['first_seen_on'],
                { orderBy: [{ name: 'first_seen_on', asc: false }] }
            );

            this.state.availableYears = yearGroups
                .map(group => group.first_seen_on)
                .filter(year => year !== null && year !== undefined)
                .sort((a, b) => b - a); // Descending order

            console.log('Years fetched:', this.state.availableYears);
        } catch (yearError) {
            console.error('Failed to fetch years', yearError);

            // Fallback: Generate last 10 years
            const currentYear = new Date().getFullYear();
            this.state.availableYears = Array.from(
                {length: 10},
                (_, i) => currentYear - i
            );
        }
    }

    get domain() {
        const domain = [];
        const { statusFilter, countryFilter, yearFilter } = this.state;
        console.log('countryFilter',countryFilter)
        if (statusFilter) domain.push(['current_status', '=', statusFilter]);
        if (countryFilter) domain.push(['country_id', '=', parseInt(countryFilter)]);
        if (yearFilter) domain.push(['first_seen_on', '=', parseInt(yearFilter)]);
        console.log('domain',domain)
        return domain;
    }

    async loadAndRender() {
        const [partnersData, projectsData] = await Promise.all([
            this.orm.call(
                'azk.partner.partner',
                'read_group',
                [
                    this.domain,
                    ['id:count', 'current_status', 'country_id'],
                    ['country_id', 'current_status']
                ],
                { lazy: false }
            ),
            this.orm.call(
                'azk.partner.partner',
                'search_read',
                [this.domain, ['average_project_size', 'country_id']],
            ),
        ]);

        const grouped = {};
        partnersData.forEach(g => {
            const country = g.country_id[1] || 'Unknown';
            grouped[country] = grouped[country] || { gold: 0, silver: 0, ready: 0 };
            grouped[country][g.current_status] = g['__count'];
        });

        const sortedCountries = Object.entries(grouped).sort((a, b) => {
            const sum = x => x.gold + x.silver + x.ready;
            return sum(b[1]) - sum(a[1]);
        });

        const top5 = sortedCountries.slice(0, 5);
        const bottom5 = sortedCountries.slice(-5);

        const buckets = {};
        projectsData.forEach(p => {
            const country = p.country_id[1] || 'Unknown';
            const size = p.average_project_size || 0;
            let bucket = '<5';
            if (size > 25) bucket = '25+';
            else if (size > 10) bucket = '11-25';
            else if (size > 5) bucket = '5-10';

            buckets[country] = buckets[country] || { '<5': 0, '5-10': 0, '11-25': 0, '25+': 0 };
            buckets[country][bucket]++;
        });

        // Aggregate project sizes for top/bottom countries
        const top5Aggregated = this.aggregateProjectSizes(top5, buckets);
        const bottom5Aggregated = this.aggregateProjectSizes(bottom5, buckets);

        this.renderPartnerCharts(top5, bottom5);
        this.renderSizeCharts(top5Aggregated, bottom5Aggregated);
    }

    aggregateProjectSizes(countries, buckets) {
        const aggregated = { '<5': 0, '5-10': 0, '11-25': 0, '25+': 0 };
        countries.forEach(([country]) => {
            if (buckets[country]) {
                Object.keys(aggregated).forEach(bucket => {
                    aggregated[bucket] += buckets[country][bucket] || 0;
                });
            }
        });
        return aggregated;
    }

    renderPartnerCharts(top, bottom) {
        const buildConfig = (data, title) => ({
            type: 'bar',
            data: {
                labels: data.map(d => d[0]),
                datasets: [
                    { label: 'Gold', data: data.map(d => d[1].gold), backgroundColor: '#FFD700' },
                    { label: 'Silver', data: data.map(d => d[1].silver), backgroundColor: '#C0C0C0' },
                    { label: 'Ready', data: data.map(d => d[1].ready), backgroundColor: '#32CD32' },
                ],
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: title
                    }
                },
                scales: {
                    x: { stacked: true },
                    y: { stacked: true },
                },
            },
        });

        const topEl = document.getElementById('top_countries_chart');
        const bottomEl = document.getElementById('bottom_countries_chart');

        if (topEl) {
            if (topEl.chart) topEl.chart.destroy();
            topEl.chart = new Chart(topEl, buildConfig(top, 'Top 5 Countries by Partners'));
        }
        if (bottomEl) {
            if (bottomEl.chart) bottomEl.chart.destroy();
            bottomEl.chart = new Chart(bottomEl, buildConfig(bottom, 'Bottom 5 Countries by Partners'));
        }
    }

    renderSizeCharts(topData, bottomData) {
        const buildConfig = (data, title) => ({
            type: 'pie',
            data: {
                labels: Object.keys(data),
                datasets: [{
                    data: Object.values(data),
                    backgroundColor: ['#a6cee3', '#1f78b4', '#b2df8a', '#33a02c'],
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: title
                    },
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });

        const topEl = document.getElementById('top_project_distribution_chart');
        const bottomEl = document.getElementById('bottom_project_distribution_chart');

        if (topEl) {
            if (topEl.chart) topEl.chart.destroy();
            topEl.chart = new Chart(topEl, buildConfig(topData, 'Top 5 Countries Project Size Distribution'));
        }
        if (bottomEl) {
            if (bottomEl.chart) bottomEl.chart.destroy();
            bottomEl.chart = new Chart(bottomEl, buildConfig(bottomData, 'Bottom 5 Countries Project Size Distribution'));
        }
    }

    applyFilters() {
        this.loadAndRender();
    }

    clearFilters() {
        this.state.statusFilter = '';
        this.state.countryFilter = '';
        this.state.yearFilter = '';
        this.loadAndRender();
    }
}

PartnerDashboard.template = 'azk_dashboard.dashboard';
registry.category('actions').add('azk_dashboard.dashboard', PartnerDashboard);
