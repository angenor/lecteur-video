/**
 * Contrat avec le Python.
 *
 * Cette forme est exactement celle produite par `lecteur/timeline.py`.
 * Si tu modifies l'un, modifie l'autre.
 */

export type Segment = {
  index: number;
  text: string;
  chars: number;
  fontSize: number;
  startFrame: number;
  endFrame: number;
  startSec?: number;
  durationSec?: number;
  notes?: string[];
};

export type Meta = {
  rubrique: string;
  speaker: string;
  date: string;
  signature: string;
  photo: string;
  disclaimer: string;
};

export type Theme = {
  page: string;
  card: string;
  accent: string;
  rubrique: string;
  bar: string;
  muted: string;
  text: string;
  module: number;
};

export type VideoData = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  fadeFrames: number;
  audio: string;
  envelope: number[];
  waveBars: number;
  waveWindowFrames: number;
  meta: Meta;
  theme: Theme;
  segments: Segment[];
};
