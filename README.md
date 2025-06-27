
# 🧩 Odoo Partner Monitor – Developer Exercise 1

This module is part of the **Odoo Developer Technical Assessment – Exercise 1**, developed to demonstrate data scraping, dashboarding, and cron automation in the Odoo 18 Community environment.

---

## 📚 Overview

The `azk_odoo_partner_monitor` module fetches and monitors official Odoo partners from [odoo.com/partners](https://www.odoo.com/partners), keeps track of changes in status and references, and provides a real-time dashboard to display partner statistics, project sizes, and geographical distribution.

---

## ✅ Features

### 🕸️ Web Scraping
- Scrapes official Odoo partners with details:
  - Partner name
  - Status (Gold, Silver, Ready)
  - Country
  - Retention rate (%)
  - Total references
  - Largest and average project size
- Supports **pagination** and **country-specific pages**
- Configurable scraping modes:
  - `all`: all partners from all countries
  - `first`: only the first page
  - `specific`: one specific page
  - `specific_c`: one specific country

### 📈 Dashboards
- OWL-based visual dashboard with:
  - Top 5 countries by number of partners
  - Bottom 5 countries by number of partners
  - Project size distribution for top and bottom countries
- Filters for:
  - Partner Status
  - Country
  - First Seen Year

### 🔁 Crons
- `fetch_partner_data`: Main scraper based on fetch mode
- `cron_validate_partners`: Detects discrepancies in reference count
- `cron_reprocess_flagged_partners`: Re-scrapes only flagged partners
- `cron_validate_countries`: Verifies per-country partner count
- `cron_reprocess_flagged_countries`: Re-scrapes data for flagged countries only

### 🧠 Smart Tracking
- Tracks partner status change history (`promoted`, `demoted`, `initial`)
- Logs reference count changes over time
- Flags records that need reprocessing

---

## 🛠️ Technical Stack

- **Odoo 18.0 Community**
- **Python 3.12**
- **BeautifulSoup 4** – for HTML scraping
- **Concurrent Futures** – for threaded requests
- **Chart.js v4** – for dashboard charts
- **OWL (Odoo Web Library)** – for frontend components

---

## 🔧 Configuration

Access system parameters under *Settings → Technical → Parameters → System Parameters*:

| Parameter Key                                      | Description                          | Example Value  |
|----------------------------------------------------|--------------------------------------|----------------|
| `azk_odoo_partner_monitor.partner_fetch_mode`      | Fetch mode (`all`, `first`, `specific`, `specific_c`) | `all`          |
| `azk_odoo_partner_monitor.partner_fetch_page`      | Page number to fetch (if mode = `specific`) | `2`         |
| `azk_odoo_partner_monitor.partner_country_id`      | `res.country` ID (if mode = `specific_c`) | `144`         |

---

## 🖥️ Screenshots

### 🔳 Filters and Charts

| Filter Bar + Top 5 Countries Chart | Project Size Distribution |
|------------------------------------|----------------------------|
| ![Dashboard Filters](screenshots/filters.png) | ![Project Size Chart](screenshots/size_chart.png) |

> 📁 *Put images in a `/screenshots/` directory inside your module and use relative paths.*

---

## 📅 Sample Cron Setup

Activate the following automated actions under *Settings → Technical → Scheduled Actions*:

| Name                        | Model                 | Method                            | Interval     |
|-----------------------------|------------------------|-----------------------------------|--------------|
| Fetch All Partners          | azk.partner.partner    | `fetch_partner_data`              | e.g. Daily   |
| Validate Partner References | azk.partner.partner    | `cron_validate_partners`          | e.g. Weekly  |
| Reprocess Flagged Partners  | azk.partner.partner    | `cron_reprocess_flagged_partners` | e.g. Hourly  |
| Validate Country Counts     | azk.partner.country    | `cron_validate_countries`         | e.g. Weekly  |
| Reprocess Flagged Countries | azk.partner.country    | `cron_reprocess_flagged_countries`| e.g. Weekly  |

---

## 🧪 Testing

You can manually test each cron from the Developer Mode via:

**Settings → Technical → Scheduled Actions**

To test the dashboard:
1. Go to `/web#action=azk_dashboard.dashboard`
2. Apply different filters
3. Confirm charts update dynamically

---

## 🚧 Known Limitations

- Charts currently support up to top/bottom 5 countries.
- Country name resolution depends on exact match with website text.
- Partner detail scraping is dependent on structure of Odoo.com, which may change.

---

## 📂 Directory Structure

```
azk_odoo_partner_monitor/
├── models/
│   ├── partner_partner.py
│   ├── partner_country.py
│   └── partner_monitor_mixin.py
├── static/
│   └── src/js/partner_dashboard.js
├── views/
│   ├── menus.xml
│   ├── dashboard_templates.xml
│   └── dashboard_search_views.xml
├── data/
│   └── ir_cron.xml
├── screenshots/
│   └── filters.png
│   └── size_chart.png
├── __manifest__.py
└── README.md
```

---

## 🧠 Author

Developed by **Majd Hsien**  
As part of Odoo Developer Technical Exercise 1  
© Azkatech 2025
