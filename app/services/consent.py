from app.db.models import Person

IDENTITY_VALIDATION_PURPOSE = "Prova de conceito academica privada Banco Arkhe"


def has_active_consent(person: Person, purpose: str | None = None) -> bool:
    """Return whether at least one applicable consent record is active.

    Legacy rows created before consent_records remain compatible through the
    denormalized acceptance timestamp, unless all applicable records are revoked.
    """
    applicable = [
        consent
        for consent in person.consents
        if purpose is None or consent.finalidade == purpose
    ]
    if any(consent.revogado_em is None for consent in applicable):
        return True
    if applicable:
        return False
    return person.consentimento_aceito_em is not None
