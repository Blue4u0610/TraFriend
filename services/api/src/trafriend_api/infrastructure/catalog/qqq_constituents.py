from __future__ import annotations

import re
from datetime import date
from html import unescape
from typing import Mapping, Optional

import httpx

from trafriend_api.domain.errors import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent

# Published by the issuer's public /qqq-etf/en/about.html holdings component.
QQQ_HOLDINGS_URL = (
    "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/holdings/fund"
    "?idType=ticker&interval=monthly&productType=ETF"
)
QQQ_HOLDINGS_SOURCE = "QQQ_EQUITY_HOLDINGS:Invesco"
_EQUITY_TYPES = frozenset({"COM", "ADR", "DRNY"})
_EXCLUDED_TYPES = frozenset({"IFUT", "CURR", "CURRCOL", "SYN"})
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,15}\Z")
_CUSIP = re.compile(r"[A-Z0-9*@#]{9}\Z")
_INSTRUMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


def fetch_qqq_constituents(
    *,
    client: Optional[httpx.Client] = None,
    instrument_ids: Optional[Mapping[str, str]] = None,
) -> tuple[NasdaqConstituent, ...]:
    """Read the current QQQ equity-holdings proxy, not a formal NDX membership list.

    The issuer can hold more than 100 equity securities, including share classes
    and spin-offs. Never truncate to 100 or infer complete index membership.
    Existing catalog IDs take precedence; a security CUSIP provides stable identity
    for new entries. The caller owns persistence and membership-version policy.
    """
    if client is None:
        with httpx.Client(timeout=20.0, follow_redirects=False) as owned_client:
            return fetch_qqq_constituents(
                client=owned_client, instrument_ids=instrument_ids
            )

    try:
        response = client.get(QQQ_HOLDINGS_URL)
    except httpx.HTTPError:
        raise ProviderUnavailableError("QQQ holdings request failed") from None
    if response.status_code in {401, 403}:
        raise ProviderAuthenticationError("QQQ holdings access is unavailable")
    if response.status_code == 429:
        raise ProviderRateLimitError("QQQ holdings request was rate limited")
    if response.status_code != 200:
        raise ProviderUnavailableError("QQQ holdings request failed")
    if len(response.content) > 1_000_000:
        raise ProviderUnavailableError("QQQ holdings response exceeds the size limit")
    try:
        payload = response.json()
    except ValueError:
        raise ProviderUnavailableError("QQQ holdings response is not valid JSON") from None
    return _parse_holdings(payload, instrument_ids or {})


def _parse_holdings(
    payload: object, instrument_ids: Mapping[str, str]
) -> tuple[NasdaqConstituent, ...]:
    if not isinstance(payload, dict) or payload.get("cusip") != "QQQ":
        raise ProviderUnavailableError("QQQ holdings identity is invalid")
    as_of = _parse_date(payload.get("effectiveBusinessDate"))
    published_date = _parse_date(payload.get("effectiveDate"))
    if as_of > published_date:
        raise ProviderUnavailableError("QQQ holdings dates are inconsistent")
    rows = payload.get("holdings")
    total = payload.get("totalNumberOfHoldings")
    if (
        not isinstance(rows, list)
        or not 1 <= len(rows) <= 500
        or type(total) is not int
        or total != len(rows)
    ):
        raise ProviderUnavailableError("QQQ holdings coverage is malformed")

    members: list[NasdaqConstituent] = []
    seen_symbols: set[str] = set()
    seen_ids: set[str] = set()
    seen_cusips: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ProviderUnavailableError("QQQ holdings row is malformed")
        security_type = row.get("securityTypeCode")
        if not isinstance(security_type, str):
            raise ProviderUnavailableError("QQQ holding security type is malformed")
        if security_type in _EXCLUDED_TYPES:
            continue
        if security_type not in _EQUITY_TYPES:
            raise ProviderUnavailableError("QQQ holding security type is unsupported")
        symbol = row.get("ticker")
        name = row.get("issuerName")
        cusip = row.get("cusip")
        if (
            not isinstance(symbol, str)
            or not _SYMBOL.fullmatch(symbol)
            or not isinstance(name, str)
            or not 1 <= len(name) <= 240
            or not name.strip()
            or any(ord(char) < 32 for char in name)
            or not isinstance(cusip, str)
            or not _CUSIP.fullmatch(cusip)
            or row.get("currency") != "USD"
        ):
            raise ProviderUnavailableError("QQQ equity holding metadata is malformed")
        instrument_id = instrument_ids.get(symbol, f"ins_cusip_{cusip.lower()}")
        if not isinstance(instrument_id, str) or not _INSTRUMENT_ID.fullmatch(instrument_id):
            raise ProviderUnavailableError("QQQ equity holding canonical identity is invalid")
        if symbol in seen_symbols or instrument_id in seen_ids or cusip in seen_cusips:
            raise ProviderUnavailableError("QQQ equity holdings contain duplicate identities")
        seen_symbols.add(symbol)
        seen_ids.add(instrument_id)
        seen_cusips.add(cusip)
        members.append(
            NasdaqConstituent(
                instrument_id=instrument_id,
                symbol=symbol,
                name=unescape(name).strip(),
                as_of=as_of,
                source=QQQ_HOLDINGS_SOURCE,
            )
        )
    if not members:
        raise ProviderUnavailableError("QQQ holdings contain no supported equity securities")
    return tuple(sorted(members, key=lambda member: member.symbol))


def _parse_date(value: object) -> date:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ProviderUnavailableError("QQQ holdings date is malformed")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ProviderUnavailableError("QQQ holdings date is malformed") from None
