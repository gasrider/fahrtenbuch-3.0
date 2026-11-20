<?php
// Fahrtenbuch – Excel-/CSV-Import (ohne Fremdbibliothek) + Zuordnung wie excel_import.py
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

// Liest die erste Tabelle einer .xlsx-Datei oder eine .csv-Datei. Rückgabe: Liste von Zeilen (erste Zeile = Überschriften).
function read_table_file(string $path, string $name): array {
  $ext = strtolower(pathinfo($name, PATHINFO_EXTENSION));
  if ($ext === 'csv' || $ext === 'txt') return read_csv($path);
  if ($ext !== 'xlsx') throw new InvalidArgumentException('Bitte eine .xlsx- oder .csv-Datei wählen (alte .xls-Dateien vorher in Excel als .xlsx speichern).');
  if (!class_exists('ZipArchive')) throw new RuntimeException('Der Server kann keine Excel-Dateien öffnen (ZipArchive fehlt). Bitte die Datei als CSV speichern und hochladen.');
  $z = new ZipArchive();
  if ($z->open($path) !== true) throw new InvalidArgumentException('Die Excel-Datei ist beschädigt oder keine echte .xlsx-Datei.');
  $shared = [];
  $ss = $z->getFromName('xl/sharedStrings.xml');
  if ($ss !== false) {
    $x = @simplexml_load_string($ss);
    if ($x) foreach ($x->si as $si) {
      if (isset($si->t)) $shared[] = (string) $si->t;
      else { $t = ''; foreach ($si->r as $r) $t .= (string) $r->t; $shared[] = $t; }
    }
  }
  $sheet = 'xl/worksheets/sheet1.xml';
  $wb = $z->getFromName('xl/workbook.xml'); $rels = $z->getFromName('xl/_rels/workbook.xml.rels');
  if ($wb !== false && $rels !== false) {
    $wx = @simplexml_load_string($wb); $rx = @simplexml_load_string($rels);
    if ($wx && $rx && isset($wx->sheets->sheet[0])) {
      $rid = (string) $wx->sheets->sheet[0]->attributes('http://schemas.openxmlformats.org/officeDocument/2006/relationships')['id'];
      foreach ($rx->Relationship as $rel) if ((string) $rel['Id'] === $rid) {
        $t = ltrim((string) $rel['Target'], '/');
        $sheet = strpos($t, 'xl/') === 0 ? $t : 'xl/' . $t;
      }
    }
  }
  $xml = $z->getFromName($sheet);
  $z->close();
  if ($xml === false) throw new InvalidArgumentException('In der Excel-Datei wurde keine Tabelle gefunden.');
  $sx = @simplexml_load_string($xml);
  if (!$sx) throw new InvalidArgumentException('Die Excel-Tabelle konnte nicht gelesen werden.');
  $rows = [];
  foreach ($sx->sheetData->row as $row) {
    $vals = [];
    foreach ($row->c as $c) {
      $ref = (string) $c['r']; $col = 0;
      if (preg_match('/^([A-Z]+)/', $ref, $m)) { foreach (str_split($m[1]) as $ch) $col = $col * 26 + (ord($ch) - 64); $col--; }
      else $col = count($vals);
      $t = (string) $c['t'];
      if ($t === 's') $v = $shared[(int) $c->v] ?? '';
      elseif ($t === 'inlineStr') $v = (string) ($c->is->t ?? '');
      elseif ($t === 'b') $v = ((string) $c->v) === '1' ? 'WAHR' : 'FALSCH';
      else $v = (string) $c->v;
      $vals[$col] = $v;
    }
    if (!$vals) { $rows[] = []; continue; }
    $line = [];
    for ($i = 0, $n = max(array_keys($vals)); $i <= $n; $i++) $line[] = $vals[$i] ?? '';
    $rows[] = $line;
  }
  return $rows;
}
function read_csv(string $path): array {
  $raw = (string) file_get_contents($path);
  if (strncmp($raw, "\xEF\xBB\xBF", 3) === 0) $raw = substr($raw, 3);
  if (!mb_check_encoding($raw, 'UTF-8')) $raw = mb_convert_encoding($raw, 'UTF-8', 'Windows-1252');
  $first = strtok($raw, "\n");
  $del = ';';
  foreach ([';', ',', "\t"] as $d) if (substr_count((string) $first, $d) > substr_count((string) $first, $del)) $del = $d;
  $rows = [];
  $fh = fopen('php://memory', 'r+'); fwrite($fh, $raw); rewind($fh);
  while (($r = fgetcsv($fh, 0, $del, '"', '\\')) !== false) $rows[] = array_map(function ($v) { return trim((string) $v); }, $r);
  fclose($fh);
  return $rows;
}

