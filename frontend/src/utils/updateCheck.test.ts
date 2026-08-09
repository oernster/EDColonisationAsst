import { describe, expect, it } from 'vitest';

import { isNewerVersion } from './updateCheck';

describe('isNewerVersion', () => {
  it('detects a newer major, minor and patch', () => {
    expect(isNewerVersion('4.0.0', '3.1.0')).toBe(true);
    expect(isNewerVersion('3.2.0', '3.1.0')).toBe(true);
    expect(isNewerVersion('3.1.1', '3.1.0')).toBe(true);
  });

  it('is false for equal or older versions', () => {
    expect(isNewerVersion('3.1.0', '3.1.0')).toBe(false);
    expect(isNewerVersion('3.0.9', '3.1.0')).toBe(false);
    expect(isNewerVersion('2.9.9', '3.0.0')).toBe(false);
  });

  it('tolerates a v prefix and a build suffix', () => {
    expect(isNewerVersion('v3.2.0', '3.1.0 (20260809)')).toBe(true);
    expect(isNewerVersion('v3.1.0', '3.1.0 (20260809)')).toBe(false);
  });

  it('handles differing segment counts numerically', () => {
    expect(isNewerVersion('3.1', '3.1.0')).toBe(false);
    expect(isNewerVersion('3.1.0.1', '3.1.0')).toBe(true);
  });

  it('never reports an update on an unparseable reading', () => {
    expect(isNewerVersion('', '3.1.0')).toBe(false);
    expect(isNewerVersion('latest', '3.1.0')).toBe(false);
    expect(isNewerVersion('3.2.0', 'unknown')).toBe(false);
  });
});
