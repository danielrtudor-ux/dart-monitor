#!/usr/bin/env python3

import json
import os
import urllib.error
import urllib.request

from fastmcp import FastMCP

mcp = FastMCP("Korea Governance Monitor")

DATA_BASE = os.environ.get(
    "GOVERNANCE_DATA_BASE",
    "https://danielrtudor-ux.github.io/dart-monitor/governance",
)


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Korea-Governance-MCP/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def clean_ticker(ticker):
    ticker = str(ticker or "").strip()

    if ticker.isdigit():
        return ticker.zfill(6)

    return ticker.upper()


@mcp.tool()
def get_company_governance(ticker: str) -> dict:
    """
    Retrieve the latest stored governance analysis for a Korean company.

    The ticker can be a six-digit Korean security ticker such as 000830.
    Returns ownership, board, AGM, governance, legal-leverage and provisional
    activist-opportunity information produced by the DART governance monitor.

    This tool retrieves an existing report. It does not run a new DART
    collection.
    """

    ticker = clean_ticker(ticker)

    url = f"{DATA_BASE}/{ticker}.json"
    data = fetch_json(url)

    if data is None:
        return {
            "status": "not_found",
            "ticker": ticker,
            "message": (
                "No stored governance report was found for this ticker. "
                "Run the ad-hoc governance workflow for the company first."
            ),
        }

    return {
        "status": "ok",
        "ticker": ticker,
        "source_url": url,
        "report": data,
    }


@mcp.tool()
def get_latest_governance_report() -> dict:
    """
    Retrieve the most recently generated ad-hoc governance report.
    """

    url = f"{DATA_BASE}/latest.json"
    data = fetch_json(url)

    if data is None:
        return {
            "status": "not_found",
            "message": "No latest governance report is currently available.",
        }

    return {
        "status": "ok",
        "source_url": url,
        "report": data,
    }


@mcp.tool()
def governance_help() -> dict:
    """
    Explain what the Korea Governance Monitor can currently do.
    """

    return {
        "service": "Korea Governance Monitor",
        "capabilities": [
            "Retrieve a stored governance report by Korean security ticker",
            "Retrieve the most recently generated governance report",
            "Provide DART-derived ownership, board and AGM information",
            "Provide provisional activist-opportunity signals and scores",
        ],
        "example": "get_company_governance(ticker='000830')",
        "note": (
            "A company must currently have been processed by the ad-hoc "
            "governance GitHub workflow before its report can be retrieved."
        ),
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))

    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=port,
    )
