## Qué cambia

<!-- Resumen breve y el porqué. Enlaza el issue: Closes #123 -->

## Tipo

- [ ] `feat` nueva funcionalidad
- [ ] `fix` corrección de error
- [ ] `refactor` sin cambio de comportamiento
- [ ] `docs` documentación
- [ ] `chore` mantenimiento / build / CI
- [ ] `test` pruebas

## Cómo se ha probado

<!-- Comandos ejecutados y resultado. -->

- [ ] `./scripts/ci.sh` (ruff + mypy --strict + vulture + pytest)
- [ ] `./scripts/smoke.sh` (UI headless, 7 rutas)
- [ ] Añadí/actualicé tests para el cambio

## Checklist

- [ ] Respeta los principios: **pasivo por defecto**, sin nube ni telemetría, dependecias
      pesadas opcionales con degradación graciosa.
- [ ] Si toco la DB, la migración es **nueva** (nunca edito una aplicada).
- [ ] No incluyo secretos, MACs ni datos personales.
- [ ] Actualicé `CHANGELOG.md` si aplica.
