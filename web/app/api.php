<?php
// Fahrtenbuch - JSON-API. Aufruf: api.php?action=..., Anmeldung per Header X-Auth-Token
declare(strict_types=1);
define('FAHRTENBUCH', 1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
@set_time_limit(120);

require __DIR__ . '/server/lib.php';
require __DIR__ . '/server/logic.php';

set_exception_handler(function (Throwable $e) {
  error_log('Fahrtenbuch: ' . $e->getMessage() . ' @ ' . $e->getFile() . ':' . $e->getLine());
  $msg = $e instanceof InvalidArgumentException || $e instanceof RuntimeException ? $e->getMessage() : 'Interner Fehler: ' . $e->getMessage();
  out(['error' => $msg], $e instanceof InvalidArgumentException ? 400 : 500);
});

if (cfg('db_name', '') === '') fail(503, 'Die App ist noch nicht installiert. Bitte installieren.php aufrufen.');

$action = (string) ($_GET['action'] ?? '');
$in = json_input();
$pdo = db();

/* ---------- Daten-Helfer ---------- */
function q(string $sql, array $args = []): PDOStatement { $st = db()->prepare($sql); $st->execute($args); return $st; }
function stammdaten(string $u): array {
  $r = q('SELECT * FROM fb_stammdaten WHERE username = ?', [$u])->fetch();
  return $r ?: ['username' => $u, 'name' => '', 'pnr' => '', 'wohnort' => '', 'dienstort' => '', 'entfernung' => 25,
    'taggeld_min_stunden' => 5, 'taggeld_basis' => 10, 'taggeld_stufung' => 2.5, 'taggeld_max_betrag' => 30, 'taggeld_max_stunden' => 13, 'km_geld' => 0.42];
}
function fahrzeuge(string $u): array {
  return array_map(function ($r) { foreach (['id', 'start_km_vorjahr', 'privat_km_min', 'privat_km_max', 'dienstlich_quote'] as $k) $r[$k] = (int) $r[$k]; unset($r['username']); return $r; },
    q('SELECT * FROM fb_fahrzeuge WHERE username = ? ORDER BY id', [$u])->fetchAll());
}
function zeitraeume(string $u): array {
  return array_map(function ($r) { return ['fahrzeug_id' => (int) $r['fahrzeug_id'], 'von' => $r['von'], 'bis' => $r['bis']]; },
    q('SELECT fahrzeug_id, von, bis FROM fb_zeitraeume WHERE username = ? ORDER BY von, id', [$u])->fetchAll());
}
function lade_jahr(string $u, int $jahr): array {
  $out = [];
  foreach (q('SELECT datum, fahrzeug_id, fahrzeug, route, km_d, km_p, abf, ank, dauer, abfahrt_km, monat FROM fb_fahrten WHERE username = ? AND jahr = ? ORDER BY datum, id', [$u, $jahr])->fetchAll() as $r) {
    $m = (int) $r['monat']; unset($r['monat']);
    $r['fahrzeug_id'] = $r['fahrzeug_id'] === null ? null : (int) $r['fahrzeug_id'];
    foreach (['km_d', 'km_p', 'abfahrt_km'] as $k) $r[$k] = (int) $r[$k];
    $out[$m][] = $r;
  }
  return $out;
}
function speichere_monat(string $u, int $jahr, int $monat, array $rows): void {
  q('DELETE FROM fb_fahrten WHERE username = ? AND jahr = ? AND monat = ?', [$u, $jahr, $monat]);
  $st = db()->prepare('INSERT INTO fb_fahrten (username, jahr, monat, datum, fahrzeug_id, fahrzeug, route, km_d, km_p, abf, ank, dauer, abfahrt_km) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)');
  foreach ($rows as $r) {
    $d = to_iso($r['datum'] ?? null);
    if (!$d) continue;
    $st->execute([$u, $jahr, $monat, $d, to_int($r['fahrzeug_id'] ?? null, null), mb_substr((string) ($r['fahrzeug'] ?? ''), 0, 190),
      (string) ($r['route'] ?? ''), to_int($r['km_d'] ?? 0), to_int($r['km_p'] ?? 0), zeit($r['abf'] ?? ''), zeit($r['ank'] ?? ''),
      substr((string) ($r['dauer'] ?? '00:00'), 0, 6), to_int($r['abfahrt_km'] ?? 0)]);
  }
}
function zeit($v): string { return preg_match('/^(\d{1,2}):(\d{2})/', (string) $v, $m) ? sprintf('%02d:%s', $m[1], $m[2]) : '00:00'; }
function speichere_jahr(string $u, int $jahr, array $daten): void {
  db()->beginTransaction();
  try { foreach ($daten as $m => $rows) speichere_monat($u, $jahr, (int) $m, $rows); db()->commit(); }
  catch (Throwable $e) { db()->rollBack(); throw $e; }
}
function start_km(string $u, int $jahr): array {
  $o = [];
  foreach (q('SELECT fahrzeug_id, start_km FROM fb_start_km WHERE username = ? AND jahr = ?', [$u, $jahr])->fetchAll() as $r) $o[(int) $r['fahrzeug_id']] = (int) $r['start_km'];
  return $o;
}
function setze_start_km(string $u, int $jahr, array $km): void {
  q('DELETE FROM fb_start_km WHERE username = ? AND jahr = ?', [$u, $jahr]);
  $st = db()->prepare('INSERT INTO fb_start_km (username, jahr, fahrzeug_id, start_km) VALUES (?,?,?,?)');
  foreach ($km as $f => $v) $st->execute([$u, $jahr, (int) $f, (int) $v]);
}
// Jahres-Anker lesen; fehlende Fahrzeuge aus "Start-KM (Vorjahr)" uebernehmen und sofort sperren
function anker(string $u, int $jahr): array {
  $a = start_km($u, $jahr); $neu = false;
  foreach (fahrzeuge($u) as $f) if (!isset($a[$f['id']])) { $a[$f['id']] = $f['start_km_vorjahr']; $neu = true; }
  if ($neu) setze_start_km($u, $jahr, $a);
  return $a;
}
function distanzen(string $u): array {
  $o = [];
  foreach (q('SELECT ort, km_einfach FROM fb_orte WHERE username = ?', [$u])->fetchAll() as $r) if ((int) $r['km_einfach'] > 0) $o[$r['ort']] = (int) $r['km_einfach'];
  return $o;
}
function matrix(string $u): array {
  $o = [];
  foreach (q('SELECT key_a, key_b, km FROM fb_matrix WHERE username = ?', [$u])->fetchAll() as $r) if ((int) $r['km'] > 0) $o[mkey($r['key_a'], $r['key_b'])] = (int) $r['km'];
  return $o;
}
function jahre(string $u): array { return array_map('intval', q('SELECT DISTINCT jahr FROM fb_fahrten WHERE username = ? ORDER BY jahr', [$u])->fetchAll(PDO::FETCH_COLUMN)); }
function gen_settings(string $u, int $jahr): array {
  $j = q('SELECT settings_json FROM fb_gen_settings WHERE username = ? AND jahr = ?', [$u, $jahr])->fetchColumn();
  $d = $j ? json_decode((string) $j, true) : null;
  return is_array($d) ? $d : [];
}
function pruefung(array $daten): array {
  $f = [];
  foreach ($daten as $m => $rows) { $x = pruefe_monat($rows); if ($x) $f[$m] = $x; }
  return $f;
}
function jahr_param(): int { $j = to_int($GLOBALS['in']['jahr'] ?? ($_GET['jahr'] ?? null), null); if ($j === null || $j < 1990 || $j > 2100) fail(400, 'Ungültiges Jahr.'); return $j; }
function rate_limit(string $key, int $max): void {
  q('DELETE FROM fb_attempts WHERE ts < UTC_TIMESTAMP() - INTERVAL 1 DAY');
  if ((int) q('SELECT COUNT(*) FROM fb_attempts WHERE ip = ? AND ts > UTC_TIMESTAMP() - INTERVAL 15 MINUTE', [$key])->fetchColumn() >= $max)
    fail(429, 'Zu viele Versuche. Bitte in 15 Minuten nochmal probieren.');
}

switch ($action) {

/* ================= Anmeldung ================= */
case 'login': {
  rate_limit(client_ip(), 10);
  $name = mb_strtolower(trim((string) ($in['username'] ?? '')), 'UTF-8');
  $u = q('SELECT * FROM fb_users WHERE username = ? OR (LENGTH(email) > 0 AND email = ?) LIMIT 1', [$name, $name])->fetch();
  if (!$u || !check_password($u, (string) ($in['password'] ?? ''))) {
    q('INSERT INTO fb_attempts (ip) VALUES (?)', [client_ip()]);
    fail(401, 'Benutzername oder Passwort stimmt nicht.');
  }
  out(['token' => issue_token((int) $u['id']), 'user' => public_user($u)]);
}
case 'me': { $u = current_user(); if (!$u) fail(401, 'Bitte neu anmelden.'); out(['user' => public_user($u), 'mail' => mail_enabled()]); }
case 'logout': {
  $t = (string) ($_SERVER['HTTP_X_AUTH_TOKEN'] ?? '');
  q('DELETE FROM fb_tokens WHERE token_hash = ?', [hash('sha256', $t)]);
  out(['ok' => true]);
}
case 'password': {
  $u = current_user(); if (!$u) fail(401, 'Bitte neu anmelden.');
  $neu = (string) ($in['new'] ?? '');
  if (strlen($neu) < 6) fail(400, 'Das neue Passwort braucht mindestens 6 Zeichen.');
  if (!(int) $u['force_pw_change'] && !check_password($u, (string) ($in['old'] ?? ''))) fail(400, 'Das bisherige Passwort stimmt nicht.');
  q('UPDATE fb_users SET pass_hash = ?, force_pw_change = 0 WHERE id = ?', [password_hash($neu, PASSWORD_DEFAULT), $u['id']]);
  q('DELETE FROM fb_tokens WHERE user_id = ? AND id <> ?', [$u['id'], $u['token_id']]);
  $u = q('SELECT * FROM fb_users WHERE id = ?', [$u['id']])->fetch();
  out(['ok' => true, 'user' => public_user($u)]);
}
case 'forgot': {
  rate_limit('forgot:' . client_ip(), 5);
  q('INSERT INTO fb_attempts (ip) VALUES (?)', ['forgot:' . client_ip()]);
  $name = mb_strtolower(trim((string) ($in['username'] ?? '')), 'UTF-8');
  $u = q('SELECT * FROM fb_users WHERE username = ? OR (LENGTH(email) > 0 AND email = ?) LIMIT 1', [$name, $name])->fetch();
  // Immer dieselbe Antwort, damit niemand Benutzernamen ausprobieren kann
  $antwort = 'Falls es den Zugang gibt und eine E-Mail hinterlegt ist, ist jetzt ein neues Passwort unterwegs. Bitte auch den Spam-Ordner prüfen.';
  if (!$u || !filter_var($u['email'], FILTER_VALIDATE_EMAIL)) out(['ok' => true, 'message' => $antwort]);
  if (!mail_enabled()) fail(503, 'Der E-Mail-Versand ist nicht eingerichtet. Bitte den Admin fragen.');
  $pw = substr(strtr(base64_encode(random_bytes(9)), '+/', 'xy'), 0, 10);
  // Erst senden, dann aendern: klappt der Versand nicht, bleibt das alte Passwort gueltig
  try { send_mail([$u['email']], 'Dein neues Passwort für das Fahrtenbuch', "Hallo {$u['username']},\n\ndein neues Passwort lautet: $pw\n\nBitte ändere es nach der Anmeldung.\n\nFahrtenbuch"); }
  catch (Throwable $e) { fail(502, 'Die E-Mail konnte nicht gesendet werden – dein bisheriges Passwort bleibt gültig. Bitte den Admin kontaktieren.'); }
  q('UPDATE fb_users SET pass_hash = ?, force_pw_change = 1 WHERE id = ?', [password_hash($pw, PASSWORD_DEFAULT), $u['id']]);
  out(['ok' => true, 'message' => $antwort]);
}

/* ================= Stammdaten ================= */
case 'stamm_get': { $u = require_user(); out(['stamm' => stammdaten($u['username'])]); }
case 'stamm_save': {
  $u = require_user(); $s = $in['stamm'] ?? [];
  q('REPLACE INTO fb_stammdaten (username, name, pnr, wohnort, dienstort, entfernung, taggeld_min_stunden, taggeld_basis, taggeld_stufung, taggeld_max_betrag, taggeld_max_stunden, km_geld) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', [
    $u['username'], trim((string) ($s['name'] ?? '')), trim((string) ($s['pnr'] ?? '')), trim((string) ($s['wohnort'] ?? '')), trim((string) ($s['dienstort'] ?? '')),
    to_int($s['entfernung'] ?? 25), to_float($s['taggeld_min_stunden'] ?? 5, 5), to_float($s['taggeld_basis'] ?? 10, 10), to_float($s['taggeld_stufung'] ?? 2.5, 2.5),
    to_float($s['taggeld_max_betrag'] ?? 30, 30), to_float($s['taggeld_max_stunden'] ?? 13, 13), to_float($s['km_geld'] ?? 0.42, 0.42)]);
  out(['ok' => true, 'stamm' => stammdaten($u['username'])]);
}

/* ================= Fahrzeuge, Zeitraeume, Orte ================= */
case 'fz_get': {
  $u = require_user(); $n = $u['username'];
  $orte = q('SELECT ort, km_einfach FROM fb_orte WHERE username = ? ORDER BY ort', [$n])->fetchAll();
  $mx = q('SELECT ort_a, ort_b, km, quelle FROM fb_matrix WHERE username = ? ORDER BY ort_a, ort_b', [$n])->fetchAll();
  out(['fahrzeuge' => fahrzeuge($n), 'zeitraeume' => zeitraeume($n), 'stamm' => stammdaten($n),
    'orte' => array_map(function ($r) { return ['ort' => $r['ort'], 'km_einfach' => (int) $r['km_einfach']]; }, $orte),
    'matrix' => array_map(function ($r) { $r['km'] = (int) $r['km']; return $r; }, $mx)]);
}
case 'fz_save': {
  // ID-stabil: vorhandene IDs werden aktualisiert, Zeilen ohne ID per Bezeichnung zugeordnet
  $u = require_user(); $n = $u['username'];
  $alt = []; $nameZuId = [];
  foreach (fahrzeuge($n) as $f) { $alt[$f['id']] = true; $nameZuId[mb_strtolower(trim($f['bezeichnung']), 'UTF-8')] = $f['id']; }
  $behalten = [];
  db()->beginTransaction();
  foreach (($in['fahrzeuge'] ?? []) as $r) {
    $bez = trim((string) ($r['bezeichnung'] ?? ''));
    if ($bez === '') continue;
    $vals = [$bez, trim((string) ($r['kennzeichen'] ?? '')), to_int($r['start_km_vorjahr'] ?? 0), to_int($r['privat_km_min'] ?? 5, 5),
      to_int($r['privat_km_max'] ?? 20, 20), max(0, min(100, to_int($r['dienstlich_quote'] ?? 90, 90)))];
    $id = to_int($r['id'] ?? null, null);
    if ($id === null || !isset($alt[$id])) $id = $nameZuId[mb_strtolower($bez, 'UTF-8')] ?? null;
    if ($id !== null && isset($alt[$id])) {
      q('UPDATE fb_fahrzeuge SET bezeichnung=?, kennzeichen=?, start_km_vorjahr=?, privat_km_min=?, privat_km_max=?, dienstlich_quote=? WHERE id=? AND username=?', array_merge($vals, [$id, $n]));
      $behalten[$id] = true;
    } else {
      q('INSERT INTO fb_fahrzeuge (bezeichnung, kennzeichen, start_km_vorjahr, privat_km_min, privat_km_max, dienstlich_quote, username) VALUES (?,?,?,?,?,?,?)', array_merge($vals, [$n]));
      $behalten[(int) db()->lastInsertId()] = true;
    }
  }
  foreach (array_keys($alt) as $id) if (!isset($behalten[$id])) {
    q('DELETE FROM fb_fahrzeuge WHERE id = ? AND username = ?', [$id, $n]);
    q('DELETE FROM fb_zeitraeume WHERE fahrzeug_id = ? AND username = ?', [$id, $n]);
  }
  db()->commit();
  out(['ok' => true, 'fahrzeuge' => fahrzeuge($n), 'zeitraeume' => zeitraeume($n)]);
}
case 'zr_save': {
  $u = require_user(); $n = $u['username'];
  $ids = array_column(fahrzeuge($n), 'id'); $rows = []; $offen = 0;
  foreach (($in['zeitraeume'] ?? []) as $r) {
    $v = to_iso($r['von'] ?? null); $b = to_iso($r['bis'] ?? null); $f = to_int($r['fahrzeug_id'] ?? null, null);
    if (!$v && !$b && $f === null) continue;
    if (!$v || !$b || $f === null || !in_array($f, $ids, true)) { $offen++; continue; }
    if ($b < $v) fail(400, 'Ein Zeitraum endet vor seinem Beginn – bitte „von“ und „bis“ prüfen.');
    $rows[] = [$n, $f, $v, $b];
  }
  if ($offen) fail(400, "$offen Zeile(n) ohne Fahrzeug oder Datum – bitte ergänzen oder löschen.");
  db()->beginTransaction();
  q('DELETE FROM fb_zeitraeume WHERE username = ?', [$n]);
  foreach ($rows as $r) q('INSERT INTO fb_zeitraeume (username, fahrzeug_id, von, bis) VALUES (?,?,?,?)', $r);
  db()->commit();
  out(['ok' => true, 'zeitraeume' => zeitraeume($n)]);
}
case 'orte_save': {
  $u = require_user(); $n = $u['username'];
  db()->beginTransaction();
  q('DELETE FROM fb_orte WHERE username = ?', [$n]);
  $seen = [];
  foreach (($in['orte'] ?? []) as $r) {
    $o = trim((string) ($r['ort'] ?? ''));
    if ($o === '' || isset($seen[norm_ort($o)])) continue;
    $seen[norm_ort($o)] = true;
    q('INSERT INTO fb_orte (username, ort, km_einfach) VALUES (?,?,?)', [$n, mb_substr($o, 0, 190), max(0, to_int($r['km_einfach'] ?? 0))]);
  }
  db()->commit();
  out(['ok' => true]);
}
case 'matrix_save': {
  $u = require_user(); $n = $u['username'];
  $alt = [];
  foreach (q('SELECT key_a, key_b, km, quelle FROM fb_matrix WHERE username = ?', [$n])->fetchAll() as $r) $alt["{$r['key_a']}|{$r['key_b']}"] = $r;
  db()->beginTransaction();
  q('DELETE FROM fb_matrix WHERE username = ?', [$n]);
  foreach (($in['matrix'] ?? []) as $r) {
    $a = trim((string) ($r['ort_a'] ?? '')); $b = trim((string) ($r['ort_b'] ?? '')); $km = to_int($r['km'] ?? 0);
    if ($a === '' || $b === '' || $km <= 0 || norm_ort($a) === norm_ort($b)) continue;
    if (strcmp(norm_ort($a), norm_ort($b)) > 0) [$a, $b] = [$b, $a];
    $k = mkey($a, $b); [$ka, $kb] = explode('|', $k);
    $q = isset($alt[$k]) && (int) $alt[$k]['km'] === $km ? $alt[$k]['quelle'] : 'manuell';
    q('REPLACE INTO fb_matrix (username, key_a, key_b, ort_a, ort_b, km, quelle) VALUES (?,?,?,?,?,?,?)', [$n, $ka, $kb, $a, $b, $km, $q]);
  }
  db()->commit();
  out(['ok' => true]);
}

/* ---------- Online-Distanzen (OpenStreetMap: Nominatim + OSRM), schrittweise vom Browser gesteuert ---------- */
case 'geo_plan': {
  $u = require_user(); $n = $u['username']; $st = stammdaten($n);
  $home = ort_clean((string) $st['wohnort']);
  if ($home === '') fail(400, 'Kein Wohnort in den Stammdaten – bitte zuerst eintragen.');
  $liste = array_merge(array_column(q('SELECT ort FROM fb_orte WHERE username = ?', [$n])->fetchAll(), 'ort'), [$home, ort_clean((string) $st['dienstort'])],
    array_map('trim', (array) ($in['zusatz'] ?? [])));
  $alle = [];
  foreach ($liste as $o) if (trim((string) $o) !== '' && !isset($alle[norm_ort($o)])) $alle[norm_ort($o)] = trim((string) $o);
  $bekannt = [];
  foreach (q('SELECT ort_key FROM fb_koordinaten WHERE username = ? AND lat IS NOT NULL', [$n])->fetchAll(PDO::FETCH_COLUMN) as $k) $bekannt[$k] = true;
  $offen = [];
  foreach ($alle as $k => $o) if (!isset($bekannt[$k])) $offen[] = $o;
  out(['orte' => array_values($alle), 'zu_suchen' => $offen]);
}
case 'geo_one': {
  $u = require_user(); $n = $u['username'];
  $ort = trim((string) ($in['ort'] ?? ''));
  if ($ort === '') fail(400, 'Ort fehlt.');
  $hit = null;
  foreach ([["$ort, Österreich", 'at'], [$ort, 'at,de'], [$ort, '']] as $i => [$qq, $cc]) {
    if ($i > 0) usleep(1100000); // Nominatim: max. 1 Anfrage pro Sekunde
    $url = 'https://nominatim.openstreetmap.org/search?' . http_build_query(array_filter(['q' => $qq, 'format' => 'json', 'limit' => 1, 'countrycodes' => $cc]));
    [$code, $res] = http_get_json($url, ['User-Agent: Fahrtenbuch-App/3.0 (OpenStreetMap-Distanzen)', 'Accept-Language: de'], 20);
    if ($code === 200 && !empty($res[0]['lat'])) { $hit = $res[0]; break; }
  }
  q('REPLACE INTO fb_koordinaten (username, ort_key, ort, lat, lon, display_name) VALUES (?,?,?,?,?,?)',
    [$n, norm_ort($ort), $ort, $hit ? (float) $hit['lat'] : null, $hit ? (float) $hit['lon'] : null, $hit ? (string) $hit['display_name'] : '']);
  out(['ok' => (bool) $hit, 'ort' => $ort, 'treffer' => $hit ? (string) $hit['display_name'] : '']);
}
case 'geo_route': {
  // Alle Strecken auf einmal ueber den OSRM-Table-Dienst; Notfall: Luftlinie x 1,25
  $u = require_user(); $n = $u['username']; $st = stammdaten($n);
  $nurFehlende = !empty($in['nur_fehlende']);
  $gewollt = [];
  foreach ((array) ($in['orte'] ?? []) as $o) $gewollt[norm_ort($o)] = true;
  $pkt = [];
  foreach (q('SELECT ort_key, ort, lat, lon FROM fb_koordinaten WHERE username = ? AND lat IS NOT NULL', [$n])->fetchAll() as $r)
    if (isset($gewollt[$r['ort_key']])) $pkt[] = $r;
  if (count($pkt) < 2) fail(400, 'Zu wenige gefundene Orte für eine Berechnung.');
  $vorh = matrix($n);
  $alt = [];
  foreach (q('SELECT key_a, key_b, quelle FROM fb_matrix WHERE username = ?', [$n])->fetchAll() as $r) $alt["{$r['key_a']}|{$r['key_b']}"] = $r['quelle'];
  $coords = implode(';', array_map(function ($p) { return sprintf('%.6F,%.6F', $p['lon'], $p['lat']); }, $pkt));
  [$code, $res, $err] = http_get_json("https://router.project-osrm.org/table/v1/driving/$coords?annotations=distance", ['User-Agent: Fahrtenbuch-App/3.0'], 60);
  $dm = ($code === 200 && ($res['code'] ?? '') === 'Ok') ? $res['distances'] : null;
  $neu = 0; $geschaetzt = 0; $cnt = count($pkt);
  for ($i = 0; $i < $cnt; $i++) for ($j = $i + 1; $j < $cnt; $j++) {
    $a = $pkt[$i]; $b = $pkt[$j]; $k = mkey($a['ort_key'], $b['ort_key']);
    if ($nurFehlende && isset($vorh[$k])) continue;
    if (($alt[$k] ?? '') === 'manuell') continue; // manuelle Korrekturen nie ueberschreiben
    $d = $dm ? max($dm[$i][$j] ?? 0, $dm[$j][$i] ?? 0) : 0;
    if ($d > 0) $km = (int) round($d / 1000);
    else {
      $p1 = deg2rad((float) $a['lat']); $p2 = deg2rad((float) $b['lat']); $dl = deg2rad((float) $b['lon'] - (float) $a['lon']);
      $h = sin(($p2 - $p1) / 2) ** 2 + cos($p1) * cos($p2) * sin($dl / 2) ** 2;
      $km = (int) round(2 * 6371 * asin(sqrt($h)) * 1.25); $geschaetzt++;
    }
    if ($km <= 0) $km = 1;
    [$ka, $kb] = explode('|', $k);
    $oa = $ka === $a['ort_key'] ? $a['ort'] : $b['ort']; $ob = $ka === $a['ort_key'] ? $b['ort'] : $a['ort'];
    q('REPLACE INTO fb_matrix (username, key_a, key_b, ort_a, ort_b, km, quelle) VALUES (?,?,?,?,?,?,?)', [$n, $ka, $kb, $oa, $ob, $km, $d > 0 ? 'osrm' : 'luftlinie']);
    $neu++;
  }
  // "km einfach" vom Wohnort automatisch nachziehen
  $m = matrix($n); $home = ort_clean((string) $st['wohnort']); $akt = [];
  foreach (q('SELECT ort, km_einfach FROM fb_orte WHERE username = ?', [$n])->fetchAll() as $r) {
    $k = mkey($home, $r['ort']);
    if (!empty($m[$k]) && (int) $m[$k] !== (int) $r['km_einfach']) {
      q('UPDATE fb_orte SET km_einfach = ? WHERE username = ? AND ort = ?', [$m[$k], $n, $r['ort']]);
      $akt[] = "{$r['ort']}: {$r['km_einfach']} → {$m[$k]} km";
    }
  }
  out(['ok' => true, 'neu' => $neu, 'geschaetzt' => $geschaetzt, 'osrm' => (bool) $dm, 'aktualisiert' => $akt]);
}

/* ---------- Excel-/CSV-Import (nur Vorschau, gespeichert wird ueber die normalen Knoepfe) ---------- */
case 'import': {
  $u = require_user();
  require __DIR__ . '/server/import.php';
  $f = $_FILES['datei'] ?? null;
  if (!$f || $f['error'] !== UPLOAD_ERR_OK) fail(400, 'Keine Datei empfangen.');
  if ($f['size'] > 5 * 1024 * 1024) fail(400, 'Die Datei ist zu groß (max. 5 MB).');
  $rows = lese_tabelle($f['tmp_name'], (string) $f['name']);
  $art = (string) ($_GET['art'] ?? '');
  if ($art === 'fahrzeuge') out(['fahrzeuge' => import_fahrzeuge($rows)]);
  if ($art === 'zeitraeume') out(['zeitraeume' => import_zeitraeume($rows, fahrzeuge($u['username']))]);
  if ($art === 'keywords') out(['keyword_text' => import_keywords($rows)]);
  if ($art === 'orte') out(['orte' => import_orte($rows)]);
  fail(400, 'Unbekannte Import-Art.');
}

/* ================= Generator / Fahrten ================= */
case 'jahr_get': {
  $u = require_user(); $n = $u['username']; $jahr = jahr_param();
  $daten = lade_jahr($n, $jahr);
  out(['jahr' => $jahr, 'jahre' => jahre($n), 'monate' => (object) $daten, 'settings' => (object) gen_settings($n, $jahr),
    'default_keywords' => DEFAULT_KEYWORDS, 'fahrzeuge' => fahrzeuge($n), 'zeitraeume' => zeitraeume($n),
    'anker' => (object) start_km($n, $jahr), 'flags' => (object) pruefung($daten)]);
}
case 'generieren': {
  $u = require_user(); $n = $u['username']; $jahr = jahr_param();
  $s = (array) ($in['settings'] ?? []);
  $modus = ($s['modus'] ?? '') === 'Ganzes Jahr' ? 'Ganzes Jahr' : 'Einzelner Monat';
  $monat = max(1, min(12, to_int($s['generierungs_monat'] ?? 1, 1)));
  $s['modus'] = $modus; $s['generierungs_monat'] = $monat;
  q('REPLACE INTO fb_gen_settings (username, jahr, settings_json) VALUES (?,?,?)', [$n, $jahr, json_encode($s, JSON_UNESCAPED_UNICODE)]);
  $fz = fahrzeuge($n);
  $kw = keywords_aus_text((string) ($s['keyword_text'] ?? ''));
  if (!$kw) fail(400, 'Keine Orte/Zwecke eingetragen (Format „Ort:Zweck1,Zweck2“ pro Zeile).');
  $anz = to_int($s['anzahl_wochen'] ?? 0);
  $p = $s + ['distanzen' => distanzen($n), 'matrix' => matrix($n),
    'urlaubstage' => $anz > 0 ? urlaubs_tage($anz, (string) ($s['verteilung'] ?? '1x4 Wochen'), to_iso($s['start_woche_1'] ?? null)) : []];
  $monate = $modus === 'Ganzes Jahr' ? range(1, 12) : [$monat];
  [$neu, $fehlende] = generiere_monate($jahr, $monate, stammdaten($n), $fz, zeitraeume($n), $kw, $p);
  // Mit gespeicherten Monaten zusammenfuehren, Kette IMMER ab dem Jahres-Anker neu aufbauen
  $daten = $modus === 'Ganzes Jahr' ? [] : lade_jahr($n, $jahr);
  foreach ($neu as $m => $rows) $daten[$m] = $rows;
  $anker = anker($n, $jahr);
  [$daten, $ende] = baue_kette_neu($daten, $anker);
  speichere_jahr($n, $jahr, $daten);
  setze_start_km($n, $jahr + 1, $ende);
  out(['ok' => true, 'monate' => (object) $daten, 'jahre' => jahre($n), 'flags' => (object) pruefung($daten), 'fehlende' => $fehlende,
    'ende' => (object) $ende, 'anker' => (object) $anker, 'generiert' => $monate]);
}
case 'monat_save': {
  // Monat speichern -> Kette des ganzen Jahres ab Anker neu, Pruefung neu
  $u = require_user(); $n = $u['username']; $jahr = jahr_param(); $monat = max(1, min(12, to_int($in['monat'] ?? 1, 1)));
  $ids = [];
  foreach (fahrzeuge($n) as $f) $ids[$f['id']] = $f['bezeichnung'];
  $nameZuId = array_change_key_case(array_flip($ids), CASE_LOWER);
  $rows = [];
  foreach ((array) ($in['rows'] ?? []) as $r) {
    $d = to_iso($r['datum'] ?? null);
    if (!$d) continue;
    $fid = to_int($r['fahrzeug_id'] ?? null, null);
    $fname = trim((string) ($r['fahrzeug'] ?? ''));
    if ($fname !== '' && isset($nameZuId[mb_strtolower($fname, 'UTF-8')])) $fid = $nameZuId[mb_strtolower($fname, 'UTF-8')];
    if ($fid !== null && !isset($ids[$fid])) $fid = null;
    $abf = zeit($r['abf'] ?? ''); $ank = zeit($r['ank'] ?? '');
    $rows[] = ['datum' => $d, 'fahrzeug_id' => $fid, 'fahrzeug' => $fid !== null ? $ids[$fid] : ($fname ?: 'Kein Fahrzeug'),
      'route' => (string) ($r['route'] ?? ''), 'km_d' => max(0, to_int($r['km_d'] ?? 0)), 'km_p' => max(0, to_int($r['km_p'] ?? 0)),
      'abf' => $abf, 'ank' => $ank, 'dauer' => ($abf === '00:00' && $ank === '00:00') ? '00:00' : dauer_string($abf, $ank), 'abfahrt_km' => 0];
  }
  $daten = lade_jahr($n, $jahr);
  $daten[$monat] = $rows;
  [$daten, $ende] = baue_kette_neu($daten, anker($n, $jahr));
  speichere_jahr($n, $jahr, $daten);
  setze_start_km($n, $jahr + 1, $ende);
  out(['ok' => true, 'monate' => (object) $daten, 'jahre' => jahre($n), 'flags' => (object) pruefung($daten)]);
}
case 'anker_reset': { $u = require_user(); q('DELETE FROM fb_start_km WHERE username = ? AND jahr = ?', [$u['username'], jahr_param()]); out(['ok' => true]); }
case 'jahr_delete': { $u = require_user(); q('DELETE FROM fb_fahrten WHERE username = ? AND jahr = ?', [$u['username'], jahr_param()]); out(['ok' => true]); }

/* ================= Privat-KM ================= */
case 'privat_verteilen': {
  $u = require_user(); $n = $u['username']; $jahr = jahr_param();
  $fid = to_int($in['fahrzeug_id'] ?? null, null);
  $fz = array_column(fahrzeuge($n), 'bezeichnung', 'id');
  if ($fid === null || !isset($fz[$fid])) fail(400, 'Bitte ein Fahrzeug wählen.');
  $gmin = max(1, to_int($in['gross_min'] ?? 300));
  $o = ['anzahl_gross' => max(0, min(12, to_int($in['anzahl_gross'] ?? 4))), 'gross_min' => $gmin, 'gross_max' => max($gmin, to_int($in['gross_max'] ?? 800)),
    'normal_min' => max(0, to_int($in['normal_min'] ?? 5)), 'normal_max' => max(1, to_int($in['normal_max'] ?? 45))];
  [$daten, $ende, $msg] = verteile_privat_km(lade_jahr($n, $jahr), $fid, $fz[$fid], to_int($in['total'] ?? 0), $o, anker($n, $jahr));
  speichere_jahr($n, $jahr, $daten);
  setze_start_km($n, $jahr + 1, $ende);
  out(['ok' => true, 'meldungen' => $msg]);
}

/* ================= HU ================= */
case 'hu_get': {
  $u = require_user();
  $rows = q('SELECT fahrzeug_id, datum, km_at_hu, werkstattort, stopps_vor_hu, stopps_nach_hu FROM fb_hu WHERE username = ? ORDER BY datum', [$u['username']])->fetchAll();
  foreach ($rows as &$r) { $r['fahrzeug_id'] = (int) $r['fahrzeug_id']; $r['km_at_hu'] = (int) $r['km_at_hu']; }
  unset($r);
  out(['hu' => $rows, 'fahrzeuge' => fahrzeuge($u['username']), 'orte' => array_column(q('SELECT ort FROM fb_orte WHERE username = ? ORDER BY ort', [$u['username']])->fetchAll(), 'ort')]);
}
case 'hu_save': {
  $u = require_user(); $n = $u['username'];
  $ids = array_column(fahrzeuge($n), 'id'); $rows = [];
  foreach ((array) ($in['hu'] ?? []) as $i => $r) {
    $f = to_int($r['fahrzeug_id'] ?? null, null); $d = to_iso($r['datum'] ?? null); $w = trim((string) ($r['werkstattort'] ?? ''));
    if ($f === null && !$d && $w === '') continue;
    if ($f === null || !in_array($f, $ids, true)) fail(400, 'Zeile ' . ($i + 1) . ': Fahrzeug fehlt.');
    if (!$d) fail(400, 'Zeile ' . ($i + 1) . ': Datum fehlt.');
    if ($w === '') fail(400, 'Zeile ' . ($i + 1) . ': Werkstattort fehlt.');
    $rows[] = [$n, $f, $d, to_int($r['km_at_hu'] ?? 0), $w, trim((string) ($r['stopps_vor_hu'] ?? '')), trim((string) ($r['stopps_nach_hu'] ?? ''))];
  }
  db()->beginTransaction();
  q('DELETE FROM fb_hu WHERE username = ?', [$n]);
  foreach ($rows as $r) q('INSERT INTO fb_hu (username, fahrzeug_id, datum, km_at_hu, werkstattort, stopps_vor_hu, stopps_nach_hu) VALUES (?,?,?,?,?,?,?)', $r);
  db()->commit();
  out(['ok' => true]);
}
case 'hu_anwenden': {
  // Jahr fuer Jahr, jedes ab seinem eigenen Anker. Bereits angewendete HUs werden uebersprungen.
  $u = require_user(); $n = $u['username'];
  $namen = array_column(fahrzeuge($n), 'bezeichnung', 'id');
  $proJahr = [];
  foreach (q('SELECT * FROM fb_hu WHERE username = ? ORDER BY datum', [$n])->fetchAll() as $r) {
    $split = function ($s) { return array_values(array_filter(array_map('trim', explode(',', (string) $s)), 'strlen')); };
    $proJahr[(int) substr($r['datum'], 0, 4)][] = ['fahrzeug_id' => (int) $r['fahrzeug_id'], 'datum' => $r['datum'], 'km_at_hu' => (int) $r['km_at_hu'],
      'werkstattort' => $r['werkstattort'], 'stopps_vor' => $split($r['stopps_vor_hu']), 'stopps_nach' => $split($r['stopps_nach_hu'])];
  }
  if (!$proJahr) fail(400, 'Keine HU-Einträge gespeichert.');
  $msg = []; $st = stammdaten($n);
  foreach ($proJahr as $jahr => $korr) {
    $daten = lade_jahr($n, $jahr);
    if (!$daten) { $msg[] = "$jahr: keine gespeicherten Fahrten – zuerst generieren."; continue; }
    [$daten, $ende, $m] = wende_hu_an($daten, anker($n, $jahr), $namen, $korr, (string) $st['wohnort'], distanzen($n), matrix($n));
    speichere_jahr($n, $jahr, $daten);
    setze_start_km($n, $jahr + 1, $ende);
    $msg = array_merge($msg, $m);
  }
  out(['ok' => true, 'meldungen' => $msg]);
}

/* ================= PDF ================= */
case 'pdf': {
  $u = require_user(); $n = $u['username']; $jahr = jahr_param();
  require __DIR__ . '/server/pdf.php';
  $daten = lade_jahr($n, $jahr);
  $monat = to_int($_GET['monat'] ?? null, null);
  if ($monat !== null) {
    if (empty($daten[$monat])) fail(404, 'Für diesen Monat sind keine Fahrten gespeichert.');
    $bin = monats_pdf($daten[$monat], $monat, $jahr, stammdaten($n), fahrzeuge($n));
    $file = sprintf('Fahrtenbuch_%d_%02d.pdf', $jahr, $monat);
  } else {
    if (!$daten) fail(404, 'Für dieses Jahr sind keine Fahrten gespeichert.');
    $bin = jahres_pdf($daten, $jahr, stammdaten($n), fahrzeuge($n));
    $file = "Fahrtenbuch_Jahresuebersicht_$jahr.pdf";
  }
  header('Content-Type: application/pdf');
  header('Content-Disposition: attachment; filename="' . $file . '"');
  echo $bin;
  exit;
}

/* ================= Admin ================= */
case 'users': {
  require_admin();
  out(['users' => array_map(function ($r) { return ['id' => (int) $r['id'], 'username' => $r['username'], 'email' => $r['email'], 'is_admin' => (bool) (int) $r['is_admin']]; },
    q('SELECT id, username, email, is_admin FROM fb_users ORDER BY username')->fetchAll())]);
}
case 'user_save': {
  $me = require_admin();
  $id = to_int($in['id'] ?? null, null);
  $name = mb_strtolower(trim((string) ($in['username'] ?? '')), 'UTF-8');
  $mail = mb_strtolower(trim((string) ($in['email'] ?? '')), 'UTF-8');
  $pw = (string) ($in['password'] ?? '');
  $admin = !empty($in['is_admin']) ? 1 : 0;
  if ($name === '') fail(400, 'Bitte einen Benutzernamen eintragen.');
  if ($mail !== '' && !filter_var($mail, FILTER_VALIDATE_EMAIL)) fail(400, 'Die E-Mail-Adresse ist ungültig.');
  if ($id === null) {
    if (strlen($pw) < 6) fail(400, 'Das Start-Passwort braucht mindestens 6 Zeichen.');
    if (q('SELECT id FROM fb_users WHERE username = ?', [$name])->fetch()) fail(400, 'Diesen Benutzernamen gibt es schon.');
    q('INSERT INTO fb_users (username, email, pass_hash, is_admin, force_pw_change) VALUES (?,?,?,?,1)', [$name, $mail, password_hash($pw, PASSWORD_DEFAULT), $admin]);
  } else {
    if ($id === (int) $me['id']) $admin = 1; // sich selbst nicht aussperren
    q('UPDATE fb_users SET email = ?, is_admin = ? WHERE id = ?', [$mail, $admin, $id]);
    if ($pw !== '') {
      if (strlen($pw) < 6) fail(400, 'Das Passwort braucht mindestens 6 Zeichen.');
      q('UPDATE fb_users SET pass_hash = ?, force_pw_change = 1 WHERE id = ?', [password_hash($pw, PASSWORD_DEFAULT), $id]);
      q('DELETE FROM fb_tokens WHERE user_id = ?', [$id]);
    }
  }
  out(['ok' => true]);
}
case 'user_delete': {
  $me = require_admin(); $id = to_int($in['id'] ?? null, null);
  if ($id === (int) $me['id']) fail(400, 'Du kannst dich nicht selbst löschen.');
  q('DELETE FROM fb_tokens WHERE user_id = ?', [$id]);
  q('DELETE FROM fb_users WHERE id = ?', [$id]);
  out(['ok' => true]);
}
case 'settings': {
  require_admin(); $s = settings_all();
  $o = [];
  foreach (['mail_mode', 'mail_from', 'mail_from_name', 'smtp_host', 'smtp_port', 'smtp_secure', 'smtp_user', 'graph_tenant', 'graph_client'] as $k) $o[$k] = $s[$k] ?? '';
  $o['smtp_pass_set'] = ($s['smtp_pass'] ?? '') !== ''; $o['graph_secret_set'] = ($s['graph_secret'] ?? '') !== '';
  out(['settings' => $o]);
}
case 'settings_save': {
  require_admin(); $s = (array) ($in['settings'] ?? []);
  foreach (['mail_mode', 'mail_from', 'mail_from_name', 'smtp_host', 'smtp_port', 'smtp_secure', 'smtp_user', 'graph_tenant', 'graph_client'] as $k)
    if (array_key_exists($k, $s)) setting_save($k, trim((string) $s[$k]));
  foreach (['smtp_pass', 'graph_secret'] as $k) if (($s[$k] ?? '') !== '') setting_save($k, (string) $s[$k]);
  out(['ok' => true]);
}
case 'mail_test': {
  $me = require_admin(); $to = trim((string) ($in['to'] ?? '')) ?: $me['email'];
  send_mail([$to], 'Test vom Fahrtenbuch', "Hallo,\n\ndiese Test-Mail zeigt: der E-Mail-Versand des Fahrtenbuchs funktioniert.\n\nFahrtenbuch");
  out(['ok' => true, 'message' => "Test-Mail an $to gesendet."]);
}
case 'supabase_import': {
  // Uebernahme aus der alten Streamlit-Datenbank, Tabelle fuer Tabelle (vom Browser gesteuert)
  require_admin();
  $url = rtrim(trim((string) ($in['url'] ?? '')), '/');
  $key = trim((string) ($in['key'] ?? ''));
  $tab = (string) ($in['tabelle'] ?? '');
  if (!preg_match('#^https://[a-z0-9-]+\.supabase\.co$#', $url) && !cfg('test_supabase')) fail(400, 'Die Supabase-Adresse muss so aussehen: https://xxxx.supabase.co');
  if ($key === '') fail(400, 'Bitte den Supabase-Key (service_role) eintragen.');
  $hole = function (string $t) use ($url, $key): array {
    $alle = []; $off = 0;
    while (true) {
      [$code, $res, $err] = http_get_json("$url/rest/v1/$t?select=*&limit=1000&offset=$off", ["apikey: $key", "Authorization: Bearer $key"], 60);
      if ($code === 404 || ($code >= 400 && strpos(json_encode($res), 'does not exist') !== false)) return [];
      if ($code !== 200 || !is_array($res)) throw new RuntimeException("Supabase-Tabelle $t: " . ($res['message'] ?? $err ?: "Fehler $code"));
      $alle = array_merge($alle, $res);
      if (count($res) < 1000) return $alle;
      $off += 1000;
    }
  };
  $low = function ($s) { return mb_strtolower(trim((string) $s), 'UTF-8'); };
  $anz = 0;
  db()->beginTransaction();
  try {
    switch ($tab) {
      case 'users':
        foreach ($hole('users') as $r) {
          $name = $low($r['username'] ?? ''); if ($name === '') continue;
          $ex = q('SELECT id FROM fb_users WHERE username = ?', [$name])->fetch();
          if ($ex) q('UPDATE fb_users SET email = IF(LENGTH(email) = 0, ?, email) WHERE id = ?', [$low($r['email'] ?? ''), $ex['id']]);
          else q('INSERT INTO fb_users (username, email, pass_hash, is_admin, force_pw_change) VALUES (?,?,?,?,?)',
            [$name, $low($r['email'] ?? ''), 'sha256:' . (string) ($r['password'] ?? ''), $name === 'christian mayerhofer' ? 1 : 0, !empty($r['force_pw_change']) ? 1 : 0]);
          $anz++;
        }
        break;
      case 'settings':
        foreach ($hole('settings') as $r) {
          q('REPLACE INTO fb_stammdaten (username, name, pnr, wohnort, dienstort, entfernung, taggeld_min_stunden, taggeld_basis, taggeld_stufung, taggeld_max_betrag, taggeld_max_stunden, km_geld) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', [
            $low($r['username']), (string) ($r['name'] ?? ''), (string) ($r['pnr'] ?? ''), (string) ($r['wohnort'] ?? ''), (string) ($r['dienstort'] ?? ''),
            to_int($r['entfernung'] ?? 25, 25), to_float($r['taggeld_min_stunden'] ?? null, 5), to_float($r['taggeld_basis'] ?? null, 10), to_float($r['taggeld_stufung'] ?? null, 2.5),
            to_float($r['taggeld_max_betrag'] ?? null, 30), to_float($r['taggeld_max_stunden'] ?? null, 13), to_float($r['km_geld'] ?? null, 0.42)]);
          $anz++;
        }
        break;
      case 'fahrzeuge':
        q('DELETE FROM fb_fahrzeuge');
        foreach ($hole('fahrzeuge') as $r) {
          q('INSERT INTO fb_fahrzeuge (id, username, bezeichnung, kennzeichen, start_km_vorjahr, privat_km_min, privat_km_max, dienstlich_quote) VALUES (?,?,?,?,?,?,?,?)', [
            (int) $r['id'], $low($r['username']), (string) $r['bezeichnung'], (string) ($r['kennzeichen'] ?? ''), to_int($r['start_km_vorjahr'] ?? 0),
            to_int($r['privat_km_min'] ?? 5, 5), to_int($r['privat_km_max'] ?? 20, 20), to_int($r['dienstlich_quote'] ?? 90, 90)]);
          $anz++;
        }
        break;
      case 'zeitraeume':
        q('DELETE FROM fb_zeitraeume');
        foreach ($hole('zeitraeume') as $r) {
          if (!to_iso($r['von'] ?? null) || !to_iso($r['bis'] ?? null) || to_int($r['fahrzeug_id'] ?? null, null) === null) continue;
          q('INSERT INTO fb_zeitraeume (username, fahrzeug_id, von, bis) VALUES (?,?,?,?)', [$low($r['username']), (int) $r['fahrzeug_id'], to_iso($r['von']), to_iso($r['bis'])]);
          $anz++;
        }
        break;
      case 'fahrten':
        q('DELETE FROM fb_fahrten');
        $st = db()->prepare('INSERT INTO fb_fahrten (username, jahr, monat, datum, fahrzeug_id, fahrzeug, route, km_d, km_p, abf, ank, dauer, abfahrt_km) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)');
        foreach ($hole('fahrten') as $r) {
          $d = to_iso($r['datum'] ?? null); if (!$d) continue;
          $st->execute([$low($r['username']), (int) $r['jahr'], (int) $r['monat'], $d, to_int($r['fahrzeug_id'] ?? null, null), (string) ($r['fahrzeug'] ?? ''),
            (string) ($r['route'] ?? ''), to_int($r['km_d'] ?? 0), to_int($r['km_p'] ?? 0), zeit($r['abf'] ?? ''), zeit($r['ank'] ?? ''), substr((string) ($r['dauer'] ?? '00:00'), 0, 6), to_int($r['abfahrt_km'] ?? 0)]);
          $anz++;
        }
        break;
      case 'hu_corrections':
        q('DELETE FROM fb_hu');
        foreach ($hole('hu_corrections') as $r) {
          if (!to_iso($r['datum'] ?? null) || to_int($r['fahrzeug_id'] ?? null, null) === null) continue;
          q('INSERT INTO fb_hu (username, fahrzeug_id, datum, km_at_hu, werkstattort, stopps_vor_hu, stopps_nach_hu) VALUES (?,?,?,?,?,?,?)', [
            $low($r['username']), (int) $r['fahrzeug_id'], to_iso($r['datum']), to_int($r['km_at_hu'] ?? 0), (string) ($r['werkstattort'] ?? ''),
            (string) ($r['stopps_vor_hu'] ?? ''), (string) ($r['stopps_nach_hu'] ?? '')]);
          $anz++;
        }
        break;
      case 'orte':
        q('DELETE FROM fb_orte');
        $km = [];
        foreach ($hole('orte_distanz') as $r) $km[$low($r['username']) . '|' . norm_ort($r['ort'])] = to_int($r['km_einfach'] ?? 0);
        $seen = [];
        foreach (array_merge($hole('orte'), $hole('orte_distanz')) as $r) {
          $k = $low($r['username']) . '|' . norm_ort($r['ort'] ?? '');
          if (trim((string) ($r['ort'] ?? '')) === '' || isset($seen[$k])) continue;
          $seen[$k] = true;
          q('INSERT INTO fb_orte (username, ort, km_einfach) VALUES (?,?,?)', [$low($r['username']), trim((string) $r['ort']), $km[$k] ?? 0]);
          $anz++;
        }
        break;
      case 'ort_koordinaten':
        q('DELETE FROM fb_koordinaten');
        foreach ($hole('ort_koordinaten') as $r) {
          q('REPLACE INTO fb_koordinaten (username, ort_key, ort, lat, lon, display_name) VALUES (?,?,?,?,?,?)', [
            $low($r['username']), norm_ort($r['ort_key'] ?? $r['ort'] ?? ''), (string) ($r['ort'] ?? ''), $r['lat'] ?? null, $r['lon'] ?? null, (string) ($r['display_name'] ?? '')]);
          $anz++;
        }
        break;
      case 'distanz_matrix':
        q('DELETE FROM fb_matrix');
        foreach ($hole('distanz_matrix') as $r) {
          [$ka, $kb] = explode('|', mkey((string) $r['key_a'], (string) $r['key_b']));
          q('REPLACE INTO fb_matrix (username, key_a, key_b, ort_a, ort_b, km, quelle) VALUES (?,?,?,?,?,?,?)', [
            $low($r['username']), $ka, $kb, (string) ($r['ort_a'] ?? $ka), (string) ($r['ort_b'] ?? $kb), to_int($r['km'] ?? 0), (string) ($r['quelle'] ?? 'osrm')]);
          $anz++;
        }
        break;
      case 'jahres_start_km':
        q('DELETE FROM fb_start_km');
        foreach ($hole('jahres_start_km') as $r) {
          q('REPLACE INTO fb_start_km (username, jahr, fahrzeug_id, start_km) VALUES (?,?,?,?)', [$low($r['username']), (int) $r['jahr'], (int) $r['fahrzeug_id'], to_int($r['start_km'] ?? 0)]);
          $anz++;
        }
        break;
      case 'generation_settings':
        q('DELETE FROM fb_gen_settings');
        foreach ($hole('generation_settings') as $r) {
          q('REPLACE INTO fb_gen_settings (username, jahr, settings_json) VALUES (?,?,?)', [$low($r['username']), (int) $r['jahr'], (string) ($r['settings_json'] ?? '{}')]);
          $anz++;
        }
        break;
      case 'system_config':
        foreach ($hole('system_config') as $r) {
          if (!empty($r['smtp_server'])) {
            foreach (['mail_mode' => 'smtp', 'smtp_host' => $r['smtp_server'], 'smtp_port' => (string) ($r['smtp_port'] ?? '465'),
              'smtp_secure' => (string) ($r['smtp_port'] ?? '') === '465' ? 'ssl' : 'tls', 'smtp_user' => (string) ($r['smtp_user'] ?? ''),
              'mail_from' => (string) ($r['smtp_user'] ?? ''), 'mail_from_name' => (string) ($r['smtp_from_name'] ?? 'Fahrtenbuch')] as $k => $v)
              if ((string) setting($k, '') === '') setting_save($k, (string) $v);
            if (!empty($r['smtp_password']) && (string) setting('smtp_pass', '') === '') setting_save('smtp_pass', (string) $r['smtp_password']);
            $anz++;
          }
        }
        break;
      default: fail(400, 'Unbekannte Tabelle.');
    }
    db()->commit();
  } catch (Throwable $e) { if (db()->inTransaction()) db()->rollBack(); throw $e; }
  out(['ok' => true, 'tabelle' => $tab, 'anzahl' => $anz]);
}

default: fail(404, 'Unbekannte Aktion.');
}
