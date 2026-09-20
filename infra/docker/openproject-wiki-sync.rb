# Una sola memoria para Obsidian, Jarvis y OpenProject (docs/OBSIDIAN.md, "Una sola
# memoria"). Lo ejecuta el servicio openproject-wiki-sync con `rails runner`, en bucle.
#
# El vault de Obsidian es la memoria; OpenProject la muestra y aporta la suya:
#
# * Vault → OpenProject: la nota de cada empresa y proyecto del vault (la red que genera
#   packages/knowledge/red.py más lo que escribas en ella en Obsidian) se publica como la
#   página "Memoria de Jarvis" de la wiki del proyecto. Se edita en Obsidian.
# * OpenProject → vault: el resto de páginas de la wiki de cada proyecto se copian al
#   vault (sources/openproject/<proyecto>/wiki/), enlazadas a la nota del proyecto, para
#   que Obsidian las muestre y Jarvis las encuentre en su memoria.
#
# Solo escribe lo que cambia (sin versiones vacías en el historial de la wiki).

require "fileutils"

$stdout.sync = true

VAULT = Pathname(ENV.fetch("JARVIS_VAULT_DIR", "/vault"))
INTERVAL = Integer(ENV.fetch("WIKI_SYNC_INTERVAL", "600"))
MIRROR_TITLE = ENV.fetch("WIKI_MIRROR_TITLE", "Memoria de Jarvis")
START = "<!-- jarvis:red:start -->"
FINISH = "<!-- jarvis:red:end -->"

# Igual que note_name() en packages/knowledge/red.py: nombre de la nota en el vault.
def note_name(text, limit = 80)
  name = text.gsub(/[\\\/:*?"<>|#^\[\]]+/, " ").gsub(/\s+/, " ").strip.gsub(/\A[ .]+|[ .]+\z/, "")
  name = name[0, limit].sub(/[ .]+\z/, "")
  name.empty? ? "sin título" : name
end

# Markdown de Obsidian → Markdown de OpenProject: sin frontmatter ni marcas, y los
# [[enlaces|alias]] como texto.
def to_openproject(markdown, source)
  body = markdown.sub(/\A---\n.*?\n---\n/m, "")
  body = body.gsub(START, "").gsub(FINISH, "").gsub(/<!--.*?-->/m, "")
  body = body.gsub(/\[\[([^\]|]+)\|([^\]]+)\]\]/, '\2').gsub(/\[\[([^\]]+)\]\]/, '\1')
  "> Página generada desde la memoria de Jarvis (Obsidian, `#{source}`). " \
    "Edítala en Obsidian: los cambios hechos aquí se sobrescriben.\n\n#{body.strip}\n"
end

# La nota de una empresa es entities/empresas/<Empresa>.md y la de un proyecto cuelga de
# ella: entities/empresas/<Empresa>/<Proyecto>.md (el árbol de packages/knowledge/red.py).
def vault_note(project)
  base = VAULT.join("entities", "empresas")
  company = project.parent&.name
  path =
    if project.parent_id
      company ? base.join(note_name(company), "#{note_name(project.name)}.md") : nil
    else
      base.join("#{note_name(project.name)}.md")
    end
  return path if path&.file?

  # Estructura plana anterior, mientras la red no haya hecho una pasada y movido la nota.
  legacy = VAULT.join("entities", project.parent_id ? "proyectos" : "empresas",
                      "#{note_name(project.name)}.md")
  legacy.file? ? legacy : nil
end

def ensure_wiki(project)
  unless project.module_enabled?(:wiki)
    project.enabled_module_names = project.enabled_module_names | ["wiki"]
    project.save!(validate: false)
    project.reload
  end
  project.wiki || Wiki.create!(project:, start_page: MIRROR_TITLE)
end

def publish(project, jarvis)
  note = vault_note(project)
  return unless note

  wiki = ensure_wiki(project)
  text = to_openproject(note.read, note.relative_path_from(VAULT).to_s)
  page = wiki.find_page(MIRROR_TITLE)
  if page.nil?
    result = WikiPages::CreateService.new(user: jarvis).call(wiki:, title: MIRROR_TITLE, text:)
    raise result.errors.full_messages.join(", ") unless result.success?

    puts "wiki: creada #{project.identifier}/#{MIRROR_TITLE}"
  elsif page.text.to_s.strip != text.strip
    result = WikiPages::UpdateService.new(user: jarvis, model: page)
      .call(text:, journal_notes: "Sincronizado desde Obsidian")
    raise result.errors.full_messages.join(", ") unless result.success?

    puts "wiki: actualizada #{project.identifier}/#{MIRROR_TITLE}"
  end
end

def export(project)
  folder = VAULT.join("sources", "openproject", project.identifier, "wiki")
  pages = project.wiki ? project.wiki.pages.reject { |p| p.title == MIRROR_TITLE } : []
  wanted = {}
  pages.each do |page|
    content = <<~MD
      ---
      title: #{page.title.to_json}
      project: #{project.name.to_json}
      updatedAt: #{page.updated_at.utc.iso8601.to_json}
      ---

      <!-- openclaw:wiki:raw-source -->

      # #{page.title}

      Página de la wiki de OpenProject del proyecto [[#{note_name(project.name)}]]. Se edita en
      OpenProject; aquí es una copia.

      #{page.text}
    MD
    target = folder.join("#{note_name(page.title)}.md")
    wanted[target.to_s] = true
    next if target.file? && target.read == content

    FileUtils.mkdir_p(folder)
    target.write(content)
    puts "vault: #{target.relative_path_from(VAULT)}"
  end
  # Páginas borradas en OpenProject: fuera también del vault (la carpeta es solo suya).
  Dir.glob(folder.join("*.md").to_s).each do |file|
    next if wanted[file]

    File.delete(file)
    puts "vault: borrada #{Pathname(file).relative_path_from(VAULT)}"
  end
end

jarvis = User.find_by!(login: "jarvis")
puts "wiki-sync: vault #{VAULT}, cada #{INTERVAL} s"
agenda = ENV.fetch("OPENPROJECT_CALENDAR_PROJECT", "Agenda")
loop do
  if VAULT.directory?
    User.execute_as(jarvis) do
      Project.active.where.not(name: agenda).find_each do |project|
        publish(project, jarvis)
        export(project)
      rescue StandardError => e
        warn "wiki: #{project.identifier}: #{e.class}: #{e.message}"
      end
    end
  else
    warn "wiki: no existe el vault #{VAULT}"
  end
  break if INTERVAL.zero?

  sleep INTERVAL
end
