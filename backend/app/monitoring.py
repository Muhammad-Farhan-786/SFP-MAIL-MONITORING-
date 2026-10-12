"""Read-only DNS and SMTP monitoring. DNS records never establish message-level alignment."""

import ipaddress, ssl, smtplib
import dns.resolver
import httpx
from .config import config
from .security import public_addresses


def result(state, summary, **evidence):
    return {"state": state, "summary": summary, "evidence": evidence}


def records(name, kind):
    try:
        answer = dns.resolver.resolve(name, kind, lifetime=8)
        if kind == "TXT":
            return [
                b"".join(r.strings).decode("utf-8", errors="replace") for r in answer
            ]
        return [str(r).rstrip(".") for r in answer]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []


def spf(domain):
    values = [r for r in records(domain, "TXT") if r.lower().startswith("v=spf1")]
    if len(values) != 1:
        return result(
            "Critical", "Your domain needs exactly one SPF record.", records=values
        )
    value = values[0]
    terms = value.split()[1:]
    import re

    pattern = r"(?:all|(?:a|mx)(?::[^/ ]+)?(?:/[0-9]{1,3})?(?://[0-9]{1,3})?|ptr(?::[^ ]+)?|(?:include|exists):[^ ]+|ip[46]:[^ ]+|(?:redirect|exp)=[^ ]+)"
    invalid = any(not re.fullmatch(pattern, t.lstrip("+-~?")) for t in terms)
    try:
        for term in terms:
            clean = term.lstrip("+-~?")
            if clean.startswith(("ip4:", "ip6:")):
                network = ipaddress.ip_network(clean.split(":", 1)[1], strict=False)
                if network.version != int(clean[2]):
                    invalid = True
    except ValueError:
        invalid = True
    if invalid:
        return result(
            "Critical",
            "SPF contains an unsupported or invalid mechanism.",
            records=values,
        )
    if any(t in ("+all", "all", "?all") for t in terms):
        return result(
            "Critical",
            "SPF allows or does not constrain unauthorized senders.",
            records=values,
        )
    lookup_count = 0
    visited = set()

    def count(name, depth=0):
        nonlocal lookup_count
        if name in visited or depth > 10:
            raise ValueError("SPF include cycle or excessive nesting")
        visited.add(name)
        found = [r for r in records(name, "TXT") if r.lower().startswith("v=spf1")]
        if len(found) != 1:
            raise ValueError("Included SPF domain must have exactly one record")
        for term in found[0].split()[1:]:
            term = term.lstrip("+-~?")
            if term.startswith(("include:", "redirect=")):
                lookup_count += 1
                count(
                    term.split(":", 1)[1] if ":" in term else term.split("=", 1)[1],
                    depth + 1,
                )
            elif (
                term == "ptr"
                or term.startswith(("a:", "a/", "mx:", "mx/", "exists:"))
                or term in ("a", "mx")
            ):
                lookup_count += 1
        visited.remove(name)

    try:
        count(domain)
    except ValueError as exc:
        return result("Critical", str(exc), records=values)
    if lookup_count > 10:
        return result(
            "Critical",
            "SPF exceeds the ten DNS lookup limit.",
            records=values,
            lookups=lookup_count,
        )
    if any("%{" in t or t.lstrip("+-~?") == "ptr" for t in terms):
        return result(
            "Warning",
            "SPF requires deeper evaluation of macros or deprecated PTR mechanisms.",
            records=values,
            lookups=lookup_count,
        )
    state = "Healthy" if terms and terms[-1] == "-all" else "Warning"
    return result(
        state,
        "SPF is configured with a strict sender policy."
        if state == "Healthy"
        else "SPF uses a soft or incomplete sender policy; review authorized senders.",
        records=values,
        lookups=lookup_count,
        scope="Configuration check; per-message evaluation and alignment require delivery telemetry",
    )


