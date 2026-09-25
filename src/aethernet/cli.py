"""Interfaz de línea de comandos: toda la potencia del backend sin GUI.

La GUI futura consume exactamente los mismos servicios que este CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import APP_TITLE, __version__
from .capabilities import detect
from .config import bootstrap_paths, load_settings, save_settings
from .core.adapter import hardware_suggestions, honest_limits, probe_adapter
from .core.analysis import AnalysisContext, run_rules
from .core.didactic import all_topics, glossary_term
from .core.forecast import WEEKDAYS, coverage, predict_channel, weekly_grid
from .core.health import score_health
from .core.oui import OuiDatabase
from .core.snapshot import diff_scans, wifi_snapshot
from .core.spectrum import spectrum_snapshot
from .data.db import Database
from .data.repository import Repository
from .integration.importer import import_and_save
from .integration.speedtest import correlate_with_congestion, run_speedtest
from .logging_setup import get_logger, setup_logging
from .models import Finding, Severity
from .report import build_report_data, export, export_channel_markdown, output_path
from .service.control import ControlChannel
from .service.daemon import MonitorService, daemon_is_running, run_daemon
from .utils import humanize_age

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Contexto
# --------------------------------------------------------------------------- #
class Context:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        paths = bootstrap_paths()
        self.paths = paths
        setup_logging(paths.log_path, console=not getattr(args, "json", False))
        self.db = Database(paths.db_path)
        self.db.migrate()
        self.repo = Repository(self.db)
        self.settings = load_settings(paths)
        self.service = MonitorService(self.repo, self.settings, paths)

    def close(self) -> None:
        self.db.close()


def _emit_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


# --------------------------------------------------------------------------- #
# Comandos
# --------------------------------------------------------------------------- #
def cmd_scan(ctx: Context) -> int:
    args = ctx.args
    result = ctx.service.scan_once(
        active=args.active,
        include_lan=ctx.settings.lan_scan_enabled if args.lan is None else args.lan,
    )
    if args.json:
        _emit_json(result.to_dict())
        return 0
    if result.error:
        print(f"Error en el escaneo: {result.error}")
        return 1
    print(f"{APP_TITLE} · escaneo {time.strftime('%H:%M:%S')}")
    if result.scan:
        print(f"  Redes visibles : {result.scan.count}")
        print(f"  Interfaz       : {result.scan.interface or '-'}")
    if result.lan_scan:
        print(f"  Dispositivos   : {result.lan_scan.count} ({result.lan_scan.source})")
    if result.health:
        print(f"  Salud          : {result.health.total}/100 ({result.health.grade})")
        print(f"  {result.health.headline}")
    _print_findings(result.findings)
    return 0


def cmd_status(ctx: Context) -> int:
    scan = ctx.repo.latest_wifi_scan()
    counts = ctx.repo.counts()
    history = {ap.bssid: [s for _, s in ctx.repo.signal_series(ap.bssid, 24)] for ap in (scan.aps if scan else [])}
    health = (
        score_health(
            scan,
            my_ssids=tuple(ctx.settings.my_ssids),
            my_bssids=tuple(ctx.settings.my_bssids),
            signal_history=history,
        )
        if scan
        else None
    )
    events = ctx.repo.list_events(limit=1, min_severity=Severity.WARNING)
    payload = {
        "counts": counts,
        "health": health.to_dict() if health else None,
        "last_scan_age": humanize_age(time.time() - scan.timestamp) if scan else None,
        "last_threat": events[0].to_dict() if events else None,
        "daemon": ctx.repo.kv_get("daemon_status", {}),
    }
    if ctx.args.json:
        _emit_json(payload)
        return 0
    print(f"{APP_TITLE} · estado")
    print(
        f"  Redes {counts['visible_networks']} · LAN {counts['lan_devices']} "
        f"· no confiables {counts['untrusted_devices']} · eventos sin leer {counts['unread_events']}"
    )
    if health:
        print(f"  Salud: {health.total}/100 ({health.grade}) — {health.headline}")
    if scan:
        print(f"  Último escaneo: {humanize_age(time.time() - scan.timestamp)}")
    if events:
        print(f"  Última amenaza: [{events[0].severity.value}] {events[0].title}")
    return 0


def cmd_networks(ctx: Context) -> int:
    args = ctx.args
    scan = ctx.repo.latest_wifi_scan()
    if scan is None:
        print("No hay escaneos. Ejecuta 'aethernet scan'.")
        return 1
    aps = list(scan.aps)
    if args.band:
        aps = [ap for ap in aps if args.band in ap.band.value]
    if args.open:
        aps = [ap for ap in aps if ap.is_open]
    if args.ssid:
        aps = [ap for ap in aps if args.ssid.lower() in ap.ssid.lower()]
    if args.new:
        known = ctx.repo.all_bssids()
        aps = [ap for ap in aps if ap.bssid not in known]
    aps.sort(key=lambda a: a.signal_dbm, reverse=True)
    if args.json:
        _emit_json([ap.to_dict() for ap in aps])
        return 0
    if not aps:
        print("Ninguna red coincide con el filtro.")
        return 0
    print(f"{'SSID':<28} {'BSSID':<18} {'CH':>3} {'BANDA':<8} {'SEG':<10} {'dBm':>5}")
    for ap in aps:
        print(
            f"{ap.display_ssid[:28]:<28} {ap.bssid:<18} {ap.channel:>3} "
            f"{ap.band.value:<8} {ap.security:<10} {ap.signal_dbm:>5}"
        )
    return 0


def cmd_devices(ctx: Context) -> int:
    args = ctx.args
    if args.trust:
        ctx.repo.set_device_trusted(args.trust.upper(), True, args.alias)
        print(f"Dispositivo {args.trust} marcado como confiable" + (f" ({args.alias})" if args.alias else ""))
        return 0
    if args.untrust:
        ctx.repo.set_device_trusted(args.untrust.upper(), False, args.alias)
        print(f"Dispositivo {args.untrust} ya no es confiable")
        return 0
    devices = ctx.repo.ghost_devices() if args.ghosts else ctx.repo.devices(online_only=args.online)
    if args.json:
        _emit_json([d.to_dict() for d in devices])
        return 0
    if not devices:
        print("Sin dispositivos en la base de datos.")
        return 0
    print(f"{'NOMBRE':<22} {'IP':<15} {'MAC':<18} {'CONF':<5} {'VENDOR':<20}")
    for device in devices:
        print(
            f"{device.display_name[:22]:<22} {device.ip:<15} {device.mac:<18} "
            f"{'sí' if device.trusted else 'no':<5} {(device.vendor or '-')[:20]:<20}"
        )
    return 0


def cmd_analyze(ctx: Context) -> int:
    scan = ctx.repo.latest_wifi_scan()
    if scan is None:
        print("No hay escaneos. Ejecuta 'aethernet scan'.")
        return 1
    previous = None
    scans = ctx.repo.recent_scans(2)
    if len(scans) > 1:
        previous = ctx.repo.get_wifi_scan(scans[1]["id"])
    history = {ap.bssid: [s for _, s in ctx.repo.signal_series(ap.bssid, 24)] for ap in scan.aps}
    context = AnalysisContext(
        scan=scan,
        previous=previous,
        lan_scan=ctx.repo.latest_lan_scan(),
        my_ssids=tuple(ctx.settings.my_ssids),
        my_bssids=tuple(ctx.settings.my_bssids),
        known_bssids=ctx.repo.all_bssids(),
        known_lan_macs={d.mac for d in ctx.repo.devices()},
        trusted_macs=set(ctx.settings.trusted_macs) | set(ctx.repo.trusted_macs()),
        signal_history=history,
        watchlist=ctx.repo.watch_map(),
        disabled_rules=set(ctx.settings.muted_rules),
    )
    findings = run_rules(context)
    if ctx.args.json:
        _emit_json([f.to_dict() for f in findings])
        return 0
    _print_findings(findings)
    return 0


def cmd_events(ctx: Context) -> int:
    args = ctx.args
    if args.action == "read":
        updated = ctx.repo.mark_event_read(all_events=args.all)
        print(f"{updated} evento(s) marcados como leídos")
        return 0
    if args.action == "mute" and args.fingerprint:
        ctx.repo.mute_fingerprint(args.fingerprint, True)
        print("Fingerprint enmudecido")
        return 0
    severity = Severity(args.severity) if args.severity else None
    events = ctx.repo.list_events(limit=args.limit, min_severity=severity, unread_only=args.unread)
    if args.json:
        _emit_json([e.to_dict() for e in events])
        return 0
    if not events:
        print("Bandeja vacía.")
        return 0
    for event in events:
        flag = " " if event.read else "●"
        count = f" ×{event.dedup_count}" if event.dedup_count > 1 else ""
        print(f"{flag} [{event.severity.value:8}] {humanize_age(time.time() - event.created_at):>12} {event.title}{count}")
    return 0


def cmd_report(ctx: Context) -> int:
    args = ctx.args
    if args.kind == "channel":
        destination = Path(args.output) if args.output else output_path(
            ctx.paths.report_dir, "aethernet-canal", "md"
        )
        path = export_channel_markdown(ctx.repo, ctx.settings, destination)
        if args.json:
            _emit_json({"file": str(path)})
        else:
            print(f"Informe de canal escrito: {path}")
        return 0
    data = build_report_data(ctx.repo, ctx.settings, event_limit=args.limit)
    fmt = args.format
    if args.output:
        destination = Path(args.output)
    else:
        extension = {"markdown": "md", "md": "md", "json": "json", "csv": "csv", "pdf": "pdf"}[fmt]
        destination = output_path(ctx.paths.report_dir, "aethernet-report", extension)
    try:
        paths = export(data, fmt, destination)
    except Exception as exc:
        print(f"No se pudo generar el informe: {exc}")
        return 1
    if args.json:
        _emit_json({"files": [str(p) for p in paths]})
        return 0
    for path in paths:
        print(f"Informe escrito: {path}")
    return 0


def cmd_compare(ctx: Context) -> int:
    args = ctx.args
    scans = ctx.repo.recent_scans(args.limit)
    if len(scans) < 2:
        print("Hacen falta al menos dos escaneos para comparar.")
        return 1
    new_id = args.to or scans[0]["id"]
    old_id = args.frm or scans[1]["id"]
    old_scan = ctx.repo.get_wifi_scan(old_id)
    new_scan = ctx.repo.get_wifi_scan(new_id)
    if old_scan is None or new_scan is None:
        print("No se encontraron los escaneos indicados.")
        return 1
    diff = diff_scans(old_scan, new_scan, old_label=old_id, new_label=new_id)
    if args.json:
        _emit_json(diff.to_dict())
        return 0
    print(diff.render())
    return 0


def cmd_snapshot(ctx: Context) -> int:
    scan = ctx.repo.latest_wifi_scan()
    if scan is None:
        print("No hay escaneo que guardar como snapshot.")
        return 1
    snapshot_id = ctx.repo.save_snapshot(wifi_snapshot(scan, label=ctx.args.label or ""))
    print(f"Snapshot #{snapshot_id} guardado.")
    return 0


def cmd_daemon(ctx: Context) -> int:
    args = ctx.args
    action = args.action
    if action == "run":
        return run_daemon(ctx.repo, ctx.settings, ctx.paths)
    channel = ControlChannel(ctx.paths.control_file)
    if action == "start":
        pid = daemon_is_running(ctx.paths)
        if pid:
            print(f"El daemon ya está en ejecución (PID {pid}).")
            return 0
        if not args.foreground:
            import subprocess

            log_file = open(ctx.paths.log_path, "a", encoding="utf-8")  # noqa: SIM115
            subprocess.Popen(
                [sys.executable, "-m", "aethernet", "daemon", "run"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            time.sleep(1.0)
            pid = daemon_is_running(ctx.paths)
            print(f"Daemon lanzado (PID {pid})" if pid else "Daemon lanzado; revisa el log si no aparece.")
            return 0
        return run_daemon(ctx.repo, ctx.settings, ctx.paths)
    if action == "stop":
        channel.send("stop")
        pid = daemon_is_running(ctx.paths)
        if pid:
            import contextlib
            import os

            with contextlib.suppress(OSError):
                os.kill(pid, 15)
        print("Orden de parada enviada.")
        return 0
    if action == "pause":
        channel.send("pause")
        print("Vigilancia pausada.")
        return 0
    if action == "resume":
        channel.send("resume")
        print("Vigilancia reanudada.")
        return 0
    if action == "scan":
        channel.send("scan")
        print("Escaneo inmediato solicitado.")
        return 0
    if action == "status":
        status = ctx.repo.kv_get("daemon_status", {})
        pid = daemon_is_running(ctx.paths)
        payload = {"pid": pid, **status}
        if args.json:
            _emit_json(payload)
            return 0
        print(f"Daemon: {'en ejecución' if pid else 'detenido'} (PID {pid or '-'})")
        if status:
            print(
                f"  paused={status.get('paused')} scans={status.get('scan_count')} "
                f"último={status.get('last_scan')} salud={status.get('last_health')}"
            )
        return 0
    return 1


def cmd_monitor(ctx: Context) -> int:
    args = ctx.args
    action = args.action
    if action == "start":
        ctx.settings.monitor_enabled = True
        save_settings(ctx.settings, ctx.paths)
        status = ctx.service.start_monitor()
        if args.json:
            _emit_json(status)
            return 0 if status.get("running") else 1
        if status.get("running"):
            print(f"Monitor pasivo activo en {status['interface']} · canales {status['channels']}")
        else:
            print(f"Monitor no disponible: {status.get('error') or status.get('reason')}")
        return 0
    if action == "stop":
        ctx.settings.monitor_enabled = False
        save_settings(ctx.settings, ctx.paths)
        status = ctx.service.stop_monitor()
        if args.json:
            _emit_json(status)
        else:
            print("Monitor pasivo detenido.")
        return 0
    if action == "status":
        status = ctx.service.monitor_status()
        if args.json:
            _emit_json(status)
            return 0
        print(f"Monitor: {'ACTIVO' if status['running'] else 'detenido'} · capaz={status['capable']}")
        print(f"  Interfaz: {status['interface'] or '-'} · base {status['base_interface'] or '-'} · CH actual {status['current_channel']}")
        print(f"  Paquetes: {status['packet_count']} · eventos: {status['event_count']} · sesión {status['session_id']}")
        if not status["capable"]:
            print(f"  Motivo: {status['reason']}")
        return 0
    if action == "events":
        rows = ctx.repo.list_monitor_events(limit=args.limit, kind=args.kind)
        if args.json:
            _emit_json(rows)
            return 0
        if not rows:
            print("Sin eventos de monitor.")
            return 0
        for row in rows:
            stamp = time.strftime("%H:%M:%S", time.localtime(row["ts"]))
            print(
                f"  {stamp} [{row['kind']:6}] {row['ssid'] or row['bssid'] or row['source_mac']} "
                f"×{row['count']} ch{row['channel']}"
            )
        return 0
    return 1


def cmd_watch(ctx: Context) -> int:
    args = ctx.args
    action = args.action
    if action == "list":
        rows = ctx.repo.list_watch()
        if args.json:
            _emit_json(rows)
            return 0
        if not rows:
            print("Lista de vigilancia vacía.")
            return 0
        for row in rows:
            print(
                f"  {row['bssid']}  {row.get('ssid') or '-'}  "
                f"CH{row.get('expected_channel') or '?'}  {row.get('expected_security') or '?'}  "
                f"{row.get('note') or ''}"
            )
        return 0
    if action == "add":
        if not args.bssid:
            print("Uso: aethernet watch add <BSSID> [--ssid S] [--note N]")
            return 1
        bssid = args.bssid.upper()
        scan = ctx.repo.latest_wifi_scan()
        ap = next((a for a in scan.aps if a.bssid == bssid), None) if scan else None
        ctx.repo.add_watch(
            bssid,
            ssid=args.ssid or (ap.ssid if ap else ""),
            note=args.note or "",
            expected_channel=ap.channel if ap else None,
            expected_security=ap.security if ap else None,
        )
        print(f"Vigilando {bssid}" + (f" (CH{ap.channel}, {ap.security})" if ap else ""))
        return 0
    if action == "remove":
        if not args.bssid:
            print("Uso: aethernet watch remove <BSSID>")
            return 1
        removed = ctx.repo.remove_watch(args.bssid)
        print("Eliminado de vigilancia." if removed else "No estaba en la lista.")
        return 0
    return 1


def cmd_forecast(ctx: Context) -> int:
    args = ctx.args
    band = args.band
    if args.action == "record":
        rec = ctx.service.record_advisory()
        if rec is None:
            print("Sin datos de espectro todavía; no se registró nada.")
            return 1
        if args.json:
            _emit_json(rec)
        else:
            print(f"Registrado: canal {rec['channel']} ({rec['availability']}% disponibilidad).")
        return 0

    buckets = ctx.repo.channel_advisory_buckets(band)
    now = time.localtime()
    hour, weekday = now.tm_hour, now.tm_wday

    if args.action == "show":
        prediction = predict_channel(buckets, weekday, hour)
        payload = {
            "band": band,
            "weekday": weekday,
            "hour": hour,
            "coverage": coverage(buckets),
            "prediction": prediction.to_dict() if prediction else None,
        }
        if args.json:
            _emit_json(payload)
            return 0
        cov = payload["coverage"]
        print(f"Previsión de canal · {band} · {WEEKDAYS[weekday]} {hour:02d}:00")
        print(f"  Cobertura: {cov['slots']}/{cov['slots_total']} franjas · {cov['observations']} observaciones")
        if prediction is None:
            print("  Aún sin datos suficientes para esta hora. Sigue usando Aethernet (o el daemon).")
            return 1
        print(f"  Canal predicho: {prediction.channel} (confianza {prediction.confidence:.0%}, "
              f"{prediction.samples} muestras, {prediction.avg_availability}% disponible)")
        print(f"  {prediction.reason}")
        return 0

    if args.action == "week":
        grid = weekly_grid(buckets, weekday)
        if args.json:
            _emit_json(grid)
            return 0
        print(f"Previsión por hora · {grid['label']} · {band}")
        marks = {1: "1", 6: "6", 11: "B", 0: "·"}
        line = "".join(marks.get(h["channel"], "?") for h in grid["hours"])
        print("  Hora  00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23")
        print("  Canal " + "  ".join(marks.get(h["channel"], "?") for h in grid["hours"]))
        print("  (1/6/11 = canal recomendado · · = sin datos)")
        _ = line
        return 0
    return 1


def cmd_doctor(ctx: Context) -> int:
    report = detect(ctx.settings.interface)
    adapter = probe_adapter(ctx.settings.interface or "")
    monitor_status = ctx.service.monitor_status()
    payload = {
        "capabilities": report.to_dict(),
        "adapter": adapter.to_dict(),
        "limits": honest_limits(adapter),
        "suggestions": hardware_suggestions(adapter),
        "monitor": monitor_status,
    }
    if ctx.args.json:
        _emit_json(payload)
        return 0
    print(f"{APP_TITLE} · diagnóstico")
    print(f"  Python {report.python} · root={report.is_root}")
    print(f"  Interfaces WiFi: {', '.join(report.wifi_interfaces) or 'ninguna'}")
    for tool in report.tools:
        mark = "✓" if tool.available else "✗"
        print(f"  {mark} {tool.name:<22} {tool.detail}")
    print(f"  Adaptador: {adapter.interface or '-'} · modo {adapter.mode} · driver {adapter.driver or '-'}")
    print(f"  Bandas: {', '.join(b.value for b in adapter.bands) or 'desconocidas'}")
    print(f"  Monitor: {'sí' if adapter.supports_monitor else 'no'} · Inyección: {'sí' if adapter.supports_injection else 'no'}")
    if honest_limits(adapter):
        print("  Límites:")
        for limit in honest_limits(adapter):
            print(f"    - {limit}")
    if hardware_suggestions(adapter):
        print("  Sugerencias:")
        for suggestion in hardware_suggestions(adapter):
            print(f"    - {suggestion}")
    if monitor_status["capable"]:
        print("  Monitor pasivo: disponible (no disruptivo, crea interfaz virtual).")
    else:
        print(f"  Monitor pasivo: no disponible — {monitor_status['reason']}")
    return 0


def cmd_config(ctx: Context) -> int:
    args = ctx.args
    if args.action == "path":
        print(ctx.paths.config_file)
        return 0
    if args.action == "show":
        if args.json:
            _emit_json(ctx.settings.to_dict())
            return 0
        for key, setting_value in ctx.settings.to_dict().items():
            print(f"{key} = {setting_value}")
        return 0
    if args.action == "set":
        if not args.key or args.value is None:
            print("Uso: config set <clave> <valor>")
            return 1
        current = ctx.settings.to_dict().get(args.key, None)
        value: Any = args.value
        if isinstance(current, bool):
            value = args.value.lower() in {"1", "true", "yes", "si", "sí", "on"}
        elif isinstance(current, int):
            try:
                value = int(args.value)
            except ValueError:
                print("Se esperaba un número entero.")
                return 1
        elif isinstance(current, list):
            value = [item.strip() for item in args.value.split(",") if item.strip()]
        setattr(ctx.settings, args.key, value)
        save_settings(ctx.settings, ctx.paths)
        print(f"{args.key} = {value}")
        return 0
    return 1


def cmd_import(ctx: Context) -> int:
    count = import_and_save(ctx.repo, ctx.args.path, set(ctx.settings.my_bssids))
    if ctx.args.json:
        _emit_json({"imported": count})
    else:
        print(f"Importadas {count} redes desde {ctx.args.path}")
    return 0


def cmd_speedtest(ctx: Context) -> int:
    result = run_speedtest()
    scan = ctx.repo.latest_wifi_scan()
    congestion = 0.0
    if scan:
        recommendation = spectrum_snapshot(scan)["recommendation"]
        congestion = min(1.0, recommendation.get("interference", 0.0) / 4.0)
    payload = correlate_with_congestion(result, congestion)
    if ctx.args.json:
        _emit_json(payload)
        return 0 if result.ok else 1
    if not result.ok:
        print(f"Test de velocidad no disponible: {result.error}")
        return 1
    print(f"Descarga: {payload['download_mbps']} Mbit/s · Subida: {payload['upload_mbps']} Mbit/s · Ping: {payload['ping_ms']} ms")
    print(payload["interpretation"])
    return 0


def cmd_oui(ctx: Context) -> int:
    db = OuiDatabase(ctx.paths)
    db.load()
    if ctx.args.refresh:
        added = db.refresh_from_ieee()
        print(f"Base OUI actualizada: +{added} entradas (total {db.size})")
    else:
        print(f"Base OUI: {db.size} entradas (caché: {ctx.paths.oui_cache})")
    return 0


def cmd_db(ctx: Context) -> int:
    if ctx.args.action == "purge":
        removed = ctx.repo.purge_old(ctx.args.days)
        if ctx.args.json:
            _emit_json(removed)
        else:
            print("Registros antiguos eliminados: " + ", ".join(f"{k}={v}" for k, v in removed.items()))
        return 0
    if ctx.args.action == "info":
        payload = {
            "path": str(ctx.paths.db_path),
            "size_bytes": ctx.paths.db_path.stat().st_size if ctx.paths.db_path.exists() else 0,
            "counts": ctx.repo.counts(),
        }
        _emit_json(payload) if ctx.args.json else print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    return 1


def cmd_tutorial(ctx: Context) -> int:
    if ctx.args.term:
        found = glossary_term(ctx.args.term)
        print(found or "Término no encontrado.")
        return 0
    for topic in all_topics():
        print(f"• {topic.title}: {topic.summary}")
    return 0


def cmd_glossary(_: Context) -> int:
    for topic in all_topics():
        print(f"{topic.key}\t{topic.summary}")
    return 0


def cmd_version(ctx: Context) -> int:
    if ctx.args.json:
        _emit_json({"version": __version__})
    else:
        print(f"{APP_TITLE} {__version__}")
    return 0


# --------------------------------------------------------------------------- #
# Presentación
# --------------------------------------------------------------------------- #
def _print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("  Sin hallazgos: no detecto amenazas conocidas con el hardware actual.")
        return
    print(f"  Hallazgos ({len(findings)}):")
    for finding in findings:
        print(f"    [{finding.severity.value:8}] {finding.title}")
        if finding.suggestion:
            print(f"        → {finding.suggestion}")


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aethernet", description=f"{APP_TITLE} — audita tu WiFi doméstico")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    def add_json(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="salida en JSON")

    p_scan = sub.add_parser("scan", help="realiza un escaneo WiFi (y LAN) ahora")
    p_scan.add_argument("--active", action="store_true", help="forzar barrido de radio (modo activo)")
    p_scan.add_argument("--lan", dest="lan", action="store_true", default=None)
    p_scan.add_argument("--no-lan", dest="lan", action="store_false")
    add_json(p_scan)
    p_scan.set_defaults(func=cmd_scan)

    p_status = sub.add_parser("status", help="resumen del estado actual")
    add_json(p_status)
    p_status.set_defaults(func=cmd_status)

    p_net = sub.add_parser("networks", help="lista las redes del último escaneo")
    p_net.add_argument("--band", help="filtra por banda (p. ej. '5')")
    p_net.add_argument("--open", action="store_true", help="solo redes abiertas")
    p_net.add_argument("--ssid", help="filtra por texto de SSID")
    p_net.add_argument("--new", action="store_true", help="solo redes no vistas antes")
    add_json(p_net)
    p_net.set_defaults(func=cmd_networks)

    p_dev = sub.add_parser("devices", help="inventario LAN")
    p_dev.add_argument("--online", action="store_true", help="solo dispositivos online")
    p_dev.add_argument("--ghosts", action="store_true", help="dispositivos vistos una sola vez")
    p_dev.add_argument("--trust", metavar="MAC", help="marcar MAC como confiable")
    p_dev.add_argument("--untrust", metavar="MAC", help="quitar confianza")
    p_dev.add_argument("--alias", help="alias para el dispositivo")
    add_json(p_dev)
    p_dev.set_defaults(func=cmd_devices)

    p_an = sub.add_parser("analyze", help="ejecuta el motor de reglas sobre el último escaneo")
    add_json(p_an)
    p_an.set_defaults(func=cmd_analyze)

    p_ev = sub.add_parser("events", help="bandeja de eventos")
    p_ev.add_argument("action", nargs="?", default="list", choices=["list", "read", "mute"])
    p_ev.add_argument("--limit", type=int, default=50)
    p_ev.add_argument("--severity", help="severidad mínima (info|warning|alert|critical)")
    p_ev.add_argument("--unread", action="store_true", help="solo sin leer")
    p_ev.add_argument("--all", action="store_true", help="marcar todos como leídos")
    p_ev.add_argument("--fingerprint", help="fingerprint a enmudecer")
    add_json(p_ev)
    p_ev.set_defaults(func=cmd_events)

    p_rep = sub.add_parser("report", help="genera un informe exportable")
    p_rep.add_argument("--format", choices=["md", "markdown", "json", "csv", "pdf"], default="md")
    p_rep.add_argument("--kind", choices=["wifi", "channel"], default="wifi", help="tipo de informe")
    p_rep.add_argument("--output", help="ruta del archivo de salida")
    p_rep.add_argument("--limit", type=int, default=50, help="eventos incluidos")
    add_json(p_rep)
    p_rep.set_defaults(func=cmd_report)

    p_cmp = sub.add_parser("compare", help="compara dos escaneos")
    p_cmp.add_argument("--from", dest="frm", help="id del escaneo antiguo")
    p_cmp.add_argument("--to", help="id del escaneo nuevo")
    p_cmp.add_argument("--limit", type=int, default=10, help="cuántos escaneos recientes considerar")
    add_json(p_cmp)
    p_cmp.set_defaults(func=cmd_compare)

    p_snap = sub.add_parser("snapshot", help="guarda el último escaneo como snapshot")
    p_snap.add_argument("--label", help="etiqueta del snapshot")
    add_json(p_snap)
    p_snap.set_defaults(func=cmd_snapshot)

    p_daemon = sub.add_parser("daemon", help="vigilancia continua")
    p_daemon.add_argument("action", choices=["start", "stop", "status", "pause", "resume", "scan", "run"])
    p_daemon.add_argument("--foreground", action="store_true", help="no desacoplar el proceso")
    add_json(p_daemon)
    p_daemon.set_defaults(func=cmd_daemon)

    p_mon = sub.add_parser("monitor", help="monitor pasivo (deauth/probes/beacons; no corta tu WiFi)")
    p_mon.add_argument("action", choices=["start", "stop", "status", "events"])
    p_mon.add_argument("--limit", type=int, default=30)
    p_mon.add_argument("--kind", help="filtra por tipo (deauth|probe|beacon|eapol)")
    add_json(p_mon)
    p_mon.set_defaults(func=cmd_monitor)

    p_watch = sub.add_parser("watch", help="lista de vigilancia de redes (avisos de cambio)")
    p_watch.add_argument("action", choices=["list", "add", "remove"])
    p_watch.add_argument("bssid", nargs="?")
    p_watch.add_argument("--ssid")
    p_watch.add_argument("--note")
    add_json(p_watch)
    p_watch.set_defaults(func=cmd_watch)

    p_fc = sub.add_parser("forecast", help="previsión de canal por hora/día (histórico)")
    p_fc.add_argument("action", nargs="?", default="show", choices=["show", "week", "record"])
    p_fc.add_argument("--band", default="2.4 GHz")
    add_json(p_fc)
    p_fc.set_defaults(func=cmd_forecast)

    p_doc = sub.add_parser("doctor", help="capacidades reales del hardware y del sistema")
    add_json(p_doc)
    p_doc.set_defaults(func=cmd_doctor)

    p_cfg = sub.add_parser("config", help="ver o editar la configuración")
    p_cfg.add_argument("action", choices=["show", "set", "path"])
    p_cfg.add_argument("key", nargs="?")
    p_cfg.add_argument("value", nargs="?")
    add_json(p_cfg)
    p_cfg.set_defaults(func=cmd_config)

    p_imp = sub.add_parser("import-external", help="importa un JSON de WiFi Analyzer")
    p_imp.add_argument("path", help="ruta al archivo JSON")
    add_json(p_imp)
    p_imp.set_defaults(func=cmd_import)

    p_speed = sub.add_parser("speedtest", help="test de velocidad correlacionado con congestión")
    add_json(p_speed)
    p_speed.set_defaults(func=cmd_speedtest)

    p_oui = sub.add_parser("oui", help="gestiona la base de fabricantes OUI")
    p_oui.add_argument("--refresh", action="store_true", help="descargar la base IEEE (requiere red)")
    p_oui.set_defaults(func=cmd_oui)

    p_db = sub.add_parser("db", help="mantenimiento de la base de datos")
    p_db.add_argument("action", choices=["info", "purge"])
    p_db.add_argument("--days", type=int, default=90, help="días de histórico a conservar")
    add_json(p_db)
    p_db.set_defaults(func=cmd_db)

    p_tut = sub.add_parser("tutorial", help="explicaciones y glosario")
    p_tut.add_argument("term", nargs="?", help="término a explicar")
    add_json(p_tut)
    p_tut.set_defaults(func=cmd_tutorial)

    p_gloss = sub.add_parser("glossary", help="imprime el glosario (clave: resumen)")
    p_gloss.set_defaults(func=cmd_glossary)

    p_ver = sub.add_parser("version", help="muestra la versión")
    add_json(p_ver)
    p_ver.set_defaults(func=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = Context(args)
    try:
        return int(args.func(ctx) or 0)
    except KeyboardInterrupt:
        print("Interrumpido.")
        return 130
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
