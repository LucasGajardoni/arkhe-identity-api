from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import decrypt_text, encrypt_text, lookup_hmac, mask_cpf
from app.db.models import ConsentRecord, FacialReference, IdentityDocument, Person
from app.schemas.admin import DocumentCreate, PersonCreate, PersonListItem, PersonUpdate
from app.services.cpf import only_digits


class PersonRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_person(self, data: PersonCreate) -> Person:
        cpf = only_digits(data.cpf)
        person = Person(
            cpf_hash=lookup_hmac(cpf),
            cpf_encrypted=encrypt_text(cpf) or "",
            nome=data.nome,
            nome_social=data.nome_social,
            data_nascimento=data.data_nascimento,
            sexo=data.sexo,
            nacionalidade=data.nacionalidade,
            nome_mae=data.nome_mae,
            nome_pai=data.nome_pai,
            situacao_cpf_interna=data.situacao_cpf_interna,
            data_inscricao_cpf=data.data_inscricao_cpf,
            email=data.email,
            telefone=data.telefone,
            status=data.status,
            consentimento_aceito_em=datetime.now(UTC) if data.consentimento.consentimento_aceito else None,
            versao_termo_consentimento=data.consentimento.versao_termo if data.consentimento.consentimento_aceito else None,
            finalidade_consentimento=data.consentimento.finalidade if data.consentimento.consentimento_aceito else None,
        )
        self.db.add(person)
        self.db.flush()
        if data.consentimento.consentimento_aceito:
            self.db.add(
                ConsentRecord(
                    person_id=person.id,
                    finalidade=data.consentimento.finalidade,
                    versao_termo=data.consentimento.versao_termo,
                )
            )
        return person

    def find_by_cpf(self, cpf: str) -> Person | None:
        stmt = (
            select(Person)
            .options(selectinload(Person.documents), selectinload(Person.facial_references), selectinload(Person.consents))
            .where(Person.cpf_hash == lookup_hmac(only_digits(cpf)))
        )
        return self.db.scalar(stmt)

    def get(self, person_id: UUID) -> Person | None:
        stmt = (
            select(Person)
            .options(selectinload(Person.documents), selectinload(Person.facial_references), selectinload(Person.consents))
            .where(Person.id == person_id)
        )
        return self.db.scalar(stmt)

    def list_people(self) -> list[PersonListItem]:
        people = self.db.scalars(
            select(Person).options(selectinload(Person.facial_references)).order_by(Person.criado_em.desc()).limit(200)
        ).all()
        result = []
        for person in people:
            cpf = decrypt_text(person.cpf_encrypted)
            result.append(
                PersonListItem(
                    id=person.id,
                    cpf_mascarado=mask_cpf(cpf) or "***",
                    nome=person.nome,
                    status=person.status,
                    criado_em=person.criado_em,
                    possui_biometria=any(ref.revogado_em is None for ref in person.facial_references),
                )
            )
        return result

    def update(self, person: Person, data: PersonUpdate) -> Person:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(person, field, value)
        return person

    def add_document(self, person: Person, data: DocumentCreate) -> IdentityDocument:
        doc = IdentityDocument(
            person_id=person.id,
            tipo=data.tipo,
            numero_encrypted=encrypt_text(data.numero) or "",
            numero_hash=lookup_hmac(data.numero.strip().upper()),
            orgao_expedidor=data.orgao_expedidor,
            uf_expedidor=data.uf_expedidor,
            pais_emissor=data.pais_emissor,
            data_emissao=data.data_emissao,
            data_validade=data.data_validade,
            principal=data.principal,
        )
        self.db.add(doc)
        return doc

    def active_facial_reference(self, person: Person) -> FacialReference | None:
        refs = [ref for ref in person.facial_references if ref.revogado_em is None]
        return sorted(refs, key=lambda ref: ref.criado_em, reverse=True)[0] if refs else None

    def revoke_facial_reference(self, person: Person) -> None:
        for ref in person.facial_references:
            if ref.revogado_em is None:
                ref.revogado_em = datetime.now(UTC)

    def delete_person(self, person: Person) -> None:
        self.db.delete(person)
