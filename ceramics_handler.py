"""
ceramics_handler.py
===================
Fresh Ceramics (Meghna Ceramics Industries Ltd - MCIL) API Integration Module.
Provides API endpoint configurations, unique ID extraction (TransactionId for SO, pay_id for CO),
payload parsing, and Telegram notification alert formatters.
"""

import json

# API Configuration Constants
CERAMICS_BASE_URL = "https://mcil.mgi.org"
DEFAULT_CERAMICS_URL_TEMPLATE = (
    "https://mcil.mgi.org/api/get-so-payment-collection"
    "?start_date={date}&end_date={date}&server_allocation=0&so=1&co=1"
    "&so_zone=0&co_zone=0&so_product_line=0&co_product_line=0"
)
DEFAULT_CERAMICS_VIEW_URL_TEMPLATE = (
    "https://mcil.mgi.org/api/view-so-payment-collection"
    "?start_date={date}&end_date={date}&server_allocation=0&so=1&co=1"
    "&so_zone=0&co_zone=0&so_product_line=0&co_product_line=0&view_so=0"
)
DEFAULT_CERAMICS_SO_UPDATE_URL = "https://mcil.mgi.org/api/updateData/1?key=ps_data_so"
DEFAULT_CERAMICS_CO_UPDATE_URL = "https://mcil.mgi.org/api/store-so-collection"

DEFAULT_CERAMICS_BEARER_TOKEN = "2170|6KxNVYnJD5RoVJTac3CsXmoqjNPCB5Y4g2w8HtNzbc8a3149"
DEFAULT_CERAMICS_CO_UPDATE_TOKEN = "1766|9TPsSMukNSsgduSMaBDW0QaWIBro3UmNqXdNbpIRc37b020b"


def get_ceramics_api_config(bearer_token=None, url_template=None):
    """
    Returns the standard API blueprint dictionary for Fresh Ceramics.
    """
    token = bearer_token or DEFAULT_CERAMICS_BEARER_TOKEN
    template = url_template or DEFAULT_CERAMICS_URL_TEMPLATE
    return {
        "name": "FreshCeramics_Pending_Orders",
        "url_template": template,
        "filter_pending": False,
        "headers": {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        }
    }


def get_ceramics_so_unique_id(item):
    """
    Extracts the unique identifier for a Fresh Ceramics Sales Order (SO).
    Primary field requirement: TransactionId
    Fallback fields: do_number, Line_Id
    """
    if not isinstance(item, dict):
        return None

    for key in ["TransactionId", "transactionid", "Transaction_Id", "do_number", "Line_Id"]:
        val = item.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return None


def get_ceramics_co_unique_id(item):
    """
    Extracts the unique identifier for a Fresh Ceramics Collection (CO).
    Primary field requirement: pay_id
    Fallback fields: TransactionId, payment_number
    """
    if not isinstance(item, dict):
        return None

    for key in ["pay_id", "payid", "Pay_Id", "TransactionId", "payment_number"]:
        val = item.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return None


def is_ceramics_so_pending(item):
    """
    Determines if a Fresh Ceramics SO record is pending SAP processing.
    An SO is pending if SO_Number is missing, empty, or 'check sap' or None.
    """
    if not isinstance(item, dict):
        return False

    process = str(item.get("process", "")).upper()
    if process and process != "SO":
        return False

    so_num = item.get("SO_Number") or item.get("so_number")
    if so_num is None or str(so_num).strip() == "" or str(so_num).strip().lower() in ["check sap", "none", "null", "-"]:
        return True
    return False


def is_ceramics_co_pending(item):
    """
    Determines if a Fresh Ceramics CO record is pending SAP processing.
    A CO is pending if collection_no is missing, empty, or None.
    """
    if not isinstance(item, dict):
        return False

    process = str(item.get("process", "")).upper()
    if process and process != "CO":
        return False

    col_no = item.get("collection_no") or item.get("Collection_No")
    if col_no is None or str(col_no).strip() == "" or str(col_no).strip().lower() in ["none", "null", "-"]:
        return True
    return False


def parse_ceramics_payload(raw_data):
    """
    Parses a raw API JSON response from Fresh Ceramics API into structured SO and CO lists.
    """
    result = {"SO": [], "CO": []}
    if not raw_data:
        return result

    data_list = []
    if isinstance(raw_data, list):
        data_list = raw_data
    elif isinstance(raw_data, dict):
        if "data" in raw_data and isinstance(raw_data["data"], list):
            data_list = raw_data["data"]
        elif "result" in raw_data and isinstance(raw_data["result"], list):
            data_list = raw_data["result"]
        else:
            data_list = [raw_data]

    for item in data_list:
        if not isinstance(item, dict):
            continue
        process_type = str(item.get("process", "")).upper()
        if process_type == "SO":
            result["SO"].append(item)
        elif process_type == "CO":
            result["CO"].append(item)

    return result


def format_ceramics_so_alert(tx_id, age_minutes, age_seconds=0, server="0"):
    """
    Formats the aging alert message for a Fresh Ceramics SO item.
    """
    return f"Fresh Ceramics SO TransactionId is {tx_id} in server {server} for {age_minutes} min {age_seconds} sec"


def format_ceramics_co_alert(pay_id, age_minutes, age_seconds=0, server="0"):
    """
    Formats the aging alert message for a Fresh Ceramics CO item.
    """
    return f"Fresh Ceramics CO pay_id is {pay_id} in server {server} for {age_minutes} min {age_seconds} sec"
