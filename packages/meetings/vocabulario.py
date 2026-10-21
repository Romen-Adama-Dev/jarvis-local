"""Vocabulario para que la transcripción no se equivoque con los nombres.

Whisper acierta mucho mejor un nombre propio si lo ha «oído» antes en el contexto previo
(`initial_prompt`), y lo que aun así confunda («Haringa» por Arinaga, «Yelca» por Dielca) se
arregla después. Tres fuentes, de más a menos específica:

1. **El proyecto** (`contexto_proyecto`): empresa, proyecto, personas del equipo y los
   nombres propios de sus hitos y tareas en OpenProject (sedes, sistemas, clientes).
2. **Canarias** (`TOPONIMOS_CANARIOS`, `PALABRAS_CANARIAS`): islas, municipios, polígonos y
   puertos, y el léxico canario que sale en una reunión normal (guagua, millo, cholas…).
3. **Empresa en España** (`TERMINOS_EMPRESA`): impuestos y trámites (IGIC, AIEM, DUA, ZEC…)
   y el vocabulario de dirección de proyectos que whisper escribe mal si no lo conoce.

`prompt_whisper` arma el contexto previo dentro del límite de whisper (sus últimos ~220
tokens: lo del proyecto va al final para que nunca se recorte) y `corregir_nombres`
sustituye, de forma conservadora, las palabras que se parecen mucho a un nombre del
proyecto. Lo que quede lo corrige el modelo al redactar el acta, que recibe la lista.
"""

import difflib
import re
import unicodedata
from collections.abc import Iterable
from typing import Protocol


def _lista(*trozos: str) -> tuple[str, ...]:
    """El diccionario se escribe como texto separado por comas, más fácil de ampliar."""
    return tuple(t.strip() for t in ",".join(trozos).split(",") if t.strip())


# Islas, capitales, municipios, núcleos, polígonos y puertos de Canarias.
TOPONIMOS_CANARIOS = _lista(
    # islas
    "Canarias, Gran Canaria, Tenerife, Lanzarote, Fuerteventura, La Palma, La Gomera, El Hierro, "
    "La Graciosa",
    # Gran Canaria
    "Las Palmas de Gran Canaria, Telde, Agüimes, Arinaga, Ingenio, Vecindario, "
    "Santa Lucía de Tirajana, San Bartolomé de Tirajana, Maspalomas, Mogán, Gáldar, Guía, Arucas, "
    "Teror, Firgas, Moya, Valleseco, Tejeda, Artenara, Agaete, La Aldea de San Nicolás, "
    "Valsequillo, Jinámar, Tamaraceite, Siete Palmas, El Sebadal, Las Torres, Lomo Blanco, "
    "El Goro, Salinetas, Melenara, Puerto de La Luz, Guanarteme, Escaleritas, Schamann, Vegueta, "
    "Triana",
    # Tenerife
    "Santa Cruz de Tenerife, San Cristóbal de La Laguna, La Laguna, La Orotava, Puerto de la Cruz, "
    "Los Realejos, Icod de los Vinos, Garachico, Tacoronte, Candelaria, Güímar, Arafo, Fasnia, "
    "Arico, Granadilla de Abona, San Miguel de Abona, Las Chafiras, Arona, Adeje, Guía de Isora, "
    "Santiago del Teide, Los Cristianos, Las Américas, El Médano, Tejina, Taco, Añaza, "
    "Los Majuelos",
    # Lanzarote y La Graciosa
    "Arrecife, Teguise, Tías, Yaiza, San Bartolomé, Tinajo, Haría, Playa Blanca, "
    "Puerto del Carmen, Costa Teguise, Argana, Playa Honda, Los Mármoles",
    # Fuerteventura
    "Puerto del Rosario, La Oliva, Corralejo, Antigua, Betancuria, Tuineje, Gran Tarajal, Pájara, "
    "Morro Jable, Costa Calma, El Matorral",
    # La Palma, La Gomera y El Hierro
    "Santa Cruz de La Palma, Los Llanos de Aridane, El Paso, Breña Alta, Tazacorte, "
    "San Sebastián de La Gomera, Valle Gran Rey, Hermigua, Vallehermoso, Valverde, La Frontera",
)

# Léxico canario habitual en una reunión de trabajo.
PALABRAS_CANARIAS = _lista(
    "guagua, guaguas, millo, papas, papas arrugadas, mojo, mojo picón, gofio, cholas, baifo, "
    "cambullón, chiquito, enyesque, magua, perenquén, bochinche, tenderete, timple, chinijo, "
    "naife, fisco, jeito, fleje, chacho, mi niño, alongarse, fos, ños, arretranco, machango, "
    "jilorio, cotufas, arveja, sancocho, potaje, barraquito, isa, folía, Cabildo, majorero, "
    "conejero, herreño, gomero, palmero, grancanario, tinerfeño",
)

