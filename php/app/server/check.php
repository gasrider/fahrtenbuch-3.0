<?php
// Fahrtenbuch – Systemprüfung (Admin): prüft Server, Daten nach dem Umzug und alle Fachregeln gegen die echten Daten.
// Ändert NICHTS. Ergebnis: Abschnitte mit Zeilen ['s' => ok|warn|err|info, 't' => Text].
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

function chk_server(): array {
  $it = [];
  $add = function ($s, $t) use (&$it) { $it[] = ['s' => $s, 't' => $t]; };
  $add(version_compare(PHP_VERSION, '7.4', '>=') ? 'ok' : 'err', 'PHP ' . PHP_VERSION);
  $add('info', 'Datenbank ' . db()->query('SELECT VERSION()')->fetchColumn());
  $add(class_exists('ZipArchive') ? 'ok' : 'warn', class_exists('ZipArchive') ? 'Excel-Import möglich (ZipArchive)' : 'ZipArchive fehlt – Excel-Import geht nicht, CSV schon');
  $add(function_exists('curl_init') ? 'ok' : 'warn', function_exists('curl_init') ? 'cURL vorhanden' : 'cURL fehlt – Online-Karte/Umzug über Fallback');
  $add(function_exists('gzcompress') ? 'ok' : 'info', function_exists('gzcompress') ? 'PDF-Komprimierung aktiv' : 'PDFs werden unkomprimiert (größer)');
  $met = (int) ini_get('max_execution_time');
  $add($met === 0 || $met >= 60 ? 'ok' : 'warn', 'Zeitlimit pro Anfrage: ' . ($met ?: 'unbegrenzt') . ' s');
  $counts = [];
  foreach (['fb_users', 'fb_settings', 'fb_fahrzeuge', 'fb_zeitraeume', 'fb_fahrten', 'fb_orte', 'fb_distanz_matrix', 'fb_ort_koordinaten', 'fb_jahres_start_km', 'fb_generation_settings', 'fb_hu'] as $t)
    $counts[] = substr($t, 3) . ' ' . fmt_int((int) db()->query("SELECT COUNT(*) FROM $t")->fetchColumn());
  $add('info', 'Datensätze: ' . implode(' · ', $counts));
  // Schutz des server-Ordners
  $https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
  $base = ($https ? 'https://' : 'http://') . ($_SERVER['HTTP_HOST'] ?? 'localhost') . rtrim(str_replace('\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '/')), '/') . '/';
  [$code, $body] = http_request('GET', $base . 'server/config.php', [], null, 10);
  if ($code === 403 || $code === 404) $add('ok', "Ordner „server“ ist geschützt (HTTP $code)");
  elseif ($code === 0) $add('info', 'Schutz des Ordners „server“ nicht prüfbar (Server erreicht sich selbst nicht) – bitte im Browser ' . $base . 'server/config.php öffnen: muss „Forbidden“ zeigen');
  else $add(trim($body) === '' ? 'warn' : 'err', "Ordner „server“ antwortet mit HTTP $code – .htaccess wirkt nicht! Bitte melden.");
  $add($https ? 'ok' : 'warn', $https ? 'Verbindung über https' : 'Seite nicht über https geöffnet');
  // Online-Karte
  require_once __DIR__ . '/routing.php';
  $t0 = microtime(true);
  $km = routen_km(47.9067, 13.3170, 47.8686, 13.1264); // Zell am Moos → Eugendorf
  if ($km === null) $add('err', 'OSRM-Routing nicht erreichbar – „Distanzen online berechnen“ fällt auf Luftlinie zurück');
  else $add($km >= 20 && $km <= 30 ? 'ok' : 'warn', "OSRM erreichbar: Zell am Moos → Eugendorf = $km km (erwartet ~24–25), " . round(microtime(true) - $t0, 1) . ' s');
  [$c2, $d2] = http_json('GET', (string) cfg('nominatim_url', 'https://nominatim.openstreetmap.org/search') . '?' . http_build_query(['q' => 'Zell am Moos, Österreich', 'format' => 'json', 'limit' => 1]), osm_headers(), null, 15);
  $add(is_array($d2) && isset($d2[0]['lat']) ? 'ok' : 'err', is_array($d2) && isset($d2[0]['lat']) ? 'Nominatim (Ortssuche) erreichbar' : "Nominatim nicht erreichbar (HTTP $c2)");
  // Mail + Registrierung
  $mode = (string) setting('mail_mode', 'off');
  $add($mode === 'off' ? 'warn' : 'ok', 'E-Mail-Versand: ' . ($mode === 'off' ? 'aus – „Passwort vergessen“ funktioniert nicht' : $mode . ', Absender ' . setting('mail_from', '–') . ' (mit „Test-E-Mail senden“ prüfen)'));
  if ($mode === 'smtp' && preg_match('/office365|outlook/i', (string) setting('smtp_host', ''))) $add('warn', 'SMTP über Microsoft 365: Passwort-SMTP wird Ende 2026 abgeschaltet → auf „Microsoft 365 (Graph)“ umstellen');
  $add(setting('invite_code', '') === '' ? 'info' : 'ok', setting('invite_code', '') === '' ? 'Registrierung gesperrt (kein Einladungs-Code)' : 'Registrierung mit Einladungs-Code möglich');
  $admins = q('SELECT username FROM fb_users WHERE is_admin = 1')->fetchAll(PDO::FETCH_COLUMN);
  $add('info', 'Admins: ' . implode(', ', $admins));
  $sha = (int) db()->query("SELECT COUNT(*) FROM fb_users WHERE pass_hash LIKE 'sha256:%'")->fetchColumn();
  if ($sha) $add('info', "$sha Benutzer haben sich seit dem Umzug noch nicht angemeldet (altes Passwort-Verfahren, wird beim ersten Login umgestellt)");
  return ['titel' => 'Server & System', 'items' => $it];
}

function chk_user(string $u): array {
  $it = [];
  $add = function ($s, $t) use (&$it) { $it[] = ['s' => $s, 't' => $t]; };
  $s = settings_load($u);
  $fz = fahrzeuge_load($u); $ids = array_column($fz, 'id'); $names = names_by_id_chk($fz);
  $add($s['wohnort'] !== '' && $s['dienstort'] !== '' ? 'ok' : 'err', 'Stammdaten: ' . ($s['name'] ?: '(kein Name)') . ', Wohnort ' . ($s['wohnort'] ?: 'FEHLT') . ', Dienstort ' . ($s['dienstort'] ?: 'FEHLT')
    . ', Entfernung ' . $s['entfernung'] . ' km, km-Geld ' . number_format((float) $s['km_geld'], 2, ',', '') . ' €, Taggeld ab ' . $s['taggeld_min_stunden'] . ' h: ' . $s['taggeld_basis'] . ' € + ' . $s['taggeld_stufung'] . ' €/h, max ' . $s['taggeld_max_betrag'] . ' € ab ' . $s['taggeld_max_stunden'] . ' h');
  if (!$fz) { $add('err', 'Keine Fahrzeuge'); return ['titel' => "Benutzer „{$u}“", 'items' => $it]; }
  $add('ok', 'Fahrzeuge: ' . implode(' · ', array_map(function ($f) { return "Nr. {$f['id']} {$f['bezeichnung']} ({$f['kennzeichen']}), Start-KM " . fmt_int($f['start_km_vorjahr']) . ", privat {$f['privat_km_min']}–{$f['privat_km_max']}, dienstl. {$f['dienstlich_quote']} %"; }, $fz)));
  foreach ($fz as $f) if ($f['privat_km_max'] <= $f['privat_km_min']) $add('info', "{$f['bezeichnung']}: Privat max ≤ min – es werden immer {$f['privat_km_min']} km verwendet");
  $zr = zeitraeume_load($u);
  $bad = array_filter($zr, function ($z) use ($ids) { return !in_array($z['fahrzeug_id'], $ids, true); });
  if ($bad) $add('err', 'Zeiträume verweisen auf Fahrzeuge, die es nicht gibt (alte Excel-IDs) – im Reiter „Fahrzeuge & Orte“ jedem Zeitraum das richtige Fahrzeug zuweisen und speichern, sonst kann nicht generiert werden.');
  $add($bad ? 'err' : ($zr ? 'ok' : 'err'), $zr ? count($zr) . ' Zeiträume: ' . implode(' · ', array_map(function ($z) use ($names) { return ($names[$z['fahrzeug_id']] ?? 'UNBEKANNT ' . $z['fahrzeug_id']) . ' ' . fmt_datum($z['von']) . '–' . fmt_datum($z['bis']); }, $zr)) : 'Keine Zeiträume – Generator geht nicht');

  // Orte & Distanzen
  $orte = orte_load($u); $m = matrix_load($u); $home = ort_clean(trim($s['wohnort']));
  $ohne = array_column(array_filter($orte, function ($o) { return $o['km_einfach'] === null; }), 'ort');
  $add($ohne ? 'warn' : 'ok', count($orte) . ' Orte, ' . count($m) . ' Strecken in der Distanz-Matrix' . ($ohne ? '; ohne „km einfach“: ' . implode(', ', $ohne) : ''));
  $zm = matrix_km($m, 'Zell am Moos', 'Eugendorf');
  if ($zm !== null) $add($zm >= 20 ? 'ok' : 'err', "Prüffall Zell am Moos ↔ Eugendorf: $zm km " . ($zm >= 20 ? '(richtig)' : '(FALSCH – erwartet ~24–25)'));
  else $add('warn', 'Prüffall Zell am Moos ↔ Eugendorf fehlt in der Matrix → „Distanzen online berechnen“ ausführen');
  $hm = matrix_km($m, $home, ort_clean(trim($s['dienstort'])));
  if ($hm !== null) $add(abs($hm - (int) $s['entfernung']) <= 5 ? 'ok' : 'warn', "Arbeitsweg laut Karte $hm km, Stammdaten {$s['entfernung']} km");
  $dist = distanzen_load($u);
  $knownKey = function ($o) use ($dist, $m, $home) {
    $k = norm_ort($o); if ($k === norm_ort($home)) return true;
    foreach ($dist as $d => $v) if (norm_ort($d) === $k) return true;
    foreach (array_keys($m) as $p) { [$a, $b] = explode('|', $p, 2); if ($a === $k || $b === $k) return true; }
    return false;
  };

  // Verdächtige Entfernungen: Orte weit weg vom Wohnort oder außerhalb Österreichs gefunden
  $weit = [];
  foreach (matrix_rows($u) as $mr) {
    $a = norm_ort($mr['ort_a']); $b = norm_ort($mr['ort_b']); $hk = norm_ort($home);
    if (($a === $hk || $b === $hk) && $mr['km'] > 80) $weit[] = ($a === $hk ? $mr['ort_b'] : $mr['ort_a']) . ' ' . $mr['km'] . ' km';
  }
  if ($weit) $add('err', 'Verdächtig weit vom Wohnort (falscher Ort auf der Karte?): ' . implode(', ', $weit) . ' – im Reiter „Fahrzeuge & Orte“ Spalte „gefunden als“ prüfen, Ortsnamen genauer schreiben (z. B. „Kirchberg bei Mattighofen“) und Distanzen neu berechnen');
  $ausland = [];
  foreach ($orte as $o) if ($o['gefunden'] !== '' && $o['gefunden'] !== 'NICHT GEFUNDEN' && stripos($o['gefunden'], 'Österreich') === false) $ausland[] = $o['ort'] . ' → ' . mb_substr($o['gefunden'], 0, 60);
  if ($ausland) $add('err', 'Auf der Karte außerhalb Österreichs gefunden: ' . implode(' | ', $ausland));
  $nf = array_column(array_filter($orte, function ($o) { return $o['gefunden'] === 'NICHT GEFUNDEN'; }), 'ort');
  if ($nf) $add('warn', 'Auf der Karte nicht gefunden: ' . implode(', ', $nf));

  // Jahre
  $jahre = jahre_load($u);
  $add('info', 'Jahre mit Fahrten: ' . ($jahre ? implode(', ', $jahre) : 'keine'));
  $prevEnd = null; $prevJ = null;
  foreach ($jahre as $j) {
    $y = year_load($u, $j); $rows = array_merge(...array_values($y));
    $tage = []; $dup = 0; $seen = []; $fremd = 0; $nameMis = 0;
    foreach ($rows as $r) {
      $tage[$r['datum']] = true;
      $sig = json_encode($r); if (isset($seen[$sig])) $dup++; $seen[$sig] = true;
      if ($r['fahrzeug_id'] !== null && !isset($names[$r['fahrzeug_id']])) $fremd++;
      elseif ($r['fahrzeug_id'] !== null && mb_strtolower($names[$r['fahrzeug_id']]) !== mb_strtolower($r['fahrzeug'])) $nameMis++;
    }
    $soll = (int) (new DateTimeImmutable("$j-12-31"))->format('z') + 1;
    $fehlTage = $soll - count($tage);
    $kd = array_sum(array_column($rows, 'km_d')); $kp = array_sum(array_column($rows, 'km_p'));
    $tp = taggeld_params($s); $tg = 0.0; $tgPriv = 0;
    foreach ($rows as $r) { if ($r['km_d'] > 0) $tg += taggeld_betrag(dauer_min($r['dauer']), $tp); elseif (taggeld_betrag(dauer_min($r['dauer']), $tp) > 0) $tgPriv++; }
    $add('info', "**$j**: " . count($rows) . ' Fahrten in ' . count($y) . ' Monaten, ' . fmt_int($kd) . ' km dienstl., ' . fmt_int($kp) . ' km privat, km-Geld ' . number_format($kd * (float) $s['km_geld'], 2, ',', '.') . ' €, Taggeld ' . number_format($tg, 2, ',', '.') . ' € (diese Summen mit dem alten Jahres-PDF vergleichen)');
    if ($fehlTage > 0 && count($y) === 12) $add('warn', "$j: $fehlTage Kalendertage ohne Eintrag");
    if ($dup) $add('err', "$j: $dup doppelte, völlig gleiche Fahrten (Umzug doppelt gelaufen?)");
    if ($fremd) $add('err', "$j: $fremd Fahrten verweisen auf ein Fahrzeug, das es nicht mehr gibt");
    if ($nameMis) $add('warn', "$j: $nameMis Fahrten mit anderem Fahrzeugnamen als in der Fahrzeugliste (Jahres-PDF zählt nach Namen)");
    if ($tgPriv) $add('ok', "$j: $tgPriv lange Tage ohne Dienst-km bekommen korrekt KEIN Taggeld");
    // Kilometerkette
    $anchor = anchor_get($u, $j);
    $km = $anchor; $gaps = []; $start = [];
    foreach ($y as $mon => $mr) foreach ($mr as $r) {
      $f = $r['fahrzeug_id']; if ($f === null) continue;
      if (!isset($start[$f])) $start[$f] = $r['abfahrt_km'];
      if (!isset($km[$f])) { $km[$f] = $r['abfahrt_km']; $gaps[] = ($names[$f] ?? "FZ $f") . ': kein Anker'; }
      if ($r['abfahrt_km'] !== $km[$f]) $gaps[] = ($names[$f] ?? "FZ $f") . ' ' . fmt_datum($r['datum']) . ': erwartet ' . fmt_int($km[$f]) . ', gespeichert ' . fmt_int($r['abfahrt_km']);
      $km[$f] = $r['abfahrt_km'] + $r['km_d'] + $r['km_p'];
    }
    $add('info', "$j Anker 1.1.: " . ($anchor ? implode(' · ', array_map(function ($f, $v) use ($names) { return ($names[$f] ?? "FZ $f") . ' ' . fmt_int($v); }, array_keys($anchor), $anchor)) : 'keiner'));
    if ($gaps) $add('err', "$j Kilometerkette: " . count($gaps) . ' Sprung/Sprünge – z. B. ' . implode(' | ', array_slice($gaps, 0, 4)) . ' → Knopf „Kette neu berechnen“');
    else $add('ok', "$j Kilometerkette lückenlos ab Anker; Endstände: " . implode(' · ', array_map(function ($f, $v) use ($names) { return ($names[$f] ?? "FZ $f") . ' ' . fmt_int($v); }, array_keys($km), $km)));
    if ($prevEnd !== null && $prevJ === $j - 1) {
      $mis = [];
      foreach ($start as $f => $v) if (isset($prevEnd[$f]) && $prevEnd[$f] !== $v) $mis[] = ($names[$f] ?? "FZ $f") . ' Ende ' . ($j - 1) . ' ' . fmt_int($prevEnd[$f]) . ' ≠ Start ' . $j . ' ' . fmt_int($v);
      $add($mis ? 'err' : 'ok', $mis ? 'Jahresübergang ' . ($j - 1) . '→' . $j . ': ' . implode(' | ', $mis) : 'Jahresübergang ' . ($j - 1) . '→' . $j . ' lückenlos');
    }
    $prevEnd = $km; $prevJ = $j;
    // Plausibilität + Orte ohne Distanz im Keyword-Text
    $fl = pruefe_jahr($y); $n = array_sum(array_map('count', $fl));
    $add($n ? 'warn' : 'ok', $n ? "$j Plausibilität: $n Auffälligkeit(en), z. B. " . implode(' | ', array_slice(array_merge(...array_values($fl)), 0, 3)) : "$j Plausibilität: keine Auffälligkeiten");
    $g = gen_settings_load($u, $j);
    if (!empty($g['keyword_text'])) {
      $miss = [];
      foreach (keywords_aus_text((string) $g['keyword_text']) as $k) if (!$knownKey($k['ort'])) $miss[$k['ort']] = true;
      $add($miss ? 'warn' : 'ok', $miss ? "$j: Orte im Generator ohne Distanz (bekämen Zufalls-km): " . implode(', ', array_keys($miss)) : "$j: alle Generator-Orte haben Distanzen");
    }
  }
  // HU
  foreach (hu_load($u) as $h) {
    $y = year_load($u, (int) substr($h['datum'], 0, 4)); $row = null;
    foreach ($y[(int) substr($h['datum'], 5, 2)] ?? [] as $r) if ($r['datum'] === $h['datum'] && $r['fahrzeug_id'] === $h['fahrzeug_id']) $row = $r;
    $txt = 'HU ' . ($names[$h['fahrzeug_id']] ?? '?') . ' ' . fmt_datum($h['datum']) . ' (' . fmt_int($h['km_at_hu']) . ' km, ' . ($h['hu_fahrt'] ? 'HU-Fahrt vorhanden' : 'offen') . ')';
    $anc = anchor_get($u, (int) substr($h['datum'], 0, 4))[$h['fahrzeug_id']] ?? null;
    if ($anc !== null && $h['km_at_hu'] <= $anc) $add('err', "$txt: HU-Stand liegt UNTER dem Jahres-Startwert " . fmt_int($anc) . ' km – HU-Kilometerstand oder Start-KM falsch');
    if (!$row) $add($h['angewendet_am'] ? 'warn' : 'info', "$txt: keine Fahrt an diesem Tag gespeichert");
    else {
      $ok = strpos($row['route'], '(HU)') !== false;
      $diff = $h['km_at_hu'] - $row['abfahrt_km'];
      $add($ok && $diff >= 0 && $diff <= 150 ? 'ok' : ($h['angewendet_am'] ? 'warn' : 'info'), "$txt: Abfahrt " . fmt_int($row['abfahrt_km']) . " km, bis HU-Stand $diff km Anfahrt" . ($ok ? '' : ' – Fahrt ist (noch) keine HU-Fahrt'));
    }
  }
  return ['titel' => "Benutzer „{$u}“", 'items' => $it];
}
function names_by_id_chk(array $fz): array { $n = []; foreach ($fz as $f) $n[$f['id']] = $f['bezeichnung']; return $n; }

function chk_pdf(string $u): array {
  require_once __DIR__ . '/pdf.php';
  $j = jahre_load($u); if (!$j) return [];
  $j = max($j); $y = year_load($u, $j); $m = max(array_keys($y));
  try {
    $a = pdf_monat($y[$m], $m, $j, settings_load($u), fahrzeuge_load($u)); $b = pdf_jahr($y, $j, settings_load($u), fahrzeuge_load($u));
    return [['s' => strncmp($a, '%PDF', 4) === 0 && strncmp($b, '%PDF', 4) === 0 ? 'ok' : 'err', 't' => 'PDF-Erzeugung: Monat ' . MONATE[$m - 1] . " $j (" . round(strlen($a) / 1024) . " KB) und Jahr $j (" . round(strlen($b) / 1024) . ' KB) erstellt']];
  } catch (Throwable $e) { return [['s' => 'err', 'PDF-Erzeugung fehlgeschlagen: ' . $e->getMessage()]]; }
}

function systempruefung(): array {
  @set_time_limit(120);
  $out = [chk_server()];
  foreach (q('SELECT username FROM fb_users ORDER BY username')->fetchAll(PDO::FETCH_COLUMN) as $u) {
    $sec = chk_user($u);
    $sec['items'] = array_merge($sec['items'], chk_pdf($u));
    $out[] = $sec;
  }
  return $out;
}
