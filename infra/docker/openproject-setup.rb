# Aprovisionamiento de OpenProject para Jarvis (perfil pm). Lo ejecuta el servicio
# openproject-setup con `rails runner` después de las migraciones y el seed. Idempotente.
#
# 1. Tipo de paquete de trabajo "Riesgo" (registro de riesgos), activo en todos los
#    proyectos y con los mismos flujos de estado que "Tarea".
# 2. Usuario administrador "jarvis" (el que usa el servidor MCP jarvis-pm, así la
#    actividad aparece como "Jarvis") con la clave de API que generó init.
# 3. La primera vez, borra los proyectos de demostración que siembra OpenProject.
# 4. El administrador humano entra como miembro en los proyectos para poder asignarle
#    tareas por nombre.

api_key = File.read("/run/jarvis/openproject_api_key").strip
raise "clave de API vacía" if api_key.empty?

# Solo usuarios humanos: la tabla también guarda el usuario de sistema (admin, sin login).
admin = User.user.where(admin: true).where.not(login: "jarvis").order(:id).first

# --- 1. Tipo Riesgo ---------------------------------------------------------------------
task_type = Type.find_by(name: "Tarea") || Type.where(is_milestone: false).order(:position).first
risk = Type.find_by(name: "Riesgo")
unless risk
  risk = Type.create!(
    name: "Riesgo",
    is_default: true,
    is_milestone: false,
    is_in_roadmap: false,
    color: Color.find_by(name: "Red") || Color.first,
    position: Type.maximum(:position).to_i + 1
  )
  Workflow.copy(task_type, nil, [risk], [])
  puts "tipo creado: Riesgo"
end
Project.find_each do |project|
  project.types << risk unless project.types.include?(risk)
end

# --- 2. Usuario Jarvis y clave de API -----------------------------------------------------
jarvis = User.find_by(login: "jarvis")
unless jarvis
  jarvis = User.new(
    login: "jarvis",
    firstname: "Jarvis",
    lastname: "(asistente)",
    mail: "jarvis@jarvis.invalid",
    admin: true,
    language: "es"
  )
  # Nadie entra con esta contraseña (Jarvis usa la clave de API); cumple la política de
  # OpenProject: mayúsculas, minúsculas, cifras y símbolos.
  jarvis.password = jarvis.password_confirmation = "#{SecureRandom.hex(24)}Aa1%"
  jarvis.activate
  jarvis.save!
  puts "usuario creado: jarvis"
end

hashed = Token::API.hash_function(api_key)
unless Token::API.exists?(user: jarvis, value: hashed)
  Token::API.where(user: jarvis).destroy_all
  token = Token::API.create!(user: jarvis, token_name: "jarvis-pm (MCP)")
  token.update_column(:value, hashed)
  puts "clave de API registrada para jarvis"
end

# --- 3. Proyectos de demostración ---------------------------------------------------------
marker = Pathname("/var/openproject/assets/.jarvis-setup-done")
unless marker.exist?
  # El servicio de borrado avisa por correo al instante; aquí no hay a quién ni SMTP.
  ActionMailer::Base.perform_deliveries = false
  Project.where(identifier: %w[demo-project your-scrum-project]).find_each do |project|
    Projects::DeleteService.new(user: jarvis, model: project).call
    puts "proyecto de demostración borrado: #{project.identifier}"
  end
  ActionMailer::Base.perform_deliveries = true
  marker.write(Time.now.utc.iso8601)
end

# --- 4. Administrador humano como miembro -----------------------------------------------
if admin
  role = ProjectRole.find_by(name: "Administrador de proyecto") || ProjectRole.givable.first
  Project.find_each do |project|
    next if Member.exists?(project:, principal: admin)

    Member.create!(project:, principal: admin, roles: [role])
    puts "#{admin.login} añadido a #{project.identifier}"
  end
end

puts "OpenProject listo para Jarvis"
