<?php
// Fahrtenbuch – einmaliger Umzug der Daten aus Supabase (REST-API mit service_role-Schlüssel).
// Die App ruft das Tabelle für Tabelle auf. Jede Tabelle ersetzt den Inhalt der passenden fb_-Tabelle.
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

const SUPABASE_TABLES = ['users', 'settings', 'system_config', 'fahrzeuge', 'zeitraeume', 'orte', 'orte_distanz', 'ort_koordinaten', 'distanz_matrix',
  'jahres_start_km', 'generation_settings', 'hu_corrections', 'fahrten'];
const SUPABASE_ORDER = [
  'users' => 'username.asc', 'settings' => 'username.asc', 'system_config' => 'id.asc', 'fahrzeuge' => 'id.asc',
  'zeitraeume' => 'username.asc,fahrzeug_id.asc,von.asc,bis.asc', 'orte' => 'username.asc,ort.asc', 'orte_distanz' => 'username.asc,ort.asc',
  'ort_koordinaten' => 'username.asc,ort_key.asc', 'distanz_matrix' => 'username.asc,key_a.asc,key_b.asc',
  'jahres_start_km' => 'username.asc,jahr.asc,fahrzeug_id.asc', 'generation_settings' => 'username.asc,jahr.asc',
  'hu_corrections' => 'username.asc,datum.asc,fahrzeug_id.asc,km_at_hu.asc', 'fahrten' => 'username.asc,datum.asc,abf.asc,fahrzeug_id.asc,km_d.asc,km_p.asc'];

function supabase_fetch_all(string $url, string $key, string $table): array {
  $base = rtrim($url, '/') . '/rest/v1/' . rawurlencode($table);
  $h = ['apikey: ' . $key, 'Authorization: Bearer ' . $key, 'Accept: application/json'];
  $orders = ['id.asc', SUPABASE_ORDER[$table] ?? ''];
  if (SUPABASE_ORDER[$table] === 'id.asc') $orders = ['id.asc'];
  $lastErr = '';
  foreach ($orders as $order) {
    $all = []; $offset = 0; $ok = true;
    while (true) {
      $q = ['select' => '*', 'limit' => 1000, 'offset' => $offset];
      if ($order !== '') $q['order'] = $order;
      [$code, $data, $err, $raw] = http_json('GET', $base . '?' . http_build_query($q), $h, null, 60);
      if ($code === 0) throw new RuntimeException('Keine Verbindung zu Supabase' . ($err ? " ($err)" : '') . '. Ist die Adresse richtig?');
      if ($code === 401 || $code === 403) throw new RuntimeException('Supabase lehnt den Schlüssel ab. Bitte den „service_role“-Schlüssel eintragen.');
      if ($code === 404 && stripos($raw, 'relation') !== false) return [];               // Tabelle gibt es dort nicht
      if ($code >= 400) { $ok = false; $lastErr = (string) ($data['message'] ?? "Fehler $code"); break; }
      if (!is_array($data)) throw new RuntimeException('Unerwartete Antwort von Supabase.');
      $all = array_merge($all, $data);
      if (count($data) < 1000) break;
      $offset += 1000;
    }
    if ($ok) return $all;
  }
  if (stripos($lastErr, 'does not exist') !== false || stripos($lastErr, 'Could not find') !== false) return [];
  throw new RuntimeException("Supabase-Tabelle $table: $lastErr");
}

