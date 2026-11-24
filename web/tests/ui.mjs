// Browser-Test gegen eine laufende Instanz (z. B. KEEP=1 python3 tests/e2e.py):
//   BASE=http://127.0.0.1:PORT/fahrtenbuch/ SHOTS=/pfad node tests/ui.mjs
// Klickt alle Tabs durch (Desktop + Handy), generiert einen Monat, speichert, laedt ein PDF.
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium, devices } = require('playwright');
const BASE = process.env.BASE, SHOTS = process.env.SHOTS || '.';
let fails = 0;
const ok = (c, t) => { console.log((c ? 'ok   ' : 'FEHLER ') + t); if (!c) fails++; };

const b = await chromium.launch();
for (const [name, opts] of [['desktop', { viewport: { width: 1400, height: 950 } }], ['handy', devices['iPhone 13']]]) {
  const ctx = await b.newContext({ ...opts, acceptDownloads: true });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { if (m.type() === 'error' && !/fonts\.g/.test(m.text())) errs.push(m.text()); });
  await p.goto(BASE);
  await p.getByLabel('Benutzername oder E-Mail').fill('christian mayerhofer');
  await p.getByLabel('Passwort').fill('geheim123');
  await p.getByRole('button', { name: 'Anmelden' }).click();
  await p.getByRole('button', { name: 'Generator' }).waitFor();
  ok(true, `${name}: Login`);
  for (const tab of ['Stammdaten', 'Generator', 'Fahrzeuge & Orte', 'Privat-KM', 'Prüfung', 'Export & HU', 'Admin']) {
    await p.locator('nav').getByRole('button', { name: tab, exact: true }).click();
    await p.waitForTimeout(900);
    const txt = await p.locator('main').innerText();
    ok(!/Lade…/.test(txt) && txt.length > 50, `${name}: Tab ${tab} geladen`);
    const breite = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(breite <= 1, `${name}: Tab ${tab} ohne waagrechte Überbreite (${breite})`);
    await p.screenshot({ path: `${SHOTS}/${name}-${tab.replace(/\W+/g, '_')}.png`, fullPage: false });
  }
  if (name === 'desktop') {
    // Generator: Jahr 2025, Einzelmonat Mai generieren, Monat bearbeiten + speichern, PDF
    await p.locator('nav').getByRole('button', { name: 'Generator', exact: true }).click();
    await p.getByLabel('Jahr öffnen').selectOption('2025');
    await p.waitForTimeout(1200);
    await p.getByLabel('Generierungs-Modus').selectOption('Einzelner Monat');
    await p.getByLabel('Monat', { exact: true }).selectOption('5');
    await p.getByRole('button', { name: /Fahrten für Mai 2025 generieren/ }).click();
    await p.getByText(/Fahrten für 1 Monat\(e\) generiert/).waitFor({ timeout: 30000 });
    ok(true, 'Generator: Mai 2025 generiert');
    ok(!/(^|\n)\s*null\s*(\n|$)/.test(await p.locator('main').innerText()), 'kein „null“ in der Anzeige');
    ok(await p.getByRole('button', { name: 'Ort korrigieren' }).count() > 0, 'fehlende Orte mit Knopf „Ort korrigieren“');
    await p.screenshot({ path: `${SHOTS}/desktop-generiert.png`, fullPage: true });
    const kmFeld = p.locator('table tbody tr').first().locator('td.num input').first();
    await kmFeld.fill('77');
    await p.getByRole('button', { name: 'Änderungen speichern' }).click();
    await p.getByText(/Kilometerkette des Jahres neu aufgebaut/).waitFor({ timeout: 20000 });
    ok(true, 'Monat bearbeitet und gespeichert');
    const [dl] = await Promise.all([p.waitForEvent('download'), p.getByRole('button', { name: /Monats-PDF Mai/ }).click()]);
    ok(/Fahrtenbuch_2025_05\.pdf/.test(dl.suggestedFilename()), 'Monats-PDF heruntergeladen: ' + dl.suggestedFilename());
    // Gesamt-Abgleich im Pruefung-Tab
    await p.locator('nav').getByRole('button', { name: 'Prüfung', exact: true }).click();
    await p.getByRole('button', { name: /Gesamt-Abgleich \d+ starten/ }).click();
    await p.getByText(/Dienstfahrten \d+ geprüft/).waitFor({ timeout: 20000 });
    ok(true, 'Gesamt-Abgleich läuft');
    await p.screenshot({ path: `${SHOTS}/desktop-abgleich.png`, fullPage: false });
    // Orte-Check zeigt Herkunft
    await p.locator('nav').getByRole('button', { name: 'Fahrzeuge & Orte', exact: true }).click();
    await p.getByText('Orte-Check', { exact: true }).waitFor();
    ok(await p.getByText('Verwendet in').count() > 0, 'Orte-Check mit Spalte „Verwendet in“');
    // Stammdaten speichern
    await p.locator('nav').getByRole('button', { name: 'Stammdaten', exact: true }).click();
    await p.getByRole('button', { name: 'Stammdaten speichern' }).click();
    await p.getByText('Stammdaten gespeichert.').waitFor();
    ok(true, 'Stammdaten gespeichert');
  }
  ok(errs.length === 0, `${name}: keine JS-Fehler ${errs.join(' | ')}`);
  await ctx.close();
}
await b.close();
console.log(fails ? `\n${fails} FEHLER` : '\nUI-TEST BESTANDEN');
process.exit(fails ? 1 : 0);
