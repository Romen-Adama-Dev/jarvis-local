import pytest

from packages.core.errors import ValidationFailedError
from packages.openproject.people import Person, onboard, parse_people, parse_projects


def test_parse_people_accepts_the_usual_ways_of_writing_a_person():
    people = parse_people(
        "Diego Sanz <Diego.Sanz@demo.invalid>; Marta Ruiz (marta.ruiz@demo.invalid)\n"
        "Lucía Martín lucia.martin@demo.invalid"
    )
    assert people == [
        Person("Diego Sanz", "diego.sanz@demo.invalid"),
        Person("Marta Ruiz", "marta.ruiz@demo.invalid"),
        Person("Lucía Martín", "lucia.martin@demo.invalid"),
    ]


@pytest.mark.parametrize("text", ["", "Diego Sanz", "<diego@demo.invalid>"])
def test_parse_people_needs_name_and_email(text):
    with pytest.raises(ValidationFailedError):
        parse_people(text)


def test_parse_projects_splits_by_semicolon_or_line():
    assert parse_projects("Talleres Norte › App de citas; Clínica › Web\n") == [
        "Talleres Norte › App de citas",
        "Clínica › Web",
    ]
    with pytest.raises(ValidationFailedError):
        parse_projects(" ; ")


class FakeOP:
    """Lo justo de OpenProjectClient para onboard."""

    def __init__(self):
        self.users_ = [{"name": "Marta Ruiz", "email": "marta.ruiz@demo.invalid"}]
        self.members = {("Clínica › Web", "marta.ruiz@demo.invalid")}
        self.created, self.assigned = [], []
        self.wps = {
            "App": [
                {
                    "id": 1,
                    "subject": "Backend",
                    "description": {"raw": "x\nResponsable: Diego Sanz"},
                    "_links": {"assignee": {"href": None}},
                },
                {
                    "id": 2,
                    "subject": "Ya asignada",
                    "description": {"raw": "Responsable: Diego Sanz"},
                    "_links": {"assignee": {"href": "/api/v3/users/9"}},
                },
                {
                    "id": 3,
                    "subject": "De Marta",
                    "description": {"raw": "Responsable: marta ruiz"},
                    "_links": {"assignee": {}},
                },
            ],
            "Web": [],
        }

    def find_project(self, name):
        if "No existe" in name:
            raise ValidationFailedError(f"El proyecto «{name}» no existe.")
        return {"name": name.split("›")[-1].strip()}

    def users(self):
        return self.users_

    def create_user(self, name, email):
        if email.startswith("rota"):
            raise ValidationFailedError("Correo ya se ha tomado por otra cuenta bloqueada")
        user = {"name": name, "email": email}
        self.users_.append(user)
        self.created.append(name)
        return user

    def add_member(self, project, user):
        if (project, user) in self.members:
            raise ValidationFailedError("Usuario ya se ha tomado.")
        self.members.add((project, user))

    def work_packages(self, project, only_open=True, limit=200):
        return self.wps[project["name"]]

    def update_work_package(self, wp_id, assignee=""):
        self.assigned.append((wp_id, assignee))


def test_onboard_creates_joins_and_assigns_pending_tasks():
    op = FakeOP()
    lines = onboard(
        op,
        [
            Person("Diego Sanz", "diego.sanz@demo.invalid"),
            Person("Marta Ruiz", "marta.ruiz@demo.invalid"),
        ],
        ["Talleres › App", "Clínica › Web"],
    )
    assert op.created == ["Diego Sanz"]  # Marta ya tenía cuenta
    assert ("Talleres › App", "diego.sanz@demo.invalid") in op.members
    assert ("Clínica › Web", "diego.sanz@demo.invalid") in op.members
    # Solo las tareas a su nombre y sin asignar (con nombre sin acentos ni mayúsculas).
    assert op.assigned == [(1, "Diego Sanz"), (3, "Marta Ruiz")]
    text = "\n".join(lines)
    assert "Diego Sanz: dado de alta" in text and "Marta Ruiz: ya tenía cuenta" in text
    assert "Clínica › Web: ya era miembro" in text


def test_onboard_checks_projects_before_creating_anyone():
    op = FakeOP()
    with pytest.raises(ValidationFailedError):
        onboard(op, [Person("Diego Sanz", "diego.sanz@demo.invalid")], ["No existe › X"])
    assert op.created == []


def test_onboard_reports_a_failed_person_and_goes_on():
    op = FakeOP()
    lines = onboard(
        op,
        [Person("Rota", "rota@demo.invalid"), Person("Diego Sanz", "diego.sanz@demo.invalid")],
        ["Talleres › App"],
    )
    assert lines[0].startswith("⚠️ Rota:")
    assert op.created == ["Diego Sanz"]
