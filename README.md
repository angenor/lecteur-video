# Lecteur vidéo de communiqués

Un texte politique entre — fichier texte ou capture d'écran — et il en sort
tout ce qu'il faut pour rendre une vidéo 9:16 au gabarit « Bandeau télé » :
la piste audio française, le découpage en segments horodatés, et l'enveloppe
d'amplitude pour animer l'onde.

Le rendu vidéo lui-même se fait dans Remotion, qui consomme le
`video-data.json` produit ici.

```
texte / image → extraction → découpage → synthèse → video-data.json → Remotion
```

## Installation

```bash
cd lecteur-video
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

export OPENROUTER_API_KEY="sk-or-..."
```

Pour le rendu vidéo, il faut aussi Node :

```bash
brew install node
```

Les dépendances Node s'installent toutes seules au premier `--render`
(environ 400 Mo dans `remotion/node_modules`, plus Chrome Headless que
Remotion télécharge une fois). Tu peux aussi les installer d'avance :

```bash
cd remotion && npm install && cd ..
```

Le cache Hugging Face est partagé avec le projet de doublage : si Voxtral y
est déjà, rien à retélécharger.

## Usage

```bash
# Texte brut, jusqu'au MP4
python build.py communique.txt --speaker "Nom Prénom" --photo photo.jpg --render

# Une ou plusieurs captures d'écran
python build.py capture1.png capture2.png --speaker "Nom Prénom" --render

# Aperçu interactif avant de rendre (bloquant, Ctrl+C pour quitter)
python build.py communique.txt --speaker "Tiemoko Antoine" --studio
```

Sans `--render`, le pipeline s'arrête au `video-data.json` — utile pour
relire le texte avant de payer les minutes de synthèse et de rendu.

Sortie dans `sortie/<nom>/` :

| fichier | contenu |
|---|---|
| `texte.txt` | le texte extrait, relisible et corrigeable |
| `segments.json` | le découpage, avec longueurs et tailles de police |
| `voix.wav` | la piste audio complète |
| `audio/` | un WAV par segment |
| `video-data.json` | le contrat consommé par Remotion |
| `<nom>.mp4` | la vidéo finale, avec `--render` |

### Relire avant de synthétiser

Sur une capture d'écran, l'extraction peut se tromper — noms propres, sigles,
chiffres. Coupe avant la synthèse, corrige, reprends :

```bash
python build.py capture.png --text-only
$EDITOR sortie/capture/texte.txt
python build.py capture.png --from-text sortie/capture/texte.txt
```

## Extraction depuis une image

Deux moteurs, choisis avec `--ocr` :

**`vision`** (défaut) envoie l'image à un modèle multimodal via OpenRouter.
Nettement meilleur sur les captures de réseaux sociaux : il gère les accents,
les fonds colorés, et sait ignorer les compteurs de likes et les boutons
« Voir plus ». C'est le seul appel réseau du projet, et le seul coût.

**`local`** utilise l'OCR natif de macOS via `ocrmac` (`pip install ocrmac`).
Gratuit et hors ligne, mais moins tolérant aux mises en page inhabituelles.
Utile pour du texte propre, ou si tu veux éviter l'API.

## Découpage

Les contraintes viennent de la maquette : le bandeau ocre dispose de 372px
utiles avant de heurter l'onde audio, soit environ **90 caractères** à 70px.

La taille de police s'adapte : 70px jusqu'à 60 caractères, 60px de 61 à 90,
52px au-delà. Ces paliers sont dans `FONT_TIERS` et doivent rester alignés
avec la composition Remotion.

Le découpage ne se contente pas de respecter la limite : il score chaque
coupure possible pour éviter de casser un groupe de sens. Couper « jusqu'au
30 | octobre » respecte la limite mais fait marquer une pause à la synthèse
au milieu d'une date. Sont pénalisées les coupures après un déterminant, une
préposition, une élision (`l'`, `d'`) ou un nombre ; sont favorisées celles
qui tombent sur une virgule ou avant un connecteur.

`test_decoupage.py` verrouille ce comportement.

## L'onde audio

Elle suit l'amplitude réelle de la voix, pas un motif aléatoire — sinon les
barres bougent pendant les silences et ça se voit immédiatement.

