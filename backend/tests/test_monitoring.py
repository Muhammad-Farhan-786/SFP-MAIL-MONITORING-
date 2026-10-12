import base64
from unittest.mock import patch
import pytest
from app import monitoring as m
from app.schemas import DomainInput, SeedInput
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


@pytest.mark.parametrize(
    "values,state",
    [
        (["v=spf1 -all", "v=spf1 ~all"], "Critical"),
        (["v=spf1 ip4:8.8.8.8 -all"], "Healthy"),
        (["v=spf1 ~all"], "Warning"),
        (["v=spf1 include:example.com -all"], "Critical"),
        (["v=spf1 +all"], "Critical"),
    ],
)
def test_spf(values, state):
    with patch.object(m, "records", return_value=values):
        assert m.spf("example.com")["state"] == state


@pytest.mark.parametrize(
    "policy,state",
    [
        ("none", "Warning"),
        ("reject", "Healthy"),
        ("quarantine", "Healthy"),
        ("invalid", "Critical"),
    ],
)
def test_dmarc(policy, state):
    with patch.object(m, "records", return_value=["v=DMARC1; p=" + policy]):
        assert m.dmarc("example.com")["state"] == state


def test_dmarc_partial():
    with patch.object(m, "records", return_value=["v=DMARC1; p=reject; pct=10"]):
        assert m.dmarc("example.com")["state"] == "Warning"


def test_dkim_valid():
    key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    )
    with patch.object(
        m,
        "records",
        return_value=["v=DKIM1; k=rsa; p=" + base64.b64encode(key).decode()],
    ):
        assert m.dkim("example.com", ["default"])["state"] == "Healthy"


def test_dkim_revoked():
    with patch.object(m, "records", return_value=["v=DKIM1; p="]):
        assert m.dkim("example.com", ["default"])["state"] == "Critical"


def test_dkim_unconfigured():
    assert m.dkim("example.com", [])["state"] == "Not Configured"


def test_mx_missing():
    with patch.object(m, "records", return_value=[]):
        assert m.mx("example.com")["state"] == "Critical"


def test_mx_valid():
    with (
        patch.object(m, "records", return_value=["10 mail.example.com"]),
        patch.object(m, "public_addresses", return_value=["8.8.8.8"]),
    ):
        assert m.mx("example.com")["state"] == "Healthy"


@pytest.mark.parametrize("tls,state", [(True, "Healthy"), (False, "Critical")])
def test_smtp_tls(tls, state):
    with (
        patch.object(m, "records", return_value=["10 mail.example.com"]),
        patch.object(m, "public_addresses", return_value=["8.8.8.8"]),
        patch.object(m.smtplib, "SMTP") as smtp,
    ):
        client = smtp.return_value.__enter__.return_value
        client.ehlo.return_value = (250, b"ok")
        client.has_extn.return_value = tls
        check, result = m.smtp("example.com")
        assert check["state"] == "Healthy"
        assert result["state"] == state


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1"])
def test_private_targets(address):
    with pytest.raises(ValueError):
        DomainInput(name="example.com", sending_ips=[address])


def test_imap_injection():
    with pytest.raises(ValueError):
        SeedInput(
            provider="Gmail",
            email="a@example.com",
            imap_host="imap.gmail.com",
            spam_folder="Spam\r\nBAD",
            password="secret",
        )


def test_smtp_network_failure_is_unknown():
    with (
        patch.object(m, "records", return_value=["10 mail.example.com"]),
        patch.object(m, "public_addresses", return_value=["8.8.8.8"]),
        patch.object(m.smtplib, "SMTP", side_effect=TimeoutError()),
    ):
        smtp, tls = m.smtp("example.com")
        assert smtp["state"] == "Unknown" and tls["state"] == "Unknown"
