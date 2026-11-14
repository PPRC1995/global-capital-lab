"""Global Capital Lab | International Cost of Capital (Sergio Rebelo class method).

Sources: Damodaran (US sector unlevered betas and Baa2/BBB spread),
OECD statutory corporate tax rates, Trading Economics sovereign 10Y yields.
Data are fetched at runtime. No illustrative rates are silently treated as live.
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import pycountry
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Global Capital Lab | Cost of Capital", page_icon="🌐", layout="wide", initial_sidebar_state="expanded")

BETAS_XLS = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
BETAS_HTML = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html"
BETAS_XLS_ALT = "https://pages.stern.nyu.edu/adamodar/pc/datasets/betas.xls"
RATINGS_URL = "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html"
OECD_URL = "https://www.oecd.org/en/publications/corporate-tax-statistics-2026_73af6222-en/full-report/statutory-corporate-income-tax-rates_ce84abb9.html"
OECD_API_URL = "https://sdmx.oecd.org/public/rest/v1/data/OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,2.0/.A..ST..S13...?startPeriod=2023"
OECD_2024_URL = "https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html"
TE_URL = "https://tradingeconomics.com/bonds"

# Trading Economics labels; add countries here if the website expands coverage.
COUNTRIES = {
    "United States": ("USD", "united-states"), "Colombia": ("COP", "colombia"),
    "Mexico": ("MXN", "mexico"), "Canada": ("CAD", "canada"),
    "United Kingdom": ("GBP", "united-kingdom"), "Germany": ("EUR", "germany"),
    "France": ("EUR", "france"), "Italy": ("EUR", "italy"),
    "Spain": ("EUR", "spain"), "Portugal": ("EUR", "portugal"),
    "Netherlands": ("EUR", "netherlands"), "Belgium": ("EUR", "belgium"),
    "Ireland": ("EUR", "ireland"), "Austria": ("EUR", "austria"),
    "Finland": ("EUR", "finland"), "Greece": ("EUR", "greece"),
    "Japan": ("JPY", "japan"), "China": ("CNY", "china"),
    "India": ("INR", "india"), "South Korea": ("KRW", "south-korea"),
    "Australia": ("AUD", "australia"), "New Zealand": ("NZD", "new-zealand"),
    "Switzerland": ("CHF", "switzerland"), "Sweden": ("SEK", "sweden"),
    "Norway": ("NOK", "norway"), "Denmark": ("DKK", "denmark"),
    "Poland": ("PLN", "poland"), "Czech Republic": ("CZK", "czech-republic"),
    "Hungary": ("HUF", "hungary"), "Turkey": ("TRY", "turkey"),
    "Brazil": ("BRL", "brazil"), "Argentina": ("ARS", "argentina"),
    "Chile": ("CLP", "chile"), "Peru": ("PEN", "peru"),
    "South Africa": ("ZAR", "south-africa"), "Egypt": ("EGP", "egypt"),
    "Israel": ("ILS", "israel"), "Saudi Arabia": ("SAR", "saudi-arabia"),
    "Indonesia": ("IDR", "indonesia"), "Malaysia": ("MYR", "malaysia"),
    "Thailand": ("THB", "thailand"), "Philippines": ("PHP", "philippines"),
    "Singapore": ("SGD", "singapore"), "Vietnam": ("VND", "vietnam"),
    "Pakistan": ("PKR", "pakistan"), "Nigeria": ("NGN", "nigeria"),
    "Kenya": ("KES", "kenya"), "Romania": ("RON", "romania"),
    "Bulgaria": ("BGN", "bulgaria"), "Croatia": ("EUR", "croatia"),
    "Slovakia": ("EUR", "slovakia"), "Slovenia": ("EUR", "slovenia"),
    "Luxembourg": ("EUR", "luxembourg"), "Iceland": ("ISK", "iceland"),
    "Taiwan": ("TWD", "taiwan"), "Hong Kong": ("HKD", "hong-kong"),
    "United Arab Emirates": ("AED", "united-arab-emirates"),
}

TAX_ALIASES = {"United States": ["United States", "USA"], "South Korea": ["Korea", "Republic of Korea"],
               "Czech Republic": ["Czechia", "Czech Republic"], "Turkey": ["Türkiye", "Turkey"],
               "United Kingdom": ["United Kingdom", "UK"], "Taiwan": ["Chinese Taipei", "Taiwan"],
               "Hong Kong": ["Hong Kong (China)", "Hong Kong"]}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GlobalCapitalLab/1.0; educational project)", "Accept-Language": "en-US,en;q=0.9"}


def get_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.text


def extract_source_date(html: str, fallback: str = "Publication date not stated") -> str:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    for pat in [r"Date of Analysis\s*:\s*Data used is as of\s*(January\s+\d{4})",
                r"Last updated on\s*(\d{1,2}\s+\w+\s+\d{4})"]:
        m = re.search(pat, text, flags=re.I)
        if m:
            return m.group(1)
    return fallback


def clean_number(value):
    if pd.isna(value):
        return None
    text = str(value).strip().replace(",", "").replace("%", "").replace("−", "-")
    try:
        x = float(text)
        return x if np.isfinite(x) else None
    except ValueError:
        return None


def _normalized_header(value):
    text = re.sub(r"\s+", " ", str(value)).strip().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _is_industry_header(value):
    h = _normalized_header(value)
    return h in ("industry name", "industry", "industry group", "industry name us") or h.startswith("industry name ")


def _is_beta_header(value):
    h = _normalized_header(value)
    # Exact unlevered beta only; never use cash-corrected or emerging-market beta.
    return h == "unlevered beta" or (h.startswith("unlevered beta ") and not any(
        bad in h for bad in ("cash", "corrected", "emerging", "adjusted")))



def parse_beta_table(df: pd.DataFrame) -> dict[str, float]:
    """Parse an industry beta table without assuming one fixed workbook layout."""
    df = df.copy()
    headers = [_normalized_header(c) for c in df.columns]
    # Prefer the ordinary US industry unlevered beta; do not accidentally use
    # the cash-corrected or emerging-markets beta column.
    industry_indices = [i for i, h in enumerate(headers) if _is_industry_header(h)]
    beta_indices = [i for i, h in enumerate(headers) if _is_beta_header(h)]
    if not industry_indices or not beta_indices:
        raise ValueError(f"Could not identify Industry Name / Unlevered Beta columns. Headings: {headers[:18]}")
    name_idx, beta_idx = industry_indices[0], beta_indices[0]
    out = {}
    for row in df.itertuples(index=False, name=None):
        if len(row) <= max(name_idx, beta_idx):
            continue
        industry = re.sub(r"\s+", " ", str(row[name_idx])).strip()
        val = clean_number(row[beta_idx])
        if industry and industry.casefold() not in ("nan", "total market", "total") and val is not None and 0 <= val < 10:
            out[industry] = val
    if len(out) < 20:
        raise ValueError(f"Only {len(out)} industries parsed; need at least 20")
    return out


def parse_beta_workbook(content: bytes) -> dict[str, float]:
    """Handle XLS, XLSX and header rows preceded by Damodaran's explanatory text."""
    # Damodaran's .xls is traditionally BIFF; some mirrors return HTML or XLSX.
    if content.lstrip()[:30].lower().startswith((b"<!doctype html", b"<html")):
        return parse_beta_html(content.decode("utf-8", errors="replace"))
    engine = "openpyxl" if content[:2] == b"PK" else "xlrd"
    wb = pd.ExcelFile(io.BytesIO(content), engine=engine)
    errors = []
    for sheet in wb.sheet_names:
        raw = pd.read_excel(wb, sheet_name=sheet, header=None, dtype=object)
        for idx in range(min(65, len(raw))):
            headings = [_normalized_header(v) for v in raw.iloc[idx].tolist()]
            if any(_is_industry_header(h) for h in headings) and any(_is_beta_header(h) for h in headings):
                candidate = raw.iloc[idx+1:].copy()
                candidate.columns = raw.iloc[idx].tolist()
                try:
                    return parse_beta_table(candidate)
                except ValueError as exc:
                    errors.append(f"{sheet}, row {idx+1}: {exc}")
    raise ValueError("No usable industry table found in workbook. " + " | ".join(errors[:3]))


