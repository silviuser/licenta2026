import type { RequirementInput } from '../api/types';

/** A blank requirement row (default importance required, confidence 0.5). */
export function emptyRequirement(): RequirementInput {
  return { text: '', importance: 'required', skillLabel: '', confidence: 0.5 };
}
