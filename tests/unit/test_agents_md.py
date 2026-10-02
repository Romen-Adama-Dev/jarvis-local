from pathlib import Path

WORKSPACE = Path(__file__).parents[2] / "integrations/openclaw/workspace"
# OpenClaw recorta los archivos de arranque del workspace a 20.000 caracteres (contados
# como en JavaScript) y avisa en el registro: "AGENTS.md is … chars (limit 20000);
# truncating". Lo que queda fuera, Jarvis no lo lee. Además migra TOOLS.md al final de
# AGENTS.md ("## Tools / ### Local notes (migrated from TOOLS.md)").
OPENCLAW_BOOTSTRAP_LIMIT = 20_000
MIGRATION_HEADER = "\n\n## Tools\n\n### Local notes (migrated from TOOLS.md)\n\n"
# Valores largos para los marcadores, para no quedarse justo con los de este servidor.
LONG_OWNER = "Nombre Apellido1 X"  # 18 caracteres
LONG_HARDWARE = "Intel(R) Xeon(R) Gold 6338 CPU @ 2.00GHz, 128 GB de RAM, NVIDIA L40S"


def _js_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def test_agents_md_fits_in_openclaw_bootstrap_context():
    agents = (WORKSPACE / "AGENTS.md").read_text(encoding="utf-8")
    tools = (WORKSPACE / "TOOLS.md").read_text(encoding="utf-8")
    rendered = agents.replace("__OWNER__", LONG_OWNER) + MIGRATION_HEADER
    rendered += tools.replace("__SERVER_HW__", LONG_HARDWARE)
    length = _js_length(rendered)
    assert length <= OPENCLAW_BOOTSTRAP_LIMIT, (
        f"AGENTS.md quedaría en {length} caracteres en el workspace: OpenClaw corta a "
        f"partir de {OPENCLAW_BOOTSTRAP_LIMIT}. Resume algo antes de añadir."
    )
