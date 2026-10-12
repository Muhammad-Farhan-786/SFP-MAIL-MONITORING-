import smtplib, ssl, imaplib, secrets
from email.message import EmailMessage
from sqlalchemy import select
from .config import config
from .security import decrypt, public_addresses
from .models import SeedMailbox, PlacementTest, now
from .monitoring import result
from .services import record, aware


def send(subject, body, recipients):
    cfg = config()
    if not cfg.smtp_host or not cfg.smtp_from or not recipients:
        return False
    public_addresses(cfg.smtp_host)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = cfg.smtp_from
    message["To"] = ", ".join(recipients)
    message.set_content(body)
    if cfg.smtp_port == 465:
        server = smtplib.SMTP_SSL(
            cfg.smtp_host,
            cfg.smtp_port,
            timeout=20,
            context=ssl.create_default_context(),
        )
    else:
        server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20)
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
    with server:
        if cfg.smtp_user:
            server.login(cfg.smtp_user, cfg.smtp_password)
        server.send_message(message)
    return True


class IMAPProvider:
    """Provider adapter: Gmail/Outlook with IMAP enabled and authorized app credentials."""

    def locate(self, seed, token):
        public_addresses(seed.imap_host)
        with imaplib.IMAP4_SSL(
            seed.imap_host, 993, ssl_context=ssl.create_default_context(), timeout=20
        ) as client:
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
        test = PlacementTest(domain_id=domain_id, seed_id=seed.id, token=token)
        db.add(test)
        db.flush()
        try:
            if not send(
                "Authorized inbox placement test " + token,
                "This is a controlled NewHotMusic email health test. Reference: "
                + token,
                [seed.email],
            ):
                test.state = "Unknown"
                test.detail = "SMTP sending is not configured"
        except Exception as exc:
            test.state = "Unknown"
            test.detail = type(exc).__name__
        tests.append(test.id)
    if not tests:
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
            {"provider": seed.provider, "state": test.state if test else "Unknown"}
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
