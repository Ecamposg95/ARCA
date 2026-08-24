from app.models.organization import Organization, OrganizationMember, ROLE_OWNER
from app.models.user import User


def test_org_defaults_mexico(db):
    org = Organization(name="Mi Negocio")
    db.add(org)
    db.commit()
    db.refresh(org)
    assert org.currency == "MXN"
    assert org.country == "MX"
    assert org.timezone == "America/Mexico_City"
    assert len(org.id) == 36


def test_membership_links_user_and_org(db):
    user = User(email="ana@example.com", password_hash="x", name="Ana")
    org = Organization(name="Tienda Ana")
    db.add_all([user, org])
    db.flush()
    member = OrganizationMember(organization_id=org.id, user_id=user.id, role=ROLE_OWNER)
    db.add(member)
    db.commit()
    assert member.role == "OWNER"
    assert member.organization_id == org.id
