/**
 * Gabarit « Bandeau télé » — 1080 × 1920.
 *
 * Transcription de la maquette validée. Les valeurs d'ancrage sont
 * reprises telles quelles et ne doivent pas être « arrondies »:
 *
 *   bottom: 880  bloc pastille / nom / date
 *   bottom: 800  onde audio (hauteur 44)  ─┐ au contact
 *   bottom: 431  bandeau ocre, HAUTEUR FIXE 369  ─┘
 *   bottom: 350  barre signature (hauteur 81)
 *
 * 431 + 369 = 800 : le bord haut du bandeau touche exactement l'onde.
 * 350 + 81  = 431 : la barre signature touche exactement le bandeau.
 * La hauteur du bandeau est constante, donc rien ne bouge d'un segment
 * à l'autre et l'onde ne peut pas se décoller.
 */

import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import type {Segment, VideoData} from './types';

const FONT_STACK = "'Helvetica Neue', Helvetica, Arial, system-ui, sans-serif";

// Ancrages, en pixels depuis le bas
const META_BOTTOM = 880;
const WAVE_BOTTOM = 800;
const WAVE_HEIGHT = 44;
const CARD_BOTTOM = 431;
const CARD_HEIGHT = 369;
const BAR_BOTTOM = 350;
const BAR_HEIGHT = 81;

const WAVE_BAR_WIDTH = 4;
const WAVE_BAR_GAP = 7;
const WAVE_BAR_MIN = 5;

/** Fenêtre glissante dans l'enveloppe: les `bars` dernières valeurs. */
const sampleWave = (
  envelope: number[],
  frame: number,
  bars: number,
  windowFrames: number,
): number[] => {
  const out: number[] = [];
  for (let i = 0; i < bars; i++) {
    // i = 0 -> le plus ancien (à gauche), i = bars-1 -> maintenant (à droite)
    const offset = windowFrames * (1 - i / (bars - 1));
    const idx = Math.round(frame - offset);
    out.push(idx >= 0 && idx < envelope.length ? envelope[idx] : 0);
  }
  return out;
};

const Stripes: React.FC<{module: number}> = ({module}) => (
  <div
    aria-hidden
    style={{
      position: 'absolute',
      inset: 0,
      background: `repeating-linear-gradient(90deg, rgba(17,16,16,.22) 0 3px, transparent 3px ${module}px)`,
      pointerEvents: 'none',
    }}
  />
);

