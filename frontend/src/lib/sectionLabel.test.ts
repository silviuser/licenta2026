import { describe, expect, it } from 'vitest';
import { cleanLabel, sectionSuffix } from './sectionLabel';

describe('cleanLabel', () => {
  it('strips a trailing (unknown)/(other) sentinel', () => {
    expect(cleanLabel('microservices (other)')).toBe('microservices');
    expect(cleanLabel('Foo (unknown)')).toBe('Foo');
    expect(cleanLabel('Bar (OTHER)')).toBe('Bar'); // case-insensitive
  });

  it('keeps real sections and meaningful ESCO parentheticals', () => {
    expect(cleanLabel('Tailwind (experience)')).toBe('Tailwind (experience)');
    expect(cleanLabel('JavaScript (languages)')).toBe('JavaScript (languages)');
    expect(cleanLabel('Java (computer programming)')).toBe('Java (computer programming)');
  });

  it('handles nullish values', () => {
    expect(cleanLabel(null)).toBe('');
    expect(cleanLabel(undefined)).toBe('');
  });
});

describe('sectionSuffix', () => {
  it('hides sentinel / blank / nullish sections', () => {
    expect(sectionSuffix('unknown')).toBe('');
    expect(sectionSuffix('other')).toBe('');
    expect(sectionSuffix('UNKNOWN')).toBe('');
    expect(sectionSuffix('')).toBe('');
    expect(sectionSuffix(null)).toBe('');
    expect(sectionSuffix(undefined)).toBe('');
  });

  it('renders informative sections', () => {
    expect(sectionSuffix('experience')).toBe(' (experience)');
    expect(sectionSuffix('skills')).toBe(' (skills)');
  });
});