def tags(value):
    out = {}
    for field in value.split(";"):
        if "=" in field:
            key, val = field.strip().split("=", 1)
            if key in out:
                raise ValueError("Duplicate record tag")
            out[key] = val.strip()
    return out


def dmarc(domain):
    values = [
        r
        for r in records("_dmarc." + domain, "TXT")
        if r.upper().startswith("V=DMARC1")
    ]
    if len(values) != 1:
        return result(
            "Critical", "Your domain needs exactly one DMARC policy.", records=values
        )
    try:
        policy = tags(values[0])
        if policy.get("p") not in ("none", "quarantine", "reject"):
            raise ValueError("Invalid DMARC policy")
        pct = int(policy.get("pct", "100"))
        if (
            not 0 <= pct <= 100
            or policy.get("adkim", "r") not in ("r", "s")
            or policy.get("aspf", "r") not in ("r", "s")
        ):
            raise ValueError("Invalid DMARC alignment or percentage")
    except ValueError as exc:
        return result("Critical", str(exc), records=values)
    state = (
        "Healthy"
        if policy["p"] in ("reject", "quarantine") and pct == 100
        else "Warning"
    )
    return result(
        state,
        "DMARC protects your domain from unauthorized messages."
        if state == "Healthy"
        else "DMARC monitors failures but does not fully quarantine or reject them.",
        records=values,
        policy=policy,
        message_alignment="Unknown without delivery telemetry",
    )


def dkim(domain, selectors):
    if not selectors:
        return result(
            "Not Configured", "Add the DKIM selectors used by your email provider."
        )
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    import base64

    outcomes = []
    for selector in selectors:
        values = records(f"{selector}._domainkey.{domain}", "TXT")
        try:
            if len(values) != 1:
                raise ValueError("Exactly one DKIM key is required")
            parsed = tags(values[0])
            key = parsed.get("p", "")
            if not key:
                raise ValueError("DKIM key is missing or revoked")
            raw = base64.b64decode(key, validate=True)
            kind = parsed.get("k", "rsa")
            if kind == "ed25519":
                if len(raw) != 32:
                    raise ValueError("Invalid Ed25519 key length")
                bits = 256
            elif kind == "rsa":
                public_key = load_der_public_key(raw)
                from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

                if not isinstance(public_key, RSAPublicKey):
                    raise ValueError("Expected an RSA key")
                bits = public_key.key_size
                if bits < 1024:
                    raise ValueError("RSA key is too short")
            else:
                raise ValueError("Unsupported DKIM key type")
            outcomes.append(
                {
                    "selector": selector,
                    "state": "Healthy"
                    if kind == "ed25519" or bits >= 2048
                    else "Warning",
                    "bits": bits,
                    "records": values,
                }
            )
        except (ValueError, TypeError) as exc:
            outcomes.append(
                {
                    "selector": selector,
                    "state": "Critical",
                    "error": str(exc),
                    "records": values,
                }
            )
    state = (
        "Critical"
        if any(x["state"] == "Critical" for x in outcomes)
        else "Warning"
        if any(x["state"] == "Warning" for x in outcomes)
        else "Healthy"
    )
    return result(
        state,
        "DKIM signing keys are published."
        if state == "Healthy"
        else "One or more DKIM selectors need attention.",
        selectors=outcomes,
        scope="Published key validity; message signatures and alignment require delivery telemetry",
    )


def mx(domain):
    values = records(domain, "MX")
    if not values or any(v.split()[-1] in (".", "") for v in values):
        return result(
            "Critical", "No usable mail exchange is configured.", records=values
        )
    hosts = [v.split()[-1] for v in values]
    addresses = {h: public_addresses(h) for h in hosts}
    return result(
        "Healthy", "Your domain can receive email.", records=values, hosts=addresses
    )


