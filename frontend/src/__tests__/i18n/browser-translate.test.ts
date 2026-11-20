/**
 * A browser's page translation rewrites the text React renders, and the next
 * update crashes with "insertBefore … not a child of this node". The page opts
 * out of machine translation and names the language it is shown in.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import i18n from '../../i18n';

const indexHtml = readFileSync(resolve(__dirname, '../../../index.html'), 'utf8');

afterEach(async () => {
  await i18n.changeLanguage('en');
});

describe('browser page translation', () => {
  it('is switched off for the whole page', () => {
    expect(indexHtml).toMatch(/<html[^>]*\btranslate="no"/);
    expect(indexHtml).toContain('<meta name="google" content="notranslate" />');
  });

  it('keeps <html lang> on the language in use', async () => {
    await i18n.changeLanguage('de');
    expect(document.documentElement.lang).toBe('de');

    await i18n.changeLanguage('en');
    expect(document.documentElement.lang).toBe('en');
  });
});
