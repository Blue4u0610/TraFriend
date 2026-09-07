# ruff: noqa: E501
"""expand the verified leveraged universe across September popular stocks

Revision ID: 20260907_0005
Revises: 20260907_0004
Create Date: 2026-09-07

This point-in-time snapshot covers every active, directly mapped single-stock
daily leveraged product found for supported September Top-100 underlyings in
Alpaca's asset catalog and then checked against its issuer's official catalog.
It excludes option-income products, products tied to a different index/basket,
and products with non-daily reset objectives.
"""

from datetime import date, datetime, timezone
from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

revision: str = "20260907_0005"
down_revision: Optional[str] = "20260907_0004"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

VERIFIED_AT = datetime(2026, 9, 7, 18, tzinfo=timezone.utc)
EFFECTIVE_FROM = date(2026, 9, 4)

ISSUER_SOURCES = {
    "Corgi": "https://corgiinvest.com/2xleveraged",
    "Defiance": "https://www.defianceetfs.com/prospectuses/",
    "Direxion": "https://www.direxion.com/single-stock-etfs",
    "GraniteShares": "https://graniteshares.com/etfs/leveraged/",
    "Leverage Shares": (
        "https://leverageshares.com/us/all-etfs?category=Daily+Leveraged"
    ),
    "ProShares": (
        "https://www.proshares.com/our-etfs/find-leveraged-and-inverse-etfs"
    ),
    "T-REX": "https://www.rexshares.com/home-2/all-funds/?llm_view=1&tm=tt",
    "Tradr ETFs": "https://www.tradretfs.com/",
}

# symbol|display name|exchange MIC
UNDERLYINGS = (
    "AAPL|Apple Inc. Common Stock|XNAS",
    "ADBE|Adobe Inc. Common Stock|XNAS",
    "ADI|Analog Devices, Inc. Common Stock|XNAS",
    "ALAB|Astera Labs, Inc. Common Stock|XNAS",
    "AMAT|Applied Materials, Inc. Common Stock|XNAS",
    "AMD|Advanced Micro Devices, Inc. Common Stock|XNAS",
    "AMZN|Amazon.com, Inc. Common Stock|XNAS",
    "APH|Amphenol Corporation|XNYS",
    "APP|Applovin Corporation Class A Common Stock|XNAS",
    "ASML|ASML Holding N.V. New York Registry Shares|XNAS",
    "AVGO|Broadcom Inc. Common Stock|XNAS",
    "BA|Boeing Company|XNYS",
    "BE|Bloom Energy Corporation|XNYS",
    "BMNR|BitMine Immersion Technologies, Inc.|XNYS",
    "BRK.B|BERKSHIRE HATHAWAY Class B|XNYS",
    "CAT|Caterpillar Inc.|XNYS",
    "CBRS|Cerebras Systems Inc. Class A Common Stock|XNAS",
    "CIEN|Ciena Corporation|XNYS",
    "COHR|Coherent Corp.|XNYS",
    "COIN|Coinbase Global, Inc. Class A Common Stock|XNAS",
    "COST|Costco Wholesale Corporation Common Stock|XNAS",
    "CRCL|Circle Internet Group, Inc.|XNYS",
    "CRDO|Credo Technology Group Holding Ltd Ordinary Shares|XNAS",
    "CRM|Salesforce, Inc.|XNYS",
    "CRWD|CrowdStrike Holdings, Inc. Class A Common Stock|XNAS",
    "CRWV|CoreWeave, Inc. Class A Common Stock|XNAS",
    "CSCO|Cisco Systems, Inc. Common Stock (DE)|XNAS",
    "DELL|Dell Technologies Inc.|XNYS",
    "GEV|GE Vernova Inc.|XNYS",
    "GLW|Corning Incorporated|XNYS",
    "GOOG|Alphabet Inc. Class C Capital Stock|XNAS",
    "GOOGL|Alphabet Inc. Class A Common Stock|XNAS",
    "HOOD|Robinhood Markets, Inc. Class A Common Stock|XNAS",
    "HPE|Hewlett Packard Enterprise Company|XNYS",
    "INTC|Intel Corporation Common Stock|XNAS",
    "IREN|IREN Limited Ordinary Shares|XNAS",
    "KLAC|KLA Corporation Common Stock|XNAS",
    "LITE|Lumentum Holdings Inc. Common Stock|XNAS",
    "LLY|Eli Lilly & Co.|XNYS",
    "LRCX|Lam Research Corporation Common Stock|XNAS",
    "LULU|lululemon athletica inc. Common Stock|XNAS",
    "META|Meta Platforms, Inc. Class A Common Stock|XNAS",
    "MRNA|Moderna, Inc. Common Stock|XNAS",
    "MRVL|Marvell Technology, Inc. Common Stock|XNAS",
    "MSFT|Microsoft Corporation Common Stock|XNAS",
    "MSTR|Strategy Inc Common Stock Class A|XNAS",
    "NBIS|Nebius Group N.V. Class A Ordinary Shares|XNAS",
    "NFLX|Netflix, Inc. Common Stock|XNAS",
    "NOW|SERVICENOW, INC.|XNYS",
    "NU|Nu Holdings Ltd.|XNYS",
    "ORCL|Oracle Corp|XNYS",
    "PANW|Palo Alto Networks, Inc. Common Stock|XNAS",
    "PATH|UiPath, Inc.|XNYS",
    "PLTR|Palantir Technologies Inc. Class A Common Stock|XNAS",
    "QCOM|QUALCOMM Incorporated Common Stock|XNAS",
    "RKLB|Rocket Lab Corporation Common Stock|XNAS",
    "SHOP|Shopify Inc. Class A subordinate voting shares|XNAS",
    "SKHY|SK hynix Inc. American Depositary Shares|XNAS",
    "SMCI|Super Micro Computer, Inc. Common Stock|XNAS",
    "SNOW|Snowflake Inc.|XNYS",
    "SPCX|Space Exploration Technologies Corp. Class A Common Stock|XNAS",
    "STX|Seagate Technology Holdings PLC Ordinary Shares (Ireland)|XNAS",
    "TSM|Taiwan Semiconductor Manufacturing Company Ltd.|XNYS",
    "TXN|Texas Instruments Incorporated Common Stock|XNAS",
    "UBER|Uber Technologies, Inc.|XNYS",
    "UNH|UNITEDHEALTH GROUP INCORPORATED (Delaware)|XNYS",
    "VRT|Vertiv Holdings Co Class A Common Stock|XNYS",
    "WDC|Western Digital Corporation Common Stock|XNAS",
    "XOM|ExxonMobil Holdings Corporation|XNYS",
)