# Empresa, impuestos y dirección de proyectos en España (y en Canarias).
TERMINOS_EMPRESA = _lista(
    "IGIC, AIEM, DUA, ZEC, RIC, Zona Especial Canaria, Reserva para Inversiones en Canarias, "
    "Gobierno de Canarias, Agencia Tributaria Canaria, IVA, IRPF, CIF, NIF, Seguridad Social, "
    "albarán, factura proforma, pedido de compra, licitación, pliego, adjudicación, ERP, SGA, CRM, "
    "TPV, acta de constitución, comité de dirección, patrocinador, interesados, entregable, "
    "cronograma, línea base, hipercuidado, análisis GAP, valor ganado, ruta crítica",
)

# Las ~220 fichas de contexto de whisper caben en unos 900 caracteres.
_PROMPT_CHARS = 900
# Lo más útil de lo fijo (islas, capitales, núcleos con polígonos e impuestos canarios), de
# más a menos importante: si no cabe todo, se cae por el final.
_TOPONIMOS_PRIORITARIOS = _lista(
    "Gran Canaria, Tenerife, Lanzarote, Fuerteventura, La Palma, La Gomera, El Hierro, "
    "Las Palmas de Gran Canaria, Santa Cruz de Tenerife, Arrecife, Puerto del Rosario, Telde, "
    "Agüimes, Arinaga, El Sebadal, Las Chafiras, San Miguel de Abona, La Laguna, Güímar, "
    "Corralejo, Teguise, IGIC, AIEM, DUA, guagua, millo, Cabildo",
)

_PALABRA = re.compile(r"[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+")
# Un nombre puede tener varias palabras: «Las Chafiras», «Puerto de La Luz», «Business Central».
_NOMBRE = re.compile(
    r"[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+(?:\s+(?:(?:de|del|la|las|los|el)\s+)?[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+)*"
)
_INICIO_FRASE = re.compile(r"(?:^|[.:;!?¿¡(«\"—–-])\s*$")
# Palabras con mayúscula que no son nombres de un proyecto (inicio de frase, cargos…).
_NO_NOMBRES = set(
    _lista(
        "hoy, estamos, gracias, primer, primero, segundo, tercer, cuarto, quinto, punto, proyecto, "
        "reunion, director, directora, responsable, consultor, tecnico, sede, sedes, isla, islas, "
        "almacen, lunes, martes, miercoles, jueves, viernes, sabado, domingo, enero, febrero, "
        "marzo, abril, mayo, junio, julio, agosto, septiembre, octubre, noviembre, diciembre",
    )
)


class _Proyectos(Protocol):
    """Lo que usa `contexto_proyecto` de OpenProjectClient."""

    def find_project(self, name: str) -> dict: ...
    def assignees(self, project_id: int) -> list[dict]: ...
    def work_packages(self, project: dict, *, only_open: bool = True) -> list[dict]: ...


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def fonetica(palabra: str) -> str:
    """Cómo suena una palabra en español de Canarias (seseo, h muda, b/v, ll/y, c/k/qu)."""
    p = re.sub(r"g(?=[ei])", "j", _sin_tildes(palabra))  # ge, gi suenan je, ji; gue, gui no
    for a, b in (
        ("ch", "1"),
        ("ll", "y"),
        ("qu", "k"),
        ("gue", "ge"),
        ("gui", "gi"),
        ("h", ""),
        ("v", "b"),
        ("ce", "se"),
        ("ci", "si"),
        ("z", "s"),
        ("c", "k"),
        ("x", "ks"),
        ("w", "u"),
    ):
        p = p.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", p).replace("1", "ch")


def _unicos(items: Iterable[str]) -> list[str]:
    vistos: set[str] = set()
    salida = []
    for item in items:
        limpio = re.sub(r"\s+", " ", item or "").strip(" ,.;")
        clave = _sin_tildes(limpio)
        if limpio and clave not in vistos:
            vistos.add(clave)
            salida.append(limpio)
    return salida


def nombres_de(textos: Iterable[str]) -> list[str]:
    """Nombres propios dentro de frases («Formación en Las Chafiras» → «Las Chafiras»). La
    mayúscula de inicio de frase no cuenta, salvo en un topónimo («Arinaga: arranque»)."""
    toponimos = {_sin_tildes(t) for t in TOPONIMOS_CANARIOS}
    nombres = []
    for texto in textos:
        texto = texto or ""
        for match in _NOMBRE.finditer(texto):
            palabras = match.group(0).split()
            al_inicio = _INICIO_FRASE.search(texto[: match.start()]) is not None
            if al_inicio and _sin_tildes(match.group(0)) not in toponimos:
                palabras = palabras[1:]
            while palabras and (palabras[0].islower() or _sin_tildes(palabras[0]) in _NO_NOMBRES):
                palabras = palabras[1:]
            if len(nombre := " ".join(palabras)) >= 4:
                nombres.append(nombre)
    return _unicos(nombres)


