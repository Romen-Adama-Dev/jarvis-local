import importlib.util
from pathlib import Path

import pytest

from packages.core.errors import ValidationFailedError

_SERVER = Path(__file__).resolve().parents[2] / "integrations/openclaw/skills/jarvis-pm/server.py"

MEMORY = """# MEMORY.md

## Metodologías

### Scrum
- Sprints de tres semanas.

## Proyectos

"""


@pytest.fixture
def pm(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("jarvis_pm_server_setup", _SERVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "MEMORY.md").write_text(MEMORY, encoding="utf-8")
    monkeypatch.setattr(module, "JARVIS_WORKSPACE_DIR", tmp_path)
    fake = FakeOP()
    monkeypatch.setattr(module, "_op", lambda: fake)
    setattr(module, "fake", fake)  # noqa: B010 (pyright no admite atributos nuevos en un módulo)
    # describe_work_package espera el formato de la API; aquí basta el título.
    monkeypatch.setattr(module, "describe_work_package", lambda wp: f"#{wp['id']} {wp['subject']}")
    return module


class FakeOP:
    def __init__(self):
        self.projects = {"Talleres Norte": {"id": 1, "name": "Talleres Norte"}}
        self.created, self.members, self.wps = [], [], []
        self.people = {"Diego Sanz", "Lucía Martín"}
        self.relations = []
        self.options = []

    def find_project(self, name):
        key = name.split("›")[-1].strip()
        if key not in self.projects:
            raise ValidationFailedError(f"El proyecto «{name}» no existe.")
        return self.projects[key]

    def create_project(self, name, parent="", description=""):
        self.created.append((name, parent))
        self.projects[name] = {"id": len(self.projects) + 1, "name": name}
        return self.projects[name]

    def project_url(self, project, view=""):
        return f"https://op/{project['name']}"

    def set_project_option(self, project, field, value):
        self.options.append((project["name"], field, value))
        return True

    def work_packages(self, project, only_open=True, limit=200):
        return [w for w in self.wps if w["project"] == project["name"]]

    def create_work_package(self, project, subject, type_name="Tarea", description="", **kw):
        wp = {
            "id": 100 + len(self.wps),
            "subject": subject,
            "project": project["name"],
            "type": type_name,
            "description": description,
            "_links": {"type": {"title": type_name}},
            **kw,
        }
        self.wps.append(wp)
        return wp

    def add_member(self, project, user):
        if user not in self.people:
            raise ValidationFailedError(f"El usuario «{user}» no existe. Opciones: x.")
        self.members.append((project, user))

    def assignees(self, project_id):
        return [{"name": n} for n in self.people]

    def work_package_url(self, wp):
        return f"https://op/wp/{wp['id']}"

    def create_relation(self, before, after, kind="precedes", description=""):
        self.relations.append((before, after, description))

    def work_package(self, wp_id):
        return {"subject": f"Paquete {wp_id}", "_links": {"project": {"title": "Web"}}}


def test_pm_setup_builds_company_project_methodology_milestone_and_team(pm):
    reply = pm.pm_setup(
        "Clínica Dental Sonrisas",
        "Web de la clínica",
        methodology="Kanban",
        final_milestone="Integración de la reserva",
        final_milestone_date="2026-12-21",
        team="Diego Sanz, Marta Ruiz",
    )
    assert pm.fake.created == [
        ("Clínica Dental Sonrisas", ""),
        ("Web de la clínica", "Clínica Dental Sonrisas"),
    ]
    memory = (pm.JARVIS_WORKSPACE_DIR / "MEMORY.md").read_text(encoding="utf-8")
    assert "- Clínica Dental Sonrisas › Web de la clínica: Kanban" in memory
    assert pm.fake.options == [("Web de la clínica", "Metodología", "Kanban")]
    # Kanban no tenía zona en MEMORY.md: se crea con su plantilla base.
    assert "### Kanban\n- **Trabajo:** Tarjetas de flujo continuo" in memory
    assert "aún no tiene reglas" not in reply and "Reglas de Kanban guardadas" in reply
    assert pm.fake.wps[0]["type"] == "Hito" and pm.fake.wps[0]["due_date"] == "2026-12-21"
    assert pm.fake.members == [("Clínica Dental Sonrisas › Web de la clínica", "Diego Sanz")]
    assert "Sin cuenta en OpenProject: Marta Ruiz" in reply and "pm_add_people" in reply


def test_pm_setup_does_not_repeat_what_exists(pm):
    pm.pm_setup(
        "Talleres Norte",
        "App de citas",
        methodology="Scrum",
        final_milestone="Salida a producción",
        final_milestone_date="2026-12-15",
    )
    reply = pm.pm_setup(
        "Talleres Norte",
        "App de citas",
        methodology="Scrum",
        final_milestone="Salida a producción",
        final_milestone_date="2026-12-15",
    )
    assert pm.fake.created == [("App de citas", "Talleres Norte")]
    assert "Empresa «Talleres Norte»: ya existía" in reply and "ya existía" in reply.splitlines()[1]
    assert len(pm.fake.wps) == 1
    assert "aún no tiene reglas" not in reply


def test_task_for_someone_without_account_stays_in_their_name(pm):
    reply = pm.pm_create_task(
        "Talleres Norte", "Diseños", assignee="Pablo Vidal", due_date="2026-10-12"
    )
    wp = pm.fake.wps[0]
    assert wp["assignee"] == "" and wp["description"].endswith("Responsable: Pablo Vidal")
    assert "se le asigna al darle de alta" in reply
    pm.pm_create_task("Talleres Norte", "Backend", assignee="diego sanz")
    assert pm.fake.wps[1]["assignee"] == "diego sanz"


def test_pm_add_people_asks_for_approval_through_the_api(pm, monkeypatch):
    sent = {}

    class FakeResponse:
        status_code = 202

        def json(self):
            return {"summary": "x", "expires_at": 1}

    class FakeApi:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, path, json):
            sent.update(path=path, json=json)
            return FakeResponse()

    monkeypatch.setenv("JARVIS_OWNER_TELEGRAM_ID", "123")
    monkeypatch.setattr(pm, "_jarvis_api", FakeApi)
    reply = pm.pm_add_people(
        "Diego Sanz <diego.sanz@demo.invalid>; Marta Ruiz <marta.ruiz@demo.invalid>",
        "Talleres Norte › App de citas; Clínica Dental Sonrisas › Web de la clínica",
    )
    assert sent["path"] == "/v1/pm/people/draft"
    assert sent["json"]["telegram_user_id"] == 123
    assert [p["email"] for p in sent["json"]["people"]] == [
        "diego.sanz@demo.invalid",
        "marta.ruiz@demo.invalid",
    ]
    assert len(sent["json"]["projects"]) == 2
    assert "Pedida la aprobación en Telegram" in reply
    assert pm.pm_add_people("Diego Sanz", "X › Y").startswith("No se pudo: Falta el correo")


