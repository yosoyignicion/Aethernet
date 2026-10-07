# Guía de uso de Aethernet

Aethernet audita tu WiFi **desde tu propio equipo**: mide señal, solapamiento de
canales, dispositivos de tu red y, si lo pides, captura tramas de gestión. No
necesita cuenta, no manda nada a Internet y no toca tu router.

Tres ideas que conviene tener presentes:

1. **Pasivo por defecto.** Escuchar no interfiere. Las funciones activas solo
   corren si las pides expresamente.
2. **Nunca corta tu WiFi.** El monitor crea una interfaz *virtual*; jamás cambia
   el tipo de tu interfaz gestionada.
3. **Honesto con el hardware.** Si algo no se puede medir, verás `n/d`, no un
   número inventado.

---

## 1. Requisitos

| Elemento | Necesario | Para qué |
| --- | --- | --- |
| Linux + NetworkManager | Sí | `nmcli` obtiene el escaneo WiFi |
| Python 3.11+ | Sí | ejecutar Aethernet |
| `iw` | Recomendado | bandas, diagnóstico y monitor mode |
| `ethtool` | Recomendado | datos del adaptador |
| `notify-send` | Opcional | avisos de escritorio |
| `scapy` + `root` | Opcional | inventario LAN activo y captura de tramas |
| `fastapi` + `uvicorn` | Opcional | API local para tus scripts |

Comprueba qué tienes con:

```bash
aethernet doctor
```

`doctor` te dice, sin adornos, qué puede y qué no puede hacer tu equipo.

---

## 2. Instalación

### Desde el código (recomendado en desarrollo)

```bash
git clone <URL-del-repo>
cd aethernet
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[ui]'          # interfaz gráfica + núcleo
```

Extras disponibles (se pueden combinar):

```bash
pip install -e '.[lan,reports,api,speedtest,ui]'
# lan        escaneo ARP con scapy
# reports    exportación PDF
# api        API local FastAPI
# speedtest  prueba de velocidad
# ui         interfaz AETHERNET (NiceGUI)
# all        todo lo anterior
```

---

## 3. Primeros pasos (CLI)

```bash
aethernet doctor                 # ¿qué soporta mi hardware?
aethernet scan --no-lan          # primer escaneo pasivo
aethernet status                 # salud, contadores y última amenaza
aethernet analyze                # motor de reglas sobre el último escaneo
```

Define **tu red** para que Aethernet distinga lo tuyo del entorno y detecte
posibles *evil twin*:

```bash
aethernet config set my_ssids MiRed
aethernet config set my_channel 6
```

Explora:

```bash
aethernet networks --open        # inventario de redes, solo abiertas
aethernet networks                # inventario completo con filtros
aethernet compare                # qué cambió entre los dos últimos escaneos
aethernet report --format md     # informe Markdown
aethernet events --unread        # bandeja de eventos sin leer
```

Todos los comandos aceptan `--json` para encadenarlos con otras herramientas.

Vigilancia continua (segundo plano):

```bash
aethernet daemon start
aethernet daemon status
aethernet daemon stop
```

---

## 4. La interfaz gráfica (AETHERNET)

```bash
aethernet-ui                     # ventana nativa si hay pywebview; si no, navegador
# o, explícitamente en el navegador:
python -m aethernet.ui --web --port 8080
```

### Atajos de teclado

| Atajo | Acción |
| --- | --- |
| `1` … `7` | saltar al módulo correspondiente |
| `R` | forzar un ciclo de escaneo |
| `/` o `Ctrl+K` | ir a Redes y buscar |
| `Ctrl+E` | exportar informe Markdown |
| `C` | copiar tu canal actual al portapapeles |

### Pantallas

- **Dashboard (`/`)** — salud de la red (gauge), contadores, semáforo del canal y
  histórico de congestión de 24 h.
- **Espectro (`/espectro`)** — reparto de potencia por canal, tu red frente a los
  vecinos, asesor de canal, co-interferencia y radar.
- **Redes (`/redes`)** — inventario BSSID con búsqueda, filtros e inspector
  (histórico RSSI, seguridad, fabricante, vigilar cambios).
- **Dispositivos (`/dispositivos`)** — nodos de tu LAN, confianza y alias.
- **Alertas (`/alertas`)** — línea temporal de incidentes y monitor pasivo.
- **Informes (`/informes`)** — vista previa del informe y exportación
  Markdown/PDF/JSON/CSV.
- **Ajustes (`/ajustes`)** — interfaz de captura, monitor, retención de datos,
  atajos y diagnóstico del sistema.

Las métricas que no se pueden medir aparecen como `n/d`.

---

## 5. Monitor pasivo (opcional, avanzado)

Captura tramas de gestión (deauth, *probes*, *beacons*, EAPOL) **sin inyectar
tráfico**. Aethernet crea una interfaz virtual de monitor (`iw phy … interface add
… type monitor`); si el driver no lo permite, se desactiva con un mensaje claro
en lugar de cortar tu conexión.

```bash
aethernet monitor status         # ¿puedo? y si no, ¿por qué?
aethernet monitor start
aethernet monitor events
```

