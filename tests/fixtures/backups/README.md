# Fixtures de copia histórica

Paquetes reales de Aethernet conservados como **golden files** para probar que una
copia antigua se restaura en una máquina limpia con el código actual.

Cada `*.tar.gz` va acompañado de un `*.expected.json` con su procedencia y las
aserciones de `tests/test_backup_compat.py`:

- versión de la app y de esquema que lo generó,
- `format_version` del paquete,
- `db_sha256` / `db_bytes` de la base,
- versión de SQLite y `page_size`,
- conteos esperados (escaneos, dispositivos, eventos), SSIDs de la config y el
  marcador `kv`.

## Regenerar y ampliar la escalera

```bash
python scripts/gen_backup_fixture.py
```

El script usa **siempre la versión actual** del código. Al añadir una migración
(append-only) o cambiar `BUNDLE_FORMAT_VERSION`, ejecútalo: creará un paquete
nuevo y **conservará los anteriores**. Nunca borres un paquete antiguo: es lo que
da cobertura a las versiones ya publicadas.

Si el `db_sha256` cambia al regenerar (p. ej. por una versión distinta de SQLite),
revisa el diff antes de commitear; el paquete y su `.expected.json` deben ir juntos.

## Cobertura actual

| Paquete | App | Esquema | Notas |
| --- | --- | --- | --- |
| `aethernet-1.3.0-schema5.tar.gz` | 1.3.0 | 5 | Primera fixture; base con 2 escaneos, LAN, evento y config. |
