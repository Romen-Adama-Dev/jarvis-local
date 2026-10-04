"""Altas de personas en OpenProject: su usuario, su sitio en los proyectos y sus tareas.

Jarvis no da de alta a nadie por su cuenta: `jarvis-pm__pm_add_people` pide la aprobación
al propietario con un botón de Telegram (como los correos, packages/security/
telegram_approval.py) y es la API, al pulsarlo, la que llama a `onboard`. Así una
persona puede trabajar en varios proyectos de varias empresas desde el primer día.

Las tareas que Jarvis creó antes de que la persona tuviera cuenta llevan
«Responsable: <nombre>» en la descripción; al darla de alta se le asignan.
"""

import re
from dataclasses import dataclass

from packages.core.errors import JarvisError, ValidationFailedError
from packages.openproject.client import _normalize

_EMAIL = re.compile(r"[^@\s<>(),;]+@[^@\s<>(),;]+\.[^@\s<>(),;]+")
_RESPONSIBLE = re.compile(r"Responsable:\s*(.+)")
_ALREADY_MEMBER = ("ya se ha tomado", "has already been taken", "ya es miembro")


@dataclass(frozen=True, slots=True)
class Person:
    name: str
    email: str


def _clean(text: str) -> str:
    return " ".join(text.replace("<", " ").replace(">", " ").strip(" ,;:-()").split())


def parse_people(text: str) -> list[Person]:
    """«Diego Sanz <diego@x.es>; Marta Ruiz (marta@x.es)» → personas. Una por línea o
    separadas por «;»; el correo es obligatorio (OpenProject lo usa para entrar)."""
    people = []
    for chunk in re.split(r"[;\n]+", text or ""):
        if not chunk.strip():
            continue
        found = _EMAIL.search(chunk)
        if not found:
            raise ValidationFailedError(f"Falta el correo de «{chunk.strip()}».")
        name = _clean(chunk[: found.start()] + " " + chunk[found.end() :])
        if not name:
            raise ValidationFailedError(f"Falta el nombre de «{found.group()}».")
        people.append(Person(name, found.group().lower()))
    if not people:
        raise ValidationFailedError("No hay ninguna persona (nombre y correo).")
    return people


def parse_projects(text: str) -> list[str]:
    """«Talleres Norte › App de citas; Clínica › Web» → proyectos (uno por línea o «;»)."""
    projects = [p.strip() for p in re.split(r"[;\n]+", text or "") if p.strip()]
    if not projects:
        raise ValidationFailedError("No hay ningún proyecto («Empresa › Proyecto»).")
    return projects


def _same_person(a: str, b: str) -> bool:
    return _normalize(a) == _normalize(b)


def _user_for(op, person: Person, lines: list[str]) -> dict:
    for user in op.users():
        if str(user.get("email", "")).lower() == person.email or _same_person(
            user.get("name", ""), person.name
        ):
            lines.append(f"👤 {person.name}: ya tenía cuenta")
            return user
    user = op.create_user(person.name, person.email)
    lines.append(f"👤 {person.name}: dado de alta ({person.email})")
    return user


def _join(op, project: str, person: Person, lines: list[str]) -> None:
    try:
        op.add_member(project, person.email)
    except ValidationFailedError as exc:
        if not any(mark in exc.message.lower() for mark in _ALREADY_MEMBER):
            raise
        lines.append(f"   · {project}: ya era miembro")
        return
    lines.append(f"   · {project}: miembro")


def _assign_pending(op, project: dict, person: Person, lines: list[str]) -> None:
    """Asigna las tareas abiertas que lo nombran como responsable y no tienen asignado."""
    for wp in op.work_packages(project, only_open=True, limit=200):
        if (wp["_links"].get("assignee") or {}).get("href"):
            continue
        named = _RESPONSIBLE.search(((wp.get("description") or {}).get("raw")) or "")
        if named and _same_person(named.group(1).strip(), person.name):
            op.update_work_package(wp["id"], assignee=person.name)
            lines.append(f"   · asignada #{wp['id']} {wp['subject']}")


def onboard(op, people: list[Person], projects: list[str]) -> list[str]:
    """Da de alta a cada persona (si no tiene cuenta), la hace miembro de cada proyecto y
    le asigna sus tareas pendientes. Devuelve una línea por paso, para el chat."""
    found = {name: op.find_project(name) for name in projects}  # falla antes de crear nada
    lines: list[str] = []
    for person in people:
        try:
            _user_for(op, person, lines)
            for name, project in found.items():
                _join(op, name, person, lines)
                _assign_pending(op, project, person, lines)
        except JarvisError as exc:
            lines.append(f"⚠️ {person.name}: {exc.message}")
    return lines
