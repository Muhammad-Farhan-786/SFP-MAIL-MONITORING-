import smtplib, ssl, imaplib, secrets, json
import httpx
from email.message import EmailMessage
from sqlalchemy import select
from .config import config
from .security import decrypt, public_addresses
from .models import SeedMailbox, PlacementTest, now
from .monitoring import result
from .services import record, aware


class PartialDelivery(Exception):
    """Some recipients were accepted; do not retry the whole list and duplicate accepted mail."""

    pass


def send(subject, body, recipients, seed_sender=False, message_id=None):
    cfg = config()
    host = cfg.seed_smtp_host if seed_sender and cfg.seed_smtp_host else cfg.smtp_host
    port = cfg.seed_smtp_port if seed_sender and cfg.seed_smtp_host else cfg.smtp_port
    username = (
        cfg.seed_smtp_user if seed_sender and cfg.seed_smtp_host else cfg.smtp_user
    )
    password = (
        cfg.seed_smtp_password
        if seed_sender and cfg.seed_smtp_host
        else cfg.smtp_password
    )
    sender = cfg.seed_smtp_from if seed_sender and cfg.seed_smtp_host else cfg.smtp_from
    if not host or not sender or not recipients:
        return False
    public_addresses(host)
    message = EmailMessage()
    message["Subject"] = subject
    if message_id:
        message["Message-ID"] = message_id
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(body)
    if port == 465:
        server = smtplib.SMTP_SSL(
            host,
            port,
            timeout=20,
            context=ssl.create_default_context(),
        )
    else:
        server = smtplib.SMTP(host, port, timeout=20)
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
    with server:
        if username:
            server.login(username, password)
        refused = server.send_message(message)
        if refused:
            raise PartialDelivery(
                "Partial SMTP acceptance; review provider recipient results"
            )
    return True


class IMAPProvider:
    """Provider adapter: Gmail/Outlook with IMAP enabled and authorized app credentials."""

    def locate(self, seed, token):
        public_addresses(seed.imap_host)
        if seed.provider == "Outlook" and seed.auth_method != "oauth2":
            raise ValueError("Outlook requires OAuth2 configuration")
        with imaplib.IMAP4_SSL(
            seed.imap_host, 993, ssl_context=ssl.create_default_context(), timeout=20
        ) as client:
            if seed.auth_method == "oauth2":
                token = oauth_access_token(seed)
                auth = f"user={seed.email}\x01auth=Bearer {token}\x01\x01".encode()
                client.authenticate("XOAUTH2", lambda _: auth)
            else:
                client.login(seed.email, decrypt(seed.encrypted_password))
            for folder, state in (
                (seed.inbox_folder, "Inbox"),
                (seed.spam_folder, "Spam"),
            ):
                status, _ = client.select(
                    '"' + folder.replace('"', "") + '"', readonly=True
                )
                if status != "OK":
                    raise ValueError("Mailbox folder cannot be opened")
                status, data = client.search(
                    None, "HEADER", "Subject", '"' + token + '"'
                )
                if status != "OK":
                    raise ValueError("Mailbox search failed")
                if data and data[0]:
                    return state
            return "Missing"


PROVIDERS = {"Gmail": IMAPProvider(), "Outlook": IMAPProvider(), "IMAP": IMAPProvider()}


