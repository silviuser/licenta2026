import type { CSSProperties, ReactNode } from 'react';
import { motion } from 'motion/react';

const EASE = [0.21, 0.47, 0.32, 0.98] as const;

interface RevealProps {
  children: ReactNode;
  /** Seconds — stagger siblings with i * 0.06. */
  delay?: number;
  style?: CSSProperties;
}

/** Fade-up entrance for cards and sections. */
export function Reveal({ children, delay = 0, style }: RevealProps) {
  return (
    <motion.div
      style={style}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}
