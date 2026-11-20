<?php
// Fahrtenbuch – Datenzugriff je Benutzer (entspricht dem Ordner database/ der Python-Version)
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

function q(string $sql, array $p = []): PDOStatement { $st = db()->prepare($sql); $st->execute($p); return $st; }

/* ---------- Stammdaten ---------- */
const SETTINGS_DEFAULT = ['name' => '', 'pnr' => '', 'wohnort' => '', 'dienstort' => '', 'entfernung' => 25, 'taggeld_min_stunden' => 5.0,
  'taggeld_basis' => 10.0, 'taggeld_stufung' => 2.5, 'taggeld_max_betrag' => 30.0, 'taggeld_max_stunden' => 13.0, 'km_geld' => 0.42];
function settings_load(string $u): array {
  $r = q('SELECT * FROM fb_settings WHERE username = ?', [$u])->fetch();
  if (!$r) return SETTINGS_DEFAULT;
  unset($r['username']);
  foreach ($r as $k => $v) $r[$k] = is_string(SETTINGS_DEFAULT[$k] ?? '') ? (string) $v : (is_int(SETTINGS_DEFAULT[$k]) ? (int) $v : (float) $v);
  return $r;
}
function settings_save(string $u, array $d): void {
  $v = [];
  foreach (SETTINGS_DEFAULT as $k => $def) {
    $x = $d[$k] ?? $def;
    $v[$k] = is_string($def) ? mb_substr(trim((string) $x), 0, 190) : (is_int($def) ? safe_int($x, $def) : safe_float($x, $def));
  }
  $cols = array_keys($v);
  q('INSERT INTO fb_settings (username, ' . implode(', ', $cols) . ') VALUES (?' . str_repeat(', ?', count($cols)) . ') ON DUPLICATE KEY UPDATE '
    . implode(', ', array_map(function ($c) { return "$c = VALUES($c)"; }, $cols)), array_merge([$u], array_values($v)));
}

/* ---------- Fahrzeuge & Zeiträume ---------- */
function fahrzeuge_load(string $u): array {
  $rows = q('SELECT id, bezeichnung, kennzeichen, start_km_vorjahr, privat_km_min, privat_km_max, dienstlich_quote FROM fb_fahrzeuge WHERE username = ? ORDER BY id', [$u])->fetchAll();
  foreach ($rows as &$r) foreach (['id', 'start_km_vorjahr', 'privat_km_min', 'privat_km_max', 'dienstlich_quote'] as $k) $r[$k] = (int) $r[$k];
  return $rows;
}
// ID-stabil: Zeilen ohne ID werden über die Bezeichnung bestehenden Fahrzeugen zugeordnet (Excel-Import!)
function fahrzeuge_save(string $u, array $rows): array {
  $alt = fahrzeuge_load($u);
  $ids = array_column($alt, 'id'); $byName = [];
  foreach ($alt as $f) $byName[mb_strtolower(trim($f['bezeichnung']))] = $f['id'];
  $keep = [];
  db()->beginTransaction();
  try {
    foreach ($rows as $r) {
      $b = trim((string) ($r['bezeichnung'] ?? ''));
      if ($b === '' || in_array(strtolower($b), ['none', 'nan'], true)) continue;
      $vals = [$b, trim((string) ($r['kennzeichen'] ?? '')), safe_int($r['start_km_vorjahr'] ?? 0), safe_int($r['privat_km_min'] ?? 5, 5),
        safe_int($r['privat_km_max'] ?? 20, 20), max(0, min(100, safe_int($r['dienstlich_quote'] ?? 90, 90)))];
      $id = safe_int($r['id'] ?? null, null);
      if ($id === null || !in_array($id, $ids, true)) $id = $byName[mb_strtolower($b)] ?? null;
      if ($id !== null && in_array($id, $ids, true) && !in_array($id, $keep, true)) {
        q('UPDATE fb_fahrzeuge SET bezeichnung = ?, kennzeichen = ?, start_km_vorjahr = ?, privat_km_min = ?, privat_km_max = ?, dienstlich_quote = ? WHERE id = ? AND username = ?',
          array_merge($vals, [$id, $u]));
        $keep[] = $id;
      } else {
        q('INSERT INTO fb_fahrzeuge (username, bezeichnung, kennzeichen, start_km_vorjahr, privat_km_min, privat_km_max, dienstlich_quote) VALUES (?, ?, ?, ?, ?, ?, ?)', array_merge([$u], $vals));
        $keep[] = (int) db()->lastInsertId();
      }
    }
    foreach (array_diff($ids, $keep) as $id) q('DELETE FROM fb_fahrzeuge WHERE id = ? AND username = ?', [$id, $u]);
    db()->commit();
  } catch (Throwable $e) { db()->rollBack(); throw $e; }
  return fahrzeuge_load($u);
}
function zeitraeume_load(string $u): array {
  $rows = q('SELECT fahrzeug_id, von, bis FROM fb_zeitraeume WHERE username = ? ORDER BY von, id', [$u])->fetchAll();
  foreach ($rows as &$r) $r['fahrzeug_id'] = (int) $r['fahrzeug_id'];
  return $rows;
}
function zeitraeume_save(string $u, array $rows): int {
  $n = 0;
  db()->beginTransaction();
  try {
    q('DELETE FROM fb_zeitraeume WHERE username = ?', [$u]);
    foreach ($rows as $r) {
      $v = parse_date_iso($r['von'] ?? null); $b = parse_date_iso($r['bis'] ?? null); $f = safe_int($r['fahrzeug_id'] ?? null, null);
      if (!$v || !$b || $f === null) continue;
      q('INSERT INTO fb_zeitraeume (username, fahrzeug_id, von, bis) VALUES (?, ?, ?, ?)', [$u, $f, $v, $b]); $n++;
    }
    db()->commit();
  } catch (Throwable $e) { db()->rollBack(); throw $e; }
  return $n;
}

