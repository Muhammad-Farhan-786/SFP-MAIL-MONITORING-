"""Pure normalization of already-authenticated Postmark/SendGrid observations."""

from datetime import datetime, timezone


def normalize(provider, event, domain):
    if provider == "postmark":
        record = event.get("RecordType")
        kind = {
            "Delivery": "delivered",
            "SpamComplaint": "complaint",
            "Bounce": "hard_bounce",
        }.get(record)
        if record == "Bounce":
            kind = (
                "soft_bounce"
                if event.get("Type") in ("SoftBounce", "Transient", "DnsError")
                else "hard_bounce"
            )
        if not kind:
            raise ValueError("Unsupported Postmark event")
        event_id = "postmark:" + str(
            event.get("ID")
            or f"{event['MessageID']}:{record}:{event.get('DeliveredAt') or event.get('BouncedAt')}"
        )
        recipient = event.get("Recipient") or event.get("Email")
        stamp = (
            event.get("DeliveredAt")
            or event.get("BouncedAt")
            or event.get("ReceivedAt")
        )
        data = {
            "event_id": event_id,
            "message_id": event.get("MessageID"),
            "kind": kind,
            "occurred_at": stamp,
            "reason": event.get("Description") or event.get("Details"),
        }
    elif provider == "sendgrid":
        kind = {
            "delivered": "delivered",
            "deferred": "deferred",
            "bounce": "hard_bounce",
            "dropped": "rejected",
            "spamreport": "complaint",
        }.get(event.get("event"))
        if not kind:
            raise ValueError("Unsupported SendGrid event")
        recipient = event.get("email")
        data = {
            "event_id": "sendgrid:" + event["sg_event_id"],
            "message_id": event.get("sg_message_id"),
            "kind": kind,
            "occurred_at": datetime.fromtimestamp(
                event["timestamp"], timezone.utc
            ).isoformat(),
            "reason": event.get("reason") or event.get("response"),
        }
    else:
        raise ValueError("Unsupported provider")
    if (
        not isinstance(recipient, str)
        or "@" not in recipient
        or not data["occurred_at"]
    ):
        raise ValueError("Recipient domain and event timestamp are required")
    data.update(domain=domain, recipient_domain=recipient.rsplit("@", 1)[1].lower())
    return data
