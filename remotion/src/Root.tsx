import {Composition} from 'remotion';
import {BandeauTele} from './BandeauTele';
import {demoData} from './demoData';
import type {VideoData} from './types';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="BandeauTele"
      component={BandeauTele}
      defaultProps={demoData}
      // La durée vient des données: c'est l'audio qui commande, pas l'inverse.
      calculateMetadata={({props}) => ({
        durationInFrames: props.durationInFrames,
        fps: props.fps,
        width: props.width,
        height: props.height,
      })}
      durationInFrames={demoData.durationInFrames}
      fps={demoData.fps}
      width={demoData.width}
      height={demoData.height}
    />
  );
};