/* ---------- Orte, Distanzen, Distanz-Matrix, Geo-Cache ---------- */
function orte_load(string $u): array {
  $rows = q('SELECT ort, km_einfach FROM fb_orte WHERE username = ? ORDER BY ort', [$u])->fetchAll();
  foreach ($rows as &$r) $r['km_einfach'] = $r['km_einfach'] === null ? null : (int) $r['km_einfach'];
  usort($rows, function ($a, $b) { return strcoll(mb_strtolower($a['ort']), mb_strtolower($b['ort'])); });
  return $rows;
}
// $rows: [['ort'=>.., 'km_einfach'=>int|null], ...] – ersetzt die ganze Liste
function orte_save(string $u, array $rows): void {
  db()->beginTransaction();
  try {
    q('DELETE FROM fb_orte WHERE username = ?', [$u]);
    $seen = [];
    foreach ($rows as $r) {
      $o = mb_substr(trim((string) ($r['ort'] ?? '')), 0, 150);
      if ($o === '' || isset($seen[$o])) continue;
      $seen[$o] = true;
      $km = ($r['km_einfach'] ?? null) === null || $r['km_einfach'] === '' ? null : max(0, safe_int($r['km_einfach'], 0));
      q('INSERT INTO fb_orte (username, ort, km_einfach) VALUES (?, ?, ?)', [$u, $o, $km]);
    }
    db()->commit();
  } catch (Throwable $e) { db()->rollBack(); throw $e; }
}
function distanzen_load(string $u): array {
  $m = [];
  foreach (orte_load($u) as $r) if ($r['km_einfach'] !== null) $m[$r['ort']] = $r['km_einfach'];
  return $m;
}
function matrix_load(string $u): array {
  $m = [];
  foreach (q('SELECT key_a, key_b, km FROM fb_distanz_matrix WHERE username = ?', [$u])->fetchAll() as $r) {
    $a = $r['key_a']; $b = $r['key_b'];
    if (strcmp($a, $b) > 0) [$a, $b] = [$b, $a];
    if ((int) $r['km'] > 0) $m["$a|$b"] = (int) $r['km'];
  }
  return $m;
}
function matrix_rows(string $u): array {
  $rows = q('SELECT ort_a, ort_b, km, quelle FROM fb_distanz_matrix WHERE username = ? ORDER BY ort_a, ort_b', [$u])->fetchAll();
  foreach ($rows as &$r) $r['km'] = (int) $r['km'];
  return $rows;
}
function matrix_upsert(string $u, string $ortA, string $ortB, int $km, string $quelle): void {
  $a = trim($ortA); $b = trim($ortB);
  $ka = norm_ort($a); $kb = norm_ort($b);
  if ($ka === '' || $kb === '' || $ka === $kb || $km <= 0) return;
  if (strcmp($ka, $kb) > 0) { [$ka, $kb] = [$kb, $ka]; [$a, $b] = [$b, $a]; }
  q('INSERT INTO fb_distanz_matrix (username, key_a, key_b, ort_a, ort_b, km, quelle) VALUES (?, ?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE ort_a = VALUES(ort_a), ort_b = VALUES(ort_b), km = VALUES(km), quelle = VALUES(quelle)', [$u, $ka, $kb, $a, $b, $km, $quelle]);
}
function geo_load(string $u): array {
  $m = [];
  foreach (q('SELECT * FROM fb_ort_koordinaten WHERE username = ?', [$u])->fetchAll() as $r)
    $m[$r['ort_key']] = ['ort' => $r['ort'], 'lat' => $r['lat'] === null ? null : (float) $r['lat'], 'lon' => $r['lon'] === null ? null : (float) $r['lon'], 'display_name' => $r['display_name'], 'ok' => (bool) (int) $r['ok']];
  return $m;
}
function geo_save(string $u, string $ort, ?array $g): void {
  q('INSERT INTO fb_ort_koordinaten (username, ort_key, ort, lat, lon, display_name, ok) VALUES (?, ?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE ort = VALUES(ort), lat = VALUES(lat), lon = VALUES(lon), display_name = VALUES(display_name), ok = VALUES(ok)',
    [$u, norm_ort($ort), trim($ort), $g['lat'] ?? null, $g['lon'] ?? null, mb_substr((string) ($g['display_name'] ?? ''), 0, 400), $g ? 1 : 0]);
}