# underlying, then space-separated symbol:leverage:issuer-key:exchange-MIC entries.
# Issuer keys use underscores only to keep this immutable migration snapshot compact.
PRODUCT_GROUPS = (
    ("AAPL", "AAPB:2:GraniteShares:XNAS AAPD:-1:Direxion:XNAS AAPE:2:Leverage_Shares:BATS AAPU:2:Direxion:XNAS AAPX:2:T-REX:BATS IOSX:2:Corgi:BATS"),
    ("ADBE", "ADBG:2:Leverage_Shares:XNAS ADBU:2:Direxion:ARCX"),
    ("ADI", "ADIU:2:Leverage_Shares:BATS"),
    ("ALAB", "ALA:2:Corgi:BATS LABX:2:Tradr_ETFs:BATS"),
    ("AMAT", "AMA:2:Defiance:XNAS AMAU:2:Leverage_Shares:BATS APMI:2:Corgi:BATS"),
    ("AMD", "AMDC:2:Corgi:BATS AMDD:-1:Direxion:XNAS AMDG:2:Leverage_Shares:XNAS AMDL:2:GraniteShares:XNAS AMUU:2:Direxion:XNAS DAMD:-2:Defiance:ARCX"),
    ("AMZN", "AMAA:2:Corgi:BATS AMZD:-1:Direxion:XNAS AMZG:2:Leverage_Shares:BATS AMZO:-2:Tradr_ETFs:BATS AMZU:2:Direxion:XNAS AMZZ:2:GraniteShares:XNAS"),
    ("APH", "APHG:2:Leverage_Shares:BATS APHU:2:T-REX:BATS"),
    ("APP", "APPC:2:Corgi:BATS APPX:2:Tradr_ETFs:XNAS"),
    ("ASML", "ASMG:2:Leverage_Shares:XNAS ASMU:2:Direxion:XNAS ASMZ:2:Corgi:BATS"),
    ("AVGO", "AVGC:2:Corgi:BATS AVGG:2:Leverage_Shares:XNAS AVGU:2:GraniteShares:XNAS AVGX:2:Defiance:XNAS AVL:2:Direxion:XNAS AVS:-1:Direxion:XNAS"),
    ("BA", "BOEG:2:Leverage_Shares:XNAS BOEU:2:Direxion:XNAS"),
    ("BE", "BEC:2:Corgi:BATS BEG:2:Leverage_Shares:XNAS BEX:2:Tradr_ETFs:BATS BEZ:-2:Tradr_ETFs:BATS"),
    ("BMNR", "BMNG:2:Leverage_Shares:XNAS BMNU:2:T-REX:BATS BMNZ:-2:Defiance:ARCX BNMC:2:Corgi:BATS"),
    ("BRK.B", "BRKL:2:Corgi:BATS BRKU:2:Direxion:XNAS"),
    ("CAT", "CATG:2:Leverage_Shares:BATS"),
    ("CBRS", "CBRG:2:Leverage_Shares:BATS CBRX:2:Tradr_ETFs:BATS CBRZ:-2:Tradr_ETFs:BATS"),
    ("CIEN", "CIEG:2:Leverage_Shares:BATS CIEX:2:Tradr_ETFs:BATS"),
    ("COHR", "COHC:2:Corgi:BATS COHH:2:Leverage_Shares:BATS COHQ:-2:Tradr_ETFs:BATS COHX:2:Tradr_ETFs:BATS"),
    ("COIN", "COIA:2:ProShares:ARCX COIG:2:Leverage_Shares:XNAS COIX:2:Corgi:BATS CONI:-2:GraniteShares:XNAS CONL:2:GraniteShares:XNAS CONX:2:Direxion:XNAS"),
    ("COST", "COTG:2:Leverage_Shares:XNAS"),
    ("CRCL", "CCUP:2:T-REX:BATS CIR:2:Corgi:BATS CRCA:2:ProShares:ARCX CRCD:-2:T-REX:BATS CRCG:2:Leverage_Shares:XNAS"),
    ("CRDO", "CRD:2:Corgi:BATS CRDU:2:Tradr_ETFs:BATS"),
    ("CRM", "CRMG:2:Leverage_Shares:XNAS"),
    ("CRWD", "CRWC:2:Corgi:BATS CRWL:2:GraniteShares:XNAS"),
    ("CRWV", "CORD:-2:T-REX:BATS CRWG:2:Leverage_Shares:XNAS CRWU:2:T-REX:BATS CRWX:2:Corgi:BATS CWVX:2:Tradr_ETFs:BATS"),
    ("CSCO", "CSCL:2:Direxion:XNAS CSCS:-1:Direxion:XNAS"),
    ("DELL", "DLLL:2:GraniteShares:XNAS"),
    ("GEV", "GEVC:2:Corgi:BATS GEVG:2:Leverage_Shares:XNAS GEVX:2:Tradr_ETFs:BATS"),
    ("GLW", "GLWG:2:Leverage_Shares:XNAS"),
    ("GOOG", "GOOX:2:T-REX:BATS"),
    ("GOOGL", "GGLL:2:Direxion:XNAS GGLS:-1:Direxion:XNAS GOGL:2:Corgi:BATS GOOL:2:Leverage_Shares:BATS GOU:2:GraniteShares:XNAS"),
    ("HOOD", "HODU:2:Direxion:XNAS HOOC:2:Corgi:BATS HOOG:2:Leverage_Shares:XNAS HOOX:2:Defiance:XNAS ROBN:2:T-REX:BATS"),
    ("HPE", "HPEL:2:Leverage_Shares:BATS"),
    ("INTC", "INT:2:Corgi:BATS INTW:2:GraniteShares:XNAS LINT:2:Direxion:XNAS"),
    ("IREN", "IRE:2:Defiance:ARCX IREC:2:Corgi:BATS IREG:2:Leverage_Shares:XNAS IREX:2:Tradr_ETFs:BATS IREZ:-2:Tradr_ETFs:BATS"),
    ("KLAC", "KLAG:2:Leverage_Shares:XNAS"),
    ("LITE", "LITC:2:Corgi:BATS LITG:2:Leverage_Shares:BATS LITU:2:T-REX:BATS LITX:2:Tradr_ETFs:BATS LITZ:-2:Tradr_ETFs:BATS"),
    ("LLY", "ELIL:2:Direxion:XNAS LLYX:2:Defiance:ARCX"),
    ("LRCX", "LRCC:2:Corgi:BATS LRCU:2:Tradr_ETFs:BATS"),
    ("LULU", "LULG:2:Leverage_Shares:XNAS"),
    ("META", "FBL:2:GraniteShares:XNAS FBX:2:Corgi:BATS METD:-1:Direxion:XNAS METG:2:Leverage_Shares:BATS METQ:-2:Tradr_ETFs:BATS METU:2:Direxion:XNAS"),
    ("MRNA", "MRNX:2:Defiance:ARCX"),
    ("MRVL", "MRVU:2:Direxion:XNAS MRVX:2:Corgi:BATS MVLL:2:GraniteShares:XNAS"),
    ("MSFT", "MSFC:2:Corgi:BATS MSFD:-1:Direxion:XNAS MSFL:2:GraniteShares:XNAS MSFU:2:Direxion:XNAS MSFX:2:T-REX:BATS"),
    ("MSTR", "MSTC:2:Corgi:BATS MSTP:2:GraniteShares:XNAS MSTU:2:T-REX:BATS MSTX:2:Defiance:XNAS MSTZ:-2:T-REX:BATS SMST:-2:Defiance:XNAS"),
    ("NBIS", "NBIC:2:Corgi:BATS NBIG:2:Leverage_Shares:XNAS NBIL:2:GraniteShares:XNAS NBIZ:-2:Tradr_ETFs:BATS NEBX:2:Tradr_ETFs:BATS"),
    ("NFLX", "NFLU:2:T-REX:BATS NFX:2:Corgi:BATS NFXL:2:Direxion:XNAS NFXS:-1:Direxion:XNAS"),
    ("NOW", "NOWL:2:GraniteShares:XNAS NOWX:2:Corgi:BATS"),
    ("NU", "NUG:2:Leverage_Shares:XNAS"),
    ("ORCL", "ORAC:2:Corgi:BATS ORCS:-1:Direxion:XNAS ORCU:2:Direxion:XNAS ORCX:2:Defiance:XNAS ORCZ:-2:Tradr_ETFs:BATS"),
    ("PANW", "PALD:-1:Direxion:XNAS PALU:2:Direxion:XNAS PANG:2:Leverage_Shares:XNAS"),
    ("PATH", "PATX:2:Tradr_ETFs:BATS"),
    ("PLTR", "PLTA:2:ProShares:ARCX PLTD:-1:Direxion:XNAS PLTG:2:Leverage_Shares:XNAS PLTL:2:Corgi:BATS PLTU:2:Direxion:XNAS PLTZ:-2:Defiance:XNAS PTIR:2:GraniteShares:XNAS"),
    ("QCOM", "QCMD:-1:Direxion:XNAS QCML:2:GraniteShares:XNAS QCMU:2:Direxion:XNAS"),
    ("RKLB", "RKLX:2:Defiance:XNAS RKLZ:-2:Defiance:XNAS RKX:2:Corgi:BATS"),
    ("SHOP", "SHPU:2:Direxion:XNAS"),
    ("SKHY", "HYNX:2:T-REX:ARCX SK:2:Corgi:BATS SKDD:-2:GraniteShares:XNAS SKHA:2:Tradr_ETFs:BATS SKHL:2:Direxion:ARCX SKHN:-2:Tradr_ETFs:BATS SKHQ:-2:Leverage_Shares:BATS SKHU:2:ProShares:ARCX SKHX:2:Leverage_Shares:BATS SKHZ:-1:Leverage_Shares:BATS SKUU:2:GraniteShares:XNAS"),
    ("SMCI", "SMCC:2:Corgi:BATS SMCL:2:GraniteShares:XNAS SMCX:2:Defiance:XNAS SMCZ:-2:Defiance:XNAS"),
    ("SNOW", "SNOU:2:T-REX:BATS"),
    ("SPCX", "DSPC:-1:Leverage_Shares:BATS LOFD:-2:Direxion:ARCX LOFF:2:Direxion:ARCX SNK:-2:GraniteShares:BATS SPAL:2:GraniteShares:BATS SPAX:2:T-REX:ARCX SPCF:2:ProShares:ARCX SPCG:-2:Tradr_ETFs:BATS SPCH:2:Leverage_Shares:BATS SPCM:2:Tradr_ETFs:BATS SPCQ:-2:Defiance:BATS SPCU:2:Defiance:BATS SSPC:-2:Leverage_Shares:BATS"),
    ("STX", "STXL:2:Defiance:BATS STXU:2:Leverage_Shares:BATS STXX:2:Tradr_ETFs:BATS"),
    ("TSM", "STSM:-2:Defiance:ARCX TSMG:2:Leverage_Shares:XNAS TSMU:2:GraniteShares:XNAS TSMX:2:Direxion:XNAS TSMZ:-1:Direxion:XNAS TWSC:2:Corgi:BATS"),
    ("TXN", "TXNU:2:Direxion:ARCX"),
    ("UBER", "UBRL:2:GraniteShares:XNAS"),
    ("UNH", "UN:2:Corgi:BATS UNHG:2:Leverage_Shares:XNAS UNHU:2:Direxion:ARCX"),
    ("VRT", "VRC:2:Corgi:BATS VRTL:2:GraniteShares:XNAS"),
    ("WDC", "WDCC:2:Corgi:BATS WDCX:2:Tradr_ETFs:BATS"),
    ("XOM", "XOMX:2:Direxion:XNAS"),
)