`waveform.py` calcule une valeur RMS par frame vidéo, la compresse en racine
carrée pour que l'onde reste lisible malgré la dynamique de la voix, la
normalise et la lisse. Le tableau `envelope` du JSON contient une valeur par
frame ; Remotion y découpe une fenêtre glissante de 90 valeurs pour obtenir
l'onde défilante du gabarit.

## L'intégration Python ↔ Remotion

Remotion est du Node/React : il ne peut pas tourner *dans* Python. Il vit donc
dans le sous-dossier `remotion/`, et `lecteur/render.py` l'appelle en
sous-processus. De ta ligne de commande, la séparation est invisible.

```
lecteur-video/
├── build.py              # le CLI, seul point d'entrée
├── lecteur/              # les briques Python
│   ├── extract.py        # texte ou image → texte
│   ├── segment.py        # texte → segments
│   ├── synthesize.py     # segments → audio
│   ├── waveform.py       # audio → enveloppe d'amplitude
│   ├── timeline.py       # tout → video-data.json
│   └── render.py         # appelle Remotion
└── remotion/             # le projet React
    ├── package.json
    ├── src/
    │   ├── BandeauTele.tsx   # le gabarit
    │   ├── types.ts          # le contrat, en miroir de timeline.py
    │   └── Root.tsx
    └── public/           # médias copiés ici avant chaque rendu
```

Deux détails d'intégration valent d'être connus. Remotion ne sert que les
fichiers de son dossier `public/` : `render.py` y copie l'audio et la photo
avant chaque rendu, et les props ne référencent que des noms relatifs. Et
`npm install` n'est lancé qu'une fois, si `node_modules` est absent.

Si le rendu échoue, `render.py` affiche la commande Remotion équivalente à
relancer à la main — c'est là que tu verras le vrai message d'erreur.

### Le contrat

`video-data.json` contient tout ce dont la composition a besoin :

```jsonc
{
  "fps": 30,
  "width": 1080, "height": 1920,
  "durationInFrames": 1234,
  "fadeFrames": 8,
  "audio": "voix.wav",
  "envelope": [0.06, 0.31, ...],   // une valeur par frame
  "waveBars": 90,                   // barres visibles simultanément
  "waveWindowFrames": 60,           // largeur de la fenêtre glissante
  "meta":  { "rubrique", "speaker", "date", "signature", "photo", "disclaimer" },
  "theme": { "page", "card", "accent", "rubrique", "bar", "muted", "module" },
  "segments": [
    { "index": 0, "text": "...", "chars": 59, "fontSize": 70,
      "startFrame": 18, "endFrame": 132 }
  ]
}
```

Cette forme est décrite deux fois : dans `lecteur/timeline.py` côté Python et
dans `remotion/src/types.ts` côté React. **Si tu modifies l'une, modifie
l'autre.**

### Les ancrages du gabarit

Ils sont repris de la maquette validée et ne doivent pas être « arrondis » :

```
bottom 880   bloc pastille / nom / date
bottom 800   onde audio (hauteur 44)
bottom 431   bandeau ocre, HAUTEUR FIXE 369
bottom 350   barre signature (hauteur 81)
```

431 + 369 = 800 : le bord haut du bandeau touche exactement l'onde.
350 + 81 = 431 : la barre signature touche exactement le bandeau.

La hauteur du bandeau est **constante**. C'est ce qui empêche l'onde de se
décoller et évite tout mouvement vertical d'un segment à l'autre. En
contrepartie, `overflow:hidden` coupe silencieusement un segment trop long :
la responsabilité est entièrement côté découpage Python, et les segments hors
limite sont signalés en fin de run.

## La mention de synthèse vocale

Par défaut, `video-data.json` porte un champ `meta.disclaimer` valant
« Texte lu par synthèse vocale », à afficher dans la barre signature.

C'est un choix délibéré. Une voix synthétique qui lit un texte signé d'un
responsable politique, en période électorale, sans que rien ne l'indique,
c'est le genre de chose qui se retourne contre l'émetteur. `--no-disclaimer`
existe, mais réfléchis avant de l'utiliser.

## Tests

```bash
python test_lecteur.py     # nettoyage, découpage, timings, enveloppe, payload
python test_decoupage.py   # qualité des coupures
```

Les étapes qui dépendent d'Apple Silicon (synthèse) et le rendu Remotion lui-même
ne sont pas couverts : ils demandent ta machine.
# lecteur-video
