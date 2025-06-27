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
                await loadJS('/azk_odoo_partner_monitor/static/lib/chartJS/chart.umd.min.js');
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
            this.state.availableCountries = await this.orm.searchRead(
                'azk.partner.country',
                [],
                ['id', 'name'],
                { order: 'name ASC', limit: 1000 }
            );
        } catch (countryError) {
            console.error('Failed to fetch countries', countryError);
            this.state.availableCountries = [
                {id: 1, name: 'United States'},
                {id: 2, name: 'Canada'},
            ];
        }

        try {
            const yearGroups = await this.orm.readGroup(
                'azk.partner.partner',
                [['first_seen_on', '!=', null]],
                ['first_seen_on'],
                ['first_seen_on'],
                { groupby: 'first_seen_on desc' }
            );

            this.state.availableYears = yearGroups
                .map(group => group.first_seen_on)
                .filter(year => year !== null && year !== undefined)
                .sort((a, b) => b - a);
        } catch (yearError) {
            console.error('Failed to fetch years', yearError);
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
        if (statusFilter) domain.push(['current_status', '=', statusFilter]);
        if (countryFilter) domain.push(['country_id', '=', parseInt(countryFilter)]);
        if (yearFilter) domain.push(['first_seen_on', '=', parseInt(yearFilter)]);
        return domain;
    }

    async loadAndRender() {
        try {
            // Fetch partner data with country information
            const partnersData = await this.orm.call(
                'azk.partner.partner',
                'read_group',
                [
                    this.domain,
                    ['id:count', 'current_status', 'country_id'],
                    ['country_id', 'current_status']
                ],
                { lazy: false }
            );

            // Fetch project data with country information
            const projectsData = await this.orm.call(
                'azk.partner.partner',
                'search_read',
                [
                    this.domain,
                    ['average_project_size', 'country_id']
                ],
                { limit: 10000 }
            );

            // Get country names
            const countryIds = [
                ...new Set([
                    ...partnersData.map(p => p.country_id ? p.country_id[0] : null),
                    ...projectsData.map(p => p.country_id ? p.country_id[0] : null)
                ].filter(id => id !== null))
            ];

            const countriesInfo = await this.orm.searchRead(
                'azk.partner.country',
                [['id', 'in', countryIds]],
                ['id', 'name']
            );

            const countryNames = {};
            countriesInfo.forEach(country => {
                countryNames[country.id] = country.name;
            });

            // Partner data processing
            const groupedPartners = {};
            partnersData.forEach(g => {
                const countryId = g.country_id ? g.country_id[0] : null;
                const countryName = countryId ? countryNames[countryId] || 'Unknown' : 'Unknown';

                if (!groupedPartners[countryId]) {
                    groupedPartners[countryId] = {
                        id: countryId,
                        name: countryName,
                        gold: 0,
                        silver: 0,
                        ready: 0
                    };
                }
                groupedPartners[countryId][g.current_status] = g['__count'];
            });

            // Convert to matrix and sort by number of partners
            const sortedCountries = Object.values(groupedPartners).sort((a, b) => {
                const totalA = a.gold + a.silver + a.ready;
                const totalB = b.gold + b.silver + b.ready;
                return totalB - totalA;
            });

            const top5 = sortedCountries.slice(0, 5);
            const bottom5 = sortedCountries.slice(-5);

            // Project data processing
            const projectBuckets = {};
            projectsData.forEach(p => {
                const countryId = p.country_id ? p.country_id[0] : null;
                const countryName = countryId ? countryNames[countryId] || 'Unknown' : 'Unknown';
                const size = p.average_project_size || 0;

                let bucket = '<5';
                if (size >= 25) bucket = '25+';
                else if (size >= 11) bucket = '11-25';
                else if (size >= 5) bucket = '5-10';

                if (!projectBuckets[countryId]) {
                    projectBuckets[countryId] = {
                        name: countryName,
                        '<5': 0,
                        '5-10': 0,
                        '11-25': 0,
                        '25+': 0
                    };
                }
                projectBuckets[countryId][bucket] += 1;
            });

            // Preparing data for graphs
            const prepareChartData = (countries) => {
                return countries.map(country => {
                    const buckets = projectBuckets[country.id] || {
                        name: country.name,
                        '<5': 0,
                        '5-10': 0,
                        '11-25': 0,
                        '25+': 0
                    };

                    return {
                        countryName: buckets.name,
                        '<5': buckets['<5'],
                        '5-10': buckets['5-10'],
                        '11-25': buckets['11-25'],
                        '25+': buckets['25+'],
                        total: buckets['<5'] + buckets['5-10'] + buckets['11-25'] + buckets['25+']
                    };
                }).filter(d => d.total > 0);
            };

            const top5Data = prepareChartData(top5);
            const bottom5Data = prepareChartData(bottom5);

            this.renderPartnerCharts(top5, bottom5);
            this.renderSizeCharts(top5Data, bottom5Data);
        } catch (error) {
            console.error('Error in loadAndRender:', error);
            const errorContainer = document.getElementById('dashboard-error');
            if (errorContainer) {
                errorContainer.innerHTML = `
                    <div class="alert alert-danger">
                        Failed to load data: ${error.message || 'Unknown error'}
                    </div>
                `;
            }
        }
    }

    renderPartnerCharts(top, bottom) {
        const buildConfig = (data, title) => ({
            type: 'bar',
            data: {
                labels: data.map(d => d.name),
                datasets: [
                    { label: 'Gold', data: data.map(d => d.gold), backgroundColor: '#FFD700' },
                    { label: 'Silver', data: data.map(d => d.silver), backgroundColor: '#C0C0C0' },
                    { label: 'Ready', data: data.map(d => d.ready), backgroundColor: '#32CD32' },
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

        const renderChart = (elementId, data, title) => {
            const el = document.getElementById(elementId);
            if (!el) return;

            if (el.chart) el.chart.destroy();

            if (data.length > 0) {
                el.chart = new Chart(el, buildConfig(data, title));
            } else {
                el.innerHTML = `<div class="text-center p-3">No data available for ${title}</div>`;
            }
        };

        renderChart('top_countries_chart', top, 'Top 5 Countries by Partners');
        renderChart('bottom_countries_chart', bottom, 'Bottom 5 Countries by Partners');
    }

    renderSizeCharts(topData, bottomData) {
        const buildConfig = (data, title) => {
            // Data preparation for each country
            const labels = data.map(d => d.countryName);
            const datasets = [
                {
                    label: '<5',
                    data: data.map(d => d['<5']),
                    backgroundColor: '#a6cee3'
                },
                {
                    label: '5-10',
                    data: data.map(d => d['5-10']),
                    backgroundColor: '#1f78b4'
                },
                {
                    label: '11-25',
                    data: data.map(d => d['11-25']),
                    backgroundColor: '#b2df8a'
                },
                {
                    label: '25+',
                    data: data.map(d => d['25+']),
                    backgroundColor: '#33a02c'
                }
            ];

            return {
                type: 'bar',
                data: { labels, datasets },
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
                    },
                    scales: {
                        x: { stacked: true },
                        y: { stacked: true }
                    }
                }
            };
        };

        const renderChart = (elementId, data, title) => {
            const el = document.getElementById(elementId);
            if (!el) return;

            if (el.chart) el.chart.destroy();

            if (data.length > 0) {
                el.chart = new Chart(el, buildConfig(data, title));
            } else {
                el.innerHTML = `<div class="text-center p-3">No project data available for ${title}</div>`;
            }
        };

        renderChart('top_project_distribution_chart', topData, 'Top 5 Countries Project Size Distribution');
        renderChart('bottom_project_distribution_chart', bottomData, 'Bottom 5 Countries Project Size Distribution');
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
