import type {VideoData} from './types';

/**
 * Données de démonstration.
 *
 * Servent uniquement à ouvrir le studio sans avoir lancé build.py.
 * En production, ces valeurs sont remplacées par le video-data.json
 * passé via --props.
 */
export const demoData: VideoData = {
  fps: 30,
  width: 1080,
  height: 1920,
  durationInFrames: 300,
  fadeFrames: 8,
  audio: '',
  envelope: Array.from({length: 300}, (_, i) =>
    0.06 + 0.94 * Math.abs(Math.sin(i / 7) * Math.sin(i / 23)),
  ),
  waveBars: 90,
  waveWindowFrames: 60,
  meta: {
    rubrique: 'POLITIQUE',
    speaker: '[Nom du responsable politique]',
    date: '26 août 2026',
    signature: "ANGENOR N'GOUANDI",
    photo: '',
    disclaimer: 'Texte lu par synthèse vocale',
  },
  theme: {
    page: '#141312',
    card: '#B65C10',
    accent: '#D97B2A',
    rubrique: '#22386B',
    bar: '#111010',
    muted: '#9E9890',
    text: '#FFFFFF',
    module: 37,
  },
  segments: [
    {
      index: 0,
      text: 'La révision de la liste électorale débutera le 15 septembre',
      chars: 59,
      fontSize: 70,
      startFrame: 18,
      endFrame: 108,
    },
    {
      index: 1,
      text: "et se poursuivra jusqu'au 30 octobre sur toute l'étendue du territoire national.",
      chars: 80,
      fontSize: 60,
      startFrame: 116,
      endFrame: 226,
    },
    {
      index: 2,
      text: 'Chaque citoyen en âge de voter devra se présenter',
      chars: 49,
      fontSize: 70,
      startFrame: 234,
      endFrame: 300,
    },
  ],
};