/* ---------- Fahrten (Jahr) ---------- */
function fahrt_norm(array $r): array {
  $fz = $r['fahrzeug_id'] ?? null;
  return ['datum' => (string) parse_date_iso($r['datum'] ?? ''), 'fahrzeug_id' => ($fz === null || $fz === '') ? null : (int) $fz,
    'fahrzeug' => mb_substr(trim((string) ($r['fahrzeug'] ?? '')), 0, 190), 'route' => trim((string) ($r['route'] ?? '')),
    'km_d' => max(0, safe_int($r['km_d'] ?? 0, 0)), 'km_p' => max(0, safe_int($r['km_p'] ?? 0, 0)),
    'abf' => zeit_norm($r['abf'] ?? ''), 'ank' => zeit_norm($r['ank'] ?? ''), 'dauer' => zeit_norm($r['dauer'] ?? ''), 'abfahrt_km' => safe_int($r['abfahrt_km'] ?? 0, 0)];
}
function zeit_norm($v): string {
  $s = trim((string) $v);
  if (preg_match('/^(\d{1,2})[:.](\d{2})/', $s, $m)) return sprintf('%02d:%02d', min(99, (int) $m[1]), min(59, (int) $m[2]));
  return '00:00';
}
function year_load(string $u, int $jahr): array {
  $y = [];
  foreach (q('SELECT datum, fahrzeug_id, fahrzeug, route, km_d, km_p, abf, ank, dauer, abfahrt_km, monat FROM fb_fahrten WHERE username = ? AND jahr = ? ORDER BY datum, id', [$u, $jahr])->fetchAll() as $r) {
    $m = (int) $r['monat']; unset($r['monat']);
    $y[$m][] = fahrt_norm($r);
  }
  ksort($y);
  return $y;
}
function jahre_load(string $u): array {
  return array_map('intval', q('SELECT DISTINCT jahr FROM fb_fahrten WHERE username = ? ORDER BY jahr', [$u])->fetchAll(PDO::FETCH_COLUMN));
}
// Speichert die angegebenen Monate (Monat ersetzen = löschen + neu einfügen)
function months_save(string $u, int $jahr, array $year): void {
  db()->beginTransaction();
  try {
    foreach ($year as $m => $rows) {
      q('DELETE FROM fb_fahrten WHERE username = ? AND jahr = ? AND monat = ?', [$u, $jahr, (int) $m]);
      foreach (array_chunk($rows, 200) as $chunk) {
        $sql = 'INSERT INTO fb_fahrten (username, jahr, monat, datum, fahrzeug_id, fahrzeug, route, km_d, km_p, abf, ank, dauer, abfahrt_km) VALUES ';
        $p = []; $ph = [];
        foreach ($chunk as $r) {
          $r = fahrt_norm($r);
          if ($r['datum'] === '') continue;
          $ph[] = '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)';
          array_push($p, $u, $jahr, (int) $m, $r['datum'], $r['fahrzeug_id'], $r['fahrzeug'], $r['route'], $r['km_d'], $r['km_p'], $r['abf'], $r['ank'], $r['dauer'], $r['abfahrt_km']);
        }
        if ($ph) q($sql . implode(', ', $ph), $p);
      }
    }
    db()->commit();
  } catch (Throwable $e) { db()->rollBack(); throw $e; }
}
function year_delete(string $u, int $jahr): void { q('DELETE FROM fb_fahrten WHERE username = ? AND jahr = ?', [$u, $jahr]); }

