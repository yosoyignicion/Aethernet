#!/usr/bin/env bash
# Construye el paquete .deb de Aethernet.
# Requiere: debhelper (dh), dh-python, pybuild-plugin-pyproject, dpkg-dev.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

missing=()
for tool in dpkg-buildpackage dh; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done

if [ "${#missing[@]}" -gt 0 ]; then
  cat >&2 <<EOF
Faltan herramientas para construir el .deb: ${missing[*]}

Instálalas con:
  sudo apt install debhelper dh-python pybuild-plugin-pyproject dpkg-dev fakeroot

Mientras tanto, puedes ejecutar Aethernet desde el código:
  pip install -e '.[ui,monitor]'
  aethernet-ui
EOF
  exit 1
fi

# Enlaza la carpeta de empaquetado Debian en la raíz del proyecto.
if [ ! -e debian ]; then
  ln -s packaging/debian debian
  trap 'rm -f debian' EXIT
fi

dpkg-buildpackage -us -uc -b
echo "Paquete generado en el directorio padre: ../aethernet_*.deb"
