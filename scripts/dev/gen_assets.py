"""
Genera los datos estáticos que usa build.py (solo se corre una vez, en local):
  - scripts/data/topo.json   curvas de nivel (paths SVG) para cabecera, mapa y tarjetas
  - scripts/data/icons.json  iconos de Simple Icons (CC0) para el tech stack

Requiere: numpy, matplotlib  (pip install numpy matplotlib)
Uso:      python scripts/dev/gen_assets.py [ruta/a/simple-icons/icons]
"""
import json, sys, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "scripts", "data")


def terrain(w, h, seed, peaks=14, res=3.0):
    rng = np.random.default_rng(seed)
    nx, ny = int(w / res), int(h / res)
    x = np.linspace(0, w, nx)
    y = np.linspace(0, h, ny)
    X, Y = np.meshgrid(x, y)
    Z = np.zeros_like(X)
    # cordillera: crestas alargadas + cerros sueltos
    for _ in range(peaks):
        cx, cy = rng.uniform(-0.1 * w, 1.1 * w), rng.uniform(-0.2 * h, 1.2 * h)
        sx, sy = rng.uniform(0.06, 0.22) * w, rng.uniform(0.15, 0.5) * h
        ang = rng.uniform(0, np.pi)
        a = rng.uniform(0.5, 1.4)
        Xr = (X - cx) * np.cos(ang) + (Y - cy) * np.sin(ang)
        Yr = -(X - cx) * np.sin(ang) + (Y - cy) * np.cos(ang)
        Z += a * np.exp(-(Xr ** 2 / (2 * sx ** 2) + Yr ** 2 / (2 * sy ** 2)))
    for k in range(1, 5):
        Z += 0.06 / k * np.sin(X / (w / (4 * k)) + rng.uniform(0, 6)) * np.cos(Y / (h / (3 * k)) + rng.uniform(0, 6))
    return X, Y, Z


def contour_paths(w, h, seed, levels=26, peaks=14, min_len=18):
    X, Y, Z = terrain(w, h, seed, peaks)
    fig = plt.figure()
    cs = plt.contour(X, Y, Z, levels=levels)
    paths = []
    for li, segs in enumerate(cs.allsegs):
        for seg in segs:
            if len(seg) < 4:
                continue
            seg = seg[:: max(1, len(seg) // 220)]  # simplificar
            length = np.sum(np.hypot(*np.diff(seg, axis=0).T))
            if length < min_len:
                continue
            d = "M" + "L".join(f"{p[0]:.1f} {p[1]:.1f}" for p in seg)
            paths.append({"d": d, "major": li % 5 == 0})
    plt.close(fig)
    return paths


def main():
    os.makedirs(OUT, exist_ok=True)
    topo = {
        "header": {"w": 1000, "h": 300, "paths": contour_paths(1000, 300, 7, levels=30, peaks=18)},
        "map": {"w": 1000, "h": 330, "paths": contour_paths(1000, 330, 21, levels=34, peaks=20)},
        "card": {"w": 480, "h": 200, "paths": contour_paths(480, 200, 3, levels=18, peaks=8)},
        "footer": {"w": 1000, "h": 240, "paths": contour_paths(1000, 240, 42, levels=24, peaks=14)},
    }
    with open(os.path.join(OUT, "topo.json"), "w") as f:
        json.dump(topo, f, separators=(",", ":"))
    print("topo:", {k: len(v["paths"]) for k, v in topo.items()})

    icons_dir = sys.argv[1] if len(sys.argv) > 1 else None
    if icons_dir:
        import re
        wanted = ["python", "javascript", "typescript", "gnubash", "linux", "docker", "proxmox",
                  "githubactions", "postgresql", "supabase", "fastapi", "nodedotjs", "react",
                  "nextdotjs", "esphome", "homeassistant", "espressif", "notion", "cloudflare",
                  "nginx", "redis", "go", "rust", "html5", "css", "tailwindcss", "vuedotjs",
                  "kubernetes", "terraform", "ansible", "grafana", "n8n", "anthropic", "claude",
                  "apple", "raspberrypi", "arduino", "openjdk", "php", "mysql", "mongodb", "git"]
        icons = {}
        for name in wanted:
            p = os.path.join(icons_dir, name + ".svg")
            if os.path.exists(p):
                m = re.search(r'<path d="([^"]+)"', open(p).read())
                if m:
                    icons[name] = m.group(1)
        with open(os.path.join(OUT, "icons.json"), "w") as f:
            json.dump(icons, f, separators=(",", ":"))
        print("icons:", len(icons), sorted(set(wanted) - set(icons)))


if __name__ == "__main__":
    main()
