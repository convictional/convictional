from dataclasses import dataclass

from app.models.accounts import Group, GroupMember, Organization, User
from config.enums import Integration
from scripts.seeds.seeder import create, fields


@dataclass
class People:
    org: Organization
    darren: User
    maren: User
    priya: User
    leo: User
    tessa: User
    arjun: User
    jordan: User
    theo: User
    emma: User
    rhea: User
    mateo: User
    all_hands: Group
    exec: Group
    engineering: Group
    gtm: Group
    legal_product: Group

    @property
    def all_users(self) -> list[User]:
        return [
            self.darren,
            self.maren,
            self.priya,
            self.leo,
            self.tessa,
            self.arjun,
            self.jordan,
            self.theo,
            self.emma,
            self.rhea,
            self.mateo,
        ]


async def _create_group(key: str, *, name: str, members: list[User]) -> Group:
    group = await create(Group, key, name=name)
    for user in members:
        await create(GroupMember, f"{key}-{user.email}", group=group, user=user)
    return group


async def seed_people() -> People:
    org = await create(Organization, "org", name="Ellery", domain="ellery.ai")

    with fields(organization=org):
        darren = await create(
            User,
            "darren",
            email="darren@ellery.ai",
            name="Darren Okafor",
            is_admin=True,
            bio="CEO & Cofounder. Ex-engineer, second-time founder. Just closed our Series A.",
            integrations=[Integration.RECALL_AI_CALENDAR, Integration.GMAIL],
        )
        maren = await create(
            User,
            "maren",
            email="maren@ellery.ai",
            name="Maren Kovacs",
            is_admin=True,
            bio="Cofounder & Head of Legal Product. JD, former GC. The voice of the customer.",
        )
        priya = await create(
            User,
            "priya",
            email="priya@ellery.ai",
            name="Priya Chandrasekaran",
            is_admin=True,
            bio="CTO & Head of Engineering. Scaling the platform to handle enterprise contract volume.",
        )
        leo = await create(
            User,
            "leo",
            email="leo@ellery.ai",
            name="Leo Park",
            is_admin=True,
            bio="Head of Product. Turning AI capability into lawyer-loved workflows.",
        )
        tessa = await create(
            User,
            "tessa",
            email="tessa@ellery.ai",
            name="Tessa Nguyen",
            is_admin=True,
            bio="Head of Revenue. Building the GTM muscle from founding AE up.",
        )
        arjun = await create(
            User,
            "arjun",
            email="arjun@ellery.ai",
            name="Arjun Mehta",
            bio="Senior Software Engineer. Backend + infra. Scaling the contract processing pipeline.",
        )
        jordan = await create(
            User,
            "jordan",
            email="jordan@ellery.ai",
            name="Jordan Reyes",
            bio="ML/AI Engineer. Evals, fine-tuning, retrieval - making the AI actually reliable.",
        )
        theo = await create(
            User,
            "theo",
            email="theo@ellery.ai",
            name="Theo Mbeki",
            bio="Software Engineer. Full-stack. Building the product surface lawyers live in.",
        )
        emma = await create(
            User,
            "emma",
            email="emma@ellery.ai",
            name="Emma Lindqvist",
            bio="Product Designer. Also doing the user research that keeps us honest.",
        )
        rhea = await create(
            User,
            "rhea",
            email="rhea@ellery.ai",
            name="Rhea Patel",
            bio="Legal Content Analyst. Ex-BigLaw associate. Owns the playbooks and ground truth data.",
        )
        mateo = await create(
            User,
            "mateo",
            email="mateo@ellery.ai",
            name="Mateo Alvarez",
            bio="Founding Account Executive. First GTM hire after Tessa. Closing our early enterprise deals.",
        )

        all_hands = await _create_group(
            "all-hands",
            name="All-Hands",
            members=[darren, maren, priya, leo, tessa, arjun, jordan, theo, emma, rhea, mateo],
        )
        exec_group = await _create_group(
            "exec",
            name="Exec",
            members=[darren, maren, priya, leo, tessa],
        )
        engineering = await _create_group(
            "engineering",
            name="Engineering",
            members=[priya, arjun, jordan, theo],
        )
        gtm = await _create_group("gtm", name="GTM", members=[tessa, mateo, darren])
        legal_product = await _create_group(
            "legal-product",
            name="Legal Product",
            members=[maren, rhea],
        )

    return People(
        org=org,
        darren=darren,
        maren=maren,
        priya=priya,
        leo=leo,
        tessa=tessa,
        arjun=arjun,
        jordan=jordan,
        theo=theo,
        emma=emma,
        rhea=rhea,
        mateo=mateo,
        all_hands=all_hands,
        exec=exec_group,
        engineering=engineering,
        gtm=gtm,
        legal_product=legal_product,
    )
