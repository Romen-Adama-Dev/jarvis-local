# Editores de ArtCraft en el navegador (docs/EDITORES.md): la web estática (WebAssembly)
# de la release de GitHub de cada app, servida con nginx sin privilegios. No hay código de
# servidor: los documentos se abren y se guardan en el navegador de quien lo usa.
#
# APP es el nombre del repo de github.com/storytold (printcraft, ...), VERSION la release
# y SHA256 el de <APP>-web-<VERSION>.zip en su SHA256SUMS.txt; los fija compose.yml.
FROM nginxinc/nginx-unprivileged:1.31.6-alpine

ARG APP
ARG VERSION
ARG SHA256

USER root
# Precomprimido con gzip (el .wasm baja de ~13 MB a ~5 MB); nginx lo sirve con gzip_static.
RUN set -eu; \
    wget -qO /tmp/web.zip \
      "https://github.com/storytold/${APP}/releases/download/v${VERSION}/${APP}-web-${VERSION}.zip"; \
    echo "${SHA256}  /tmp/web.zip" | sha256sum -c -; \
    unzip -q /tmp/web.zip -d /tmp/web; \
    rm -rf /usr/share/nginx/html; \
    mv "/tmp/web/${APP}-web-${VERSION}" /usr/share/nginx/html; \
    rm -rf /tmp/web /tmp/web.zip; \
    gzip -9 -k /usr/share/nginx/html/*.wasm /usr/share/nginx/html/*.js /usr/share/nginx/html/index.html

COPY nginx.conf /etc/nginx/conf.d/default.conf
USER 101