def upgrade() -> None:
    underlyings = sa.table(
        "underlyings",
        sa.column("id", sa.String),
        sa.column("symbol", sa.String),
        sa.column("display_name", sa.String),
        sa.column("instrument_type", sa.String),
        sa.column("exchange_mic", sa.String),
        sa.column("currency", sa.String),
        sa.column("active", sa.Boolean),
        sa.column("profit_ratio_available", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    products = sa.table(
        "leveraged_products",
        sa.column("id", sa.String),
        sa.column("relationship_id", sa.String),
        sa.column("symbol", sa.String),
        sa.column("display_name", sa.String),
        sa.column("exchange_mic", sa.String),
        sa.column("underlying_id", sa.String),
        sa.column("signed_leverage", sa.Numeric),
        sa.column("issuer", sa.String),
        sa.column("direction", sa.String),
        sa.column("active", sa.Boolean),
        sa.column("objective_period", sa.String),
        sa.column("authoritative_source", sa.String),
        sa.column("verified_at", sa.DateTime(timezone=True)),
        sa.column("effective_from", sa.Date),
        sa.column("effective_to", sa.Date),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    underlying_rows = [_underlying_row(item) for item in UNDERLYINGS]
    connection.execute(
        insert(underlyings)
        .values(underlying_rows)
        .on_conflict_do_nothing(index_elements=["symbol"])
    )
    product_rows = [
        _product_row(underlying_symbol, spec)
        for underlying_symbol, group in PRODUCT_GROUPS
        for spec in group.split()
    ]
    connection.execute(
        insert(products)
        .values(product_rows)
        .on_conflict_do_nothing(index_elements=["symbol"])
    )


def _underlying_row(item: str) -> dict[str, object]:
    symbol, name, exchange_mic = item.split("|")
    return {
        "id": _underlying_id(symbol, exchange_mic),
        "symbol": symbol,
        "display_name": name,
        "instrument_type": "stock",
        "exchange_mic": exchange_mic,
        "currency": "USD",
        "active": True,
        "profit_ratio_available": False,
        "created_at": VERIFIED_AT,
        "updated_at": VERIFIED_AT,
    }


def _product_row(underlying_symbol: str, spec: str) -> dict[str, object]:
    symbol, leverage, issuer_key, exchange_mic = spec.split(":")
    issuer = issuer_key.replace("_", " ")
    leverage_id = leverage.replace("-", "n").replace(".", "p")
    direction = "LONG" if not leverage.startswith("-") else "INVERSE"
    return {
        "id": f"ins_{_slug(symbol)}_{exchange_mic.lower()}",
        "relationship_id": (
            f"rel_{_slug(underlying_symbol)}_{_slug(symbol)}_{leverage_id}x"
        ),
        "symbol": symbol,
        "display_name": (
            f"{issuer} {leverage}x {underlying_symbol} Daily ETF"
        ),
        "exchange_mic": exchange_mic,
        "underlying_id": _underlying_id_for_symbol(underlying_symbol),
        "signed_leverage": leverage,
        "issuer": issuer,
        "direction": direction,
        "active": True,
        "objective_period": "daily",
        "authoritative_source": ISSUER_SOURCES[issuer],
        "verified_at": VERIFIED_AT,
        "effective_from": EFFECTIVE_FROM,
        "effective_to": None,
        "created_at": VERIFIED_AT,
        "updated_at": VERIFIED_AT,
    }


def _underlying_id_for_symbol(symbol: str) -> str:
    for item in UNDERLYINGS:
        candidate, _name, exchange_mic = item.split("|")
        if candidate == symbol:
            return _underlying_id(symbol, exchange_mic)
    raise ValueError(f"missing underlying snapshot row for {symbol}")


def _underlying_id(symbol: str, exchange_mic: str) -> str:
    return f"ins_{_slug(symbol)}_{exchange_mic.lower()}"


def _slug(symbol: str) -> str:
    return symbol.lower().replace(".", "_")


def downgrade() -> None:
    product_symbols = sorted(
        spec.split(":", maxsplit=1)[0]
        for _underlying_symbol, group in PRODUCT_GROUPS
        for spec in group.split()
    )
    underlying_symbols = sorted(item.split("|", maxsplit=1)[0] for item in UNDERLYINGS)
    products = sa.table("leveraged_products", sa.column("symbol", sa.String))
    underlyings = sa.table("underlyings", sa.column("symbol", sa.String))
    op.execute(products.delete().where(products.c.symbol.in_(product_symbols)))
    op.execute(underlyings.delete().where(underlyings.c.symbol.in_(underlying_symbols)))