def contexto_proyecto(client: _Proyectos | None, company: str, project: str) -> list[str]:
    """Empresa, proyecto, equipo y nombres propios de las tareas e hitos del proyecto en
    OpenProject. Si no se puede consultar (sin OpenProject, proyecto nuevo…), lo que se sepa."""
    terminos = [company, project]
    if client is None or not project:
        return _unicos(terminos)
    try:
        proyecto = client.find_project(f"{company} › {project}" if company else project)
    except Exception:  # noqa: BLE001 - el acta sale igual sin el contexto del proyecto
        try:
            proyecto = client.find_project(project)
        except Exception:  # noqa: BLE001
            return _unicos(terminos)
    try:
        personas = [a.get("name", "") for a in client.assignees(proyecto["id"])]
    except Exception:  # noqa: BLE001
        personas = []
    try:
        asuntos = [wp.get("subject", "") for wp in client.work_packages(proyecto, only_open=False)]
    except Exception:  # noqa: BLE001
        asuntos = []
    return _unicos([*terminos, *personas, *nombres_de(asuntos)])


def prompt_whisper(contexto: Iterable[str] = (), extra: str = "", base: str = "") -> str:
    """Contexto previo para whisper: `base`, lo canario y al final lo del proyecto, que es lo
    que whisper conserva si se pasa del límite. Si no cabe todo, sobra antes lo canario (por
    el final de la lista) que la base, y la base antes que el proyecto."""
    especifico = _unicos([*contexto, *re.split(r"\s*,\s*", extra or "")])
    vistos = {_sin_tildes(t) for t in especifico}
    fijo = [t for t in _unicos(re.split(r"\s*,\s*", base or "")) if _sin_tildes(t) not in vistos]
    vistos |= {_sin_tildes(t) for t in fijo}
    canario = [t for t in _TOPONIMOS_PRIORITARIOS if _sin_tildes(t) not in vistos]
    while canario and len(", ".join([*fijo, *canario, *especifico])) > _PROMPT_CHARS:
        canario.pop()
    while fijo and len(", ".join([*fijo, *especifico])) > _PROMPT_CHARS:
        fijo.pop()
    texto = ", ".join([*fijo, *canario, *especifico])
    if len(texto) > _PROMPT_CHARS:  # ni el proyecto cabe entero: se queda con el final
        texto = texto[-_PROMPT_CHARS:].split(", ", 1)[-1]
    return texto + "."


def vocabulario_acta(contexto: Iterable[str] = (), limite: int = 100) -> list[str]:
    """Lista para el modelo que redacta el acta: lo del proyecto, lo más habitual de
    Canarias, los términos de empresa y el resto de topónimos, hasta `limite`."""
    return _unicos([*contexto, *_TOPONIMOS_PRIORITARIOS, *TERMINOS_EMPRESA, *TOPONIMOS_CANARIOS])[
        :limite
    ]


def corregir_nombres(texto: str, nombres: Iterable[str], umbral: float = 0.84) -> str:
    """Sustituye palabras que suenan casi igual que un nombre del proyecto («Haringa»,
    «Arinata» → «Arinaga»). Solo toca palabras con mayúscula que no son ya un nombre
    conocido, y solo si el parecido fonético es alto y empiezan por el mismo sonido."""
    candidatos: dict[str, str] = {}
    for nombre in nombres:
        for palabra in _PALABRA.findall(nombre or ""):
            if len(palabra) >= 5:
                candidatos.setdefault(fonetica(palabra), palabra)
    conocidos = {_sin_tildes(p) for p in candidatos.values()}
    conocidos |= {_sin_tildes(w) for t in TOPONIMOS_CANARIOS for w in _PALABRA.findall(t)}
    if not candidatos:
        return texto

    def sustituir(match: re.Match) -> str:
        palabra = match.group(0)
        clave = _sin_tildes(palabra)
        if len(palabra) < 4 or clave in conocidos or clave in _NO_NOMBRES:
            return palabra
        sonido = fonetica(palabra)
        mejor, puntos = None, 0.0
        for son, nombre in candidatos.items():
            if not son or not sonido or son[0] != sonido[0]:
                continue
            ratio = difflib.SequenceMatcher(None, sonido, son).ratio()
            if ratio > puntos:
                mejor, puntos = nombre, ratio
        return mejor if mejor and puntos >= umbral else palabra

    return _PALABRA.sub(sustituir, texto)
