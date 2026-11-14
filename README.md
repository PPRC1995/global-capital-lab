# Global Capital Lab

**International Cost of Capital App — Kellogg MBA / International Finance**

A Streamlit dashboard comparing the cost of equity, pretax and after-tax borrowing cost, and WACC in **USD** and a selected country's currency.

## Features
- Dark dashboard with side-by-side USD/local-currency metrics and a comparison chart.
- U.S. industry **unlevered betas** from Damodaran, including *Software (System & Application)*.
- Damodaran **Baa2/BBB spread for large nonfinancial firms**.
- Corporate tax rates from OECD via its SDMX API, with a clear manual fallback if access fails.
- 10-year government yields from Trading Economics.
- Refresh button; clear source status, vintage, and manual overrides if a site blocks scraping.
- Select industry and country, ERP, debt share, and U.S. or foreign **project tax rate**.
- Optional manual override for foreign BBB spread; otherwise automatic currency conversion.
- All-industry comparison and CSV downloads.
- Built-in verification tests for the four conditions in the assignment.

## Classroom formulas

All rates below are **decimal rates** (6.5% = 0.065). The same tax rate, ERP, and debt share apply to both currencies.

1. `D/E = d / (1 - d)`
2. `beta_E = beta_U * (1 + (1 - tax) * D/E)`
3. `Re_USD = Rf_USD + beta_E * ERP`
4. `Rd_USD = Rf_USD + s_USD`
5. `WACC_USD = (1-d)*Re_USD + d*Rd_USD*(1-tax)`
6. `Re_FX = (1+Re_USD)*(1+Rf_FX)/(1+Rf_USD) - 1`
7. `s_FX = s_USD*(1+Rf_FX)/(1+Rf_USD)` (unless manually overridden)
8. `Rd_FX = Rf_FX + s_FX`
9. `WACC_FX = (1-d)*Re_FX + d*Rd_FX*(1-tax)`

`d`: target debt financing share; `tax`: selected project tax rate; `beta_U`: unlevered industry beta; `beta_E`: relevered beta; `Rf`: 10-year government yield proxy; `ERP`: equity risk premium; `s`: BBB borrowing spread; `FX`: foreign-currency version.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Publish with Streamlit Community Cloud

1. Push `app.py`, `requirements.txt`, and this `README.md` to a public GitHub repository.
2. Sign in to [share.streamlit.io](https://share.streamlit.io/) using GitHub.
3. Select **Create app**, choose the repository and branch `main`, set the main file path to `app.py`, and deploy.
4. Check **Manage app → Logs** if any source blocks automated requests.

## Data sources and limitations

| Input | Source |
|---|---|
| U.S. unlevered betas | [Damodaran U.S. betas XLS](https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls) |
| BBB spread (Baa2/BBB, large nonfinancial) | [Damodaran ratings](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html) |
| Corporate tax rates | [OECD Corporate Tax Statistics 2026](https://www.oecd.org/en/publications/corporate-tax-statistics-2026_73af6222-en/full-report/statutory-corporate-income-tax-rates_ce84abb9.html) |
| 10-year sovereign yields | [Trading Economics Bonds](https://tradingeconomics.com/bonds) |

Data refresh on app startup, and when clicking the refresh button. The app caches beta/spread/tax downloads for one hour and bond yields for 30 minutes. **Websites can change their HTML or restrict bots.** If an input cannot be fetched and verified, the app displays a warning and requires a manual value; it does not quietly substitute a fictional live rate. The app first requests the OECD SDMX dataset for 2026 combined general-government statutory rates; a verified manual tax rate may still be necessary if the endpoint or page is unavailable. The app displays the source's stated data vintage where available and separately identifies the fetch timestamp.

Supported countries correspond to those in the dropdown and can be extended in the `COUNTRIES` mapping. Some countries use a shared currency (EUR) but have different sovereign yields. These yields are used as the assignment's country proxies, not as perfectly risk-free rates.

## Verification / independent benchmark

Classroom **Colombia illustration**, not current market quotes:

- Unlevered beta = 0.80; debt share = 30%; corporate tax = 35%; ERP = 6.5%.
- U.S. 10-year yield = 4.0%; Colombia 10-year yield = 12.0%; USD BBB spread = 1.5%.
- D/E = 0.30/0.70 = 0.4285714.
- Levered beta = 0.80 × [1 + (1 − 0.35) × 0.4285714] = 1.0228571.
- USD cost of equity = 0.04 + 1.0228571 × 0.065 = **10.6486%**.
- USD cost of debt = 0.04 + 0.015 = **5.5000%**.
- USD WACC = 0.70 × 10.6485714% + 0.30 × 5.5% × 0.65 = **8.5265%**.
- FX factor = 1.12 / 1.04 = 1.0769231.
- COP cost of equity = 1.106485714 × 1.0769231 − 1 = **19.1600%**.
- COP spread = 1.5% × 1.0769231 = **1.6154%**.
- COP cost of debt = 12% + 1.6153846% = **13.6154%**.
- COP WACC = 0.70 × 19.16% + 0.30 × 13.6153846% × 0.65 = **16.0670%**.

The app also checks: (1) identical yields give identical USD and foreign results when the foreign spread override is off; (2) 0% debt makes WACC equal cost of equity; (3) changing only the foreign spread leaves all USD outputs unchanged. These tests are available in the **Verification tests** expander.

## AI-assisted development

This app was developed with AI assistance. The student is responsible for reviewing the source inputs, verifying the calculations, and including actual AI chat screenshots and an independent calculation in the submission document.