def test_new_methodology_gets_its_rules_in_the_same_call(pm):
    reply = pm.pm_setup(
        "Clínica",
        "Web",
        methodology="Kanban",
        methodology_rules="- Tablero: Nuevo → En curso → Cerrado\n- Límite WIP: 2 por persona",
    )
    memory = (pm.JARVIS_WORKSPACE_DIR / "MEMORY.md").read_text(encoding="utf-8")
    assert (
        "### Kanban\n- Tablero: Nuevo → En curso → Cerrado\n- Límite WIP: 2 por persona" in memory
    )
    assert "aún no tiene reglas" not in reply and "Reglas de Kanban guardadas" in reply
    # Un método que ya existe no se toca aunque lleguen reglas.
    pm.pm_setup("Talleres Norte", "App", methodology="Scrum", methodology_rules="- Otra cosa")
    assert "- Otra cosa" not in (pm.JARVIS_WORKSPACE_DIR / "MEMORY.md").read_text(encoding="utf-8")


def test_task_after_another_creates_the_dependency(pm):
    reply = pm.pm_create_task("Talleres Norte", "Integrar la reserva", after=168)
    assert pm.fake.relations == [(168, pm.fake.wps[0]["id"], "")]
    assert "Empieza después de #168" in reply


def test_link_tasks_between_projects(pm):
    reply = pm.pm_link_tasks(168, 190, note="La web usa la reserva de la app")
    assert pm.fake.relations == [(168, 190, "La web usa la reserva de la app")]
    assert "#168 Paquete 168 → #190 Paquete 190 (Web)" in reply


def test_assignee_ignores_accents(pm):
    pm.pm_create_task("Talleres Norte", "Diseños", assignee="Lucia Martin")
    assert pm.fake.wps[0]["assignee"] == "Lucia Martin"  # existe como «Lucía Martín»


def test_method_without_template_or_rules_asks_for_them(pm):
    reply = pm.pm_setup("Talleres Norte", "Taller", methodology="Lean Startup")
    assert "«Lean Startup» aún no tiene reglas" in reply


def test_task_after_a_project_depends_on_its_final_milestone(pm):
    pm.fake.projects["App de citas"] = {"id": 7, "name": "App de citas"}
    for wp_id, date in ((168, "2026-12-15"), (150, "2026-11-01")):
        pm.fake.wps.append(
            {
                "id": wp_id,
                "project": "App de citas",
                "date": date,
                "_links": {"type": {"title": "Hito"}},
            }
        )
    reply = pm.pm_create_task(
        "Talleres Norte", "Integrar la reserva", after="Talleres Norte › App de citas"
    )
    assert pm.fake.relations[-1][0] == 168 and "Empieza después de #168" in reply
    pm.pm_create_task("Talleres Norte", "Otra", after="#150")
    assert pm.fake.relations[-1][0] == 150
    assert pm.pm_create_task("Talleres Norte", "Sin hito", after="Talleres Norte").startswith(
        "No se pudo"
    )