def smtp(domain):
    values = records(domain, "MX")
    if not values:
        return result(
            "Critical", "No mail server is available for SMTP testing.", hosts=[]
        ), result("Unknown", "TLS cannot be checked without an SMTP host.", hosts=[])
    outcomes = []
    for value in sorted(values, key=lambda v: int(v.split()[0]))[:5]:
        host = value.split()[-1]
        item = {"host": host, "smtp": False, "tls": False}
        try:
            # Connect to a validated IP to prevent DNS rebinding; preserve hostname for certificate checks.
            address = public_addresses(host)[0]
            with smtplib.SMTP(timeout=10) as client:
                client._host = host
                client.connect(address, 25)
                code, _ = client.ehlo()
                item["smtp"] = code == 250
                if client.has_extn("starttls"):
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
                    item["tls"] = True
                else:
                    item["error"] = "STARTTLS not offered"
        except ssl.SSLCertVerificationError as exc:
            item["tls"] = False
            item["error"] = type(exc).__name__
        except OSError as exc:
            item["smtp"] = None
            item["tls"] = None
            item["error"] = type(exc).__name__
        except (smtplib.SMTPException, ValueError) as exc:
            item["error"] = type(exc).__name__
        outcomes.append(item)
    return (
        result(
            "Critical"
            if any(x["smtp"] is False for x in outcomes)
            else "Unknown"
            if any(x["smtp"] is None for x in outcomes)
            else "Healthy",
            "Mail server availability checked.",
            hosts=outcomes,
        ),
        result(
            "Critical"
            if any(x["tls"] is False for x in outcomes)
            else "Unknown"
            if any(x["tls"] is None for x in outcomes)
            else "Healthy",
            "Verified TLS encryption checked on inbound MX servers.",
            hosts=outcomes,
        ),
    )


def ptr(address):
    from dns.reversename import from_address

    values = records(str(from_address(address)), "PTR")
    valid = any(address in public_addresses(host) for host in values)
    return result(
        "Healthy" if valid else "Warning",
        "Reverse DNS matches the sending IP."
        if valid
        else "Configure forward-confirmed reverse DNS with your hosting provider.",
        address=address,
        records=values,
    )


def blacklist(addresses, domain=None):
    zones = [z.strip() for z in config().dnsbl_zones.split(",") if z.strip()]
    domain_zones = [
        z.strip() for z in config().domain_dnsbl_zones.split(",") if z.strip()
    ]
    if not (zones and addresses) and not (domain_zones and domain):
        return result(
            "Not Configured",
            "Configure sending targets and licensed DNSBL sources before checking.",
            sources=[],
        )
    sources = []
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.version != 4:
            sources.append(
                {
                    "source": "DNSBL",
                    "target": address,
                    "state": "Unknown",
                    "reason": "This adapter supports IPv4 only",
                }
            )
            continue
        reverse = ".".join(reversed(address.split(".")))
        for zone in zones:
            try:
                answers = records(reverse + "." + zone, "A")
                # Provider query/error responses are not listings.
                if any(a.startswith("127.255.") or a == "127.0.0.255" for a in answers):
                    state = "Unknown"
                elif answers and all(a.startswith("127.") for a in answers):
                    state = "Critical"
                elif answers:
                    state = "Unknown"
                else:
                    state = "Healthy"
                sources.append(
                    {
                        "source": zone,
                        "target": address,
                        "state": state,
                        "answers": answers,
                    }
                )
            except Exception as exc:
                sources.append(
                    {
                        "source": zone,
                        "target": address,
                        "state": "Unknown",
                        "error": type(exc).__name__,
                    }
                )
    if domain:
        for zone in domain_zones:
            try:
                answers = records(domain + "." + zone, "A")
                state = (
                    "Unknown"
                    if any(
                        a.startswith("127.255.") or a == "127.0.0.255" for a in answers
                    )
                    else "Critical"
                    if answers and all(a.startswith("127.") for a in answers)
                    else "Unknown"
                    if answers
                    else "Healthy"
                )
                sources.append(
                    {
                        "source": zone,
                        "target": domain,
                        "state": state,
                        "answers": answers,
                    }
                )
            except Exception as exc:
                sources.append(
                    {
                        "source": zone,
                        "target": domain,
                        "state": "Unknown",
                        "error": type(exc).__name__,
                    }
                )
    state = (
        "Critical"
        if any(x["state"] == "Critical" for x in sources)
        else "Unknown"
        if any(x["state"] == "Unknown" for x in sources)
        else "Healthy"
    )
    return result(
        state,
        "A sending IP is blocklisted."
        if state == "Critical"
        else "Configured blocklist sources checked.",
        sources=sources,
    )


