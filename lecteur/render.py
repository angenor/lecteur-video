"""Rendu vidéo: pilotage de Remotion depuis Python.

Remotion est un projet Node/React, il ne peut pas tourner *dans* Python.
Ce module l'appelle en sous-processus, ce qui rend la séparation invisible
depuis la ligne de commande: `build.py --render` sort un MP4.

Deux détails d'intégration:
  - Remotion ne sert que les fichiers de son dossier `public/`. On y copie
    donc l'audio et la photo avant le rendu, et le JSON de props ne référence
    que des noms relatifs.
  - `npm install` n'est lancé qu'une fois, si `node_modules` est absent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

COMPOSITION_ID = "BandeauTele"
ENTRY = "src/index.ts"

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class RenderError(RuntimeError):
    pass


def project_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "remotion"


def check_node() -> None:
    for binary in ("node", "npx"):
        if shutil.which(binary) is None:
            raise RenderError(
                f"{binary} introuvable. Installe Node.js: brew install node"
            )


def ensure_dependencies(root: Path, *, quiet: bool = False) -> None:
    if (root / "node_modules").is_dir():
        return
    if not quiet:
        print("  première utilisation: installation des dépendances Node...")
    proc = subprocess.run(
        ["npm", "install"], cwd=root, capture_output=True, text=True
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise RenderError(f"npm install a échoué:\n{tail}")


def stage_assets(payload: dict, audio: Path, photo: str | None, root: Path) -> dict:
    """Copie les médias dans public/ et réécrit les chemins en relatif."""
    public = root / "public"
    public.mkdir(parents=True, exist_ok=True)

    staged = json.loads(json.dumps(payload))  # copie profonde

    if not audio.exists():
        raise RenderError(f"Audio introuvable: {audio}")
    shutil.copy(audio, public / "voix.wav")
    staged["audio"] = "voix.wav"

    if photo:
        src = Path(photo)
        if not src.exists():
            raise RenderError(f"Photo introuvable: {src}")
        if src.suffix.lower() not in PHOTO_SUFFIXES:
            raise RenderError(
                f"Format de photo non géré: {src.suffix}. "
                f"Attendu: {', '.join(sorted(PHOTO_SUFFIXES))}"
            )
        name = f"photo{src.suffix.lower()}"
        shutil.copy(src, public / name)
        staged["meta"]["photo"] = name
    else:
        staged["meta"]["photo"] = ""

    return staged


def render(
    payload: dict,
    audio: Path,
    output: Path,
    *,
    photo: str | None = None,
    concurrency: int | None = None,
    quiet: bool = False,
) -> Path:
    check_node()
    root = project_dir()
    if not (root / "package.json").exists():
        raise RenderError(f"Projet Remotion introuvable dans {root}")

    ensure_dependencies(root, quiet=quiet)

    staged = stage_assets(payload, audio, photo, root)
    props_path = root / "props.json"
    props_path.write_text(
        json.dumps(staged, ensure_ascii=False), encoding="utf-8"
    )

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "npx", "remotion", "render", ENTRY, COMPOSITION_ID, str(output),
        f"--props={props_path}",
    ]
    if concurrency:
        cmd.append(f"--concurrency={concurrency}")

    proc = subprocess.run(cmd, cwd=root, text=True)
    if proc.returncode != 0:
        raise RenderError(
            "Le rendu Remotion a échoué. Relance à la main pour le détail:\n"
            f"  cd {root} && {' '.join(cmd[:6])} --props=props.json"
        )
    if not output.exists():
        raise RenderError(f"Remotion n'a produit aucun fichier: {output}")
    return output


def studio(payload: dict, audio: Path, photo: str | None = None) -> None:
    """Ouvre l'aperçu interactif sur les données réelles.

    Bloquant: le studio tourne jusqu'à Ctrl+C.
    """
    check_node()
    root = project_dir()
    ensure_dependencies(root)

    staged = stage_assets(payload, audio, photo, root)
    (root / "props.json").write_text(
        json.dumps(staged, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nStudio: http://localhost:3000   (Ctrl+C pour quitter)")
    subprocess.run(
        ["npx", "remotion", "studio", ENTRY, "--props=props.json"], cwd=root
    )
