<?php
// Fahrtenbuch - Excel-/CSV-Import (xlsx wird direkt gelesen, keine Zusatzpakete noetig)
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

function norm_col($s): string {
  $s = (string) $s;
  if (class_exists('Normalizer')) $s = (string) Normalizer::normalize($s, Normalizer::FORM_D);
  $s = preg_replace('/\p{Mn}/u', '', $s);
  $s = strtr($s, ['ä' => 'a', 'ö' => 'o', 'ü' => 'u', 'Ä' => 'a', 'Ö' => 'o', 'Ü' => 'u', 'ß' => 'ss']);
  return trim(preg_replace('/[^a-z0-9]+/', '_', mb_strtolower(trim($s), 'UTF-8')), '_');
}

// Liefert die erste Tabelle als Liste von Zeilen (Zeile = Liste von Zellwerten)
function lese_tabelle(string $path, string $name): array {
  if (preg_match('/\.csv$/i', $name)) {
    $txt = (string) file_get_contents($path);
    if (!mb_check_encoding($txt, 'UTF-8')) $txt = mb_convert_encoding($txt, 'UTF-8', 'Windows-1252');
    $txt = preg_replace('/^\xEF\xBB\xBF/', '', $txt);
    $first = strtok($txt, "\n");
    $sep = substr_count($first, ';') > substr_count($first, ',') ? ';' : ',';
    $rows = [];
    foreach (preg_split('/\r?\n/', $txt) as $l) if (trim($l) !== '') $rows[] = str_getcsv($l, $sep, '"', '\\');
    return $rows;
  }
  if (!class_exists('ZipArchive')) throw new RuntimeException('Excel-Dateien können auf diesem Server nicht gelesen werden – bitte als CSV speichern.');
  $zip = new ZipArchive();
  if ($zip->open($path) !== true) throw new RuntimeException('Die Datei ist keine gültige Excel-Datei (.xlsx).');
  $strings = [];
  if (($x = $zip->getFromName('xl/sharedStrings.xml')) !== false) {
    $sx = simplexml_load_string($x);
    foreach ($sx->si as $si) {
      if (isset($si->t)) $strings[] = (string) $si->t;
      else { $t = ''; foreach ($si->r as $r) $t .= (string) $r->t; $strings[] = $t; }
    }
  }
  // Datumsformate erkennen (Excel speichert Datum als Zahl)
  $dateStyles = [];
  if (($x = $zip->getFromName('xl/styles.xml')) !== false) {
    $sx = simplexml_load_string($x);
    $custom = [];
    if (isset($sx->numFmts)) foreach ($sx->numFmts->numFmt as $nf) $custom[(int) $nf['numFmtId']] = (string) $nf['formatCode'];
    $i = 0;
    if (isset($sx->cellXfs)) foreach ($sx->cellXfs->xf as $xf) {
      $id = (int) $xf['numFmtId'];
      $isDate = ($id >= 14 && $id <= 22) || ($id >= 45 && $id <= 47) || (isset($custom[$id]) && preg_match('/[dmy]/i', preg_replace('/"[^"]*"|\[[^\]]*\]/', '', $custom[$id])));
      if ($isDate) $dateStyles[$i] = true;
      $i++;
    }
  }
  $sheet = $zip->getFromName('xl/worksheets/sheet1.xml');
  if ($sheet === false) {
    for ($i = 0; $i < $zip->numFiles; $i++) { $n = $zip->getNameIndex($i); if (preg_match('#^xl/worksheets/[^/]+\.xml$#', $n)) { $sheet = $zip->getFromName($n); break; } }
  }
  $zip->close();
  if ($sheet === false) throw new RuntimeException('Kein Tabellenblatt in der Excel-Datei gefunden.');
  $sx = simplexml_load_string($sheet);
  $rows = [];
  foreach ($sx->sheetData->row as $row) {
    $vals = [];
    foreach ($row->c as $c) {
      $ref = (string) $c['r'];
      preg_match('/^([A-Z]+)/', $ref, $m);
      $col = 0;
      foreach (str_split($m[1] ?? 'A') as $ch) $col = $col * 26 + (ord($ch) - 64);
      $t = (string) $c['t']; $v = isset($c->v) ? (string) $c->v : '';
      if ($t === 's') $v = $strings[(int) $v] ?? '';
      elseif ($t === 'inlineStr') $v = (string) ($c->is->t ?? '');
      elseif ($t === 'b') $v = $v === '1' ? 'WAHR' : 'FALSCH';
      elseif ($v !== '' && is_numeric($v) && isset($dateStyles[(int) $c['s']])) $v = gmdate('Y-m-d', (int) round(((float) $v - 25569) * 86400));
      $vals[$col - 1] = $v;
    }
    if (!$vals) continue;
    $max = max(array_keys($vals));
    $line = [];
    for ($i = 0; $i <= $max; $i++) $line[] = $vals[$i] ?? '';
    $rows[] = $line;
  }
  return $rows;
}

// Tabelle -> Liste assoziativer Zeilen mit normierten Spaltennamen, leere Zeilen raus
function tabelle_assoc(array $rows): array {
  if (!$rows) return [];
  $head = array_map('norm_col', array_shift($rows));
  $out = [];
  foreach ($rows as $r) {
    $a = []; $leer = true;
    foreach ($head as $i => $h) { if ($h === '') continue; $v = trim((string) ($r[$i] ?? '')); $a[$h] = $v; if ($v !== '') $leer = false; }
    if (!$leer) $out[] = $a;
  }
  return $out;
}
// Erste vorhandene Spalte aus den Kandidaten (exakt, dann "enthaelt")
function spalte(array $head, array $kand): ?string {
  foreach ($kand as $k) if (in_array($k, $head, true)) return $k;
  foreach ($head as $h) foreach ($kand as $k) if (strpos($h, $k) !== false) return $h;
  return null;
}

