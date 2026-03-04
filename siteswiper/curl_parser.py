"""Parse cURL commands into structured request dictionaries.

Handles both Chrome and Firefox 'Copy as cURL' formats.
Includes Ontario Parks-specific helpers for the /api/cart/commit endpoint.
"""

import json
import shlex
import uuid
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


def parse_curl(curl_string: str) -> dict:
    """Parse a cURL command string into a structured request dictionary.

    Args:
        curl_string: Raw cURL command (may be multi-line with backslash continuations).

    Returns:
        Dictionary with keys: method, url, headers, cookies, body, compressed, verify_ssl

    Raises:
        ValueError: If the input is not a valid cURL command.
    """
    # Normalize: join backslash-continued lines
    normalized = curl_string.strip()
    normalized = normalized.replace("\\\n", " ").replace("\\\r\n", " ")

    # Strip leading $ (common when copying from docs)
    if normalized.startswith("$ "):
        normalized = normalized[2:]

    # Tokenize
    try:
        tokens = shlex.split(normalized)
    except ValueError as e:
        raise ValueError(f"Failed to parse cURL command: {e}") from e

    if not tokens or tokens[0] != "curl":
        raise ValueError("Input does not appear to be a cURL command (must start with 'curl')")

    # Parse tokens
    method = None
    url = None
    headers = {}
    body = None
    compressed = False
    verify_ssl = True

    i = 1  # Skip 'curl'
    while i < len(tokens):
        token = tokens[i]

        if token in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()

        elif token in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                header_str = tokens[i]
                # Split on first ': ' or ':'
                if ": " in header_str:
                    key, value = header_str.split(": ", 1)
                elif ":" in header_str:
                    key, value = header_str.split(":", 1)
                    value = value.lstrip()
                else:
                    key, value = header_str, ""
                headers[key] = value

        elif token in ("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode"):
            i += 1
            if i < len(tokens):
                body = tokens[i]

        elif token in ("-b", "--cookie"):
            i += 1
            if i < len(tokens):
                # -b passes cookies directly; merge into Cookie header
                existing = headers.get("Cookie", "")
                if existing:
                    headers["Cookie"] = existing + "; " + tokens[i]
                else:
                    headers["Cookie"] = tokens[i]

        elif token == "--compressed":
            compressed = True

        elif token in ("-k", "--insecure"):
            verify_ssl = False

        elif token in ("-L", "--location"):
            pass  # Follow redirects — httpx does this by default

        elif token in ("-s", "--silent", "-S", "--show-error", "-v", "--verbose"):
            pass  # Display flags, not relevant for replay

        elif token in ("-o", "--output", "-A", "--user-agent", "-e", "--referer",
                       "--connect-timeout", "-m", "--max-time", "--retry",
                       "-u", "--user", "--proxy"):
            # These take a value argument; skip it
            i += 1

        elif token.startswith("http://") or token.startswith("https://"):
            url = token

        elif token.startswith("'http://") or token.startswith("'https://"):
            # Shouldn't happen after shlex, but handle just in case
            url = token.strip("'")

        i += 1

    if not url:
        raise ValueError("No URL found in cURL command")

    # Infer method if not explicitly set
    if method is None:
        method = "POST" if body else "GET"

    # Extract cookies from Cookie header
    cookies = {}
    cookie_header = headers.get("Cookie", "")
    if cookie_header:
        for pair in cookie_header.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                cookies[key.strip()] = value.strip()

    # Parse URL for display info
    parsed_url = urlparse(url)

    return {
        "method": method,
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "body": body,
        "compressed": compressed,
        "verify_ssl": verify_ssl,
        "host": parsed_url.hostname,
        "path": parsed_url.path,
    }


def format_body_params(body: str | None) -> dict | None:
    """Parse a URL-encoded or JSON body into a dict for display/editing.

    Returns None if the body is not parseable as form params or JSON.
    """
    if not body:
        return None

    import json

    # Try JSON first
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return {"type": "json", "params": parsed}
    except (json.JSONDecodeError, TypeError):
        pass

    # Try URL-encoded form data
    if "=" in body and not body.startswith("{"):
        from urllib.parse import parse_qs
        params = parse_qs(body, keep_blank_values=True)
        # parse_qs returns lists; flatten single-value params
        flat = {}
        for key, values in params.items():
            flat[key] = values[0] if len(values) == 1 else values
        if flat:
            return {"type": "form", "params": flat}

    return None