function normalize_col($s): string {
  $s = strtr((string) $s, ['ä' => 'a', 'ö' => 'o', 'ü' => 'u', 'Ä' => 'a', 'Ö' => 'o', 'Ü' => 'u', 'á' => 'a', 'à' => 'a', 'é' => 'e', 'è' => 'e', 'í' => 'i', 'ó' => 'o', 'ú' => 'u']);
  $s = mb_strtolower(trim($s), 'UTF-8');
  return trim((string) preg_replace('/[^\p{L}\p{N}_]+/u', '_', $s), '_');
}
// Tabelle → Liste assoziativer Zeilen mit normalisierten Überschriften, leere Zeilen entfernt
function table_assoc(array $rows): array {
  if (!$rows) return [[], []];
  $head = array_map('normalize_col', array_shift($rows));
  $out = [];
  foreach ($rows as $r) {
    $a = []; $empty = true;
    foreach ($head as $i => $h) { $v = trim((string) ($r[$i] ?? '')); if ($v !== '') $empty = false; if ($h !== '' && !array_key_exists($h, $a)) $a[$h] = $v; }
    if (!$empty) $out[] = $a;
  }
  return [array_values(array_filter($head, 'strlen')), $out];
}
// Benennt die erste passende Spalte um (exakt, sonst „enthält“) – wie helpers.coalesce
function coalesce_col(array $head, array $cands): ?string {
  foreach ($cands as $c) if (in_array($c, $head, true)) return $c;
  foreach ($head as $h) foreach ($cands as $c) if (strpos($h, $c) !== false) return $h;
  return null;
}
function col_val(array $row, ?string $col, $def = '') { return ($col !== null && isset($row[$col]) && $row[$col] !== '') ? $row[$col] : $def; }
function excel_date($v): ?string {
  $v = trim((string) $v);
  if ($v === '') return null;
  if (is_numeric($v) && (float) $v > 20000 && (float) $v < 80000) return (new DateTimeImmutable('1899-12-30'))->modify('+' . (int) floor((float) $v) . ' days')->format('Y-m-d');
  return parse_date_iso(preg_replace('/\s.*$/', '', $v));
}
function num_or($v, int $def): int {
  $s = str_replace([' ', "\u{a0}"], '', trim((string) $v));
  if ($s === '') return $def;
  if (preg_match('/^-?\d{1,3}(\.\d{3})+$/', $s)) $s = str_replace('.', '', $s);   // 206.371
  $s = str_replace(',', '.', $s);
  return is_numeric($s) ? (int) round((float) $s) : $def;
}

