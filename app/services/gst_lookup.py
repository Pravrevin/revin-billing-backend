"""
gst_lookup.py
-------------
Validate an Indian GSTIN and (optionally) fetch the taxpayer's details from a
GST verification provider so the "Add Supplier" form can auto-fill itself.

Design goals:
  * Always usable offline — even with no provider key, a structurally valid
    GSTIN yields the state (from the state code) and PAN (chars 3-12).
  * Pluggable provider — AppyFlow is the default; the key is read from settings
    (``GST_API_KEY`` / ``GST_API_PROVIDER`` in .env).

The endpoint maps the result straight onto PartyMaster fields, so the keys here
mirror the Add Supplier form (party_name, address, state, city, pincode,
pan_card, gstin).
"""
from __future__ import annotations

import re
from typing import Optional

import requests

from app.config import settings

# 15 chars: 2-digit state code, 10-char PAN, entity digit, 'Z', checksum char.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")

_CHECKSUM_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# GST state codes → state name (matches INDIA_STATES on the frontend).
STATE_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}


class GstLookupError(Exception):
    """Raised for an invalid GSTIN or a provider failure the caller should surface."""


def _checksum_ok(gstin: str) -> bool:
    """Verify the 15th character using the standard GSTIN modulo-36 checksum."""
    factor = 1
    total = 0
    for ch in gstin[:14]:
        code = _CHECKSUM_CHARS.index(ch)
        digit = code * factor
        total += digit // 36 + digit % 36
        factor = 2 if factor == 1 else 1
    expected = _CHECKSUM_CHARS[(36 - (total % 36)) % 36]
    return expected == gstin[14]


def normalize_gstin(raw: str) -> str:
    """Upper-case, strip spaces, and validate format + checksum. Raises on failure."""
    gstin = (raw or "").strip().upper().replace(" ", "")
    if len(gstin) != 15:
        raise GstLookupError("GSTIN must be exactly 15 characters.")
    if not GSTIN_RE.match(gstin):
        raise GstLookupError("Invalid GSTIN format.")
    if not _checksum_ok(gstin):
        raise GstLookupError("Invalid GSTIN — checksum digit does not match.")
    return gstin


def _base_result(gstin: str) -> dict:
    """Details derivable from the GSTIN alone, no network call."""
    return {
        "gstin": gstin,
        "pan_card": gstin[2:12],
        "state": STATE_CODES.get(gstin[0:2]),
        "party_name": None,
        "address": None,
        "city": None,
        "pincode": None,
        "status": None,
        "source": "derived",
    }


def _lookup_appyflow(gstin: str, base: dict) -> dict:
    """Fetch full taxpayer details from AppyFlow's verifyGST API."""
    resp = requests.get(
        "https://appyflow.in/api/verifyGST",
        params={"gstNo": gstin, "key_secret": settings.gst_api_key},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        msg = data.get("message") or "GST number could not be verified."
        raise GstLookupError(str(msg))

    info = data.get("taxpayerInfo") or {}
    if not info:
        # Valid format but provider returned nothing usable — keep derived data.
        return base

    addr = ((info.get("pradr") or {}).get("addr")) or {}
    full_addr = (info.get("pradr") or {}).get("adr")

    result = dict(base)
    result.update(
        {
            "party_name": info.get("tradeNam") or info.get("lgnm") or base["party_name"],
            "address": full_addr or base["address"],
            "state": addr.get("stcd") or base["state"],
            "city": addr.get("dst") or addr.get("city") or addr.get("loc") or base["city"],
            "pincode": (str(addr["pncd"]) if addr.get("pncd") else base["pincode"]),
            "status": info.get("sts"),
            "source": "appyflow",
        }
    )
    return result


_PROVIDERS = {
    "appyflow": _lookup_appyflow,
}


def lookup_gstin(raw_gstin: str) -> dict:
    """
    Validate the GSTIN and return supplier details mapped to PartyMaster fields.

    Falls back to derived (state + PAN) data when no provider key is configured
    or the provider call fails, so the form can still pre-fill what it can.
    """
    gstin = normalize_gstin(raw_gstin)
    base = _base_result(gstin)

    key = (settings.gst_api_key or "").strip()
    if not key:
        return base

    provider = _PROVIDERS.get((settings.gst_api_provider or "").strip().lower())
    if provider is None:
        return base

    try:
        return provider(gstin, base)
    except GstLookupError:
        raise
    except requests.RequestException:
        # Network/provider outage — degrade gracefully to derived data.
        return base
