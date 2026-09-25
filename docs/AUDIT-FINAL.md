# Auditoría final — Aethernet 1.1.0

> Estado del proyecto tras la iteración de "utilidades accionables". Fecha: 2026-09-26.
> Verificación: todo lo citado sale de comandos ejecutados, no de suposiciones.

## 0. Resumen

Aethernet pasa de **diagnosticar** a **decidir**: canal recomendado en vivo,
previsión por hora/día, gestor de canal con veredicto de mejora, separación
tu-red/vecinos, vigilancias y mejor identificación de dispositivos. Se mantiene
la filosofía: local, pasivo, honesto con el hardware y **sin tocar tu router**.

## 1. Gates verificados

| Gate | Resultado | Comando |
| --- | --- | --- |
| Lint | limpio | `ruff check src tests` |
| Tipos | 0 errores (66 archivos) | `mypy --strict src/aethernet` |
| Código muerto | 0 | `vulture src/aethernet --min-confidence 80` |
| Tests | **139 passed** | `pytest` |
| UI | 7/7 rutas HTTP 200, 0 trazas | `scripts/smoke.sh` |
| CI local | OK | `scripts/ci.sh` |

## 2. Métricas objetivas

| Métrica | Valor |
| --- | --- |
| Versión | 1.1.0 |
| Paquete | `aethernet` (scripts `aethernet`, `aethernet-ui`) |
| Migraciones DB | v1 inicial · v2 evidencia+monitor · v3 previsión · v4 watchlist |
| TODOs/FIXME | 0 |
| `subprocess(shell=True)` | 0 |
| `print()` fuera del CLI | 0 |
| Dependencias obligatorias | 0 (solo stdlib) |

## 3. Cobertura funcional

| Área | Estado |
| --- | --- |
| Dashboard (salud, contadores, congestión, tarjeta de canal) | ✅ |
| Espectro (barras, tu-red-vs-vecinos, heatmap, radar, asesor, previsión, gestor) | ✅ |
| Redes (tabla, filtros, inspector, grupo SSID, vigilar) | ✅ |
| Dispositivos (inventario, confianza/alias, identificación por tipo) | ✅ |
| Alertas (timeline, evidencia, monitor, aviso de canal) | ✅ |
| Informes (wifi md/json/csv/pdf + informe de canal md) | ✅ |
| Ajustes (hardware, muestreo, monitor, triggers, previsión, persistencia) | ✅ |
| Daemon + API local | ✅ |
| Monitor pasivo no disruptivo | ✅ implementado (validación en hardware pendiente) |
| Comparador de escaneos (UI) | ⏳ solo CLI (`compare`) |

## 4. Límites conocidos (honestos)

- **Monitor mode no validado en hardware** en este equipo: falta `iw`, `scapy`
  (instalable) y root. Los decoders/pipeline se prueban con tramas sintéticas.
  Checklist de validación en `docs/ROADMAP.md`.
- **No cambia el router**: un cliente WiFi no puede fijar el canal del AP; la app
  recomienda y tú aplicas. Es una decisión de diseño, no una carencia.
- **Solo 2.4 GHz** con el adaptador actual (MT7601U).
- **`.deb`** aplazado (requiere `debhelper`); `packaging/` listo.
- **CI en GitHub** pendiente (tras feedback).
- Comparador de escaneos solo por CLI.

## 5. Riesgos

| Riesgo | Severidad | Mitigación |
| --- | --- | --- |
| Previsión poco fiable con pocos datos | media | `MIN_SAMPLES` y cobertura visible; mensajes honestos |
| Avisos de canal ruidosos | baja | umbral `channel_watch_min_improvement` + dedup por fingerprint |
| Dependencia de `nmcli`/`iw` según sistema | media | `doctor` reporta capacidades; degradación graciosa |
| Monitor tumba el WiFi | mitigado | **vif no disruptiva**; nunca `set type monitor` en la gestionada |

## 6. Decisiones clave

1. **Previsión sobre histórico**, no sobre un escaneo suelto → evita cambios que
   desestabilicen la red.
2. **No-acción sobre el router** → el usuario mantiene el control.
3. **NiceGUI** por fidelidad al mockup de Stitch.
4. **Dependencias opcionales** con degradación honesta.
5. **Aislamiento de pruebas**: decoders por tramas sintéticas, UI por HTTP.

## 7. Recomendaciones

**Ahora**
- Configurar `my_ssids`, `my_bssids` y `my_channel` para que el asesor y las
  reglas apunten a tu red.
- Dejar `aethernet daemon start` corriendo 1-2 semanas para poblar la previsión.

**Después**
- Validar monitor en hardware compatible (checklist).
- Comparador de escaneos en UI.
- CI en GitHub Actions.

**Algún día**
- `.deb` + AppImage; auditoría de contraste AA; mypy en tests.

## 8. Próxima iteración (criterio de "hecho")

- [ ] **Monitor validado**: `doctor` "disponible" y `monitor start` captura sin cortar el WiFi.
- [ ] **Comparador UI**: dos escaneos lado a lado con `diff_scans` visible.
- [ ] **CI GitHub**: workflow con `ci.sh` verde en push/PR.
- [ ] **Empaquetado**: `.deb` instalable que arranca `aethernet-ui`.
- [ ] **Previsión útil**: ≥2 semanas de datos y precisión verificada por hora.

## 9. Anexos (comandos)

```bash
./scripts/ci.sh
./scripts/smoke.sh
aethernet forecast show
aethernet report --kind channel
aethernet watch add <BSSID> --note "mi red"
aethernet doctor
```