def start_placement(db, domain_id):
    tests = []
    for seed in db.scalars(
        select(SeedMailbox).where(
            SeedMailbox.domain_id == domain_id, SeedMailbox.active.is_(True)
        )
    ):
        token = "NHM-" + secrets.token_hex(16)
        test = PlacementTest(
            domain_id=domain_id,
            seed_id=seed.id,
            token=token,
            sender_scope=config().seed_sending_source
            if config().seed_smtp_host
            else "Monitoring notification SMTP; does not verify production sending infrastructure",
        )
        db.add(test)
        db.flush()
        try:
            if not send(
                "Authorized inbox placement test " + token,
                "This is a controlled NewHotMusic email health test. Reference: "
                + token,
                [seed.email],
                seed_sender=True,
            ):
                test.state = "Unknown"
                test.detail = "SMTP sending is not configured"
        except Exception as exc:
            test.state = "Unknown"
            test.detail = type(exc).__name__
        if test.state == "Pending":
            tests.append(test.id)
    if not list(
        db.scalars(
            select(SeedMailbox.id).where(
                SeedMailbox.domain_id == domain_id, SeedMailbox.active.is_(True)
            )
        )
    ):
        record(
            db,
            domain_id,
            "Inbox Placement",
            result(
                "Not Configured",
                "Add authorized seed mailboxes to test inbox placement.",
            ),
        )
    db.commit()
    return tests


def finish_placement(db, test):
    seed = db.get(SeedMailbox, test.seed_id)
    if not seed or not seed.active:
        test.state = "Unknown"
        test.detail = "Seed mailbox disabled before collection"
        test.checked_at = now()
        db.commit()
        return True
    try:
        state = PROVIDERS[seed.provider].locate(seed, test.token)
        if (
            state == "Missing"
            and (now() - aware(test.created_at)).total_seconds()
            < config().seed_missing_after_seconds
        ):
            test.detail = "Waiting for the delivery window"
            db.commit()
            return False
        test.state = state
        test.detail = "Seed mailbox folder checked."
    except Exception as exc:
        test.state = "Unknown"
        test.detail = type(exc).__name__
    test.checked_at = now()
    db.commit()
    return True


def placement_summary(db, domain_id):
    seeds = list(
        db.scalars(
            select(SeedMailbox).where(
                SeedMailbox.domain_id == domain_id, SeedMailbox.active.is_(True)
            )
        )
    )
    values = []
    for seed in seeds:
        test = db.scalar(
            select(PlacementTest)
            .where(PlacementTest.seed_id == seed.id)
            .order_by(PlacementTest.created_at.desc())
        )
        values.append(
            {
                "provider": seed.provider,
                "state": test.state if test else "Unknown",
                "sender_scope": test.sender_scope if test else "Not Measured",
                "checked_at": test.checked_at.isoformat()
                if test and test.checked_at
                else None,
            }
        )
    state = (
        "Not Configured"
        if not seeds
        else "Critical"
        if any(v["state"] == "Spam" for v in values)
        else "Warning"
        if any(v["state"] == "Missing" for v in values)
        else "Unknown"
        if any(v["state"] not in ("Inbox", "Spam", "Missing") for v in values)
        else "Healthy"
    )
    record(
        db,
        domain_id,
        "Inbox Placement",
        result(
            state,
            "Authorized seed mailbox placement measured."
            if seeds
            else "No authorized seed mailboxes configured.",
            providers=values,
        ),
    )
    db.commit()


def oauth_access_token(seed):
    from .security import encrypt

    credentials = json.loads(decrypt(seed.encrypted_password))
    if seed.provider == "Gmail":
        endpoint = "https://oauth2.googleapis.com/token"
    elif seed.provider == "Outlook":
        import re

        tenant = credentials.get("tenant", "common")
        if not re.fullmatch(r"(common|organizations|[0-9a-fA-F-]{36})", tenant):
            raise ValueError("Invalid OAuth tenant")
        endpoint = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    else:
        raise ValueError("OAuth provider not supported")
    data = {
        "grant_type": "refresh_token",
        "client_id": credentials["client_id"],
        "refresh_token": credentials["refresh_token"],
    }
    if credentials.get("client_secret"):
        data["client_secret"] = credentials["client_secret"]
    if seed.provider == "Outlook":
        data["scope"] = (
            "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
        )
    response = httpx.post(endpoint, data=data, timeout=15, follow_redirects=False)
    response.raise_for_status()
    body = response.json()
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("OAuth access token missing")
    if body.get("refresh_token"):
        credentials["refresh_token"] = body["refresh_token"]
        seed.encrypted_password = encrypt(json.dumps(credentials))
    return token