// Fahrzeugliste: Excel-IDs werden IGNORIERT, Zuordnung spaeter ueber die Bezeichnung
function import_fahrzeuge(array $rows): array {
  $rows = tabelle_assoc($rows);
  if (!$rows) return [];
  $head = array_keys($rows[0]);
  $cBez = spalte($head, ['bezeichnung', 'fahrzeug', 'name', 'modell']);
  if (!$cBez) throw new RuntimeException('Keine Spalte „Bezeichnung“ gefunden.');
  $cKz = spalte($head, ['kennzeichen', 'kennz']);
  $cStart = spalte($head, ['start_km_vorjahr', 'startkmvorjahr', 'start_km', 'startkm', 'vorjahr_km', 'start_km_jahr']);
  $cEnd = null;
  foreach ($head as $h) if (preg_match('/^(endkilometer|endkm|kilometerstand_ende|km_stand_ende)/', $h)) { $cEnd = $h; break; }
  $cMin = spalte($head, ['privat_km_min', 'min_privat_km', 'privatkmin']);
  $cMax = spalte($head, ['privat_km_max', 'max_privat_km', 'privatkmax']);
  $cQ = spalte($head, ['dienstlich_quote', 'dienstlichquote', 'dienstl_quote', 'nutzungsprofil']);
  $out = [];
  foreach ($rows as $r) {
    $bez = trim((string) ($r[$cBez] ?? ''));
    if ($bez === '' || in_array(strtolower($bez), ['none', 'nan'], true)) continue;
    $start = $cStart ? (int) to_float($r[$cStart] ?? 0) : 0;
    if ($start === 0 && $cEnd) $start = (int) to_float($r[$cEnd] ?? 0);
    $out[] = ['bezeichnung' => $bez, 'kennzeichen' => $cKz ? (string) $r[$cKz] : '', 'start_km_vorjahr' => $start,
      'privat_km_min' => $cMin && $r[$cMin] !== '' ? (int) to_float($r[$cMin]) : 5,
      'privat_km_max' => $cMax && $r[$cMax] !== '' ? (int) to_float($r[$cMax]) : 20,
      'dienstlich_quote' => $cQ && $r[$cQ] !== '' ? (int) to_float($r[$cQ]) : 90];
  }
  return $out;
}

// Zeitraeume: Zuordnung ueber Kennzeichen/Bezeichnung; nur alte IDs -> fahrzeug_id bleibt leer
function import_zeitraeume(array $rows, array $fahrzeuge): array {
  $rows = tabelle_assoc($rows);
  if (!$rows) return [];
  $head = array_keys($rows[0]);
  $cKz = spalte($head, ['kennzeichen', 'kennz']);
  $cBez = spalte($head, ['bezeichnung', 'fahrzeug', 'name', 'modell']);
  $cVon = spalte($head, ['von', 'beginn', 'start', 'from']);
  $cBis = spalte($head, ['bis', 'ende', 'end', 'to']);
  if (!$cVon || !$cBis) throw new RuntimeException('Spalten „von“ und „bis“ nicht gefunden.');
  $kz = []; $bz = [];
  foreach ($fahrzeuge as $f) { $kz[mb_strtoupper(trim((string) $f['kennzeichen']))] = (int) $f['id']; $bz[mb_strtoupper(trim((string) $f['bezeichnung']))] = (int) $f['id']; }
  $out = [];
  foreach ($rows as $r) {
    $von = to_iso($r[$cVon] ?? null); $bis = to_iso($r[$cBis] ?? null);
    if (!$von || !$bis) continue;
    $fid = null;
    if ($cKz && ($r[$cKz] ?? '') !== '') $fid = $kz[mb_strtoupper(trim($r[$cKz]))] ?? null;
    if ($fid === null && $cBez) $fid = $bz[mb_strtoupper(trim((string) ($r[$cBez] ?? '')))] ?? null;
    $out[] = ['fahrzeug_id' => $fid, 'von' => $von, 'bis' => $bis];
  }
  return $out;
}

function import_keywords(array $rows): string {
  $rows = tabelle_assoc($rows);
  if (!$rows) return '';
  $head = array_keys($rows[0]);
  $cOrt = spalte($head, ['ort', 'ziel', 'stadt']); $cZw = spalte($head, ['zweck', 'grund']);
  if (!$cOrt || !$cZw) throw new RuntimeException('Spalten „Ort“ und „Zweck“ nicht gefunden.');
  $map = [];
  foreach ($rows as $r) { $o = trim($r[$cOrt]); $z = trim($r[$cZw]); if ($o !== '' && $z !== '') $map[$o][] = $z; }
  $lines = [];
  foreach ($map as $o => $z) $lines[] = $o . ':' . implode(',', array_unique($z));
  return implode("\n", $lines);
}

function import_orte(array $rows): array {
  $rows = tabelle_assoc($rows);
  if (!$rows) return [];
  $head = array_keys($rows[0]);
  $c = spalte($head, ['ort', 'ortsname', 'adresse', 'ziel', 'kunde', 'werkstattort']);
  if (!$c) throw new RuntimeException('Keine Ort-Spalte erkannt – benötigt: „Ort“ (oder „Adresse“/„Ziel“).');
  $out = [];
  foreach ($rows as $r) { $o = trim((string) $r[$c]); if ($o !== '' && !in_array(strtolower($o), ['none', 'nan'], true)) $out[$o] = true; }
  return array_keys($out);
}
