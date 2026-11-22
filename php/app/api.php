<?php
// Fahrtenbuch – JSON-API. Aufruf: api.php?action=…  (Anmeldung per Header X-Auth-Token)
declare(strict_types=1);
define('FAHRTENBUCH', 1);

header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');

require __DIR__ . '/server/lib.php';
require __DIR__ . '/server/logic.php';
require __DIR__ . '/server/data.php';

set_exception_handler(function (Throwable $e) {
  if ($e instanceof InvalidArgumentException) fail(400, $e->getMessage());
  error_log('Fahrtenbuch: ' . $e->getMessage() . ' @ ' . $e->getFile() . ':' . $e->getLine());
  fail(500, 'Serverfehler: ' . $e->getMessage());
});
@set_time_limit(120);

$action = (string) ($_GET['action'] ?? '');
$in = json_input();
function in_str(string $k, string $d = ''): string { $v = json_input()[$k] ?? $d; return is_scalar($v) ? trim((string) $v) : $d; }
function in_int(string $k, int $d = 0): int { return safe_int(json_input()[$k] ?? null, $d) ?? $d; }
function in_arr(string $k): array { $v = json_input()[$k] ?? []; return is_array($v) ? $v : []; }
function year_payload(string $u, int $jahr, array $year): array {
  $out = [];
  foreach ($year as $m => $rows) $out[(string) $m] = $rows;
  return ['jahr' => $jahr, 'monate' => (object) $out, 'flags' => (object) pruefe_jahr($year), 'anker' => (object) anchor_get($u, $jahr), 'jahre' => jahre_load($u)];
}
function names_by_id(array $fz): array { $n = []; foreach ($fz as $f) $n[$f['id']] = $f['bezeichnung']; return $n; }

// Analyse-Schlüssel (nur lesen): vom Admin erzeugt, Header X-Api-Key, nur für admin_check und analyse_export
function analyse_key_ok(): bool {
  $k = (string) ($_SERVER['HTTP_X_API_KEY'] ?? '');
  $h = (string) setting('analyse_key_hash', ''); $bis = (string) setting('analyse_key_bis', '');
  if ($k === '' || $h === '' || $bis === '' || $bis < gmdate('Y-m-d H:i:s')) return false;
  return hash_equals($h, hash('sha256', $k));
}
function require_admin_or_key(): void { if (!analyse_key_ok()) require_admin(); }