def reputation(addresses):
    if not config().abuseipdb_key or not addresses:
        return result(
            "Not Configured",
            "Configure the AbuseIPDB integration and sending IPs.",
            source="AbuseIPDB",
            targets=[],
        )
    values = []
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        for address in addresses:
            r = client.get(
                "https://api.abuseipdb.com/api/v2/check",
                headers={"Key": config().abuseipdb_key, "Accept": "application/json"},
                params={"ipAddress": address, "maxAgeInDays": 90},
            )
            r.raise_for_status()
            data = r.json()["data"]
            values.append(
                {"address": address, "abuse_confidence": data["abuseConfidenceScore"]}
            )
    worst = max(v["abuse_confidence"] for v in values)
    return result(
        "Critical" if worst >= 50 else "Warning" if worst > 0 else "Healthy",
        "IP abuse reputation checked. This is not a mailbox provider deliverability score.",
        source="AbuseIPDB",
        targets=values,
    )


def domain_reputation(domain):
    from urllib.parse import urlsplit

    url = config().domain_reputation_url
    if not url:
        return result(
            "Not Configured",
            "Configure an authorized domain reputation API.",
            source="Domain reputation API",
        )
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return result(
            "Unknown", "The reputation integration requires a valid HTTPS URL."
        )
    public_addresses(parsed.hostname)
    headers = {"Accept": "application/json"}
    if config().domain_reputation_key:
        headers["Authorization"] = "Bearer " + config().domain_reputation_key
    response = httpx.get(
        url,
        params={"domain": domain},
        headers=headers,
        timeout=15,
        follow_redirects=False,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("state") not in (
        "Healthy",
        "Warning",
        "Critical",
        "Unknown",
    ) or not isinstance(data.get("summary"), str):
        raise ValueError("Provider response must contain a supported state and summary")
    return result(
        data["state"],
        data["summary"][:1000],
        source=parsed.hostname,
        domain=domain,
        metrics=data.get("metrics", {}),
    )


def run(domain, selectors, addresses, group):
    checks = {}
    tasks = {}
    if group == "auth":
        tasks = {
            "SPF": lambda: spf(domain),
            "DKIM": lambda: dkim(domain, selectors),
            "DMARC": lambda: dmarc(domain),
            "MX": lambda: mx(domain),
        }
        if addresses:

            def ptr_check():
                items = [ptr(a) for a in addresses]
                return result(
                    "Healthy"
                    if all(x["state"] == "Healthy" for x in items)
                    else "Warning",
                    "Reverse DNS checked.",
                    targets=items,
                )

            tasks["PTR"] = ptr_check
    elif group == "smtp":
        try:
            checks["SMTP"], checks["TLS"] = smtp(domain)
        except Exception as exc:
            checks = {
                k: result(
                    "Unknown",
                    "SMTP check could not complete.",
                    error=type(exc).__name__,
                )
                for k in ("SMTP", "TLS")
            }
    elif group == "blacklist":
        tasks = {"Blacklist": lambda: blacklist(addresses, domain)}
    elif group == "reputation":
        tasks = {
            "IP Reputation": lambda: reputation(addresses),
            "Domain Reputation": lambda: domain_reputation(domain),
        }
    for category, function in tasks.items():
        try:
            checks[category] = function()
        except Exception as exc:
            checks[category] = result(
                "Unknown",
                "The check could not determine a result. Review resolver or provider connectivity.",
                error=type(exc).__name__,
            )
    return checks
