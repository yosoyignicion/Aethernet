Diseño visual: "Retro-Futurista Terminal"
Filosofía
Un instrumento de precisión de los 80 soñado por alguien de 2080. Fondo oscuro profundo, acentos neón, tipografía monoespaciada para datos, sans-serif geométrica para interfaz. Nada de skeuomorfismo. Nada de degradados chillones. Minimalismo con carácter.

La referencia mental: los paneles de Alien, la estética de Blade Runner 2049, las terminales de Fallout pero sin el verde fosforescente cansino, y un toque de Cyberpunk 2077 en los acentos.

Paleta (modo oscuro por defecto)
text
Fondo base        #0A0E14    negro azulado profundo
Superficie        #11161F    paneles elevados
Superficie alta   #1A2029    hover, tarjetas
Borde sutil       #232A36
Borde activo      #2E3A4D

Texto principal   #E6EDF3    blanco roto
Texto secundario  #8B98A8    gris azulado
Texto deshabilit. #4A5568

Acento primario   #00E5A0    verde menta eléctrico (éxito, ok, datos vivos)
Acento secundario #00B8FF    cian brillante (info, enlaces, focos)
Acento aviso      #FFB800    ámbar (advertencias)
Acento alerta     #FF4D6D    coral intenso (alertas)
Acento crítico    #FF0055    magenta (crítico)

Gráficos          #00E5A0 / #00B8FF / #FFB800 / #FF4D6D (según severidad)
Rejilla gráficos  #1A2029
Paleta alternativa (modo claro, para quien lo prefiera)
text
Fondo             #F5F7FA
Superficie        #FFFFFF
Texto principal   #0A0E14
Texto secundario  #4A5568
Acento primario   #00A878    verde más profundo
Acento secundario #0088CC
Tipografía
Datos / cifras / logs: JetBrains Mono o IBM Plex Mono. Refuerza la sensación de instrumento.

Interfaz / etiquetas: Inter o IBM Plex Sans. Limpia, geométrica, legible.

Títulos: Space Grotesk o Chakra Petch para el toque retro-futurista.

Tamaños: 11/13/15/20/28. Escala 1.25. Nada de 12.5.

Layout
Ventana sin bordes nativos (custom titlebar) con botones minimalistas dibujados a mano.

Sidebar izquierda de 64 px con iconos monocromos (dashboard, espectro, redes, dispositivos, alertas, informes, ajustes). Al hover, expande a 220 px con etiquetas. Animación suave 180 ms.

Área principal con tarjetas flotantes, separadas por 16 px, radio de esquina 12 px.

Esquinas redondeadas en todo. Nada cortante.

Rejilla de 8 px para todo. Espaciado consistente.

Modo compacto opcional para pantallas pequeñas.

Animaciones y microinteracciones
Fade-in de tarjetas al cargar (200 ms, escalonado 40 ms por tarjeta).

Pulso sutil en el indicador de "escaneando": un punto verde que late cada 1.5 s.

Transición de pestañas: slide horizontal 250 ms con easing cubic-bezier(0.4, 0, 0.2, 1).

Números que cuentan al actualizarse (de 42 a 47 en 400 ms), como un odómetro digital.

Hover en tarjetas: borde se ilumina con el acento primario y aparece un halo de 1 px.

Alertas nuevas: entran deslizándose desde la derecha con un destello breve del borde.

Gráfico de canales: barras que crecen desde 0 al cargar (600 ms, easing out).

Radar polar: barrido continuo tipo radar marítimo, 4 s por vuelta, muy sutil.

Score radial: la aguja se mueve al valor con easing, y el color del arco cambia según rango.

Cursor: en botones primarios, un pequeño brillo que sigue al ratón (radial gradient).

Transición de tema claro/oscuro: crossfade de 400 ms en toda la ventana.

Log de escaneo: líneas que aparecen con efecto typewriter muy rápido (5 ms por carácter), en la fuente mono.

Notificación in-app: tarjeta que baja desde arriba, se queda 4 s, sube.

Nada de animaciones gratuitas. Cada una comunica algo: cambio de estado, dato nuevo, atención requerida.

Iconografía
Iconos monolineales, 1.5 px de grosor, esquinas redondeadas.

Librería base: Lucide o Phosphor (MIT, libres).

Iconos personalizados para conceptos propios: "espectro", "evil twin", "snapshot".

Nunca emojis en la interfaz principal. Solo en logs de desarrollo.

Detalles que marcan la diferencia
Barra de estado inferior fina (24 px) con: modo de escaneo, adaptador, última actualización, latencia de DB, versión.

Esquinas con "brackets" decorativos sutiles en las tarjetas principales, como visores de cámara retro.

Scanline muy sutil (opacidad 3 %) sobre el fondo de las tarjetas de datos, opcional en ajustes.

Cursor de texto en monoespaciada como bloque parpadeante (modo retro) o línea fina (modo moderno), configurable.

Tema "Terminal Verde" como easter egg: fosforescente sobre negro, para los nostálgicos.

Accesibilidad
Contraste mínimo AA (4.5:1) en todo texto.

No depender solo del color: cada severidad lleva icono + etiqueta textual.

Soporte de escala de UI 100 / 125 / 150 %.

Atajos de teclado: Ctrl+R escanear, Ctrl+1..7 pestañas, Ctrl+K paleta de comandos, Esc cerrar modales.

Paleta de comandos (Ctrl+K) tipo VS Code: escribe "escanear", "exportar", "canal" y ejecuta sin tocar el ratón.

Personalidad de la app
Honesta: nunca dice "estás seguro", dice "no detecto amenazas conocidas con el hardware actual".

Tranquila: no dramatiza. Un vecino nuevo no es un ataque. Distingue info de alerta.

Curiosa: te enseña. Cada dato tiene un tooltip que explica qué significa.

Local-first: sin nube, sin cuentas, sin permisos raros. La DB es tuya, en ~/.local/share/homenet-audit/.

Rápida: la GUI nunca bloquea. Los escaneos van en hilos. Todo < 100 ms de respuesta percibida.

Qué hace que sea "la perfecta"
No es la que más features tiene. Es la que abres, miras 3 segundos, y ya sabes si tu red está bien o no. Todo lo demás — espectro, alertas, informes — está al servicio de esa primera impresión. La estética retro-futurista no es decoración: es reducir la fricción cognitiva para que leer datos complejos sea placentero. Y la honestidad técnica (saber qué no puede hacer con tu adaptador actual) es lo que la separa de las apps que prometen y no cumplen.

Cuando la tengas, querrás abrirla aunque no pase nada. Eso es el éxito.