export const BandeauTele: React.FC<VideoData> = ({
  envelope = [],
  waveBars = 90,
  waveWindowFrames = 60,
  fadeFrames = 8,
  audio,
  meta,
  theme,
  segments = [],
}) => {
  const frame = useCurrentFrame();
  const wave = sampleWave(envelope, frame, waveBars, waveWindowFrames);

  return (
    <AbsoluteFill style={{backgroundColor: theme.page, fontFamily: FONT_STACK}}>
      {audio ? <Audio src={staticFile(audio)} /> : null}

      {/* Fond: portrait plein cadre, ou aplat si aucune photo */}
      {meta.photo ? (
        <Img
          src={staticFile(meta.photo)}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
      ) : (
        <AbsoluteFill
          style={{
            backgroundColor: '#3A3835',
            alignItems: 'center',
            justifyContent: 'flex-start',
            paddingTop: 560,
          }}
        >
          <span
            style={{
              fontWeight: 800,
              fontSize: 40,
              letterSpacing: '.2em',
              color: theme.muted,
            }}
          >
            PHOTO
          </span>
        </AbsoluteFill>
      )}

      {/* Voile: rend le texte lisible par-dessus n'importe quel portrait */}
      <AbsoluteFill style={{backgroundColor: 'rgba(20,19,18,.7)'}} />

      {/* Pastille rubrique + nom + date */}
      <div
        style={{
          position: 'absolute',
          left: theme.module,
          right: theme.module,
          bottom: META_BOTTOM,
          display: 'flex',
          flexDirection: 'column',
          gap: 22,
          alignItems: 'flex-start',
        }}
      >
        <span
          style={{
            backgroundColor: theme.rubrique,
            color: theme.text,
            fontWeight: 800,
            fontSize: 28,
            letterSpacing: '.18em',
            textTransform: 'uppercase',
            padding: '12px 20px',
          }}
        >
          {meta.rubrique}
        </span>
        <span
          style={{
            color: theme.text,
            fontWeight: 800,
            fontSize: 52,
            lineHeight: 1.02,
            letterSpacing: '-.02em',
            maxWidth: 760,
          }}
        >
          {meta.speaker}
        </span>
        <span
          style={{
            color: theme.muted,
            fontWeight: 800,
            fontSize: 26,
            letterSpacing: '.12em',
            textTransform: 'uppercase',
          }}
        >
          {meta.date}
        </span>
      </div>

      {/* Onde audio: amplitude réelle de la voix, fenêtre glissante */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: WAVE_BOTTOM,
          height: WAVE_HEIGHT,
          display: 'flex',
          alignItems: 'flex-end',
          gap: WAVE_BAR_GAP,
          padding: `0 ${theme.module}px`,
        }}
      >
        {wave.map((value, i) => (
          <span
            key={i}
            style={{
              display: 'block',
              width: WAVE_BAR_WIDTH,
              height:
                WAVE_BAR_MIN + (WAVE_HEIGHT - WAVE_BAR_MIN) * value,
              backgroundColor: theme.accent,
            }}
          />
        ))}
      </div>

      {/* Bandeau ocre — hauteur fixe, texte centré verticalement */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: CARD_BOTTOM,
          height: CARD_HEIGHT,
          overflow: 'hidden',
          backgroundColor: theme.card,
          padding: `0 ${theme.module}px`,
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'center',
        }}
      >
        <Stripes module={theme.module} />

        {segments.map((seg: Segment) => {
          // Fondu entrant et sortant; hors de sa plage, le segment est
          // à opacité 0 et n'occupe aucun espace (position absolue).
          const opacity = interpolate(
            frame,
            [
              seg.startFrame - fadeFrames,
              seg.startFrame,
              seg.endFrame - fadeFrames,
              seg.endFrame,
            ],
            [0, 1, 1, 0],
            {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
          );
          if (opacity <= 0.001) return null;

          const shift = interpolate(
            frame,
            [seg.startFrame - fadeFrames, seg.startFrame],
            [14, 0],
            {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
          );

          return (
            <p
              key={seg.index}
              style={{
                position: 'absolute',
                left: theme.module,
                right: theme.module,
                margin: 0,
                color: theme.text,
                fontWeight: 800,
                fontSize: seg.fontSize,
                lineHeight: 1.02,
                letterSpacing: '-.03em',
                textWrap: 'pretty',
                opacity,
                transform: `translateY(${shift}px)`,
              }}
            >
              {seg.text}
            </p>
          );
        })}
      </div>

      {/* Barre signature */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: BAR_BOTTOM,
          height: BAR_HEIGHT,
          boxSizing: 'border-box',
          backgroundColor: theme.bar,
          padding: `20px ${theme.module}px`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 24,
        }}
      >
        <span
          style={{
            color: theme.text,
            fontWeight: 800,
            fontSize: 34,
            letterSpacing: '.12em',
            textTransform: 'uppercase',
            whiteSpace: 'nowrap',
          }}
        >
          {meta.signature}
        </span>
        {meta.disclaimer ? (
          <span
            style={{
              color: theme.muted,
              fontWeight: 800,
              fontSize: 17,
              letterSpacing: '.1em',
              textTransform: 'uppercase',
              textAlign: 'right',
              whiteSpace: 'nowrap',
            }}
          >
            {meta.disclaimer}
          </span>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
