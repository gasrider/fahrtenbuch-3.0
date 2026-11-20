// Browser-Test (Playwright) gegen eine laufende, frisch installierte Instanz.
// Aufruf: BASE=http://127.0.0.1:8793/fahrtenbuch/ USER="christian mayerhofer" PW=geheim123 node tests/ui_test.mjs
// Prüft: Anmeldung, alle Reiter ohne JS-Fehler, keine waagrechte Überbreite am Handy, Fahrzeuge/Orte/Matrix anlegen,
// Jahr generieren, Monat bearbeiten + speichern, PDF-Download.
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium, devices } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8793/fahrtenbuch/';
const USER = process.env.USER_NAME || 'christian mayerhofer';
const PW = process.env.PW || 'geheim123';
const SHOTS = process.env.SHOTS || '';
let fails = 0;
const check = (c, m) => { console.log((c ? '  ok   ' : '  FAIL ') + m); if (!c) fails++; };

const browser = await chromium.launch();
for (const [label, ctxOpts] of [['Desktop', { viewport: { width: 1280, height: 900 } }], ['Handy', devices['iPhone 13']]]) {
  console.log(label);
  const ctx = await browser.newContext({ ...ctxOpts, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/fonts\.g/.test(m.text())) errors.push(m.text()); });
  await page.goto(BASE);
  await page.fill('input[autocomplete=username]', USER);
  await page.fill('input[type=password]', PW);
  await page.click('button[type=submit]');
  await page.waitForSelector('nav');
  check(true, 'Anmeldung');

  if (label === 'Desktop') {
    // Stammdaten
    await page.click('nav >> text=Stammdaten');
    await page.locator('label:has-text("Wohnort") input').first().fill('Oberhofen am Irrsee');
    await page.locator('label:has-text("Dienstort") input').fill('Straßwalchen');
    await page.locator('label:has-text("Name") input').first().fill('Christian Mayerhofer');
    await page.click('text=Stammdaten speichern');
    await page.waitForSelector('#toast:not([hidden])');
    // Fahrzeuge
    await page.click('nav >> text=Fahrzeuge & Orte');
    await page.click('text=+ Fahrzeug');
    const fzRow = page.locator('.card:has(h2:text("Fahrzeuge")) tbody tr').last();
    await fzRow.locator('input').nth(0).fill('VW Polo');
    await fzRow.locator('input').nth(1).fill('VB-70');
    await fzRow.locator('input').nth(2).fill('206371');
    await fzRow.locator('input').nth(2).blur();
    await page.locator('button:text("Fahrzeuge & Zeiträume speichern")').first().click();
    await page.waitForFunction(() => document.querySelector('.card tbody td.ro')?.textContent?.trim() !== '');
    await page.click('text=+ Zeitraum');
    const zRow = page.locator('.card:has(h2:text("Nutzungszeiträume")) tbody tr').last();
    await zRow.locator('select').selectOption({ index: 1 });
    await page.locator('button:text("Fahrzeuge & Zeiträume speichern")').last().click();
    await page.waitForTimeout(800);
    check(await page.locator('.card:has(h2:text("Nutzungszeiträume")) tbody tr').count() === 1, 'Zeitraum gespeichert');
    // Orte + Matrix
    for (const o of ['Zell am Moos', 'Eugendorf']) {
      await page.click('text=+ Ort');
      const r = page.locator('.card:has(h2:text("Orte & Distanzen")) tbody tr').last();
      await r.locator('input').first().fill(o); await r.locator('input').first().blur();
    }
    await page.click('text=Orte speichern');
    await page.waitForTimeout(800);
    for (const [a, b, k] of [['Oberhofen am Irrsee', 'Zell am Moos', 5], ['Oberhofen am Irrsee', 'Eugendorf', 28], ['Zell am Moos', 'Eugendorf', 25]]) {
      await page.fill('input[placeholder="Ort A"]', a); await page.fill('input[placeholder="Ort B"]', b); await page.fill('input[placeholder="km"]', String(k));
      await page.click('button:text("Hinzufügen")');
    }
    await page.click('text=Matrix speichern');
    await page.waitForTimeout(800);
    check(await page.locator('.card:has(h2:text("Distanz-Matrix")) tbody tr').count() === 3, 'Distanz-Matrix gespeichert');
    // Generieren
    await page.click('nav >> text=Generator');
    await page.locator('textarea').fill('Zell am Moos:KB,Schaden\nEugendorf:Angebot');
    await page.click('button:text("Fahrten generieren")');
    await page.waitForSelector('text=Fahrten für 12 Monat(e) generiert', { timeout: 60000 });
    check(true, 'Ganzes Jahr generiert');
    if (SHOTS) await page.screenshot({ path: SHOTS + '/generator.png', fullPage: true });
    // Monat bearbeiten
    await page.click('text=Fahrten ansehen');
    await page.waitForSelector('tr.sum');
    const first = page.locator('.card tbody tr').first();
    await first.locator('input[aria-label="Reiseweg – Ziel – Zweck"]').fill('Testfahrt geändert');
    await first.locator('input[aria-label="Reiseweg – Ziel – Zweck"]').blur();
    await page.click('text=Änderungen speichern');
    await page.waitForSelector('#toast:not([hidden])');
    check(await page.locator('input[aria-label="Reiseweg – Ziel – Zweck"]').first().inputValue() === 'Testfahrt geändert', 'Monat gespeichert');
    if (SHOTS) await page.screenshot({ path: SHOTS + '/fahrten.png' });
    // PDF
    await page.click('nav >> text=PDF-Export');
    const [dl] = await Promise.all([page.waitForEvent('download'), page.click('text=Jahres-PDF herunterladen')]);
    check(/Fahrtenbuch_Jahr_\d{4}\.pdf/.test(dl.suggestedFilename()), 'Jahres-PDF Download ' + dl.suggestedFilename());
  }

  // Alle Reiter durchklicken + Überbreite prüfen
  for (const t of ['Generator', 'Fahrten & Prüfung', 'Fahrzeuge & Orte', 'Privat-KM', 'HU', 'PDF-Export', 'Stammdaten', 'Admin']) {
    await page.click(`nav >> text="${t}"`);
    await page.waitForTimeout(500);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(over <= 1, `${t}: keine waagrechte Überbreite (${over}px)`);
    if (SHOTS && label === 'Handy') await page.screenshot({ path: `${SHOTS}/handy-${t.replace(/\W+/g, '_')}.png` });
  }
  check(errors.length === 0, 'keine JS-Fehler ' + (errors.length ? errors.join(' | ') : ''));
  await ctx.close();
}
await browser.close();
console.log(fails ? fails + ' FEHLER' : 'ALLES GRÜN');
process.exit(fails ? 1 : 0);
