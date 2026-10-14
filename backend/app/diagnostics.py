"""Evidence-based guidance; never supplies guessed DNS values or performs remediation."""

KNOWLEDGE = {
    "SPF": (
        "Authoritative DNS panel and an inventory of every legitimate sending service",
        [
            "Locate TXT records at the domain root and identify all v=spf1 records.",
            "Compare observed mechanisms and include chains against the official configuration for each legitimate sender.",
            "Consolidate conflicting records, remove cycles, and review the lookup budget while preserving authorized senders.",
            "Publish only the sender-approved configuration; wait for its TTL/propagation.",
        ],
        "Run the SPF retest, then verify Return-Path SPF and alignment on an actual sent message.",
    ),
    "DKIM": (
        "Sending-provider console and authoritative DNS panel",
        [
            "Identify the sending provider and obtain its active selector names and generated public keys.",
            "Inspect each SELECTOR._domainkey.DOMAIN TXT/CNAME record shown in the evidence.",
            "Publish the provider-generated value unchanged and enable signing at that provider if needed.",
            "Do not invent a selector or regenerate a provider's private signing key.",
        ],
        "Retest the configured selectors and inspect a real message's DKIM-Signature and Authentication-Results headers.",
    ),
    "DMARC": (
        "Authoritative DNS panel and provider authentication reports",
        [
            "Inspect the TXT policy at _dmarc.DOMAIN, including p, pct, aspf and adkim.",
            "Resolve conflicting/invalid tags and confirm legitimate senders pass aligned SPF or DKIM.",
            "Review reports before increasing enforcement; do not blindly switch p=none to reject.",
            "Apply an approved policy through the DNS owner and wait for propagation.",
        ],
        "Retest the published policy and verify alignment in a real received message.",
    ),
    "MX": (
        "Authoritative DNS panel and inbound mail-provider configuration",
        [
            "Compare domain MX targets and priorities with the inbound provider's official records.",
            "Check target A/AAAA resolution and whether a null MX intentionally disables reception.",
            "Ask the DNS owner to correct only verified routing discrepancies.",
        ],
        "Retest MX resolution and confirm the inbound provider receives an authorized test message.",
    ),
    "SMTP": (
        "Monitoring VPS network/egress configuration and remote mail administrator",
        [
            "Check the evidence for the MX host, response code, timeout or connection failure.",
            "Verify outbound TCP 25 from the monitoring VPS before attributing a timeout to the remote server.",
            "Ask the remote administrator to inspect listener availability, routing and firewall policy; the monitor cannot change that server.",
        ],
        "Repeat the read-only EHLO probe from the monitoring VPS; distinguish network-unknown from confirmed SMTP rejection.",
    ),
    "TLS": (
        "Remote mail administrator or provider certificate management",
        [
            "Inspect STARTTLS advertisement and the observed TLS/certificate failure.",
            "Check certificate expiry, chain trust and matching MX hostname with the mail provider.",
            "Have the authorized administrator install/renew the correct certificate or enable STARTTLS.",
            "Do not disable certificate verification to obtain a passing result.",
        ],
        "Retest STARTTLS with hostname and chain verification enabled.",
    ),
    "PTR": (
        "Sending-IP hosting provider or IP address owner",
        [
            "Check the configured sending IP and observed PTR target.",
            "Ask the IP owner to configure a PTR matching a publicly resolving sending hostname.",
            "Confirm forward A/AAAA resolution maps that hostname back to the same sending IP.",
        ],
        "Retest forward-confirmed reverse DNS for each known sending IP.",
    ),
    "Blacklist": (
        "Source operator's authorized portal and sending-IP/domain administrator",
        [
            "Identify the exact source, target and listing response from the evidence.",
            "Confirm this query is licensed and is not a provider error/quota response.",
            "Investigate unauthorized traffic or abuse with the responsible sender/provider.",
            "Use that source's official investigation/delisting procedure only after addressing its stated cause.",
        ],
        "Retest the same authorized sources; a clean result does not imply universal reputation.",
    ),
    "IP Reputation": (
        "Configured reputation-provider account and sending-IP administrator",
        [
            "Review the named source and measured indicator; do not equate abuse confidence with inbox placement.",
            "Check provider quota/authentication for Unknown results.",
            "Investigate reported abuse and legitimate sending practices with the sender; follow the provider's documented review process.",
        ],
        "Retest the configured API and compare new evidence against the previous observation.",
    ),
    "Domain Reputation": (
        "Authorized domain reputation provider and sending-domain owner",
        [
            "Configure a supported, authorized API if no source is connected.",
            "Review the actual provider metrics and evidence; do not infer provider reputation from DNS alone.",
            "Coordinate remediation with the domain owner using that source's documented findings.",
        ],
        "Retest the configured API; unconfigured sources cannot be marked healthy.",
    ),
    "Bounce Rate": (
        "Sending-provider telemetry console and recipient-list owner",
        [
            "Connect signed delivery telemetry if it is unmeasured.",
            "Inspect actual SMTP codes and bounce reasons, separating temporary from permanent failures.",
            "Have the sender suppress known invalid recipients and investigate repeated temporary failures.",
            "Review opt-in list hygiene and sender policy without sending unsolicited test traffic.",
        ],
        "Verify fresh authenticated events and retest the configured 24-hour bounce threshold.",
    ),
    "Delivery Rate": (
        "Sending-provider event console and application webhook integration",
        [
            "Verify the signed event adapter, timestamp window and unique provider event IDs.",
            "Inspect deferred/rejected/permanent failure evidence and the sender's queue status.",
            "Ask the sender to investigate the observed SMTP response; delivered means provider delivery, not guaranteed inbox placement.",
        ],
        "Receive fresh authenticated terminal events and retest delivery/failure thresholds.",
    ),
    "Inbox Placement": (
        "Authorized seed-account owner and authorized sending service",
        [
            "Confirm the exact SMTP sender scope; monitoring notification SMTP is not proof about production sending.",
            "Use provider-approved OAuth for Outlook and supported OAuth/app-password access for Gmail.",
            "Verify actual Inbox and Spam/Junk folder names and the complete delivery wait window.",
            "Inspect the seed message and headers; investigate Unknown authentication errors before inferring Spam/Missing.",
        ],
        "Run a new controlled seed test with authorized accounts and compare observed folder placement.",
    ),
}


def diagnose(category, state, summary, evidence):
    access, steps, verify = KNOWLEDGE.get(
        category,
        (
            "Monitoring administrator",
            ["Inspect the recorded evidence and repeat the failed check."],
            "Retest the same observed signal.",
        ),
    )
    if state in ("Not Configured", "Not Measured"):
        cause = "The required selectors, sending targets, credentials or data source have not been configured, as described by this check."
    elif state == "Unknown":
        cause = "The observation is inconclusive. Resolver, network, authentication or provider availability must be checked; a production-server fault is not proven."
    elif category == "SPF" and len(evidence.get("records", [])) > 1:
        cause = "More than one SPF record was observed, creating conflicting sender authorization."
    elif category == "DMARC" and evidence.get("policy", {}).get("p") == "none":
        cause = "The observed DMARC policy requests monitoring without quarantine/reject enforcement."
    else:
        cause = (
            "The observed validation result indicates: "
            + summary
            + " Confirm the cause against the attached evidence before changing configuration."
        )
    return {
        "likely_cause": cause,
        "required_access": access,
        "solution_steps": steps,
        "verification": verify,
        "evidence_basis": summary,
        "automatic_remediation": False,
    }
