"""The contact card for the number MedPull texts from.

A text from an unsaved number shows as digits. Sendblue delivers a file
whose URL ends in ``.vcf`` as a contact card the person can save in one tap,
after which every later text arrives under a name: the clinic's, when the
card was asked for with one ("H.I.R.T. Physical Therapy via MedPull"), else
"MedPull". The route that serves it is in ``app/api/sendblue_webhook.py``;
the demo phone's welcome text is the one message that attaches it.
"""

from __future__ import annotations

from app.config import settings

DEFAULT_NAME = "MedPull"
MEDIA_TYPE = "text/vcard; charset=utf-8"


def card_name(clinic_name: str | None) -> str:
    """The name the card saves the line under."""
    clinic_name = (clinic_name or "").strip()
    return f"{clinic_name} via MedPull" if clinic_name else DEFAULT_NAME


def _escape(value: str) -> str:
    """A vCard text value: backslash, comma and semicolon are escaped and a
    line break is spelled out (RFC 6350, 3.4)."""
    return (value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def vcard(name: str, number: str) -> str:
    """A vCard 3.0 for an organisation with one mobile number. ``ORG`` with
    ``X-ABShowAs:COMPANY`` is what makes an iPhone file it under the name
    itself rather than as a person with no first name."""
    name = _escape(name)
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "N:;;;;",
        f"FN:{name}",
        f"ORG:{name}",
        "X-ABShowAs:COMPANY",
        f"TEL;TYPE=CELL:{number}",
        "END:VCARD",
    ]
    return "\r\n".join(lines) + "\r\n"


def card_url(clinic_id: str | None = None) -> str | None:
    """The public URL of the card, ending in ``.vcf`` as Sendblue requires
    of a media link, or None when there is no public host to name (a
    laptop) or no line to put on the card."""
    base = (settings.checkin_base_url or "").strip().rstrip("/")
    if not base or not settings.sendblue_from_number:
        return None
    if clinic_id:
        return f"{base}/api/contact/{clinic_id}.vcf"
    return f"{base}/api/contact.vcf"
