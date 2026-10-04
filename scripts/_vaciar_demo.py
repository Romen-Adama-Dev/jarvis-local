"""Vacía lo que crean la demo y sus ensayos (docs/demo/GUION.md), y nada más.

Lo lanza scripts/vaciar-demo con uno o varios guiones (docs/demo/guion-*.json); cada uno
dice en «vaciar» qué crea:

* empresas: se borran de OpenProject con todos sus proyectos, paquetes y reuniones (sin
  mandar correos), sus documentos del RAG, sus proyectos de MEMORY.md y su carpeta del
  vault (entities/Empresas/<empresa>);
* correos: personas de prueba que se borran de OpenProject;
* metodologias: zonas de MEMORY.md (y su nota de Conocimiento) que crea el guion;
* contactos: notas de persona que crea (entities/Contactos/👤 <nombre>.md).

Además quita los nexos (entities/Nexos), que la red vuelve a calcular. El resto del
servidor no se toca. Antes de borrar enseña lo que va a hacer y pide confirmación.
"""

import argparse
import json
from pathlib import Path

from _benchmark_demo import compose, python_in, rails

ROOT = Path(__file__).resolve().parents[1]

RESET_MEMORY = """
import json, sys
from pathlib import Path
from packages.core.directives import parse_directives, write_directive
from packages.core.scope import slugify
scope = json.loads(sys.argv[1])
memory = Path("/state/workspace-jarvis/MEMORY.md")
companies = {slugify(c) for c in scope["empresas"]}
labels = parse_directives(memory.read_text(encoding="utf-8")).labels
for (company, _), label in labels.items():
    if company in companies:
        write_directive(memory, "proyecto", label, "", replace_all=True)
        print(f"MEMORY.md: fuera {label}")
for method in scope["metodologias"]:
    write_directive(memory, "metodologia", method, "", replace_all=True)
    print(f"MEMORY.md: fuera la zona {method}")
"""

RESET_RAG = """
import asyncio, json, sys, httpx
async def main(companies):
    token = open("/run/jarvis/jarvis_api_internal_token").read().strip()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", headers=headers) as api:
        for doc in (await api.get("/v1/documents")).json()["documents"]:
            if (doc.get("doc_metadata") or {}).get("company") in companies:
                await api.delete(f"/v1/documents/{doc['id']}")
                print(f"RAG: fuera {doc['filename']}")
asyncio.run(main(json.loads(sys.argv[1])))
"""


def scope_of(paths: list[str]) -> dict[str, list[str]]:
    scope: dict[str, list[str]] = {
        "empresas": [],
        "correos": [],
        "metodologias": [],
        "contactos": [],
    }
    for path in paths:
        for key, values in (
            json.loads((ROOT / path).read_text(encoding="utf-8")).get("vaciar", {}).items()
        ):
            if key in scope:
                scope[key] += [v for v in values if v not in scope[key]]
    return scope


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("guiones", nargs="+", help="docs/demo/guion-voz.json …")
    parser.add_argument("--si", action="store_true", help="no pedir confirmación")
    args = parser.parse_args()
    scope = scope_of(args.guiones)
    print("Se va a borrar:")
    for key, values in scope.items():
        print(f"  {key}: {', '.join(values) or '—'}")
    if not args.si and input("¿Seguro? Escribe «sí»: ").strip().lower() not in {"sí", "si"}:
        raise SystemExit("Nada borrado.")
    rails(f"""
admin = User.user.where(admin: true).where.not(login: "jarvis").order(:id).first
User.current = admin
Project.where(name: {json.dumps(scope["empresas"])}, parent_id: nil).each do |project|
  Projects::DeleteService.new(user: admin, model: project).call
  puts "OpenProject: fuera #{{project.name}}"
end
User.where(mail: {json.dumps(scope["correos"])}).each do |user|
  Principals::DeleteJob.perform_now(user)
  puts "OpenProject: fuera #{{user.name}}"
end
""")
    print(python_in("knowledge", RESET_MEMORY, json.dumps(scope)), end="")
    print(python_in("api", RESET_RAG, json.dumps(scope["empresas"])), end="")
    paths = [f'"entities/Empresas/{c}"' for c in scope["empresas"]]
    paths += [f'"concepts/Conocimiento/Metodologías/{m}"' for m in scope["metodologias"]]
    paths += [f'"entities/Contactos/👤 {c}.md"' for c in scope["contactos"]]
    compose(
        "exec",
        "-T",
        "knowledge",
        "sh",
        "-c",
        f"cd /state/wiki/main && rm -rf {' '.join(paths)} entities/Nexos",
    )
    print("Vault: fuera " + ", ".join(p.strip('"') for p in paths) + " y entities/Nexos")
    print("Hecho. La red de Obsidian se rehace sola en unos minutos.")


if __name__ == "__main__":
    main()