function supabase_import_table(string $url, string $key, string $table, array $me): array {
  if (!preg_match('#^https://[a-z0-9-]+\.supabase\.co/?$#i', $url) && !cfg('test_any_supabase_url')) throw new InvalidArgumentException('Bitte die Supabase-Adresse in der Form https://xxxx.supabase.co eintragen.');
  if (strlen($key) < 20) throw new InvalidArgumentException('Bitte den service_role-Schlüssel eintragen.');
  if (!in_array($table, SUPABASE_TABLES, true)) throw new InvalidArgumentException('Unbekannte Tabelle.');
  $rows = supabase_fetch_all($url, $key, $table);
  $s = function ($v, int $len = 190) { return mb_substr(trim((string) ($v ?? '')), 0, $len); };
  $u = function ($v) { return norm_username((string) ($v ?? '')); };
  $n = 0; $hinweis = '';
  db()->beginTransaction();
  try {
    switch ($table) {
      case 'users':
        foreach ($rows as $r) {
          $name = $u($r['username'] ?? ''); if ($name === '') continue;
          $pw = strtolower(trim((string) ($r['password'] ?? '')));
          $hash = preg_match('/^[a-f0-9]{64}$/', $pw) ? 'sha256:' . $pw : password_hash(random_password(16), PASSWORD_DEFAULT);
          $exists = q('SELECT id FROM fb_users WHERE username = ?', [$name])->fetchColumn();
          if ($exists) {
            // bestehender Zugang (z. B. der Admin aus der Installation): Passwort bleibt, E-Mail wird übernommen
            if (valid_email((string) ($r['email'] ?? ''))) q('UPDATE fb_users SET email = ? WHERE id = ?', [mb_strtolower(trim($r['email'])), $exists]);
          } else {
            q('INSERT INTO fb_users (username, pass_hash, email, force_pw_change, is_admin) VALUES (?, ?, ?, ?, ?)',
              [$name, $hash, mb_strtolower($s($r['email'] ?? '')), !empty($r['force_pw_change']) ? 1 : 0, $name === FB_ADMIN_DEFAULT ? 1 : 0]);
          }
          $n++;
        }
        q('UPDATE fb_users SET is_admin = 1 WHERE username = ?', [FB_ADMIN_DEFAULT]);
        break;
      case 'settings':
        q('DELETE FROM fb_settings');
        foreach ($rows as $r) { $name = $u($r['username'] ?? ''); if ($name === '') continue; settings_save($name, $r); $n++; }
        break;
      case 'system_config':
        $c = $rows[0] ?? [];
        if (!empty($c['smtp_server'])) {
          $port = (string) ($c['smtp_port'] ?? '465');
          setting_save('mail_mode', 'smtp'); setting_save('smtp_host', $s($c['smtp_server'])); setting_save('smtp_port', $port);
          setting_save('smtp_secure', $port === '465' ? 'ssl' : 'tls'); setting_save('smtp_user', $s($c['smtp_user'] ?? ''));
          setting_save('mail_from', $s($c['smtp_user'] ?? '')); setting_save('mail_from_name', $s($c['smtp_from_name'] ?? 'Fahrtenbuch System'));
          if (!empty($c['smtp_password'])) setting_save('smtp_pass', (string) $c['smtp_password']);
          $n = 1;
        }
        break;
      case 'fahrzeuge':
        q('DELETE FROM fb_fahrzeuge');
        foreach ($rows as $r) {
          if (!isset($r['id'])) continue;
          q('INSERT INTO fb_fahrzeuge (id, username, bezeichnung, kennzeichen, start_km_vorjahr, privat_km_min, privat_km_max, dienstlich_quote) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            [(int) $r['id'], $u($r['username'] ?? ''), $s($r['bezeichnung'] ?? ''), $s($r['kennzeichen'] ?? '', 64), safe_int($r['start_km_vorjahr'] ?? 0, 0),
              safe_int($r['privat_km_min'] ?? 5, 5), safe_int($r['privat_km_max'] ?? 20, 20), safe_int($r['dienstlich_quote'] ?? 90, 90)]);
          $n++;
        }
        break;
      case 'zeitraeume':
        q('DELETE FROM fb_zeitraeume');
        foreach ($rows as $r) {
          $v = parse_date_iso($r['von'] ?? null); $b = parse_date_iso($r['bis'] ?? null); $f = safe_int($r['fahrzeug_id'] ?? null, null);
          if (!$v || !$b || $f === null) continue;
          q('INSERT INTO fb_zeitraeume (username, fahrzeug_id, von, bis) VALUES (?, ?, ?, ?)', [$u($r['username'] ?? ''), $f, $v, $b]); $n++;
        }
        break;
      case 'orte':
        q('DELETE FROM fb_orte');
        foreach ($rows as $r) { $o = $s($r['ort'] ?? '', 150); if ($o === '') continue; q('INSERT IGNORE INTO fb_orte (username, ort, km_einfach) VALUES (?, ?, NULL)', [$u($r['username'] ?? ''), $o]); $n++; }
        break;
      case 'orte_distanz':
        foreach ($rows as $r) {
          $o = $s($r['ort'] ?? '', 150); if ($o === '') continue;
          q('INSERT INTO fb_orte (username, ort, km_einfach) VALUES (?, ?, ?) ON DUPLICATE KEY UPDATE km_einfach = VALUES(km_einfach)', [$u($r['username'] ?? ''), $o, max(0, safe_int($r['km_einfach'] ?? 0, 0))]);
          $n++;
        }
        break;
      case 'ort_koordinaten':
        q('DELETE FROM fb_ort_koordinaten');
        foreach ($rows as $r) {
          $k = norm_ort($r['ort_key'] ?? ($r['ort'] ?? '')); if ($k === '') continue;
          $ok = isset($r['lat'], $r['lon']);
          q('INSERT IGNORE INTO fb_ort_koordinaten (username, ort_key, ort, lat, lon, display_name, ok) VALUES (?, ?, ?, ?, ?, ?, ?)',
            [$u($r['username'] ?? ''), mb_substr($k, 0, 150), $s($r['ort'] ?? $k, 150), $ok ? (float) $r['lat'] : null, $ok ? (float) $r['lon'] : null, $s($r['display_name'] ?? '', 400), $ok ? 1 : 0]);
          $n++;
        }
        break;
      case 'distanz_matrix':
        q('DELETE FROM fb_distanz_matrix');
        foreach ($rows as $r) {
          $km = safe_int($r['km'] ?? 0, 0);
          $a = (string) ($r['ort_a'] ?? $r['key_a'] ?? ''); $b = (string) ($r['ort_b'] ?? $r['key_b'] ?? '');
          if ($km <= 0) continue;
          matrix_upsert($u($r['username'] ?? ''), $a, $b, $km, in_array($r['quelle'] ?? '', ['osrm', 'haversine', 'manuell'], true) ? $r['quelle'] : 'osrm');
          $n++;
        }
        break;
      case 'jahres_start_km':
        q('DELETE FROM fb_jahres_start_km');
        foreach ($rows as $r) {
          $j = safe_int($r['jahr'] ?? null, null); $f = safe_int($r['fahrzeug_id'] ?? null, null);
          if ($j === null || $f === null) continue;
          q('INSERT INTO fb_jahres_start_km (username, jahr, fahrzeug_id, start_km) VALUES (?, ?, ?, ?) ON DUPLICATE KEY UPDATE start_km = VALUES(start_km)', [$u($r['username'] ?? ''), $j, $f, safe_int($r['start_km'] ?? 0, 0)]);
          $n++;
        }
        break;
      case 'generation_settings':
        q('DELETE FROM fb_generation_settings');
        foreach ($rows as $r) {
          $j = safe_int($r['jahr'] ?? null, null); if ($j === null) continue;
          $js = $r['settings_json'] ?? '{}'; if (!is_string($js)) $js = json_encode($js, JSON_UNESCAPED_UNICODE);
          q('INSERT INTO fb_generation_settings (username, jahr, settings_json) VALUES (?, ?, ?) ON DUPLICATE KEY UPDATE settings_json = VALUES(settings_json)', [$u($r['username'] ?? ''), $j, $js]);
          $n++;
        }
        break;
      case 'hu_corrections':
        q('DELETE FROM fb_hu');
        foreach ($rows as $r) {
          $d = parse_date_iso($r['datum'] ?? null); $f = safe_int($r['fahrzeug_id'] ?? null, null);
          if (!$d || $f === null) continue;
          // Annahme: in Supabase gespeicherte HU-Einträge wurden schon auf die Fahrten angewendet → als „angewendet“ markieren
          q('INSERT INTO fb_hu (username, fahrzeug_id, datum, km_at_hu, werkstattort, stopps_vor_hu, stopps_nach_hu, angewendet_am) VALUES (?, ?, ?, ?, ?, ?, ?, UTC_TIMESTAMP())',
            [$u($r['username'] ?? ''), $f, $d, safe_int($r['km_at_hu'] ?? 0, 0), $s($r['werkstattort'] ?? ''), implode(',', stopps_liste($r['stopps_vor_hu'] ?? '')), implode(',', stopps_liste($r['stopps_nach_hu'] ?? ''))]);
          $n++;
        }
        if ($n) $hinweis = 'HU-Einträge wurden als „bereits angewendet“ übernommen (sie stecken schon in den Fahrten).';
        break;
      case 'fahrten':
        q('DELETE FROM fb_fahrten');
        $batch = []; $p = [];
        $flush = function () use (&$batch, &$p) {
          if (!$batch) return;
          q('INSERT INTO fb_fahrten (username, jahr, monat, datum, fahrzeug_id, fahrzeug, route, km_d, km_p, abf, ank, dauer, abfahrt_km) VALUES ' . implode(', ', $batch), $p);
          $batch = []; $p = [];
        };
        foreach ($rows as $r) {
          $f = fahrt_norm($r);
          if ($f['datum'] === '') continue;
          $jahr = safe_int($r['jahr'] ?? null, null) ?? (int) substr($f['datum'], 0, 4);
          $mon = safe_int($r['monat'] ?? null, null) ?? (int) substr($f['datum'], 5, 2);
          $batch[] = '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)';
          array_push($p, $u($r['username'] ?? ''), $jahr, $mon, $f['datum'], $f['fahrzeug_id'], $f['fahrzeug'], $f['route'], $f['km_d'], $f['km_p'], $f['abf'], $f['ank'], $f['dauer'], $f['abfahrt_km']);
          $n++;
          if (count($batch) >= 200) $flush();
        }
        $flush();
        break;
    }
    db()->commit();
  } catch (Throwable $e) { if (db()->inTransaction()) db()->rollBack(); throw $e; }
  return ['table' => $table, 'gelesen' => count($rows), 'uebernommen' => $n, 'hinweis' => $hinweis];
}
