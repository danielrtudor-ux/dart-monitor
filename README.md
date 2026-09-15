# OpenDART valuation monitor

This repository checks the tickers in `tickers.txt` against Korea's OpenDART API, calculates reviewed trailing twelve-month valuation metrics, and publishes a sortable dashboard.

**Dashboard:** https://danielrtudor-ux.github.io/dart-monitor/

The dashboard reads `docs/dashboard-data.json`, a compact public feed generated from the complete valuation and audit outputs. Blank ratios are deliberate when debt, cash restrictions, ownership claims, currency conversion, or the relevant profit measure is unsuitable.

## Setup

1. Add an Actions repository secret named exactly `DART_API_KEY` containing the OpenDART API key.
2. Run **Actions → Update DART feed and valuations → Run workflow** for the first collection.
3. Enable **Settings → Pages**, choose **Deploy from a branch**, branch `main`, folder `/docs`.

The workflow runs at 07:30 Korea time and commits updated DART, valuation, audit and dashboard feeds.

## Security

The DART API key is read only from the GitHub Actions secret. It is never written to the public output.