// Fahrzeugliste: Excel-ID wird IGNORIERT (alte IDs!), Zuordnung später über die Bezeichnung
function import_fahrzeuge(array $rows): array {
  [$head, $data] = table_assoc($rows);
  $cB = coalesce_col($head, ['bezeichnung', 'fahrzeug', 'name', 'modell']);
  $cK = coalesce_col($head, ['kennzeichen', 'kennz']);
  $cEnd = null;
  foreach ($head as $h) if (preg_match('/^(endkilometer|endkm|kilometerstand_ende|km_stand_ende)/', $h)) { $cEnd = $h; break; }
  $cS = coalesce_col($head, ['start_km_vorjahr', 'startkmvorjahr', 'start_km', 'startkm', 'vorjahr_km', 'start_km_jahr']);
  $cMin = coalesce_col($head, ['privat_km_min', 'privatkmmmin', 'min_privat_km', 'privatkmin']);
  $cMax = coalesce_col($head, ['privat_km_max', 'privatkmmmax', 'max_privat_km', 'privatkmax']);
  $cQ = coalesce_col($head, ['dienstlich_quote', 'dienstlichquote', 'dienstl_quote', 'nutzungsprofil']);
  if ($cB === null) throw new InvalidArgumentException('Keine Spalte „Bezeichnung“ (oder Fahrzeug/Name/Modell) gefunden.');
  $out = [];
  foreach ($data as $r) {
    $b = trim((string) col_val($r, $cB));
    if ($b === '') continue;
    $start = num_or(col_val($r, $cS, ''), 0);
    if ($start === 0 && $cEnd !== null) $start = num_or(col_val($r, $cEnd, ''), 0);
    $out[] = ['bezeichnung' => $b, 'kennzeichen' => trim((string) col_val($r, $cK)), 'start_km_vorjahr' => $start,
      'privat_km_min' => num_or(col_val($r, $cMin, ''), 5), 'privat_km_max' => num_or(col_val($r, $cMax, ''), 20), 'dienstlich_quote' => num_or(col_val($r, $cQ, ''), 90)];
  }
  return $out;
}
// Zeiträume: Zuordnung über Kennzeichen, dann Bezeichnung. Nur alte IDs → bleibt offen (manuell wählen)
function import_zeitraeume(array $rows, array $fahrzeuge): array {
  [$head, $data] = table_assoc($rows);
  $cK = coalesce_col($head, ['kennzeichen', 'kennz']);
  $cB = coalesce_col($head, ['bezeichnung', 'fahrzeug', 'name', 'modell']);
  $cV = coalesce_col($head, ['von', 'beginn', 'start', 'from']);
  $cBis = coalesce_col($head, ['bis', 'ende', 'end', 'to']);
  if ($cV === null || $cBis === null) throw new InvalidArgumentException('Keine Spalten „von“ und „bis“ gefunden.');
  $byK = []; $byB = [];
  foreach ($fahrzeuge as $f) { $byK[mb_strtoupper(trim((string) $f['kennzeichen']))] = (int) $f['id']; $byB[mb_strtoupper(trim((string) $f['bezeichnung']))] = (int) $f['id']; }
  unset($byK['']);
  $out = [];
  foreach ($data as $r) {
    $v = excel_date(col_val($r, $cV)); $b = excel_date(col_val($r, $cBis));
    if (!$v || !$b) continue;
    $fid = null;
    if ($cK !== null) $fid = $byK[mb_strtoupper(trim((string) col_val($r, $cK)))] ?? null;
    if ($fid === null && $cB !== null) $fid = $byB[mb_strtoupper(trim((string) col_val($r, $cB)))] ?? null;
    $out[] = ['fahrzeug_id' => $fid, 'von' => $v, 'bis' => $b];
  }
  return $out;
}
function import_keywords(array $rows): array {
  [$head, $data] = table_assoc($rows);
  $cO = coalesce_col($head, ['ort', 'ziel', 'stadt']); $cZ = coalesce_col($head, ['zweck', 'grund']);
  if ($cO === null || $cZ === null) throw new InvalidArgumentException('Keine Spalten „Ort“ und „Zweck“ gefunden.');
  $out = [];
  foreach ($data as $r) { $o = trim((string) col_val($r, $cO)); $z = trim((string) col_val($r, $cZ)); if ($o !== '') $out[] = ['ort' => $o, 'zweck' => $z]; }
  return $out;
}
function import_orte(array $rows): array {
  [$head, $data] = table_assoc($rows);
  $col = null;
  foreach (['ort', 'ortsname', 'adresse', 'ziel', 'kunde', 'werkstattort'] as $c) if (in_array($c, $head, true)) { $col = $c; break; }
  if ($col === null) foreach ($head as $h) foreach (['ort', 'ziel', 'kunde'] as $k) if ($col === null && strpos($h, $k) !== false) $col = $h;
  if ($col === null) throw new InvalidArgumentException('Keine Ort-Spalte erkannt – benötigt: „Ort“ (oder „Adresse“/„Ziel“).');
  $out = [];
  foreach ($data as $r) { $v = trim((string) ($r[$col] ?? '')); if ($v !== '' && !in_array(strtolower($v), ['none', 'nan'], true)) $out[$v] = true; }
  return array_keys($out);
}
