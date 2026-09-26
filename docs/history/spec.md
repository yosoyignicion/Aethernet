HomeNet Audit — La app Python perfecta para auditar tu WiFi doméstico
Visión
Una app de escritorio que no parece un script con botones pegados, sino un instrumento. Un panel de control tipo nave espacial retro-futurista que te dice, sin que tengas que pensar, cómo está tu red, qué ha cambiado, y qué deberías hacer. Pasiva por defecto, activa cuando tú lo pides, honesta sobre lo que puede y no puede hacer con el hardware que tienes.

Linux Mint, Python 3.11, CustomTkinter, SQLite, scapy, nmcli. Cero dependencias raras. Portable, local, sin nube, sin telemetría. Tuya.

Arquitectura mental: tres capas, cero acoplamiento
Capa Core (lógica pura, testeable sin GUI):

wifi_scan: escaneo vía nmcli + iw, parseo robusto.

lan_scan: ARP scan con scapy, resolución de vendor, hostname.

db: SQLite con histórico, snapshots, eventos.

analysis: motor de reglas — salud, evil twin, congestión, tendencias.

alerts: cola de eventos, notificaciones notify-send, filtros.

report: exportadores Markdown/PDF/JSON/CSV.

Capa Servicio (daemon opcional):

Vigilancia continua en background, escaneos programados, escribe en DB.

La GUI nunca bloquea. El daemon nunca dibuja.

Capa UI (CustomTkinter + canvas personalizado):

Dashboard en vivo, pestañas, animaciones, notificaciones in-app.

Funcionalidades detalladas
1. Dashboard principal — "El Salpicadero"
Lo primero que ves al abrir. Un panel con:

Score de salud WiFi (0–100) en un medidor radial animado, con desglose: canal, ancho de banda, seguridad, congestión, estabilidad. Cada factor con su nota y una frase corta: "Canal 6 saturado: 7 vecinos compiten contigo."

Indicador de banda actual (2.4 / 5 / 6 GHz) con la frecuencia exacta y el canal.

Contadores vivos: redes visibles, dispositivos en LAN, dispositivos no confiables, eventos sin leer.

Última amenaza detectada: la más reciente, con timestamp relativo ("hace 2 h").

Sparkline de congestión de las últimas 24 h.

Estado del adaptador: modo (managed/monitor), capacidades (bandas, inyección), driver.

2. Analizador de espectro
Gráfico de barras apiladas por canal (1–13 en 2.4 GHz; 36–165 en 5 GHz cuando puedas).

Curva de solapamiento que muestra visualmente cómo los canales 1, 6 y 11 se pisan.

Heatmap temporal: eje X = hora del día, eje Y = canal, color = congestión. Descubres patrones que no ves a simple vista.

Recomendación activa: "Cámbiate al canal 11. Está libre el 82 % del tiempo."

Radar polar (extra visual): cada red dibujada como un punto en un radar según señal y canal.

3. Inventario WiFi del entorno
Tabla enriquecida con:

SSID, BSSID, canal, banda, seguridad (WPA2/WPA3/WEP/Abierta), señal (dBm + barra), fabricante del AP (por OUI), primera/última vez vista.

Etiquetas: "Mi red", "Vecino estable", "Itinerante", "Sospechosa", "Oculta".

Filtros rápidos: solo 2.4 GHz, solo abiertas, solo nuevas hoy, solo con mi SSID.

Ordenación por cualquier columna. Búsqueda instantánea.

Panel lateral al seleccionar: histórico de señal, canales usados, cambios detectados.

4. Detección de anomalías
Motor de reglas que corre tras cada escaneo:

Evil twin / gemelo malvado: mismo SSID que tu red, distinto BSSID. Alerta roja.

SSID sospechosamente parecido al tuyo (Levenshtein): "MiWiFi_5G" vs "MiWifi_5G".

AP nuevo con señal fuerte cerca: posible dispositivo instalado recientemente.

Cambio de canal de tu router sin que tú lo hayas hecho.

Caída brusca de señal de tu AP.

Red abierta nueva en tu entorno.

WPS detectado en tu red (cuando tengas monitor mode).

Deauth flood contra tu AP (monitor mode).

Probe requests con SSIDs tuyos desde dispositivos desconocidos (monitor mode).

Cada anomalía: severidad (info / aviso / alerta / crítico), descripción clara, evidencia (datos crudos), y acción sugerida.

5. Inventario LAN (tu propia red)
ARP scan de tu subred.

MAC, IP, hostname, vendor, alias personal, confiable o no.

Detección de nuevos dispositivos con notificación.

Botón "marcar como confiable" con nombre: "TV salón", "Móvil Ana", "Impresora".

Histórico: cuándo aparece y desaparece cada dispositivo.

Vista de "dispositivos fantasmas": los que viste una vez y nunca más.

6. Vigilancia continua (daemon opcional)
Escaneos cada N minutos (configurable, 5–60).

Escribe en DB, dispara alertas.

La GUI solo lee la DB — puedes cerrarla y el daemon sigue.

Botón "pausar vigilancia" y "escanear ahora".

7. Alertas y bandeja de eventos
Bandeja cronológica con filtros por severidad.

Notificaciones de escritorio (notify-send) con icono por severidad.

Sonido opcional (campana suave, no alarma de submarine).

Modo silencioso por horas (no te despierta a las 3 AM porque un vecino encendió el microondas).

Marcar como leído / silenciar tipo de evento / silenciar BSSID concreto.

8. Informes exportables
Markdown para leer en el móvil o subir a un repo.

PDF con gráficos embebidos (reportlab + matplotlib).

JSON para análisis externo.

CSV de escaneos y dispositivos.

Plantilla de informe: "Estado de mi WiFi — [fecha]" con resumen ejecutivo, gráficos, hallazgos y recomendaciones.

9. Comparador de snapshots
Elige dos escaneos (o dos fechas) y ve el diff: redes nuevas, desaparecidas, canales cambiados, señales alteradas.

Útil cuando mueves el router, cambias de canal, o sospechas que algo ha cambiado en el edificio.

10. Módulo didáctico
Panel de ayuda con explicaciones breves: qué es un beacon, un probe request, por qué WPS es malo, qué es un evil twin, qué significa RSSI en dBm.

Glosario emergente al pasar el ratón sobre términos técnicos.

"Modo aprendizaje": tooltips extendidos y enlaces a recursos.

11. Configuración honesta
Pestaña que muestra qué puede y qué no puede hacer la app con tu hardware actual.

Diagnóstico del adaptador: bandas soportadas, modos disponibles, driver, limitaciones.

Sugerencias: "Para monitor mode necesitas un adaptador con chipset X."

12. Extras de integración
Test de velocidad puntual con speedtest-cli, correlacionado con congestión.

Importar escaneo externo (JSON de WiFi Analyzer del móvil) para cubrir 5 GHz aunque tu adaptador no lo vea.

API local (opcional, FastAPI en localhost) para que otros scripts tuyos consulten la DB.



