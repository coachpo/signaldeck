"""Original-document selection through Oracle's existing bounded SEC adapter."""

import json
import os

from .contracts import RuntimeToolContext
from .runtime_sec_filings import (
    execute_sec_filings_lookup,
    parse_sec_filings_lookup_arguments,
)


def filing_sources(symbol, cik, as_of_date, *, insider=False):
    arguments = {
        "formTypes": ["4"] if insider else ["10-K", "10-Q", "8-K"],
        "itemLimit": 5,
        "includeOwnershipTransactions": insider,
    }
    if symbol:
        arguments["ticker"] = symbol
    if cik and not symbol:
        arguments["cik"] = cik
    if as_of_date:
        arguments["endDate"] = as_of_date.isoformat()
    result = execute_sec_filings_lookup(
        RuntimeToolContext({"edgar_contact_email": os.environ.get("EDGAR_CONTACT_EMAIL", "")}),
        parse_sec_filings_lookup_arguments(json.dumps(arguments)),
    )
    if symbol and cik and result.get("cik"):
        expected = str(cik).upper().removeprefix("CIK").lstrip("0")
        resolved = str(result["cik"]).lstrip("0")
        if expected != resolved:
            return {
                "filings": [],
                "ownershipTransactions": [],
                "warnings": [{"code": "sec_symbol_cik_mismatch"}],
            }
    return result
