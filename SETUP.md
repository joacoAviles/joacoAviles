# JOACO / DEVELOPER HUB — cómo funciona

Todo el perfil se genera desde `config.json`. No edites `README.md` ni `assets/generated/` a mano:
el workflow los reescribe.

## Instalación (5 min)

1. Crea el repo especial: **github.com/new → nombre = tu usuario exacto** (ej. `joacoAviles`), público.
2. Sube el contenido de esta carpeta a `main`.
3. **Settings → Actions → General → Workflow permissions → Read and write**.
4. El push dispara el workflow; en ~1 min aparecen `stats.svg`, `panel.svg`, `route.svg`
   y las tarjetas con tus datos reales. Después corre solo todos los días.

Si tu usuario no es `joacoAviles`, cámbialo en `config.json` → `username`.

## Qué editar

| Quieres cambiar…          | Dónde                                                    |
|---------------------------|----------------------------------------------------------|
| Proyectos destacados      | `config.json → projects` (`repo` = `owner/nombre` real)  |
| Chips del tech stack      | `config.json → stack` (`icon` = slug de simpleicons.org; `lang` = lenguaje que lo ilumina en amarillo si es top 3 en tus repos) |
| Textos, lema, coordenadas | `config.json`                                            |
| Fotos                     | `assets/photos/` (ver `LEEME.md` ahí)                    |
| Links de la ruta          | `config.json → route[].url` (si pones alguno, aparece una fila de links bajo el mapa) |

Un proyecto cuyo `repo` no existe o es privado se muestra igual, sin estrellas ni forks
(nunca se inventan números): muestra el dominio de `url` o "EN CONSTRUCCIÓN".

## Contribuciones privadas (opcional)

Con el `GITHUB_TOKEN` por defecto solo se cuentan las públicas. Para incluir las privadas:
crea un PAT *classic* con scope `read:user` y guárdalo como secret `PROFILE_TOKEN`.

## Probar en local

```bash
pip install fonttools brotli
GH_TOKEN=$(gh auth token) python scripts/build.py      # datos reales
python scripts/build.py --demo --out /tmp/preview     # datos falsos, marcados DEMO
```

## Sidebar nativo de GitHub

La columna izquierda del mockup (foto, bio, ubicación, links, followers) **ya la dibuja GitHub**.
Complétala en *Settings → Public profile*: Bio, Location `Santiago, Chile`, URL `aviarockets.com`,
email público, y la foto con el contorno amarillo como avatar.

## Notas técnicas

- Las animaciones son CSS/SMIL dentro del SVG; GitHub las muestra porque las sirve como `<img>`.
  Respetan `prefers-reduced-motion`.
- Las fuentes (Archivo Black, Permanent Marker, JetBrains Mono, Inter — todas OFL) van embebidas
  y recortadas a los caracteres usados. Iconos: Simple Icons (CC0).
- `scripts/dev/gen_assets.py` regenera las curvas de nivel (necesita numpy + matplotlib). Cambia
  las semillas si quieres otra cordillera.