/* ---------- Jahres-Anker (Startkilometer 1.1.) ---------- */
function anchor_get(string $u, int $jahr): array {
  $m = [];
  foreach (q('SELECT fahrzeug_id, start_km FROM fb_jahres_start_km WHERE username = ? AND jahr = ?', [$u, $jahr])->fetchAll() as $r) $m[(int) $r['fahrzeug_id']] = (int) $r['start_km'];
  return $m;
}
function anchor_set(string $u, int $jahr, array $km): void {
  q('DELETE FROM fb_jahres_start_km WHERE username = ? AND jahr = ?', [$u, $jahr]);
  foreach ($km as $f => $k) q('INSERT INTO fb_jahres_start_km (username, jahr, fahrzeug_id, start_km) VALUES (?, ?, ?, ?)', [$u, $jahr, (int) $f, (int) $k]);
}
function anchor_delete(string $u, int $jahr): void { q('DELETE FROM fb_jahres_start_km WHERE username = ? AND jahr = ?', [$u, $jahr]); }
// Liest den Anker. Fehlende Fahrzeuge werden aus „Start-KM (Vorjahr)“ übernommen und SOFORT gesperrt.
function anchor_get_or_create(string $u, int $jahr, array $fahrzeuge): array {
  $a = anchor_get($u, $jahr); $neu = false;
  foreach ($fahrzeuge as $f) if (!isset($a[(int) $f['id']])) { $a[(int) $f['id']] = (int) $f['start_km_vorjahr']; $neu = true; }
  if ($neu) anchor_set($u, $jahr, $a);
  return $a;
}

/**
 * Speichert geänderte Monate eines Jahres: Kilometerkette des GANZEN Jahres ab dem gesperrten Anker neu,
 * Folgejahres-Anker = Endstände; hat das Folgejahr schon Fahrten, wird dessen Kette ebenfalls nachgezogen.
 * $changed: [monat => rows] (null = nur Kette neu). Liefert [year, endKm].
 */
function year_commit(string $u, int $jahr, ?array $changed, array $fahrzeuge): array {
  $year = year_load($u, $jahr);
  if ($changed) foreach ($changed as $m => $rows) $year[(int) $m] = array_map('fahrt_norm', $rows);
  foreach ($year as $m => $rows) if (!$rows) unset($year[$m]);
  $anchor = anchor_get_or_create($u, $jahr, $fahrzeuge);
  $end = kette_neu($year, $anchor);
  $toSave = $year;
  if ($changed) foreach (array_keys($changed) as $m) if (!isset($toSave[(int) $m])) $toSave[(int) $m] = [];
  months_save($u, $jahr, $toSave);
  anchor_set($u, $jahr + 1, $end);
  // Kette über die Jahresgrenze lückenlos halten
  $j = $jahr + 1; $prevEnd = $end;
  while ($j <= $jahr + 30) {
    $next = year_load($u, $j);
    if (!$next) break;
    $a = anchor_get_or_create($u, $j, $fahrzeuge);
    $prevEnd = kette_neu($next, $a);
    months_save($u, $j, $next);
    anchor_set($u, $j + 1, $prevEnd);
    $j++;
  }
  return [$year, $end];
}

/* ---------- Generierungs-Einstellungen, HU ---------- */
function gen_settings_load(string $u, int $jahr): array {
  $v = q('SELECT settings_json FROM fb_generation_settings WHERE username = ? AND jahr = ?', [$u, $jahr])->fetchColumn();
  $d = $v ? json_decode((string) $v, true) : [];
  return is_array($d) ? $d : [];
}
function gen_settings_save(string $u, int $jahr, array $s): void {
  q('INSERT INTO fb_generation_settings (username, jahr, settings_json) VALUES (?, ?, ?) ON DUPLICATE KEY UPDATE settings_json = VALUES(settings_json)',
    [$u, $jahr, json_encode($s, JSON_UNESCAPED_UNICODE)]);
}
function stopps_liste($v): array {
  if (is_array($v)) $v = implode(',', $v);
  return array_values(array_filter(array_map('trim', explode(',', (string) $v)), 'strlen'));
}
function hu_load(string $u): array {
  $rows = q('SELECT id, fahrzeug_id, datum, km_at_hu, werkstattort, stopps_vor_hu, stopps_nach_hu, angewendet_am FROM fb_hu WHERE username = ? ORDER BY datum, id', [$u])->fetchAll();
  foreach ($rows as &$r) { $r['id'] = (int) $r['id']; $r['fahrzeug_id'] = (int) $r['fahrzeug_id']; $r['km_at_hu'] = (int) $r['km_at_hu']; $r['stopps_vor_hu'] = (string) $r['stopps_vor_hu']; $r['stopps_nach_hu'] = (string) $r['stopps_nach_hu']; }
  return $rows;
}
