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

GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "danielrtudor-ux")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "dart-monitor")
GITHUB_WORKFLOW = os.environ.get(
    "GITHUB_WORKFLOW",
    "ad-hoc-governance.yml",
)
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Korea-Governance-MCP/1.1",
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


def github_api_request(url, method="GET", payload=None):
    token = os.environ.get("GITHUB_TOKEN")

    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is not configured on the server."
        )

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Korea-Governance-MCP/1.1",
    }

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return {
                "status_code": response.status,
                "body": json.loads(body) if body else None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API error {exc.code}: {body}"
        ) from exc


@mcp.tool()
def get_company_governance(ticker: str) -> dict:
    """
    Retrieve the latest stored governance analysis for a Korean company.

    The ticker can be a six-digit Korean security ticker such as 003240.
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
                "Use run_governance_analysis to generate one."
            ),
        }

    return {
        "status": "ok",
        "ticker": ticker,
        "source_url": url,
        "report": data,
    }


@mcp.tool()
def run_governance_analysis(ticker: str) -> dict:
    """
    Trigger the GitHub Actions ad-hoc governance workflow for a Korean company.

    Use this when a fresh governance report is needed or when no stored report
    exists yet.

    The workflow runs asynchronously. After triggering it, wait for the GitHub
    workflow to finish, then call get_company_governance(ticker) to retrieve
    the generated report.
    """

    ticker = clean_ticker(ticker)

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/"
        f"{GITHUB_WORKFLOW}/dispatches"
    )

    payload = {
        "ref": GITHUB_BRANCH,
        "inputs": {
            "ticker": ticker,
        },
    }

    result = github_api_request(
        url,
        method="POST",
        payload=payload,
    )

    return {
        "status": "triggered",
        "ticker": ticker,
        "workflow": GITHUB_WORKFLOW,
        "branch": GITHUB_BRANCH,
        "github_status_code": result["status_code"],
        "message": (
            "Governance analysis was triggered successfully. "
            "The GitHub Actions workflow runs asynchronously. "
            "Retrieve the report after the workflow completes."
        ),
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
            "Trigger a fresh DART governance analysis by Korean security ticker",
            "Retrieve a stored governance report by Korean security ticker",
            "Retrieve the most recently generated governance report",
            "Provide DART-derived ownership, board and AGM information",
            "Provide provisional activist-opportunity signals and scores",
        ],
        "typical_workflow": [
            "Call run_governance_analysis(ticker)",
            "Wait for the GitHub Actions workflow to finish",
            "Call get_company_governance(ticker)",
            "Interpret the governance data and produce the activist assessment",
        ],
        "example": "run_governance_analysis(ticker='003240')",
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))

    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=port,
    )