def rebuild_body(body_info: dict) -> str:
    """Rebuild a request body from parsed parameters.

    Args:
        body_info: Dict with 'type' ('json' or 'form') and 'params' dict.

    Returns:
        Encoded body string.
    """
    if body_info["type"] == "json":
        return json.dumps(body_info["params"], separators=(",", ":"))
    elif body_info["type"] == "form":
        return urlencode(body_info["params"], doseq=True)
    else:
        raise ValueError(f"Unknown body type: {body_info['type']}")


# ---------------------------------------------------------------------------
# Ontario Parks /api/cart/commit helpers
# ---------------------------------------------------------------------------

def is_op_cart_commit(parsed: dict) -> bool:
    """Return True if this looks like an Ontario Parks /api/cart/commit request."""
    return "/api/cart/commit" in parsed.get("path", "")


def extract_op_booking_fields(body: str) -> dict | None:
    """Extract the key booking fields from an Ontario Parks cart commit body.

    Returns a dict with the 4 editable booking fields, or None if the body
    doesn't match the expected structure.
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None

    cart = data.get("cart")
    if not cart:
        return None

    bookings = cart.get("bookings", [])
    blockers = cart.get("resourceBlockers", [])
    if not bookings or not blockers:
        return None

    booking_ver = bookings[0].get("newVersion", {})
    blocker_ver = blockers[0].get("newVersion", {})

    start_date = booking_ver.get("startDate") or blocker_ver.get("startDate")
    end_date = booking_ver.get("endDate") or blocker_ver.get("endDate")
    resource_id = blocker_ver.get("resourceId")
    resource_location_id = (
        booking_ver.get("resourceLocationId")
        or blocker_ver.get("resourceLocationId")
    )

    if not all([start_date, end_date, resource_id is not None, resource_location_id is not None]):
        return None

    return {
        "startDate": start_date,
        "endDate": end_date,
        "resourceId": resource_id,
        "resourceLocationId": resource_location_id,
    }


def apply_op_booking_fields(body: str, fields: dict) -> str:
    """Write the 4 booking fields back to every nested location in the body.

    Updates all 7 nested paths where these values appear and returns the
    updated JSON string (compact, matching the original format).
    """
    data = json.loads(body)
    cart = data["cart"]

    booking_ver = cart["bookings"][0]["newVersion"]
    blocker_ver = cart["resourceBlockers"][0]["newVersion"]

    # Start date — 2 locations
    booking_ver["startDate"] = fields["startDate"]
    blocker_ver["startDate"] = fields["startDate"]

    # End date — 2 locations
    booking_ver["endDate"] = fields["endDate"]
    blocker_ver["endDate"] = fields["endDate"]

    # Resource ID (site number) — 1 location
    blocker_ver["resourceId"] = fields["resourceId"]

    # Resource location ID (park) — 2 locations
    booking_ver["resourceLocationId"] = fields["resourceLocationId"]
    blocker_ver["resourceLocationId"] = fields["resourceLocationId"]

    return json.dumps(data, separators=(",", ":"))


def extract_op_shopper_fields(body: str) -> dict | None:
    """Extract personal info fields from an Ontario Parks cart body.

    Returns a dict with keys:
        firstName, lastName, email,
        primaryPhoneNumber, primaryCountryCode,
        streetAddress, city, region, regionCode, country
    or None if the body doesn't have the expected shopper structure.
    """
    try:
        data = json.loads(body)
        cart = data.get("cart", data)
        current = (cart.get("shopper") or {}).get("currentVersion") or {}
        if not current:
            return None
        phone = current.get("phoneNumbers") or {}
        addresses = current.get("addresses") or []
        addr = addresses[0] if addresses else {}
        return {
            "firstName": current.get("firstName", ""),
            "lastName": current.get("lastName", ""),
            "email": current.get("email", ""),
            "primaryPhoneNumber": phone.get("primaryPhoneNumber", ""),
            "primaryCountryCode": phone.get("primaryCountryCode"),
            "streetAddress": addr.get("streetAddress", ""),
            "city": addr.get("city", ""),
            "region": addr.get("region", ""),
            "regionCode": addr.get("regionCode", ""),
            "country": addr.get("country", ""),
        }
    except Exception:
        return None


def apply_op_shopper_fields(body: str, fields: dict) -> str:
    """Write personal info into all relevant locations in a cart commit body.

    Updates:
      - cart.shopper.currentVersion  (name, email, phone, address)
      - cart.bookings[0].newVersion.occupant  (firstName, lastName)

    Returns compact JSON string.
    """
    data = json.loads(body)
    cart = data.get("cart", data)

    # shopper.currentVersion
    current = (cart.get("shopper") or {}).get("currentVersion")
    if isinstance(current, dict):
        current["firstName"] = fields.get("firstName", "")
        current["lastName"] = fields.get("lastName", "")
        current["email"] = fields.get("email", "")
        phone = current.get("phoneNumbers")
        if isinstance(phone, dict):
            phone["primaryPhoneNumber"] = fields.get("primaryPhoneNumber", "")
            phone["primaryCountryCode"] = fields.get("primaryCountryCode")
        addresses = current.get("addresses")
        if addresses:
            a = addresses[0]
            a["streetAddress"] = fields.get("streetAddress", "")
            a["city"] = fields.get("city", "")
            a["region"] = fields.get("region", "")
            a["regionCode"] = fields.get("regionCode", "")
            a["country"] = fields.get("country", "")

    # occupant in first booking
    bookings = cart.get("bookings") or []
    if bookings:
        occupant = (bookings[0].get("newVersion") or {}).get("occupant")
        if isinstance(occupant, dict):
            occupant["firstName"] = fields.get("firstName", "")
            occupant["lastName"] = fields.get("lastName", "")

    return json.dumps(data, separators=(",", ":"))


def regenerate_op_session_uuids(body: str) -> tuple[str, dict[str, str]]:
    """Regenerate the 4 groups of session UUIDs in an Ontario Parks cart body.

    Generates a fresh v4 UUID for each group and updates all occurrences
    consistently. Does NOT touch shopperUid or userUid (account IDs).

    Returns:
        Tuple of (updated_body_str, mapping) where mapping is
        {"cartUid": "new-uuid", "bookingUid": "new-uuid", ...}.
    """
    data = json.loads(body)
    cart = data["cart"]
    booking = cart["bookings"][0]
    booking_ver = booking["newVersion"]
    blockers = cart.get("resourceBlockers", [])
    txn = cart.get("newTransaction", {})

    new_cart_uid = str(uuid.uuid4())
    new_booking_uid = str(uuid.uuid4())
    new_txn_uid = str(uuid.uuid4())

    # cartUid — 2 locations (+ 1 in blocker if present)
    cart["cartUid"] = new_cart_uid
    booking["cartUid"] = new_cart_uid

    # bookingUid — 1 location (+ 1 in blocker if present)
    booking["bookingUid"] = new_booking_uid

    # resourceBlocker fields — only when blockers exist
    if blockers:
        blocker = blockers[0]
        blocker_ver = blocker["newVersion"]
        new_blocker_uid = str(uuid.uuid4())

        blocker["cartUid"] = new_cart_uid
        blocker["bookingUid"] = new_booking_uid
        blocker["resourceBlockerUid"] = new_blocker_uid
        blocker_ver["cartTransactionUid"] = new_txn_uid

        if booking_ver.get("resourceBlockerUids"):
            booking_ver["resourceBlockerUids"] = [new_blocker_uid]
    else:
        new_blocker_uid = None
        # Clear resourceBlockerUids if it was somehow populated
        if booking_ver.get("resourceBlockerUids"):
            booking_ver["resourceBlockerUids"] = []

    # cartTransactionUid / createTransactionUid — 4 locations (+ 1 in blocker above)
    cart["createTransactionUid"] = new_txn_uid
    if txn:
        txn["cartTransactionUid"] = new_txn_uid
    booking["createTransactionUid"] = new_txn_uid
    booking_ver["cartTransactionUid"] = new_txn_uid

    mapping = {
        "cartUid": new_cart_uid,
        "bookingUid": new_booking_uid,
        "cartTransactionUid": new_txn_uid,
    }
    if new_blocker_uid:
        mapping["resourceBlockerUid"] = new_blocker_uid

    return json.dumps(data, separators=(",", ":")), mapping


def apply_op_uuids_from_step1_response(commit_body: str, step1_response_body: str) -> str:
    """Inject UUIDs from the step 1 response into the commit body.

    Parses the step 1 response JSON, extracts the 4 session UUID groups
    (cartUid, bookingUid, resourceBlockerUid, cartTransactionUid), and
    writes them to all expected paths in the commit body.

    Tries multiple response shapes since the exact format depends on the
    specific pre-commit endpoint the user captures.

    Returns:
        Updated commit body JSON string.

    Raises:
        ValueError: If required UUIDs cannot be found in the step 1 response.
    """
    response = json.loads(step1_response_body)

    if not isinstance(response, dict):
        raise ValueError(
            f"Step 1 response is not a JSON object (got {type(response).__name__}). "
            f"The server may have returned an error. Check the step 1 response logs."
        )

    # Response may be {cart: {...}} or the cart object directly
    cart_resp = response.get("cart", response)

    cart_uid = cart_resp.get("cartUid")

    bookings = cart_resp.get("bookings") or []
    booking_uid = None
    if bookings:
        booking_uid = bookings[0].get("bookingUid") or bookings[0].get("uid")

    blockers = cart_resp.get("resourceBlockers") or []
    blocker_uid = None
    if blockers:
        blocker_uid = (
            blockers[0].get("resourceBlockerUid") or blockers[0].get("uid")
        )

    txn_uid = cart_resp.get("createTransactionUid") or cart_resp.get("cartTransactionUid")

    missing = []
    if not cart_uid:
        missing.append("cartUid")
    if not booking_uid:
        missing.append("bookingUid")
    if not blocker_uid:
        missing.append("resourceBlockerUid")
    if not txn_uid:
        missing.append("cartTransactionUid / createTransactionUid")
    if missing:
        raise ValueError(
            f"Step 1 response is missing required UUIDs: {', '.join(missing)}. "
            f"Check that you captured the correct pre-commit request and that "
            f"its response contains a cart object with booking and resourceBlocker arrays."
        )

    # Inject into commit body — same paths as regenerate_op_session_uuids
    data = json.loads(commit_body)
    cart = data["cart"]
    booking = cart["bookings"][0]
    booking_ver = booking["newVersion"]
    blocker = cart["resourceBlockers"][0]
    blocker_ver = blocker["newVersion"]
    txn = cart.get("newTransaction", {})

    # cartUid — 3 locations
    cart["cartUid"] = cart_uid
    booking["cartUid"] = cart_uid
    blocker["cartUid"] = cart_uid

    # bookingUid — 2 locations
    booking["bookingUid"] = booking_uid
    blocker["bookingUid"] = booking_uid

    # resourceBlockerUid — 2 locations
    if booking_ver.get("resourceBlockerUids"):
        booking_ver["resourceBlockerUids"] = [blocker_uid]
    blocker["resourceBlockerUid"] = blocker_uid

    # cartTransactionUid / createTransactionUid — 5 locations
    cart["createTransactionUid"] = txn_uid
    if txn:
        txn["cartTransactionUid"] = txn_uid
    booking["createTransactionUid"] = txn_uid
    booking_ver["cartTransactionUid"] = txn_uid
    blocker_ver["cartTransactionUid"] = txn_uid

    return json.dumps(data, separators=(",", ":"))


def update_referer_params(referer: str, fields: dict) -> str:
    """Update startDate, endDate, and resourceLocationId in a Referer URL.

    Only modifies params that already exist in the URL.
    """
    parsed = urlparse(referer)
    params = parse_qs(parsed.query, keep_blank_values=True)

    param_map = {
        "startDate": fields.get("startDate"),
        "endDate": fields.get("endDate"),
        "resourceLocationId": fields.get("resourceLocationId"),
    }

    changed = False
    for key, new_val in param_map.items():
        if new_val is not None and key in params:
            params[key] = [str(new_val)]
            changed = True

    if not changed:
        return referer

    # Rebuild — flatten single-value lists for clean output
    new_query = urlencode({k: v[0] if len(v) == 1 else v for k, v in params.items()}, doseq=True)
    return urlunparse(parsed._replace(query=new_query))
