import './GrafiFigure.css';
import grafiTransparentImg from './assets/grafi-transparent-v5.png?url';

export interface GrafiFigureProps {
  motionEnabled?: boolean;
  size?: 'compact' | 'default';
  /** Use for duplicate appearances inside interactive controls. */
  decorative?: boolean;
}

export function GrafiFigure({
  motionEnabled = true,
  size = 'default',
  decorative = false,
}: GrafiFigureProps) {
  return (
    <div
      className={[
        'grafi-figure',
        size === 'compact' ? 'grafi-figure--compact' : '',
        motionEnabled ? 'grafi-figure--motion' : 'grafi-figure--motion-off',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="grafi-figure__inner">
        <img
          className="grafi-figure__img"
          src={grafiTransparentImg}
          alt={decorative ? '' : 'Grafi advisor'}
          aria-hidden={decorative ? true : undefined}
          draggable={false}
        />
      </div>
    </div>
  );
}
