"""Non-derivative Form 4 evidence through the existing Oracle provider."""

import json
from datetime import date

from .research_documents import SourceCoverage, digest, timestamp
from .research_documents_discovery import filing_sources
from .research_documents_evidence import ResearchEvidence


def insider_evidence(query, now, bound):
    if not (query.symbol or query.cik):
        return [], SourceCoverage(
            source_id="insider", complete=False, observed_at=now, warning="symbol_or_cik_required"
        )
    result = filing_sources(query.symbol, query.cik, query.as_of_date, insider=True)
    filings = {f["accessionNumber"]: f for f in result.get("filings", [])}
    evidence = []
    gaps = [str(w.get("code", "sec_source_warning")) for w in result.get("warnings", [])]
    for transaction in result.get("ownershipTransactions", []):
        filing = filings.get(transaction["accessionNumber"], {})
        published = timestamp(filing.get("acceptedAt"))
        if not published or published >= bound or not filing.get("url"):
            gaps.append("form4_publication_unknown_or_after_cutoff")
            continue
        source_id = "sec:" + transaction["accessionNumber"]
        text = json.dumps(transaction, sort_keys=True, ensure_ascii=False)
        evidence.append(
            ResearchEvidence(
                evidence_id=digest((source_id + text).encode()),
                source_id=source_id,
                kind="observation",
                title="Form 4 non-derivative transaction",
                url=filing["url"],
                published_at=published,
                retrieved_at=now,
                value=transaction.get("shares"),
                unit="shares" if transaction.get("shares") is not None else None,
                text=text,
                locator="nonDerivativeTable/nonDerivativeTransaction",
                accession=transaction["accessionNumber"],
                metric="insider_transaction_shares",
                verified=True,
                source_type="sec",
                symbol=transaction.get("issuerTicker"),
                period_end=(
                    date.fromisoformat(transaction["transactionDate"])
                    if transaction.get("transactionDate")
                    else None
                ),
            )
        )
    return evidence, SourceCoverage(
        source_id="insider",
        complete=not gaps,
        observed_at=now,
        evidence_ids=[e.evidence_id for e in evidence],
        warning="; ".join(
            gaps + ["bounded latest five Form 4 filings; non-derivative transactions only"]
        ),
    )
