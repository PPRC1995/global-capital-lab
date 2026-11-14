# Global Capital Lab

**International Cost of Capital | Cross-Border Valuation Dashboard**

An interactive Streamlit dashboard that compares the cost of equity, pretax and after-tax cost of debt, and weighted average cost of capital (WACC) in **U.S. dollars** and a selected country's currency.

**Live app:** https://global-capital-lab.streamlit.app/

## Features

- Dark-themed dashboard with side-by-side USD and local-currency results and a comparison chart.
- U.S. industry unlevered betas from Aswath Damodaran.
- Damodaran's Baa2/BBB borrowing spread for large nonfinancial firms.
- Corporate tax rates retrieved from OECD data sources.
- 10-year government bond yields retrieved from Trading Economics.
- Select an industry and target country, and adjust the equity risk premium and target debt share.
- Choose the U.S. or selected-country corporate tax rate; the selected rate is used consistently in both currencies.
- Manually override the unlevered beta, tax rate, borrowing spreads, and government yields when needed.
- Automatically convert the foreign-currency BBB spread unless a manual override is enabled.
- Refresh market data, review source information and retrieval status, and download CSV results.
- Compare cost of capital across all available industries.

## Model formulas

All rates are expressed as decimals in the calculations (for example, 6.5% = 0.065). The same project tax rate, equity risk premium, and debt share apply to both financing currencies.

1. `D/E = d / (1 - d)`
2. `beta_E = beta_U * (1 + (1 - tax) * D/E)`
3. `Re_USD = Rf_USD + beta_E * ERP`
4. `Rd_USD = Rf_USD + s_USD`
5. `WACC_USD = (1 - d) * Re_USD + d * Rd_USD * (1 - tax)`
6. `Re_FX = (1 + Re_USD) * (1 + Rf_FX) / (1 + Rf_USD) - 1`
7. `s_FX = s_USD * (1 + Rf_FX) / (1 + Rf_USD)` (unless manually overridden)
8. `Rd_FX = Rf_FX + s_FX`
9. `WACC_FX = (1 - d) * Re_FX + d * Rd_FX * (1 - tax)`

Where:
- `d` = target debt share, `D / (D + E)`
- `tax` = project corporate tax rate
- `beta_U` = unlevered industry beta
- `beta_E` = levered equity beta
- `ERP` = equity risk premium
- `Rf` = 10-year government bond yield used as a rate proxy
- `s` = BBB borrowing spread
- `FX` = selected foreign currency

The app retains full precision for calculations and rounds values for display.

## Data sources

| Input | Source |
| --- | --- |
| U.S. industry unlevered betas | [Damodaran U.S. industry betas](https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls) |
| Baa2/BBB borrowing spread for large nonfinancial firms | [Damodaran ratings and spreads](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html) |
| Statutory corporate income tax rates | [OECD Corporate Tax Statistics](https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html) |
| 10-year government bond yields | [Trading Economics Bonds](https://tradingeconomics.com/bonds) |

The application requests OECD data through its official SDMX service and may use other official OECD publications if necessary. Data are fetched on app startup and when the **Refresh market data** button is pressed. Industry betas, spreads, and tax data are cached for one hour; bond yields are cached for 30 minutes. Refresh clears these caches.

Source information and available data dates are displayed in the dashboard. Retrieval times are identified separately from original market observation dates. If a website blocks access or a data point cannot be retrieved, the app reports the issue rather than silently substituting an assumed live rate. Manual overrides remain available.

## Default configuration

- **Industry:** Software (System & Application)
- **Target country:** United States
- **Project tax rate:** U.S. statutory corporate tax rate
- **Equity risk premium:** 6.5%
- **Target debt financing:** 30%

## Run locally

Install Python and then run these commands in the project folder:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Upload `app.py`, `requirements.txt`, and `README.md` to a GitHub repository.
2. Sign in at [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub.
3. Create a new app, select the repository and branch, and set the main file path to `app.py`.
4. Deploy the app and use **Manage app → Logs** to review any data retrieval issues.

## Model checks and assumptions

The model is designed to support independent checks, including:

- **Equal government yields:** With the foreign spread override off and other shared inputs unchanged, identical government yields produce identical USD and foreign-currency results.
- **Zero debt:** At a 0% debt share, WACC equals the cost of equity in each currency.
- **Foreign spread override:** Changing only the foreign BBB spread changes foreign-currency debt costs and WACC, while leaving the USD results unchanged.

These checks can be reproduced by adjusting the inputs in the dashboard. They are not presented as a separate built-in testing panel.

The model uses U.S. industry betas as a proxy for project operating risk, 10-year government yields as currency-specific rate proxies, and one project tax rate for both financing scenarios. Government yields may include sovereign, term, and liquidity risk. The foreign-currency conversion uses relative government yields and does not add a separate country equity risk premium. Interest deductions are assumed to be usable.

## Project information

This project was developed with AI-assisted programming. Model outputs should be independently checked before being used for financial decisions. The dashboard is intended for financial analysis and educational exploration, not investment advice.