switch ($action) {

/* ===================== Anmeldung ===================== */
case 'login': {
  $user = norm_username(in_str('username')); $pw = (string) ($in['password'] ?? '');
  if (too_many_attempts(client_ip()) || too_many_attempts('u:' . $user, 8)) fail(429, 'Zu viele Fehlversuche. Bitte 15 Minuten warten.');
  $r = q('SELECT * FROM fb_users WHERE username = ?', [$user])->fetch();
  if (!$r || !check_password($r, $pw)) { note_attempt(client_ip()); note_attempt('u:' . $user); fail(401, 'Benutzername oder Passwort falsch.'); }
  $r = q('SELECT * FROM fb_users WHERE id = ?', [$r['id']])->fetch();
  out(['token' => issue_token((int) $r['id']), 'user' => public_user($r)]);
}
case 'register': {
  $code = (string) setting('invite_code', '');
  if ($code === '') fail(403, 'Die Registrierung ist gesperrt. Bitte den Admin um einen Zugang bitten.');
  if (too_many_attempts(client_ip())) fail(429, 'Zu viele Versuche. Bitte 15 Minuten warten.');
  if (!hash_equals($code, in_str('invite'))) { note_attempt(client_ip()); fail(400, 'Der Einladungs-Code ist falsch. Bitte beim Admin nachfragen.'); }
  $user = norm_username(in_str('username')); $mail = mb_strtolower(in_str('email')); $pw = (string) ($in['password'] ?? '');
  if ($user === '' || mb_strlen($user) > 64) fail(400, 'Bitte einen Benutzernamen eintragen.');
  if (!valid_email($mail)) fail(400, 'Bitte eine gültige E-Mail-Adresse eintragen.');
  if (mb_strlen($pw) < 6) fail(400, 'Das Passwort braucht mindestens 6 Zeichen.');
  if (q('SELECT COUNT(*) FROM fb_users WHERE username = ?', [$user])->fetchColumn()) fail(400, 'Diesen Benutzernamen gibt es schon.');
  q('INSERT INTO fb_users (username, pass_hash, email) VALUES (?, ?, ?)', [$user, password_hash($pw, PASSWORD_DEFAULT), $mail]);
  out(['ok' => true]);
}
case 'reset_request': {
  $user = norm_username(in_str('username'));
  if (too_many_attempts('r:' . client_ip(), 5, 60)) fail(429, 'Zu viele Anfragen. Bitte später erneut versuchen.');
  note_attempt('r:' . client_ip());
  $r = q('SELECT * FROM fb_users WHERE username = ?', [$user])->fetch();
  if (!$r || !valid_email((string) $r['email'])) fail(400, 'Für diesen Benutzernamen ist keine E-Mail-Adresse hinterlegt. Bitte den Admin fragen.');
  $pw = random_password();
  send_mail([$r['email']], 'Ihr neues Passwort für das Fahrtenbuch', "Hallo,\n\nSie haben ein neues Passwort für das Fahrtenbuch angefordert.\n\nIhr neues Passwort lautet: $pw\n\nBitte ändern Sie dieses Passwort sofort nach dem ersten Login.\n\nViele Grüße\n" . setting('mail_from_name', 'Fahrtenbuch'));
  q('UPDATE fb_users SET pass_hash = ?, force_pw_change = 1 WHERE id = ?', [password_hash($pw, PASSWORD_DEFAULT), $r['id']]);
  out(['ok' => true]);
}
case 'me': { $u = require_user(); out(['user' => public_user($u)]); }
case 'logout': { $u = require_user(); q('DELETE FROM fb_tokens WHERE id = ?', [$u['token_id']]); out(['ok' => true]); }
case 'password': {
  $u = require_user(); $neu = (string) ($in['new'] ?? '');
  if (!(int) $u['force_pw_change'] && !check_password($u, (string) ($in['old'] ?? ''))) fail(400, 'Das bisherige Passwort stimmt nicht.');
  if (mb_strlen($neu) < 6) fail(400, 'Das neue Passwort braucht mindestens 6 Zeichen.');
  q('UPDATE fb_users SET pass_hash = ?, force_pw_change = 0 WHERE id = ?', [password_hash($neu, PASSWORD_DEFAULT), $u['id']]);
  q('DELETE FROM fb_tokens WHERE user_id = ? AND id <> ?', [$u['id'], $u['token_id']]);
  out(['ok' => true]);
}

/* ===================== Stammdaten, Fahrzeuge, Orte ===================== */
case 'init': {
  $u = require_user(); $n = $u['username'];
  out(['user' => public_user($u), 'settings' => settings_load($n), 'fahrzeuge' => fahrzeuge_load($n), 'zeitraeume' => zeitraeume_load($n),
    'orte' => orte_load($n), 'matrix' => matrix_rows($n), 'hu' => hu_load($n), 'jahre' => jahre_load($n), 'keyword_default' => DEFAULT_KEYWORD_TEXT]);
}
case 'settings_save': { $u = require_user(); settings_save($u['username'], in_arr('settings')); out(['settings' => settings_load($u['username'])]); }
case 'fahrzeuge_save': {
  $u = require_user(); $n = $u['username'];
  $fz = fahrzeuge_save($n, in_arr('fahrzeuge'));
  $hinweis = '';
  if (array_key_exists('zeitraeume', $in)) {
    $ids = array_column($fz, 'id'); $z = [];
    foreach (in_arr('zeitraeume') as $r) if (in_array(safe_int($r['fahrzeug_id'] ?? null, null), $ids, true)) $z[] = $r;
    $cnt = zeitraeume_save($n, $z);
    if ($cnt < count(in_arr('zeitraeume'))) $hinweis = (count(in_arr('zeitraeume')) - $cnt) . ' Zeitraum/Zeiträume ohne gültiges Fahrzeug oder Datum wurden nicht gespeichert.';
  }
  out(['fahrzeuge' => $fz, 'zeitraeume' => zeitraeume_load($n), 'hinweis' => $hinweis]);
}
case 'orte_save': { $u = require_user(); orte_save($u['username'], in_arr('orte')); out(['orte' => orte_load($u['username'])]); }
case 'matrix_save': {
  $u = require_user(); $n = $u['username'];
  $alt = [];
  foreach (matrix_rows($n) as $r) $alt[norm_ort($r['ort_a']) . '|' . norm_ort($r['ort_b'])] = $r;
  db()->beginTransaction();
  q('DELETE FROM fb_distanz_matrix WHERE username = ?', [$n]);
  foreach (in_arr('rows') as $r) {
    $a = trim((string) ($r['ort_a'] ?? '')); $b = trim((string) ($r['ort_b'] ?? '')); $km = safe_int($r['km'] ?? 0, 0);
    if ($a === '' || $b === '' || $km <= 0) continue;
    $k1 = norm_ort($a) . '|' . norm_ort($b); $k2 = norm_ort($b) . '|' . norm_ort($a);
    $o = $alt[$k1] ?? $alt[$k2] ?? null;
    $quelle = ($o && (int) $o['km'] === $km) ? $o['quelle'] : 'manuell';
    matrix_upsert($n, $a, $b, $km, $quelle);
  }
  db()->commit();
  out(['matrix' => matrix_rows($n)]);
}
case 'import': {
  $u = require_user(); $n = $u['username'];
  require __DIR__ . '/server/import.php';
  $typ = (string) ($_GET['typ'] ?? '');
  $f = $_FILES['file'] ?? null;
  if (!$f || ($f['error'] ?? 1) !== UPLOAD_ERR_OK) fail(400, 'Die Datei kam nicht an. Bitte noch einmal wählen.');
  if ($f['size'] > 5 * 1024 * 1024) fail(400, 'Die Datei ist zu groß (max. 5 MB).');
  $rows = read_table_file($f['tmp_name'], (string) $f['name']);
  if ($typ === 'fahrzeuge') {
    $fz = import_fahrzeuge($rows); $by = [];
    foreach (fahrzeuge_load($n) as $x) $by[mb_strtolower(trim($x['bezeichnung']))] = $x['id'];
    foreach ($fz as &$x) $x['id'] = $by[mb_strtolower($x['bezeichnung'])] ?? null;
    out(['fahrzeuge' => $fz]);
  }
  if ($typ === 'zeitraeume') out(['zeitraeume' => import_zeitraeume($rows, fahrzeuge_load($n))]);
  if ($typ === 'orte') out(['orte' => import_orte($rows)]);
  if ($typ === 'keywords') {
    $kw = import_keywords($rows); $by = [];
    foreach ($kw as $k) $by[$k['ort']][] = $k['zweck'];
    $txt = [];
    foreach ($by as $o => $z) $txt[] = $o . ':' . implode(',', array_filter($z, 'strlen'));
    out(['keyword_text' => implode("\n", $txt), 'anzahl' => count($kw)]);
  }
  fail(400, 'Unbekannter Import-Typ.');
}

/* ===================== Jahr / Generator ===================== */
case 'year_get': {
  $u = require_user(); $n = $u['username']; $jahr = in_int('jahr', (int) date('Y'));
  out(year_payload($n, $jahr, year_load($n, $jahr)) + ['gen' => (object) gen_settings_load($n, $jahr)]);
}
case 'generate': {
  $u = require_user(); $n = $u['username']; $jahr = in_int('jahr');
  if ($jahr < 2000 || $jahr > 2100) fail(400, 'Bitte ein gültiges Jahr wählen.');
  $g = in_arr('gen');
  $fz = fahrzeuge_load($n); $zr = zeitraeume_load($n);
  if (!$fz || !$zr) fail(400, 'Für die Generierung werden Fahrzeuge und Zeiträume benötigt (Tab „Fahrzeuge & Orte“).');
  $kwText = (string) ($g['keyword_text'] ?? DEFAULT_KEYWORD_TEXT);
  $keywords = keywords_aus_text($kwText);
  if (!$keywords) fail(400, 'Bitte mindestens einen Ort mit Zweck eintragen (Format „Ort:Zweck1,Zweck2“).');
  $modus = ($g['modus'] ?? '') === 'Ganzes Jahr' ? 'Ganzes Jahr' : 'Einzelner Monat';
  $monat = max(1, min(12, safe_int($g['generierungs_monat'] ?? 1, 1)));
  $wochen = max(0, min(4, safe_int($g['anzahl_wochen'] ?? 0, 0)));
  $start = parse_date_iso($g['start_woche_1'] ?? null) ?? "$jahr-04-01";
  $save = ['modus' => $modus, 'generierungs_monat' => $monat, 'anzahl_wochen' => $wochen, 'verteilung' => (string) ($g['verteilung'] ?? '1x4 Wochen'),
    'start_woche_1' => $start, 'urlaub_fahrzeug_name' => (string) ($g['urlaub_fahrzeug_name'] ?? ''), 'urlaub_km_min' => safe_int($g['urlaub_km_min'] ?? 30, 30),
    'urlaub_km_max' => safe_int($g['urlaub_km_max'] ?? 80, 80), 'prob_werktag' => safe_int($g['prob_werktag'] ?? 75, 75),
    'prob_feiertag_urlaub' => safe_int($g['prob_feiertag_urlaub'] ?? 5, 5), 'target_km_min' => safe_int($g['target_km_min'] ?? 1650, 1650),
    'target_km_max' => safe_int($g['target_km_max'] ?? 2000, 2000), 'hauptfahrzeug_name' => (string) ($g['hauptfahrzeug_name'] ?? ''),
    'hauptfahrzeug_anteil' => safe_int($g['hauptfahrzeug_anteil'] ?? 70, 70), 'keyword_text' => $kwText];
  gen_settings_save($n, $jahr, $save);
  $monate = $modus === 'Ganzes Jahr' ? range(1, 12) : [$monat];
  $anchor = anchor_get_or_create($n, $jahr, $fz);
  $fzGen = array_map(function ($f) use ($anchor) { $f['start_km_vorjahr'] = $anchor[$f['id']] ?? $f['start_km_vorjahr']; return $f; }, $fz);
  $p = $save + ['vacation_days' => $wochen > 0 ? urlaubs_tage($wochen, $save['verteilung'], $start) : [], 'distanzen' => distanzen_load($n), 'matrix' => matrix_load($n)];
  [$gen, $fehlende] = generiere_monate($jahr, $monate, settings_load($n), $fzGen, $zr, $keywords, $p);
  $fix = 0;
  foreach ($gen as &$rows) $fix += korrigiere_geschwindigkeiten($rows);
  unset($rows);
  [$year, $end] = year_commit($n, $jahr, $gen, $fz);
  // HU-Einträge in neu generierten Monaten dürfen wieder angewendet werden
  foreach ($monate as $m) q('UPDATE fb_hu SET angewendet_am = NULL WHERE username = ? AND YEAR(datum) = ? AND MONTH(datum) = ?', [$n, $jahr, $m]);
  $names = names_by_id($fz); $endList = [];
  foreach ($end as $id => $km) if (isset($names[$id])) $endList[] = ['fahrzeug' => $names[$id], 'km' => $km];
  out(year_payload($n, $jahr, $year) + ['gen' => (object) $save, 'fehlende' => $fehlende, 'endkm' => $endList, 'zeit_korrekturen' => $fix, 'generiert' => $monate]);
}
case 'month_save': {
  $u = require_user(); $n = $u['username']; $jahr = in_int('jahr'); $monat = in_int('monat');
  if ($monat < 1 || $monat > 12) fail(400, 'Ungültiger Monat.');
  $fz = fahrzeuge_load($n); $byName = [];
  foreach ($fz as $f) $byName[mb_strtolower(trim($f['bezeichnung']))] = $f['id'];
  $rows = [];
  foreach (in_arr('rows') as $r) {
    $r = fahrt_norm($r);
    if ($r['datum'] === '') continue;
    if ((int) substr($r['datum'], 0, 4) !== $jahr || (int) substr($r['datum'], 5, 2) !== $monat) fail(400, 'Das Datum ' . fmt_datum($r['datum']) . ' gehört nicht zu ' . MONATE[$monat - 1] . " $jahr.");
    $id = $byName[mb_strtolower($r['fahrzeug'])] ?? null;
    if ($id !== null) $r['fahrzeug_id'] = $id; elseif ($r['fahrzeug'] === '' || $r['fahrzeug'] === 'Kein Fahrzeug') $r['fahrzeug_id'] = null;
    if ($r['dauer'] === '00:00' && $r['abf'] !== '00:00') $r['dauer'] = dauer_string($r['abf'], $r['ank']);
    $rows[] = $r;
  }
  [$year] = year_commit($n, $jahr, [$monat => $rows], $fz);
  out(year_payload($n, $jahr, $year));
}
case 'anchor_reset': { $u = require_user(); anchor_delete($u['username'], in_int('jahr')); out(['ok' => true]); }
case 'year_delete': { $u = require_user(); year_delete($u['username'], in_int('jahr')); out(['ok' => true, 'jahre' => jahre_load($u['username'])]); }

/* ===================== Privat-KM ===================== */
case 'privat': {
  $u = require_user(); $n = $u['username']; $jahr = in_int('jahr'); $fid = in_int('fahrzeug_id');
  $fz = fahrzeuge_load($n); $names = names_by_id($fz);
  if (!isset($names[$fid])) fail(400, 'Bitte ein Fahrzeug wählen.');
  $year = year_load($n, $jahr);
  $anchor = anchor_get_or_create($n, $jahr, $fz);
  [$year, , $msg] = verteile_privat_km($year, $fid, in_int('total_km'), $names[$fid], [
    'anzahl_gross' => in_int('anzahl_gross', 4), 'gross_min' => in_int('gross_min', 300), 'gross_max' => in_int('gross_max', 800),
    'normal_min' => in_int('normal_min', 5), 'normal_max' => in_int('normal_max', 45)], $anchor);
  [$year] = year_commit($n, $jahr, $year, $fz);
  out(year_payload($n, $jahr, $year) + ['meldungen' => $msg]);
}

/* ===================== HU ===================== */
case 'hu_save': {
  $u = require_user(); $n = $u['username'];
  $ids = array_column(fahrzeuge_load($n), 'id'); $alt = [];
  foreach (hu_load($n) as $h) $alt[$h['id']] = $h;
  $fehler = []; $keep = [];
  db()->beginTransaction();
  foreach (in_arr('rows') as $i => $r) {
    $z = $i + 1;
    $fid = safe_int($r['fahrzeug_id'] ?? null, null); $d = parse_date_iso($r['datum'] ?? null); $w = trim((string) ($r['werkstattort'] ?? ''));
    if ($fid === null && !$d && $w === '') continue;
    if (!in_array($fid, $ids, true)) { $fehler[] = "Zeile $z: Fahrzeug fehlt"; continue; }
    if (!$d) { $fehler[] = "Zeile $z: Datum fehlt/ungültig"; continue; }
    if ($w === '') { $fehler[] = "Zeile $z: Werkstattort fehlt"; continue; }
    $vals = [$fid, $d, max(0, safe_int($r['km_at_hu'] ?? 0, 0)), $w, implode(',', stopps_liste($r['stopps_vor_hu'] ?? '')), implode(',', stopps_liste($r['stopps_nach_hu'] ?? ''))];
    $id = safe_int($r['id'] ?? null, null);
    if ($id !== null && isset($alt[$id])) {
      q('UPDATE fb_hu SET fahrzeug_id = ?, datum = ?, km_at_hu = ?, werkstattort = ?, stopps_vor_hu = ?, stopps_nach_hu = ? WHERE id = ? AND username = ?', array_merge($vals, [$id, $n]));
      $keep[] = $id;
    } else {
      q('INSERT INTO fb_hu (fahrzeug_id, datum, km_at_hu, werkstattort, stopps_vor_hu, stopps_nach_hu, username) VALUES (?, ?, ?, ?, ?, ?, ?)', array_merge($vals, [$n]));
      $keep[] = (int) db()->lastInsertId();
    }
  }
  if ($fehler) { db()->rollBack(); fail(400, implode(' · ', $fehler)); }
  foreach (array_diff(array_keys($alt), $keep) as $id) q('DELETE FROM fb_hu WHERE id = ? AND username = ?', [$id, $n]);
  db()->commit();
  out(['hu' => hu_load($n)]);
}
case 'hu_apply': {
  $u = require_user(); $n = $u['username']; $force = !empty($in['force']);
  $all = hu_load($n);
  // „angewendet“ zählt nur, wenn die HU-Fahrt auch wirklich in den Fahrten steht (Umzug hat pauschal markiert)
  $todo = array_values(array_filter($all, function ($h) use ($force) { return $force || $h['angewendet_am'] === null || !$h['hu_fahrt']; }));
  if (!$todo) fail(400, $all ? 'Alle HU-Einträge wurden bereits angewendet. Nochmal anwenden würde die Kilometer doppelt verändern.' : 'Keine HU-Einträge vorhanden.');
  $fz = fahrzeuge_load($n); $names = names_by_id($fz); $s = settings_load($n);
  $byYear = [];
  foreach ($todo as $h) $byYear[(int) substr($h['datum'], 0, 4)][] = $h;
  ksort($byYear);
  $msg = []; $last = null;
  foreach ($byYear as $jahr => $list) {
    $year = year_load($n, $jahr);
    if (!$year) { $msg[] = "**$jahr**: keine gespeicherten Fahrten – zuerst im Generator generieren."; continue; }
    $corr = array_map(function ($h) { return ['fahrzeug_id' => $h['fahrzeug_id'], 'datum' => $h['datum'], 'km_at_hu' => $h['km_at_hu'], 'werkstattort' => $h['werkstattort'],
      'stopps_vor' => stopps_liste($h['stopps_vor_hu']), 'stopps_nach' => stopps_liste($h['stopps_nach_hu'])]; }, $list);
    $anchor = anchor_get_or_create($n, $jahr, $fz);
    $zr = array_map(function ($z) { return [$z['von'], $z['bis'], (int) $z['fahrzeug_id']]; }, zeitraeume_load($n));
    $huDates = [];
    foreach ($all as $h) if ((int) substr($h['datum'], 0, 4) === $jahr) $huDates[$h['fahrzeug_id']][] = $h['datum'];
    [$year, , $m, $ok] = wende_hu_an($year, $anchor, $names, $corr, (string) $s['wohnort'], distanzen_load($n), matrix_load($n), $zr, $huDates);
    $msg = array_merge($msg, $m);
    if (!$ok) continue;
    [$year] = year_commit($n, $jahr, $year, $fz);
    foreach ($ok as $i) q('UPDATE fb_hu SET angewendet_am = UTC_TIMESTAMP() WHERE id = ?', [$list[$i]['id']]);
    $last = $jahr;
  }
  out(['meldungen' => $msg, 'hu' => hu_load($n), 'jahr' => $last]);
}

/* ===================== PDF ===================== */
case 'pdf': {
  $u = require_user(); $n = $u['username'];
  require __DIR__ . '/server/pdf.php';
  $jahr = in_int('jahr'); $typ = in_str('typ'); $year = year_load($n, $jahr);
  $fz = fahrzeuge_load($n); $s = settings_load($n);
  if ($typ === 'monat') {
    $m = in_int('monat');
    if (empty($year[$m])) fail(400, 'Keine Fahrten für ' . (MONATE[$m - 1] ?? '?') . " $jahr gespeichert.");
    $pdf = pdf_monat($year[$m], $m, $jahr, $s, $fz); $fn = sprintf('Fahrtenbuch_%d_%02d.pdf', $jahr, $m);
  } else {
    if (!$year) fail(400, "Keine Fahrten im Jahr $jahr gespeichert.");
    $pdf = pdf_jahr($year, $jahr, $s, $fz); $fn = "Fahrtenbuch_Jahr_$jahr.pdf";
  }
  header('Content-Type: application/pdf');
  header('Content-Disposition: attachment; filename="' . $fn . '"');
  header('Content-Length: ' . strlen($pdf));
  echo $pdf;
  exit;
}

/* ===================== Online-Karte (schrittweise) ===================== */
case 'geo_start': {
  $u = require_user(); $n = $u['username']; $s = settings_load($n);
  $home = ort_clean(trim((string) $s['wohnort'])); $dienst = ort_clean(trim((string) $s['dienstort']));
  if ($home === '') fail(400, 'Kein Wohnort in den Stammdaten hinterlegt – bitte zuerst im Tab „Stammdaten“ eintragen.');
  $list = []; $seen = [];
  $kwOrte = [];
  foreach (jahre_load($n) as $j) { $g = gen_settings_load($n, $j); foreach (keywords_aus_text((string) ($g['keyword_text'] ?? '')) as $k) $kwOrte[] = $k['ort']; }
  foreach (hu_load($n) as $h) $kwOrte = array_merge($kwOrte, [$h['werkstattort']], stopps_liste($h['stopps_vor_hu']), stopps_liste($h['stopps_nach_hu']));
  foreach (array_merge([$home, $dienst], array_column(orte_load($n), 'ort'), $kwOrte, array_map('strval', in_arr('zusatz'))) as $o) {
    $o = trim($o); $k = norm_ort($o);
    if ($o === '' || isset($seen[$k])) continue;
    $seen[$k] = true; $list[] = $o;
  }
  $geo = geo_load($n);
  out(['orte' => array_map(function ($o) use ($geo) { $g = $geo[norm_ort($o)] ?? null; return ['ort' => $o, 'cached' => (bool) ($g['ok'] ?? false)]; }, $list)]);
}
case 'geo_geocode': {
  $u = require_user(); $n = $u['username'];
  require __DIR__ . '/server/routing.php';
  $res = [];
  $s = settings_load($n); $hk = norm_ort(ort_clean(trim((string) $s['wohnort'])));
  $hg = geo_load($n)[$hk] ?? null; $nahe = ($hg && $hg['ok']) ? [$hg['lat'], $hg['lon']] : null;
  foreach (array_slice(in_arr('orte'), 0, 6) as $o) {
    $o = trim((string) $o);
    if ($o === '') continue;
    $g = geocodiere_ort($o, norm_ort($o) === $hk ? null : $nahe);
    if (norm_ort($o) === $hk && $g) $nahe = [$g['lat'], $g['lon']];
    geo_save($n, $o, $g);
    $res[] = ['ort' => $o, 'ok' => (bool) $g, 'name' => $g['display_name'] ?? ''];
    usleep(GEO_PAUSE_US);
  }
  out(['ergebnisse' => $res]);
}
case 'geo_pairs': {
  $u = require_user(); $n = $u['username']; $nur = !empty($in['nur_fehlende']);
  $geo = geo_load($n); $vorh = [];
  foreach (matrix_rows($n) as $r) $vorh[norm_ort($r['ort_a']) . '|' . norm_ort($r['ort_b'])] = $r['quelle'];
  $keys = [];
  foreach (in_arr('orte') as $o) { $k = norm_ort($o); if ($k !== '' && ($geo[$k]['ok'] ?? false)) $keys[$k] = true; }
  $keys = array_keys($keys); $pairs = [];
  for ($i = 0; $i < count($keys); $i++) for ($j = $i + 1; $j < count($keys); $j++) {
    $a = $keys[$i]; $b = $keys[$j];
    if (strcmp($a, $b) > 0) [$a, $b] = [$b, $a];
    $q = $vorh["$a|$b"] ?? null;
    if ($q === 'manuell') continue;            // manuelle Korrekturen werden nie automatisch überschrieben
    if ($nur && $q !== null) continue;
    $pairs[] = [$a, $b];
  }
  out(['pairs' => $pairs]);
}
case 'geo_route': {
  $u = require_user(); $n = $u['username'];
  require __DIR__ . '/server/routing.php';
  $geo = geo_load($n); $res = [];
  foreach (array_slice(in_arr('pairs'), 0, 12) as $p) {
    [$a, $b] = [(string) ($p[0] ?? ''), (string) ($p[1] ?? '')];
    $ga = $geo[$a] ?? null; $gb = $geo[$b] ?? null;
    if (!($ga['ok'] ?? false) || !($gb['ok'] ?? false)) continue;
    $km = routen_km($ga['lat'], $ga['lon'], $gb['lat'], $gb['lon']); $q = 'osrm';
    if ($km === null) { $km = haversine_km($ga['lat'], $ga['lon'], $gb['lat'], $gb['lon']); $q = 'haversine'; }
    matrix_upsert($n, $ga['ort'], $gb['ort'], max(1, $km), $q);
    $res[] = ['a' => $ga['ort'], 'b' => $gb['ort'], 'km' => $km, 'quelle' => $q];
    usleep(OSRM_PAUSE_US);
  }
  out(['ergebnisse' => $res]);
}
case 'geo_finish': {
  // km einfach (Wohnort → Ort) automatisch aus der Matrix übernehmen
  $u = require_user(); $n = $u['username']; $s = settings_load($n);
  $home = norm_ort(ort_clean(trim((string) $s['wohnort']))); $m = matrix_load($n);
  $orte = orte_load($n); $akt = [];
  foreach ($orte as &$o) {
    $km = matrix_km($m, $home, $o['ort']);
    if ($km !== null && $km !== $o['km_einfach']) { $akt[] = $o['ort'] . ': ' . ($o['km_einfach'] ?? '–') . " → $km km"; $o['km_einfach'] = $km; }
  }
  unset($o);
  orte_save($n, $orte);
  out(['orte' => orte_load($n), 'matrix' => matrix_rows($n), 'aktualisiert' => $akt]);
}

/* ===================== Admin ===================== */
case 'admin_users': {
  require_admin();
  out(['users' => q('SELECT username, email, is_admin, force_pw_change, created_at FROM fb_users ORDER BY username')->fetchAll()]);
}
case 'admin_user_save': {
  $me = require_admin(); $user = norm_username(in_str('username'));
  $r = q('SELECT * FROM fb_users WHERE username = ?', [$user])->fetch();
  $mail = mb_strtolower(in_str('email')); $pw = (string) ($in['password'] ?? '');
  if ($mail !== '' && !valid_email($mail)) fail(400, 'Bitte eine gültige E-Mail-Adresse eintragen.');
  if ($pw !== '' && mb_strlen($pw) < 6) fail(400, 'Das Passwort braucht mindestens 6 Zeichen.');
  if (!$r) {
    if ($user === '') fail(400, 'Bitte einen Benutzernamen eintragen.');
    if ($pw === '') fail(400, 'Für einen neuen Zugang bitte ein Start-Passwort eintragen.');
    q('INSERT INTO fb_users (username, pass_hash, email, force_pw_change, is_admin) VALUES (?, ?, ?, 1, ?)', [$user, password_hash($pw, PASSWORD_DEFAULT), $mail, empty($in['is_admin']) ? 0 : 1]);
  } else {
    if ($mail !== '') q('UPDATE fb_users SET email = ? WHERE id = ?', [$mail, $r['id']]);
    if ($pw !== '') { q('UPDATE fb_users SET pass_hash = ?, force_pw_change = 1 WHERE id = ?', [password_hash($pw, PASSWORD_DEFAULT), $r['id']]); q('DELETE FROM fb_tokens WHERE user_id = ?', [$r['id']]); }
    if (array_key_exists('is_admin', $in) && (int) $r['id'] !== (int) $me['id']) q('UPDATE fb_users SET is_admin = ? WHERE id = ?', [empty($in['is_admin']) ? 0 : 1, $r['id']]);
  }
  out(['ok' => true]);
}
case 'admin_user_delete': {
  $me = require_admin(); $user = norm_username(in_str('username'));
  if ($user === $me['username']) fail(400, 'Du kannst dich nicht selbst löschen.');
  foreach (['fb_settings', 'fb_fahrzeuge', 'fb_zeitraeume', 'fb_fahrten', 'fb_hu', 'fb_orte', 'fb_jahres_start_km', 'fb_generation_settings', 'fb_ort_koordinaten', 'fb_distanz_matrix', 'fb_users'] as $t)
    q("DELETE FROM $t WHERE username = ?", [$user]);
  out(['ok' => true]);
}
case 'admin_view': {
  require_admin(); $user = norm_username(in_str('username'));
  out(['settings' => settings_load($user), 'fahrzeuge' => fahrzeuge_load($user), 'jahre' => jahre_load($user)]);
}
case 'admin_config': {
  require_admin();
  $keys = ['mail_mode', 'mail_from', 'mail_from_name', 'smtp_host', 'smtp_port', 'smtp_secure', 'smtp_user', 'graph_tenant', 'graph_client', 'invite_code'];
  $c = [];
  foreach ($keys as $k) $c[$k] = (string) setting($k, '');
  $c['analyse_bis'] = (setting('analyse_key_hash', '') !== '' && setting('analyse_key_bis', '') > gmdate('Y-m-d H:i:s')) ? (string) setting('analyse_key_bis') : '';
  $c['smtp_pass_set'] = setting('smtp_pass', '') !== ''; $c['graph_secret_set'] = setting('graph_secret', '') !== '';
  out(['config' => $c]);
}
case 'admin_config_save': {
  require_admin(); $c = in_arr('config');
  foreach (['mail_mode', 'mail_from', 'mail_from_name', 'smtp_host', 'smtp_port', 'smtp_secure', 'smtp_user', 'graph_tenant', 'graph_client', 'invite_code'] as $k)
    if (array_key_exists($k, $c)) setting_save($k, trim((string) $c[$k]));
  foreach (['smtp_pass', 'graph_secret'] as $k) if (($c[$k] ?? '') !== '') setting_save($k, (string) $c[$k]);
  out(['ok' => true]);
}
case 'admin_mail_test': {
  require_admin(); $to = in_str('to');
  if (!valid_email($to)) fail(400, 'Bitte eine gültige E-Mail-Adresse eintragen.');
  try { send_mail([$to], 'Fahrtenbuch – Test-E-Mail', "Hallo,\n\ndiese Test-E-Mail zeigt: Der E-Mail-Versand des Fahrtenbuchs funktioniert.\n"); }
  catch (Throwable $e) { fail(400, $e->getMessage()); }
  out(['ok' => true]);
}
case 'admin_check': {
  require_admin_or_key();
  require __DIR__ . '/server/check.php';
  out(['abschnitte' => systempruefung(), 'zeit' => (new DateTimeImmutable('now', new DateTimeZone('Europe/Vienna')))->format('d.m.Y H:i')]);
}
case 'analyse_export': {
  // Alle Daten aller Benutzer lesend (für die Analyse); Passwörter/Schlüssel sind NICHT enthalten
  require_admin_or_key();
  $out = [];
  foreach (q('SELECT username, email, is_admin, force_pw_change, created_at FROM fb_users ORDER BY username')->fetchAll() as $usr) {
    $n = $usr['username']; $jahre = jahre_load($n); $y = []; $a = []; $g = [];
    foreach ($jahre as $j) { $y[$j] = year_load($n, $j); $g[$j] = gen_settings_load($n, $j); }
    foreach (q('SELECT DISTINCT jahr FROM fb_jahres_start_km WHERE username = ?', [$n])->fetchAll(PDO::FETCH_COLUMN) as $j) $a[$j] = anchor_get($n, (int) $j);
    $out[] = ['user' => $usr, 'settings' => settings_load($n), 'fahrzeuge' => fahrzeuge_load($n), 'zeitraeume' => zeitraeume_load($n), 'orte' => orte_load($n),
      'matrix' => matrix_rows($n), 'anker' => $a, 'gen' => $g, 'hu' => hu_load($n), 'fahrten' => $y];
  }
  out(['benutzer' => $out, 'zeit' => gmdate('c')]);
}
case 'admin_analyse_key': {
  require_admin();
  if (!empty($in['sperren'])) { setting_save('analyse_key_hash', ''); setting_save('analyse_key_bis', ''); out(['ok' => true]); }
  $key = 'fbk_' . bin2hex(random_bytes(24));
  setting_save('analyse_key_hash', hash('sha256', $key)); setting_save('analyse_key_bis', gmdate('Y-m-d H:i:s', time() + 14 * 86400));
  out(['key' => $key, 'bis' => setting('analyse_key_bis')]);
}
case 'admin_rechain': {
  // Kilometerkette eines Jahres ab dem gesperrten Anker neu aufbauen (nur abfahrt_km ändert sich, km bleiben)
  require_admin(); $user = norm_username(in_str('username')); $jahr = in_int('jahr');
  if (!year_load($user, $jahr)) fail(400, "Keine Fahrten für $user im Jahr $jahr.");
  [, $end] = year_commit($user, $jahr, null, fahrzeuge_load($user));
  out(['ok' => true, 'endkm' => $end]);
}
case 'admin_supabase': {
  $me = require_admin();
  require __DIR__ . '/server/migrate.php';
  @set_time_limit(300);
  out(supabase_import_table(in_str('url'), in_str('key'), in_str('table'), $me));
}

default:
  fail(404, 'Unbekannte Aktion.');
}