Requiere adaptador con *monitor mode*, `iw`, `scapy` y privilegios
(`root` / `CAP_NET_ADMIN`). Consulta `aethernet doctor` para el veredicto.

> **Nota honesta:** la captura real depende del adaptador. Tarjetas con chipsets
> Atheros AR9271, RTL8812AU/8821AU o MediaTek MT7612U suelen funcionar bien.

---

## 6. API local (opcional)

Pensada para tus scripts, ligada a `127.0.0.1`:

```bash
aethernet api --print-token      # muestra el token de la API
aethernet api                    # API en http://127.0.0.1:8765
```

- Los `GET` de solo lectura están abiertos en local.
- Los `POST` (`/scan`, `/monitor/start`, `/monitor/stop`, `/events/{id}/read`)
  exigen la cabecera `X-Aethernet-Token` con el token anterior.
- El token se guarda por instalación en el directorio de datos con permisos
  `0600` (o define `AETHERNET_API_TOKEN`). Nunca se escribe en el código.
- Si escuchas fuera de *loopback*, Aethernet te avisa: el token es tu única defensa.

---

## 7. Copia y restauración (backup offline)

Un informe **exporta** datos; una copia de seguridad debe poder **recuperar** el
estado en otra máquina, sin la instalación original. Aethernet empaqueta todo en
un único `.tar.gz`:

- `aethernet.db` — la base, con una copia **consistente** (aunque el daemon escriba).
- `config.toml` — tus ajustes: redes propias, alias, retención…
- `manifest.json` — versión de formato, de la app y del esquema, más el hash
  SHA-256 de la base para detectar corrupción.

**Sin secretos:** el token de la API no viaja (se regenera) y el secreto de sesión
de la UI no es necesario. No hay claves que guardar aparte.

```bash
aethernet backup                         # crea aethernet-backup-FECHA.tar.gz
aethernet backup --output ~/mi-copia.tar.gz
aethernet backup --include-reports       # añade también los informes exportados

aethernet restore copia.tar.gz           # restaura (valida y resguarda la actual)
aethernet restore --verify copia.tar.gz  # solo valida la copia, sin escribir
```

Notas:

- `restore` **valida antes de escribir**, rechaza copias de un esquema más nuevo,
  resguarda tu base actual como `aethernet.db.bak-…` y aplica migraciones si la
  copia es más antigua.
- Si el **daemon** está activo, deténlo (o usa `--force`).
- En la interfaz, *Ajustes* permite crear la copia, ver su antigüedad y restaurar
  con un diálogo de confirmación.
- **Máquina limpia**: instala Aethernet, lanza `aethernet restore copia.tar.gz` y
  recuperarás tu histórico e informes como si nada hubiera pasado.

---

## 8. Privacidad y datos

- **Sin red saliente.** La interfaz sirve fuentes e iconos localmente.
- Nada se sube a la nube. No hay telemetría.

Dónde vive todo (rutas XDG):

| Qué | Ruta |
| --- | --- |
| Configuración | `~/.config/aethernet/config.toml` |
| Datos y base SQLite | `~/.local/share/aethernet/aethernet.db` |
| Informes | `~/.local/share/aethernet/reports/` |
| Caché OUI | `~/.cache/aethernet/oui.tsv` |

**Borrar el histórico**: en *Ajustes* puedes purgar registros antiguos o fijar la
retención automática (días; `0` la desactiva). Para borrarlo todo, elimina el
directorio de datos.

---

## 9. Resolución de problemas

**`No module named aethernet`**
Instala el paquete (`pip install -e '.[ui]'`) o ejecuta con `PYTHONPATH=src`.

**La UI no arranca / puerto ocupado**
Prueba otro puerto: `python -m aethernet.ui --web --port 8081`.

**"Falta `iw` para crear la interfaz de monitor"**
Instala `iw` (`sudo apt install iw`). Sin `iw` la app sigue funcionando, pero sin
monitor mode.

**No veo redes / el escaneo sale vacío**
Comprueba `nmcli device wifi list`. En algunos equipos hace falta que el servicio
NetworkManager esté activo.

**El ARP scan no encuentra dispositivos**
Necesita `root` y `scapy`. Ejecuta `sudo .venv/bin/aethernet scan --active --lan`.

**Iconos como texto (`data_object`)**
Ese nombre no existe en Material Symbols y se pinta el texto; usa `data_array`.
Es cosmético.

---

## 10. Glosario rápido

- **dBm** — potencia de señal. Cerca de 0 es mejor; `-30` excelente, `-90` pésimo.
- **SSID / BSSID** — nombre de la red / dirección MAC del punto de acceso.
- **Canal** — en 2.4 GHz solo 1, 6 y 11 no se solapan. Menos vecinos, mejor.
- **WPS** — botón de emparejamiento; cómodo pero históricamente débil.
- **Evil twin** — un AP que imita tu SSID para engañarte.
- **Deauth** — trama que expulsa clientes; puede ser ataque o interferencia.

---

## 11. Aviso legal

Aethernet está pensado para **auditar tu propia red**. Auditar redes ajenas sin
autorización puede ser ilegal en tu jurisdicción. El modo activo (inyección,
captura) solo debe usarse en equipos y redes que controles o tengas permiso
explícito para probar.
