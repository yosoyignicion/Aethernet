"""API HTTP local (FastAPI) de solo lectura sobre la base de datos.

Por defecto escucha en 127.0.0.1 y no expone ninguna operación destructiva.
Los endpoints que mutan estado o activan hardware (``POST``) exigen la cabecera
``X-Aethernet-Token`` con el token por instalación (ver ``resolve_api_token``).
FastAPI/uvicorn son opcionales; si faltan, se avisa con claridad.
"""

from __future__ import annotations

from typing import Any, cast

from .. import __version__
from ..capabilities import detect
from ..config import Paths, Settings, api_token_path, resolve_api_token, tokens_match
from ..core.health import score_health
from ..core.spectrum import spectrum_snapshot
from ..logging_setup import get_logger
from ..models import Severity
from ..service.daemon import MonitorService

log = get_logger(__name__)


class APIDependencyError(RuntimeError):
    pass


def create_app(
    repo: Any,
    settings: Settings,
    service: MonitorService | None = None,
    paths: Paths | None = None,
) -> Any:
    """Fábrica de la app FastAPI. Se importa FastAPI aquí para no exigirlo siempre."""
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, Query
    except ImportError as exc:  # pragma: no cover
        raise APIDependencyError(
            "La API local requiere FastAPI: pip install 'aethernet[api]'"
        ) from exc

    app = FastAPI(
        title="Aethernet API",
        version=__version__,
        description="Consulta local de la base de datos de Aethernet. Solo localhost.",
    )

    token_file = api_token_path(paths)
    expected_token = resolve_api_token(paths)

    def require_token(x_aethernet_token: str | None = Header(default=None)) -> None:
        """Exige el token de la API en operaciones que mutan estado o hardware."""
        if not tokens_match(expected_token, x_aethernet_token):
            raise HTTPException(status_code=401, detail="token de API inválido o ausente")

    mutate = [Depends(require_token)]

    @app.get("/health")
    def health() -> dict[str, Any]:
        capabilities = detect(settings.interface).to_dict()
        return {
            "status": "ok",
            "capabilities": capabilities,
            "daemon": repo.kv_get("daemon_status", {}),
            "api_token_file": str(token_file),
        }

    @app.get("/score")
    def score() -> dict[str, Any]:
        scan = repo.latest_wifi_scan()
        if scan is None:
            return {"total": None, "detail": "sin escaneos"}
        history = repo.signal_history([ap.bssid for ap in scan.aps], 24)
        health_score = score_health(
            scan,
            my_ssids=tuple(settings.my_ssids),
            my_bssids=tuple(settings.my_bssids),
            signal_history=history,
        )
        return health_score.to_dict()

    @app.get("/wifi/latest")
    def wifi_latest() -> dict[str, Any]:
        scan = repo.latest_wifi_scan()
        if scan is None:
            raise HTTPException(status_code=404, detail="sin escaneos")
        return cast("dict[str, Any]", scan.to_dict())

    @app.get("/wifi/scans")
    def wifi_scans(limit: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
        scans = repo.recent_scans(limit)
        return {"count": len(scans), "scans": scans}

    @app.get("/wifi/history/{bssid}")
    def wifi_history(bssid: str, hours: float = Query(24, gt=0, le=24 * 30)) -> dict[str, Any]:
        series = repo.signal_series(bssid, hours)
        return {
            "bssid": bssid,
            "points": [{"timestamp": ts, "signal_dbm": dbm} for ts, dbm in series],
        }

    @app.get("/spectrum")
    def spectrum() -> dict[str, Any]:
        scan = repo.latest_wifi_scan()
        if scan is None:
            raise HTTPException(status_code=404, detail="sin escaneos")
        return spectrum_snapshot(scan)

    @app.get("/lan/latest")
    def lan_latest() -> dict[str, Any]:
        scan = repo.latest_lan_scan()
        if scan is None:
            raise HTTPException(status_code=404, detail="sin escaneos LAN")
        return cast("dict[str, Any]", scan.to_dict())

    @app.get("/lan/devices")
    def lan_devices(online_only: bool = False) -> dict[str, Any]:
        devices = repo.devices(online_only=online_only)
        return {"count": len(devices), "devices": [d.to_dict() for d in devices]}

    @app.get("/events")
    def events(
        limit: int = Query(50, ge=1, le=500),
        severity: str | None = None,
        unread_only: bool = False,
    ) -> dict[str, Any]:
        min_severity = None
        if severity:
            try:
                min_severity = Severity(severity)
            except ValueError:
                raise HTTPException(status_code=400, detail="severidad no válida") from None
        events_list = repo.list_events(limit=limit, min_severity=min_severity, unread_only=unread_only)
        return {"count": len(events_list), "events": [e.to_dict() for e in events_list]}

    @app.post("/events/{event_id}/read", dependencies=mutate)
    def read_event(event_id: int) -> dict[str, Any]:
        updated = repo.mark_event_read(event_id)
        if not updated:
            raise HTTPException(status_code=404, detail="evento no encontrado")
        return {"ok": True}

    @app.get("/snapshots")
    def snapshots(kind: str | None = None, limit: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
        items = repo.list_snapshots(kind, limit)
        return {"count": len(items), "snapshots": [s.to_dict() for s in items]}

    @app.post("/scan", dependencies=mutate)
    def trigger_scan(active: bool = False) -> dict[str, Any]:
        if service is None:
            raise HTTPException(status_code=503, detail="servicio no disponible")
        result = service.scan_once(active=active)
        return result.to_dict()

    # -- monitor pasivo -------------------------------------------------- #
    @app.get("/monitor/status")
    def monitor_status() -> dict[str, Any]:
        if service is None:
            return {"capable": False, "running": False, "reason": "servicio no disponible"}
        return service.monitor_status()

    @app.get("/monitor/events")
    def monitor_events(limit: int = Query(50, ge=1, le=500), kind: str | None = None) -> dict[str, Any]:
        rows = repo.list_monitor_events(limit=limit, kind=kind)
        return {"count": len(rows), "events": rows, "stats": repo.monitor_stats()}

    @app.post("/monitor/start", dependencies=mutate)
    def monitor_start() -> dict[str, Any]:
        if service is None:
            raise HTTPException(status_code=503, detail="servicio no disponible")
        return service.start_monitor()

    @app.post("/monitor/stop", dependencies=mutate)
    def monitor_stop() -> dict[str, Any]:
        if service is None:
            raise HTTPException(status_code=503, detail="servicio no disponible")
        return service.stop_monitor()

    return app


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def serve(
    repo: Any,
    settings: Settings,
    host: str | None = None,
    port: int | None = None,
    paths: Paths | None = None,
) -> None:
    """Arranca uvicorn en primer plano."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise APIDependencyError("uvicorn no está instalado: pip install 'aethernet[api]'") from exc

    app = create_app(repo, settings, paths=paths)
    bound_host = host or settings.api_host
    if bound_host not in _LOOPBACK_HOSTS:
        log.warning(
            "la API escucha en %s (no es loopback): el token de API es tu única defensa",
            bound_host,
        )
    uvicorn.run(app, host=bound_host, port=port or settings.api_port, log_level="info")
