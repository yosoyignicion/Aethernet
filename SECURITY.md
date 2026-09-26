# Política de seguridad

Aethernet es una herramienta **local** de auditoría WiFi. No envía datos a
Internet, no tiene backend remoto y no recopila telemetría. Aun así, usamos el
canal privado de GitHub para cualquier fallo con impacto de seguridad.

## Cómo reportar

1. Abre un **aviso privado** en la pestaña *Security → Report a vulnerability*
   del repositorio (GitHub Security Advisories).
2. Si no puedes, abre un issue **sin detalles explotables** pidiendo contacto.

Incluye: versión/commit, sistema operativo, pasos de reproducción, impacto y, si
la tienes, una propuesta de mitigación. Evita adjuntar MACs, SSID, handshakes o
cualquier material sensible real; usa datos redactados o sintéticos.

## Alcance

En alcance:

- Ejecución de comandos o rutas derivadas de datos de red no confiables
  (SSID, BSSID, hostnames, respuestas de `iw`/`nmcli`/`ethtool`).
- Escritura/lectura de ficheros fuera de los directorios XDG previstos.
- Fuga de secretos (token de API, secreto de sesión) o de material capturado.
- La API local: bypass del token en endpoints que mutan estado o activan hardware.
- Comportamiento del monitor que pueda afectar a la interfaz gestionada del usuario.

Fuera de alcance:

- Requerir `root`/`CAP_NET_ADMIN` para monitor mode o ARP scan: es por diseño.
- Resultados "incompletos" cuando el hardware no soporta una medición: se muestra
  `n/d` de forma honesta.
- Ataques que exijan control físico del equipo o de la red del usuario.

## Principios que protegemos

- **Pasivo por defecto.** El monitor crea una interfaz *virtual* y nunca cambia el
  tipo de la interfaz gestionada; jamás inyecta tráfico salvo petición explícita.
- **Sin red saliente.** La UI sirve fuentes e iconos localmente (`/ae-fonts`).
- **Sin secretos en el código.** El token de API y el secreto de sesión se generan
  por instalación; el token se persiste con permisos `0600`.

Gracias por ayudar a mantenerlo seguro.
