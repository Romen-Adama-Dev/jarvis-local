# Servicio admin (perfil admin, docs/ADMIN.md): cliente de Docker + compose, git y Python
# del sistema para server.py. El código se lee del repo montado en /repo.
FROM docker:29-cli
RUN apk add --no-cache python3 git
ENTRYPOINT ["python3", "/repo/infra/docker/admin/server.py"]
