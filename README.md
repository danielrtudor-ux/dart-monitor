# OpenDART daily monitor

This repository checks the tickers in `tickers.txt` against the Korean Financial Supervisory Service OpenDART API each morning and writes recent filings to `docs/dart-latest.json`.

## Setup
1. Create a GitHub repository and upload these files, preserving the `.github/workflows/` folder.
2. In the repository go to **Settings → Secrets and variables → Actions → New repository secret**.
3. Name the secret exactly `DART_API_KEY`.
4. Paste your OpenDART API key as the value. Never put the key in a normal file.
5. Open **Actions → Update DART feed → Run workflow** for the first test.
6. Open `docs/dart-latest.json`. If it worked, `status: Not run yet` will have been replaced by real data.
7. For a public web URL, enable **Settings → Pages**, choose **Deploy from a branch**, branch `main`, folder `/docs`.

The workflow is scheduled for 23:00 UTC, which is 08:00 KST.

## Security
The DART API key is read only from the GitHub Actions secret named `DART_API_KEY`. It is not written to the JSON output.