def parse_beta_html(html: str) -> dict[str, float]:
    """Parse the HTML table without assuming the headers are the first row."""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.select("table"):
        rows = table.select("tr")
        for j, tr in enumerate(rows[:25]):
            cells = [x.get_text(" ", strip=True) for x in tr.find_all(["th", "td"], recursive=False)]
            heads = [_normalized_header(x) for x in cells]
            if not (any(_is_industry_header(h) for h in heads) and any(_is_beta_header(h) for h in heads)):
                continue
            data = [[x.get_text(" ", strip=True) for x in rr.find_all(["th", "td"], recursive=False)] for rr in rows[j+1:]]
            try:
                return parse_beta_table(pd.DataFrame(data, columns=cells))
            except (ValueError, AssertionError):
                continue
    raise ValueError("No valid Damodaran industry table found in HTML")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_betas():
    """Try the professor's XLS first; fallback to Damodaran's own HTML table."""
    errors = []
    try:
        response = requests.get(BETAS_XLS, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = parse_beta_workbook(response.content)
        return data, "Damodaran U.S. betas (official XLS)", "Workbook publication date: see source", BETAS_XLS
    except Exception as exc:
        errors.append(f"Official XLS: {exc}")
    try:
        response = requests.get(BETAS_XLS_ALT, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = parse_beta_workbook(response.content)
        return data, "Damodaran U.S. betas (official XLS alternate URL)", "Workbook publication date: see source", BETAS_XLS_ALT
    except Exception as exc:
        errors.append(f"Alternate official XLS: {exc}")
    try:
        html = get_html(BETAS_HTML)
        data = parse_beta_html(html)
        return data, "Damodaran U.S. betas (official HTML)", extract_source_date(html), BETAS_HTML
    except Exception as exc:
        errors.append(f"Official HTML: {exc}")
    raise RuntimeError(" | ".join(errors))


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_bbb():
    html = get_html(RATINGS_URL)
    tables = pd.read_html(io.StringIO(html))
    for table in tables:
        for _, row in table.iterrows():
            cells = [str(x).strip() for x in row.tolist()]
            for i, cell in enumerate(cells):
                if re.search(r"\bBaa2\s*/\s*BBB\b", cell, re.I):
                    # In Damodaran table the large nonfinancial rating is col 2 and spread col 3.
                    if i <= 3 and i + 1 < len(cells):
                        value = clean_number(cells[i + 1])
                        if value is not None and 0 < value < 30:
                            return value / 100, extract_source_date(html), RATINGS_URL
    # Defensive HTML extraction if table parser flattens the columns.
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]
        for i, cell in enumerate(cells):
            if re.search(r"\bBaa2\s*/\s*BBB\b", cell, re.I) and i <= 3 and i + 1 < len(cells):
                val = clean_number(cells[i + 1])
                if val is not None and 0 < val < 30:
                    return val / 100, extract_source_date(html), RATINGS_URL
    raise ValueError("Baa2/BBB spread not found in large nonfinancial column")


def extract_oecd_tax_table(html: str) -> dict[str, float]:
    """Parse only a table explicitly identifying jurisdiction and combined statutory rate.

    Never guess rates from an OECD chart or take unrelated effective tax rates.
    """
    for df in pd.read_html(io.StringIO(html)):
        # Flatten multi-level headings when needed.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join(str(v) for v in col if not str(v).startswith("Unnamed")) for col in df.columns]
        columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
        country_col = next((c for c in columns if re.search(r"jurisdiction|country|economy", c, re.I)), None)
        rate_col = next((c for c in columns if re.search(r"combined.*statutory|statutory.*combined", c, re.I)), None)
        if not country_col or not rate_col:
            continue
        df.columns = columns
        rates = {}
        for _, row in df.iterrows():
            country = str(row[country_col]).strip()
            value = clean_number(row[rate_col])
            if value is not None and 0 <= value <= 60 and country and country != "nan":
                rates[country] = value / 100
        if len(rates) >= 15:
            return rates
    raise ValueError("OECD combined statutory country-rate table not available in page HTML")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_oecd():
    """OECD SDMX API; use latest reported year per jurisdiction, not an unreported 2026 year."""
    errors = []
    try:
        response = requests.get(OECD_API_URL, headers={**HEADERS, "Accept": "csvfile, text/csv;q=0.9, */*;q=0.5"}, timeout=35)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        columns = {str(c).upper(): c for c in df.columns}
        country_col = columns.get("REF_AREA")
        value_col = columns.get("OBS_VALUE")
        time_col = columns.get("TIME_PERIOD")
        if not all([country_col, value_col, time_col]):
            raise ValueError("OECD SDMX CSV missing REF_AREA / OBS_VALUE / TIME_PERIOD")
        df = df.loc[pd.to_numeric(df[time_col], errors="coerce").between(2020, datetime.now(timezone.utc).year)].copy()
        # Combined statutory general-government rate: avoid central-only / effective rates.
        # Reject ambiguous responses instead of silently selecting a different measure.
        for field, allowed in [("MEASURE", "CIT_C"), ("TARGETING", "ST"), ("INSTITUTIONAL_SECTOR", "S13")]:
            if field in columns:
                values = df[columns[field]].astype(str).str.upper()
                if not (values == allowed).any():
                    raise ValueError(f"OECD dataset does not contain required {field}={allowed}")
                df = df.loc[values == allowed]
        rates = {}
        df = df.sort_values(time_col, ascending=False).drop_duplicates(subset=[country_col], keep="first")
        latest_year = int(pd.to_numeric(df[time_col], errors="coerce").max()) if len(df) else 0
        for _, row in df.iterrows():
            code = str(row[country_col]).strip()
            val = clean_number(row[value_col])
            if val is None or not 0 <= val <= 60:
                continue
            try:
                name = pycountry.countries.get(alpha_3=code).name
            except (AttributeError, KeyError):
                continue
            rates[name] = val / 100
        # Reconcile common OECD / ISO country-name differences.
        for iso, name in {"USA": "United States", "GBR": "United Kingdom", "KOR": "South Korea",
                          "CZE": "Czech Republic", "TUR": "Turkey", "HKG": "Hong Kong",
                          "TWN": "Taiwan", "ARE": "United Arab Emirates"}.items():
            if country_col in df:
                rows = df.loc[df[country_col].astype(str) == iso]
                if not rows.empty:
                    val = clean_number(rows.iloc[0][value_col])
                    if val is not None:
                        rates[name] = val / 100
        if len(rates) < 15:
            raise ValueError(f"Only {len(rates)} combined statutory rates parsed")
        return rates, f"OECD SDMX (latest reported, through {latest_year}; country years may differ)", OECD_API_URL
    except Exception as exc:
        errors.append(f"SDMX: {exc}")
    # Publication HTML fallback, only when the table has explicit labels.
    for url, vintage in [(OECD_URL, "2026"), (OECD_2024_URL, "2024")]:
        try:
            rates = extract_oecd_tax_table(get_html(url))
            return rates, vintage, url
        except Exception as exc:
            errors.append(f"{vintage} HTML: {exc}")
    raise RuntimeError("OECD statutory rates unavailable. Enter verified manual rates. " + " | ".join(errors))


def yield_from_table(html: str, country: str) -> float:
    """Read the main Trading Economics bonds listing and locate country 10Y row."""
    names = {"United States": ["US 10Y", "United States 10Y"],
             "United Kingdom": ["UK 10Y", "United Kingdom 10Y"],
             "South Korea": ["South Korea 10Y", "Korea 10Y"]}.get(country, [f"{country} 10Y"])
    for df in pd.read_html(io.StringIO(html)):
        if df.shape[1] < 2:
            continue
        for _, row in df.iterrows():
            first = str(row.iloc[0]).strip()
            if any(first.lower() == n.lower() for n in names):
                val = clean_number(row.iloc[1])
                if val is not None and -5 < val < 100:
                    return val / 100
    raise ValueError(f"{country} 10Y row not available in listing")


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_yield(country: str):
    currency, slug = COUNTRIES[country]
    errors = []
    try:
        html = get_html(TE_URL)
        val = yield_from_table(html, country)
        return val, TE_URL, "Retrieved live; quote as-of not verified"
    except Exception as exc:
        errors.append(f"Bonds table: {exc}")
    # The country page is a secondary Trading Economics source, same provider.
    url = f"https://tradingeconomics.com/{slug}/government-bond-yield"
    try:
        html = get_html(url)
        for table in pd.read_html(io.StringIO(html)):
            cols = [str(c).lower() for c in table.columns]
            if "bonds" in cols and "yield" in cols:
                for _, row in table.iterrows():
                    if "10Y" in str(row.iloc[cols.index("bonds")]):
                        val = clean_number(row.iloc[cols.index("yield")])
                        if val is not None and -5 < val < 100:
                            return val / 100, url, "Retrieved live; quote as-of not verified"
        # Published summary sometimes says '10-year government bond yield ... percent'.
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        m = re.search(r"10.year government bond yield[^.]{0,180}?([0-9]+(?:\.[0-9]+)?)\s*percent", text, re.I)
        if m:
            val = float(m.group(1))
            if -5 < val < 100:
                return val / 100, url, "Retrieved live; quote as-of not verified"
        raise ValueError("Could not verify 10Y quote")
    except Exception as exc:
        errors.append(f"Country page: {exc}")
    raise RuntimeError(" | ".join(errors))


def find_tax(rates: dict, country: str):
    names = TAX_ALIASES.get(country, [country])
    for name in names:
        for key, value in rates.items():
            if key.casefold().strip() == name.casefold().strip():
                return value
    return None


def calculate(beta_u: float, tax: float, debt: float, erp: float, rf_us: float, rf_foreign: float,
              spread_us: float, spread_foreign_override: float | None = None):
    """All rates in decimals. Exact classroom equations; no intermediate rounding."""
    if not (0 <= debt < 1):
        raise ValueError("Debt share must be at least 0% and below 100%")
    if not (0 <= tax <= 1):
        raise ValueError("Tax rate must be between 0 and 100%")
    if rf_us <= -1 or rf_foreign <= -1:
        raise ValueError("Government yields must be above -100%")
    de = debt / (1 - debt)
    beta_e = beta_u * (1 + (1 - tax) * de)
    re_us = rf_us + beta_e * erp
    rd_us = rf_us + spread_us
    wacc_us = (1 - debt) * re_us + debt * rd_us * (1 - tax)
    factor = (1 + rf_foreign) / (1 + rf_us)
    re_foreign = (1 + re_us) * factor - 1
    spread_foreign = spread_us * factor if spread_foreign_override is None else spread_foreign_override
    rd_foreign = rf_foreign + spread_foreign
    wacc_foreign = (1 - debt) * re_foreign + debt * rd_foreign * (1 - tax)
    return dict(de=de, beta_e=beta_e, re_us=re_us, rd_us=rd_us, wacc_us=wacc_us,
                factor=factor, re_foreign=re_foreign, spread_foreign=spread_foreign,
                rd_foreign=rd_foreign, wacc_foreign=wacc_foreign)


def check_math():
    c = calculate(.8, .35, .3, .065, .04, .12, .015)
    expected = dict(beta_e=1.0228571428571427, re_us=.10648571428571428,
                    rd_us=.055, wacc_us=.085265, re_foreign=.1916,
                    spread_foreign=.016153846153846154, rd_foreign=.13615384615384615,
                    wacc_foreign=.16067)
    # Expected WACC numbers computed with full precision from professor's example.
    # Tolerances accommodate the slide's rounded display only.
    checks = {"Colombia classroom example": all(abs(c[k] - v) < 1e-5 for k, v in expected.items())}
    same = calculate(.8, .35, .3, .065, .04, .04, .015)
    checks["Equal yields → equal results"] = all(abs(same[a] - same[b]) < 1e-12 for a, b in
                                                   [("re_us", "re_foreign"), ("rd_us", "rd_foreign"), ("wacc_us", "wacc_foreign")])
    zero = calculate(.8, .35, 0, .065, .04, .12, .015)
    checks["Zero debt → WACC equals cost of equity"] = (abs(zero["wacc_us"] - zero["re_us"]) < 1e-12
                                                       and abs(zero["wacc_foreign"] - zero["re_foreign"]) < 1e-12)
    changed = calculate(.8, .35, .3, .065, .04, .12, .015, .05)
    checks["Foreign spread override leaves USD unchanged"] = all(abs(c[k] - changed[k]) < 1e-12 for k in
                                                                    ["re_us", "rd_us", "wacc_us"])
    return checks, c


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
html, body, [class*='css'], [data-testid='stApp'] {font-family:'DM Sans',sans-serif;}
[data-testid='stApp'] {background:#0b0e12;color:#f3f5f7;}
[data-testid='stSidebar'] {background:#12171d;border-right:1px solid #28303a;}
[data-testid='stSidebar'] label, [data-testid='stSidebar'] p, [data-testid='stSidebar'] span, [data-testid='stSidebar'] h1, [data-testid='stSidebar'] h2, [data-testid='stSidebar'] h3, [data-testid='stSidebar'] [data-testid='stCaptionContainer'] {color:#f3f5f7 !important;}
[data-testid='stSidebar'] [data-testid='stWidgetLabel'] p {color:#f3f5f7 !important;}
[data-testid='stSidebar'] [data-testid='stMarkdownContainer'] p {color:#e4eaf0 !important;}
[data-testid='stSidebar'] [data-testid='stSlider'] [data-testid='stTickBar'] {color:#e4eaf0 !important;}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif;letter-spacing:-.035em;}
h1 {font-size:3.1rem !important;}
[data-testid='stMetric'] {background:#161c23;border:1px solid #2a343d;border-radius:16px;padding:18px 20px;}
[data-testid='stMetricLabel'] {color:#a8b4c0;}
[data-testid='stMetricValue'] {color:#c8ff72;font-family:'Space Grotesk';}
div.stButton>button[kind='primary'] {background:#c8ff72;color:#0b0e12;border:0;font-weight:700;}
div.stButton>button {border-radius:10px;}
hr {border-color:#29313a;}
.hero {padding:26px 30px;border-radius:20px;background:linear-gradient(110deg,#1b242b,#11151a);border:1px solid #2b363e;margin:4px 0 22px;}
.eyebrow {color:#c8ff72;font-weight:700;letter-spacing:.16em;font-size:.73rem;}
.subtitle {color:#a9b6c3;font-size:1.05rem;}
.small {font-size:.82rem;color:#a7b3bf;}
.green {color:#c8ff72;}

/* Global Capital Lab — accessible executive dark UI */
[data-testid="stApp"] { background: #090d12 !important; color: #f4f7fb !important; }
[data-testid="stSidebar"] { background: #111923 !important; border-right: 1px solid #293441 !important; }
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p,
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] { color: #edf3f9 !important; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: #aebdca !important; }
[data-testid="stSidebar"] div[data-baseweb="select"] *,
[data-testid="stSidebar"] div[data-baseweb="input"] input { color: #18222d !important; }
[data-testid="stSidebar"] [data-testid="stSlider"] p { color: #f4f7fb !important; }
[data-testid="stMetric"] { box-shadow: 0 6px 22px rgba(0,0,0,.16); }
[data-testid="stAlert"] { border-radius: 12px !important; }
[data-testid="stExpander"] { border-radius: 14px !important; border-color: #33404d !important; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
.hero { padding: 32px 36px !important; background: linear-gradient(120deg,#1b2730,#10161e) !important; border: 1px solid #33424c !important; }
.hero h1 { color: #fff !important; }
.hero .subtitle { color: #c1cfdb !important; }

/* Clean up the data and download experience */
[data-testid="stDownloadButton"] button {background:#c8ff72 !important;color:#0a1117 !important;border:1px solid #c8ff72 !important;font-weight:750 !important;opacity:1 !important;}
[data-testid="stDownloadButton"] button:disabled {background:#303b46 !important;color:#d8e2eb !important;opacity:1 !important;}
[data-testid="stApp"] [data-testid="stDataFrame"] {border:1px solid #344150 !important;border-radius:12px;}
[data-testid="stSidebar"] [data-testid="stButton"] button {background:#c8ff72 !important;color:#0c151d !important;font-weight:700 !important;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#cbd5df !important;}
[data-testid="stApp"] [data-testid="stExpander"] {background:#131b24;border:1px solid #354454;border-radius:12px;}
[data-testid="stApp"] [data-testid="stAlert"] {border-radius:12px;}
</style>
"""
CSS += """
<style>
[data-testid="stAppViewContainer"] { background: radial-gradient(circle at 80% 0%, #14212b 0, #0a0f15 40%, #090d12 100%) !important; }
[data-testid="stSidebar"] {background:#111a23 !important;}
[data-testid="stSidebar"] button {font-weight:700 !important;}
/* The global sidebar white-text rule must not override the lime button's label. */
[data-testid="stSidebar"] [data-testid="stButton"] button,
[data-testid="stSidebar"] [data-testid="stButton"] button p,
[data-testid="stSidebar"] [data-testid="stButton"] button span,
[data-testid="stSidebar"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] p {
  color:#101820 !important;
  -webkit-text-fill-color:#101820 !important;
  font-weight:800 !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] button:hover {background:#d8ff99 !important;}
[data-testid="stSidebar"] [data-testid="stButton"] button:focus-visible {outline:2px solid #ffffff !important;outline-offset:2px;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {font-size:.91rem !important;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:#b8c8d5 !important;}
[data-testid="stDownloadButton"] button {background:#c8ff72 !important;color:#0c151d !important;border-radius:10px !important;}
[data-testid="stDownloadButton"] button:disabled {background:#35404a !important;color:#e3eaf0 !important;}
[data-testid="stMetric"] {background:linear-gradient(145deg,#18242d,#121b24) !important;border:1px solid #33434e !important;}
[data-testid="stExpander"] {background:#131c25 !important;}
[data-testid="stApp"] a {color:#a7ceff;}
.hero {border:1px solid #40505d !important;box-shadow:0 14px 45px rgba(0,0,0,.20);}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

if "refresh_counter" not in st.session_state:
    st.session_state.refresh_counter = 0

with st.sidebar:
    st.markdown("### 🌐 GLOBAL CAPITAL LAB")
    st.caption("International Valuation · Kellogg")
    if st.button("↻ Refresh market data", use_container_width=True):
        fetch_betas.clear(); fetch_bbb.clear(); fetch_oecd.clear(); fetch_yield.clear()
        st.session_state.refresh_counter += 1
        st.rerun()
    st.caption("Fetches run on page load and refresh. Failed sources require manual values; no hidden estimates.")

    country = st.selectbox("Target country", list(COUNTRIES), index=0)
    currency = COUNTRIES[country][0]
    st.caption(f"Currency: {currency} | USD base comparison")
    erp_pct = st.number_input("Equity risk premium (%)", min_value=0., max_value=50., value=6.5, step=.25)
    debt_pct = st.slider("Target debt financing (%)", min_value=0, max_value=95, value=30, step=5)
    st.divider()
    st.markdown("#### Manual inputs / overrides")
    st.caption("Switch ON to override fetched values. All rates are annual percentages.")

# Collect live data with explicit error reporting.
issues = []
try:
    betas, beta_source, beta_date, beta_url = fetch_betas()
except Exception as exc:
    betas = {}; beta_source = "Unavailable"; beta_date = "Unavailable"; beta_url = BETAS_XLS
    issues.append(f"Industry betas: {exc}")
try:
    spread_us_live, spread_date, spread_url = fetch_bbb()
except Exception as exc:
    spread_us_live = None; spread_date = "Unavailable"; spread_url = RATINGS_URL
    issues.append(f"BBB spread: {exc}")
try:
    tax_rates, tax_vintage, tax_url = fetch_oecd()
except Exception as exc:
    tax_rates = {}; tax_vintage = "Unavailable"; tax_url = OECD_URL
    issues.append(f"OECD corporate tax rates: {exc}")
try:
    rf_us_live, us_yield_url, us_yield_date = fetch_yield("United States")
except Exception as exc:
    rf_us_live = None; us_yield_url = TE_URL; us_yield_date = "Unavailable"
    issues.append(f"U.S. 10Y yield: {exc}")
if country == "United States":
    rf_foreign_live, foreign_yield_url, foreign_yield_date = rf_us_live, us_yield_url, us_yield_date
else:
    try:
        rf_foreign_live, foreign_yield_url, foreign_yield_date = fetch_yield(country)
    except Exception as exc:
        rf_foreign_live = None; foreign_yield_url = TE_URL; foreign_yield_date = "Unavailable"
        issues.append(f"{country} 10Y yield: {exc}")

us_tax_live = find_tax(tax_rates, "United States")
foreign_tax_live = find_tax(tax_rates, country)

with st.sidebar:
    if betas:
        names = sorted(betas)
        preferred = next((x for x in names if x.casefold() == "software (system & application)"), None)
        industry = st.selectbox("Industry (Damodaran U.S.)", names, index=names.index(preferred) if preferred else 0)
        beta_default = betas[industry]
    else:
        industry = st.text_input("Industry", value="Software (System & Application)")
        beta_default = None
    manual_beta = st.toggle("Override unlevered beta", value=beta_default is None)
    beta_input = st.number_input("Unlevered beta", min_value=0., max_value=10., value=float(beta_default or 0.), step=.05, format="%.4f", disabled=not manual_beta)
    beta_u = beta_input if manual_beta else beta_default

    tax_choice = st.radio("Project tax rate for BOTH currencies", ["U.S. tax rate", "Selected-country tax rate"], horizontal=False)
    selected_tax_live = us_tax_live if tax_choice == "U.S. tax rate" else foreign_tax_live
    manual_tax = st.toggle("Override project corporate tax", value=selected_tax_live is None)
    tax_input = st.number_input("Corporate tax rate (%)", min_value=0., max_value=100., value=round(selected_tax_live * 100, 3) if selected_tax_live is not None else 0., step=.5, format="%.3f", disabled=not manual_tax)
    tax = tax_input / 100 if manual_tax else selected_tax_live

    manual_spread = st.toggle("Override USD BBB spread", value=spread_us_live is None)
    spread_input = st.number_input("USD BBB spread (percentage points)", min_value=0., max_value=40., value=round(spread_us_live * 100, 4) if spread_us_live is not None else 0., step=.1, format="%.4f", disabled=not manual_spread)
    spread_us = spread_input / 100 if manual_spread else spread_us_live

    manual_us = st.toggle("Override U.S. 10Y yield", value=rf_us_live is None)
    us_input = st.number_input("U.S. 10Y yield (%)", min_value=-5., max_value=100., value=round(rf_us_live * 100, 4) if rf_us_live is not None else 0., step=.1, format="%.4f", disabled=not manual_us)
    rf_us = us_input / 100 if manual_us else rf_us_live

    manual_foreign = st.toggle("Override selected-country 10Y yield", value=rf_foreign_live is None)
    foreign_input = st.number_input(f"Selected-country 10Y yield ({country}, %)", min_value=-5., max_value=100., value=round(rf_foreign_live * 100, 4) if rf_foreign_live is not None else 0., step=.1, format="%.4f", disabled=not manual_foreign)
    rf_foreign = foreign_input / 100 if manual_foreign else rf_foreign_live
    # When comparing USD to USD, a single manually overridden U.S. yield applies to both sides.
    if country == "United States" and not manual_foreign:
        rf_foreign = rf_us

    foreign_override_on = st.toggle("Override foreign BBB spread", value=False)
    auto_foreign_spread = (spread_us * (1 + rf_foreign) / (1 + rf_us)) if None not in (spread_us, rf_foreign, rf_us) else None
    foreign_spread_input = st.number_input(f"{currency} BBB spread (percentage points)", min_value=0., max_value=40.,
                                           value=round(auto_foreign_spread * 100, 4) if auto_foreign_spread is not None else 0.,
                                           step=.1, format="%.4f", disabled=not foreign_override_on, key="foreign_bbb_spread_input")
    foreign_spread_override = foreign_spread_input / 100 if foreign_override_on else None

st.markdown("<div class='hero'><div class='eyebrow'>CROSS-BORDER VALUATION INTELLIGENCE</div><h1>Global Capital Lab<span class='green'>.</span></h1><div class='subtitle'>Compare project financing costs in USD and local currency, using transparent market inputs and classroom formulas.</div></div>", unsafe_allow_html=True)

if issues:
    st.warning(f"Market data: {len(issues)} source(s) unavailable. Open Data availability & troubleshooting for details; verified manual overrides remain available.")
    with st.expander("Data availability & troubleshooting", expanded=False):
        for issue in issues:
            short = issue.split(":", 1)[0]
            st.markdown(f"**{short}** — automatic retrieval unavailable. Use the matching manual override and check the source link below.")
            st.caption(issue[:650])
        st.caption("The app never labels an unavailable source as live. Market data refresh requires network access from Streamlit Cloud.")

missing = [name for name, value in [("Unlevered beta", beta_u), ("Project tax rate", tax),
                                    ("USD BBB spread", spread_us), ("U.S. government yield", rf_us),
                                    ("Foreign government yield", rf_foreign)] if value is None]
if missing:
    st.error("To calculate results, enter verified manual inputs for: " + ", ".join(missing) + ".")
    st.stop()

try:
    c = calculate(beta_u, tax, debt_pct / 100, erp_pct / 100, rf_us, rf_foreign, spread_us, foreign_spread_override)
except ValueError as exc:
    st.error(str(exc)); st.stop()

st.markdown(f"#### {industry} · United States vs. {country}")
cols = st.columns(3)
cols[0].metric("USD WACC", f"{c['wacc_us']:.2%}")
cols[1].metric(f"{currency} WACC", f"{c['wacc_foreign']:.2%}")
cols[2].metric("Target debt share", f"{debt_pct}%")

left, right = st.columns(2, gap="large")
with left:
    st.subheader("🇺🇸 USD Financing")
    st.metric("Cost of Equity", f"{c['re_us']:.4%}")
    st.metric("Cost of Debt · Pretax", f"{c['rd_us']:.4%}")
    st.metric("Cost of Debt · After tax", f"{c['rd_us'] * (1 - tax):.4%}")
with right:
    st.subheader(f"🌍 {currency} Financing")
    st.metric("Cost of Equity", f"{c['re_foreign']:.4%}")
    st.metric("Cost of Debt · Pretax", f"{c['rd_foreign']:.4%}")
    st.metric("Cost of Debt · After tax", f"{c['rd_foreign'] * (1 - tax):.4%}")

comparison = pd.DataFrame({
    "Metric": ["Cost of equity", "Pretax cost of debt", "After-tax cost of debt", "WACC"],
    "USD": [c["re_us"], c["rd_us"], c["rd_us"] * (1 - tax), c["wacc_us"]],
    f"{currency} (selected)": [c["re_foreign"], c["rd_foreign"], c["rd_foreign"] * (1 - tax), c["wacc_foreign"]],
})
fig = go.Figure()
for col, color in [("USD", "#c8ff72"), (f"{currency} (selected)", "#7b95ff")]:
    fig.add_trace(go.Bar(name=col, x=comparison["Metric"], y=comparison[col] * 100,
                         marker_color=color, text=[f"{x:.2%}" for x in comparison[col]], textposition="outside"))
fig.update_layout(barmode="group", template="plotly_dark", paper_bgcolor="#0b0e12", plot_bgcolor="#0b0e12",
                  font_color="#e9edf1", legend_orientation="h", yaxis_title="Annual cost (%)",
                  margin=dict(t=25, b=25, l=20, r=20), height=370)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Calculation walkthrough · All nine formulas", expanded=False):
    st.markdown(f"""
**1. Debt / Equity:** d / (1 − d) = {debt_pct/100:.4f} / {1-debt_pct/100:.4f} = **{c['de']:.6f}**

**2. Levered beta:** βE = βU × [1 + (1 − tax) × D/E] = **{c['beta_e']:.6f}**

**3. USD cost of equity:** Re = U.S. 10Y + βE × ERP = **{c['re_us']:.4%}**

**4. USD cost of debt:** Rd = U.S. 10Y + BBB spread = **{c['rd_us']:.4%}**

**5. USD WACC:** (1 − d) × Re + d × Rd × (1 − tax) = **{c['wacc_us']:.4%}**

**6. Foreign cost of equity:** Re* = (1 + Re) × (1 + foreign 10Y)/(1 + U.S. 10Y) − 1 = **{c['re_foreign']:.4%}**

**7. Foreign BBB spread:** s* = s × (1 + foreign 10Y)/(1 + U.S. 10Y) = **{c['spread_foreign']:.4%}** {('(manual override)' if foreign_override_on else '(automatic)')}

**8. Foreign cost of debt:** Rd* = foreign 10Y + foreign BBB spread = **{c['rd_foreign']:.4%}**

**9. Foreign WACC:** (1 − d) × Re* + d × Rd* × (1 − tax) = **{c['wacc_foreign']:.4%}**

**Definitions:** d = target debt share; βU = unlevered industry beta; βE = relevered equity beta; tax = one selected project corporate tax rate used in both currencies; ERP = equity risk premium; s = USD BBB spread; * = foreign currency. All percentage inputs are converted to decimal rates before calculation. No intermediate rounding.
""")

st.subheader("All-industry comparison")
if betas:
    rows = []
    for name, b in sorted(betas.items()):
        val = calculate(b, tax, debt_pct / 100, erp_pct / 100, rf_us, rf_foreign, spread_us, foreign_spread_override)
        rows.append({"Industry": name, "Unlevered beta": b, "Levered beta": val["beta_e"],
                     "USD Cost of Equity (%)": val["re_us"] * 100, f"{currency} Cost of Equity (%)": val["re_foreign"] * 100,
                     "USD WACC (%)": val["wacc_us"] * 100, f"{currency} WACC (%)": val["wacc_foreign"] * 100})
    industries_df = pd.DataFrame(rows)
    st.dataframe(industries_df, use_container_width=True, hide_index=True)
    st.download_button("↓ Download all industries (CSV)", industries_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="global_capital_lab_all_industries.csv", mime="text/csv")
else:
    st.warning("The all-industry comparison requires the official Damodaran beta table. Automatic download is currently unavailable; press Refresh market data to retry. The app will not invent industry betas.")

result_df = comparison.copy()
result_df["USD"] *= 100
result_df[f"{currency} (selected)"] *= 100
st.download_button("↓ Download selected comparison (CSV)", result_df.to_csv(index=False).encode("utf-8-sig"),
                   file_name="global_capital_lab_comparison.csv", mime="text/csv")

st.subheader("Data sources & assumptions")
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
source_rows = [
    ("U.S. industry unlevered betas", beta_source, beta_date, beta_url, "Manual" if manual_beta else "Fetched"),
    ("Baa2/BBB spread · large nonfinancial", "Damodaran", spread_date, spread_url, "Manual" if manual_spread else "Fetched"),
    ("Statutory corporate tax rates", "OECD", tax_vintage, tax_url, "Manual" if manual_tax else "Fetched"),
    ("U.S. 10Y government yield", "Trading Economics", us_yield_date, us_yield_url, "Manual" if manual_us else "Fetched"),
    (f"{country} 10Y government yield", "Trading Economics", foreign_yield_date, foreign_yield_url, "Manual" if manual_foreign else "Fetched"),
    ("Foreign BBB spread", "Classroom conversion formula", "Current calculation", "", "Manual" if foreign_override_on else "Calculated"),
]
source_df = pd.DataFrame(source_rows, columns=["Input", "Provider", "Source data date", "Source URL", "Mode"])
st.dataframe(source_df, hide_index=True, use_container_width=True,
             column_config={"Source URL": st.column_config.LinkColumn("Official source", display_text="Open source ↗"),
                            "Input": st.column_config.TextColumn(width="large"),
                            "Source data date": st.column_config.TextColumn(width="medium")})
st.caption(f"Page fetch checked at {now}. This is the fetch time, not necessarily the market quote's as-of date. Please verify market dates and tax vintage at the linked source. Government yields are used as classroom risk-free proxies; they may contain sovereign risk. Tax rate and ERP are held constant across currencies. No separate country equity premium is added.")

# Verification checks remain available through check_math(), but are not displayed in the app.

st.caption("Global Capital Lab · Educational project · Formula conventions: Sergio Rebelo, International Finance, 2026")
