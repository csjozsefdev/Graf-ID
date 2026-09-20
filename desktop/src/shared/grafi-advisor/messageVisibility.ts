import type { ReactNode } from 'react';

export function isMessageVisible(message: ReactNode | null | undefined): boolean {
  if (message === null || message === undefined || message === false) {
    return false;
  }
  if (typeof message === 'string') {
    return message.trim().length > 0;
  }
  return true;
}
