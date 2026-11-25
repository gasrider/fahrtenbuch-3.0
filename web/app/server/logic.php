<?php
// Fahrtenbuch - Fachlogik (Generator, Kilometerkette, Pruefung, Taggeld, HU, Privat-KM).
// 1:1-Uebertragung der bewaehrten Python-Logik aus der Streamlit-Version.
// Eine Fahrt ist ein Array: datum (Y-m-d), fahrzeug_id (int|null), fahrzeug, route,
// km_d, km_p, abf, ank, dauer, abfahrt_km. Ein Jahr ist [monat => [fahrten...]].
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

const MONATE = ['Jänner', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
const WOCHENTAGE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
const IGNORE_ROUTES = ['Keine Fahrt', 'Sonntag', 'Feiertag', 'Urlaub'];
const MIN_LEG_KM = 8;
const SCALE_MIN = 0.70;
const SCALE_MAX = 1.70;
const HU_FAKTOR_MIN = 0.5;
const HU_FAKTOR_MAX = 2.0;
// Plausibilitaet: eine einfache Strecke zwischen zwei Orten der Region ist nie laenger.
// Laengere Werte stammen fast immer von einer falsch gefundenen Ortschaft
// (z. B. "Neumarkt" -> Neumarkt in der Steiermark statt Neumarkt am Wallersee).
const PLAUSI_LEG_KM = 120;
// Orte werden nur akzeptiert, wenn sie hoechstens so weit (Luftlinie) vom Wohnort liegen
const MAX_ORT_ENTFERNUNG_KM = 100;

/* ---------- Helfer ---------- */
function to_int($v, ?int $default = 0): ?int {
  if ($v === null) return $default;
  if (is_int($v)) return $v;
  if (is_float($v)) return is_nan($v) ? $default : (int) $v;
  $s = strtolower(trim(str_replace(['.', ','], '', (string) $v)));
  if ($s === '' || in_array($s, ['none', 'nan', 'nat', 'null'], true)) return $default;
  return preg_match('/^-?\d+$/', $s) ? (int) $s : $default;
}
function to_float($v, float $default = 0.0): float {
  if ($v === null || $v === '') return $default;
  if (is_int($v) || is_float($v)) return (float) $v;
  $s = str_replace(',', '.', trim((string) $v));
  return is_numeric($s) ? (float) $s : $default;
}
// Datum (ISO, dd.mm.yyyy, Excel-Zahl) -> 'Y-m-d' oder null
function to_iso($v): ?string {
  if ($v === null) return null;
  $s = trim((string) $v);
  if ($s === '' || in_array(strtolower($s), ['nat', 'nan', 'none', 'null'], true)) return null;
  if (preg_match('/^(\d{4})-(\d{2})-(\d{2})/', $s, $m)) return checkdate((int) $m[2], (int) $m[3], (int) $m[1]) ? "$m[1]-$m[2]-$m[3]" : null;
  if (preg_match('/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/', $s, $m)) return checkdate((int) $m[2], (int) $m[1], (int) $m[3]) ? sprintf('%04d-%02d-%02d', $m[3], $m[2], $m[1]) : null;
  if (is_numeric($s) && (float) $s > 20000 && (float) $s < 80000) return gmdate('Y-m-d', (int) round(((float) $s - 25569) * 86400));
  return null;
}
function luftlinie_km(float $lat1, float $lon1, float $lat2, float $lon2): float {
  $p1 = deg2rad($lat1); $p2 = deg2rad($lat2); $dl = deg2rad($lon2 - $lon1);
  $h = sin(($p2 - $p1) / 2) ** 2 + cos($p1) * cos($p2) * sin($dl / 2) ** 2;
  return 2 * 6371 * asin(min(1.0, sqrt($h)));
}
// Unplausible Distanzen sammeln (fuer den Hinweis nach Generierung/HU)
function verdacht(?string $text = null): array {
  static $liste = [];
  if ($text === null) { $l = array_keys($liste); $liste = []; return $l; }
  $liste[$text] = true;
  return [];
}
function norm_ort($n): string { return mb_strtolower(trim((string) $n), 'UTF-8'); }
function mkey(string $a, string $b): string { $a = norm_ort($a); $b = norm_ort($b); return strcmp($a, $b) <= 0 ? "$a|$b" : "$b|$a"; }
function ort_clean(string $s): string { return strpos($s, ',') !== false ? trim(substr($s, strrpos($s, ',') + 1)) : trim($s); }
function hhmm(int $min): string { $min = max(0, $min); return sprintf('%02d:%02d', intdiv($min, 60), $min % 60); }
function dauer_min($d): int { $p = explode(':', (string) $d); return count($p) === 2 && is_numeric($p[0]) && is_numeric($p[1]) ? (int) $p[0] * 60 + (int) $p[1] : 0; }
function dauer_string(string $abf, string $ank): string { $m = dauer_min($ank) - dauer_min($abf); if ($m < 0) $m += 1440; return hhmm($m); }
function rint(int $lo, int $hiExcl): int { return $hiExcl <= $lo ? $lo : mt_rand($lo, $hiExcl - 1); } // wie numpy integers(lo, hi)
function rnd(): float { return mt_rand() / (mt_getrandmax() + 1); }
function sample(array $arr, int $n): array { if (!$arr) return []; $keys = (array) array_rand($arr, min($n, count($arr))); shuffle($keys); return array_map(function ($k) use ($arr) { return $arr[$k]; }, $keys); }

/* ---------- Kalender ---------- */
function easter_sunday(int $y): string {
  $a = $y % 19; $b = intdiv($y, 100); $c = $y % 100; $d = intdiv($b, 4); $e = $b % 4;
  $f = intdiv($b + 8, 25); $g = intdiv($b - $f + 1, 3); $h = (19 * $a + $b - $d - $g + 15) % 30;
  $i = intdiv($c, 4); $k = $c % 4; $l = (32 + 2 * $e + 2 * $i - $h - $k) % 7; $m = intdiv($a + 11 * $h + 22 * $l, 451);
  return sprintf('%04d-%02d-%02d', $y, intdiv($h + $l - 7 * $m + 114, 31), (($h + $l - 7 * $m + 114) % 31) + 1);
}
function austria_holidays(int $y): array {
  $e = new DateTimeImmutable(easter_sunday($y));
  $d = ["$y-01-01", "$y-01-06", "$y-05-01", "$y-08-15", "$y-10-26", "$y-11-01", "$y-12-08", "$y-12-25", "$y-12-26"];
  foreach ([1, 39, 50, 60] as $off) $d[] = $e->modify("+$off day")->format('Y-m-d');
  return array_fill_keys($d, true);
}
function urlaubs_tage(int $anzahl, string $verteilung, ?string $start): array {
  $out = [];
  if ($anzahl <= 0 || !$start) return $out;
  $s = new DateTimeImmutable($start);
  $bloecke = $verteilung === '2x2 Wochen' ? [[0, 14], [26 * 7, 14]] : ($verteilung === '4x1 Woche' ? [[0, 7], [91, 7], [182, 7], [273, 7]] : [[0, 28]]);
  foreach ($bloecke as [$off, $len]) for ($j = 0; $j < $len; $j++) $out[$s->modify('+' . ($off + $j) . ' day')->format('Y-m-d')] = true;
  return $out;
}

/* ---------- Taggeld ---------- */
function taggeld_params(array $st): array {
  return ['min' => to_float($st['taggeld_min_stunden'] ?? null, 5), 'basis' => to_float($st['taggeld_basis'] ?? null, 10),
    'stufung' => to_float($st['taggeld_stufung'] ?? null, 2.5), 'max' => to_float($st['taggeld_max_betrag'] ?? null, 30),
    'max_h' => to_float($st['taggeld_max_stunden'] ?? null, 13)];
}
// Taggeld nur bei echter Dienstfahrt (km_d > 0)
function taggeld(int $dauerMin, int $kmD, array $p): float {
  if ($kmD <= 0) return 0.0;
  $h = $dauerMin / 60.0;
  if ($h < $p['min']) return 0.0;
  if ($h >= $p['max_h']) return round($p['max'], 2);
  return round(min($p['basis'] + ($h - $p['min']) * $p['stufung'], $p['max']), 2);
}

/* ---------- Kilometerkette: immer ab dem Jahres-Anker ---------- */
function sort_fahrten(array $rows): array {
  $i = 0;
  foreach ($rows as &$r) $r['_i'] = $i++;
  unset($r);
  usort($rows, function ($a, $b) { return strcmp((string) $a['datum'], (string) $b['datum']) ?: $a['_i'] <=> $b['_i']; });
  foreach ($rows as &$r) unset($r['_i']);
  return $rows;
}
function baue_kette_neu(array $jahr, array $anchor): array {
  $km = [];
  foreach ($anchor as $f => $v) $km[(int) $f] = (int) $v;
  ksort($jahr);
  foreach ($jahr as $m => $rows) {
    $rows = sort_fahrten($rows);
    foreach ($rows as &$r) {
      $f = to_int($r['fahrzeug_id'] ?? null, null);
      $r['fahrzeug_id'] = $f;
      $r['km_d'] = to_int($r['km_d'] ?? 0); $r['km_p'] = to_int($r['km_p'] ?? 0);
      if ($f !== null) { $r['abfahrt_km'] = $km[$f] ?? 0; $km[$f] = ($km[$f] ?? 0) + $r['km_d'] + $r['km_p']; }
      else $r['abfahrt_km'] = 0;
    }
    unset($r);
    $jahr[$m] = $rows;
  }
  return [$jahr, $km];
}

/* ---------- Plausibilitaetspruefung ---------- */
function ist_ignore_route($route): bool {
  $s = (string) $route;
  foreach (IGNORE_ROUTES as $ign) if ($s === $ign || strpos($s, "$ign:") === 0 || strpos($s, "$ign ") === 0) return true;
  return false;
}
function pruefe_monat(array $rows): array {
  $flags = []; $proTag = [];
  foreach ($rows as $r) {
    $d = date('d.m.Y', strtotime((string) $r['datum']));
    $total = to_int($r['km_d']) + to_int($r['km_p']);
    $dm = dauer_min($r['dauer'] ?? '');
    if ($total > 0 && $dm > 0 && $total / $dm * 60 > 130)
      $flags[] = "$d: Unrealistische Geschwindigkeit – $total km in {$r['dauer']} (~" . round($total / $dm * 60) . ' km/h).';
    if (to_int($r['km_d']) > 2 * PLAUSI_LEG_KM * 1.5)
      $flags[] = "$d: Dienstfahrt mit " . to_int($r['km_d']) . ' km – ungewöhnlich lang, Distanzen der Orte prüfen.';
    if ($total === 0 && !ist_ignore_route($r['route'] ?? ''))
      $flags[] = "$d: Dienstreise „" . mb_substr((string) $r['route'], 0, 30) . '…“ eingetragen, aber 0 km.';
    if ($total > 0 && dauer_min($r['ank'] ?? '') < dauer_min($r['abf'] ?? ''))
      $flags[] = "$d: Ankunft ({$r['ank']}) liegt vor der Abfahrt ({$r['abf']}).";
    $proTag[(string) $r['datum']][] = (string) ($r['abf'] ?? '');
  }
  foreach ($proTag as $datum => $abf) if (count($abf) > 1 && count(array_unique($abf)) < count($abf))
    $flags[] = date('d.m.Y', strtotime($datum)) . ': Mehrere Fahrten mit exakt gleicher Abfahrtszeit.';
  return $flags;
}
// Kilometer bleiben, nur die Fahrzeit wird bei > 100 km/h verlaengert
function korrigiere_geschwindigkeit(array $rows, int $max = 100): array {
  foreach ($rows as &$r) {
    $t = to_int($r['km_d']) + to_int($r['km_p']); $dm = dauer_min($r['dauer']);
    if ($t <= 0 || $dm <= 0 || $t / $dm * 60 <= $max) continue;
    $neu = min((int) ($t / $max * 60) + 20, 840);
    // Ankunft spaetestens 23:59 - sonst die Abfahrt vorziehen, damit Dauer und Zeiten zusammenpassen
    $abf = min(dauer_min($r['abf']), 23 * 60 + 59 - $neu);
    $r['abf'] = hhmm(max(0, $abf));
    $r['ank'] = hhmm(max(0, $abf) + $neu);
    $r['dauer'] = hhmm($neu);
  }
  unset($r);
  return $rows;
}

/* ---------- Generator (Monatsziele v5: echte Streuung) ---------- */
function matrix_wert(array $matrix, string $a, string $b): ?int {
  $na = norm_ort($a); $nb = norm_ort($b);
  if ($na === '' || $nb === '' || $na === $nb || empty($matrix[mkey($a, $b)])) return null;
  $km = (int) $matrix[mkey($a, $b)];
  if ($km > PLAUSI_LEG_KM) { [$x, $y] = strcmp($na, $nb) <= 0 ? [$a, $b] : [$b, $a]; verdacht("$x – $y: $km km"); return null; }
  return $km;
}
function leg_km(array $dist, array $matrix, string $a, string $b): int {
  $na = norm_ort($a); $nb = norm_ort($b);
  $m = matrix_wert($matrix, $a, $b);
  if ($m !== null) return $m;
  if (!array_key_exists($na, $dist) || !array_key_exists($nb, $dist)) return rint(15, 35);
  return max(abs($dist[$na] - $dist[$nb]), MIN_LEG_KM);
}
function tour_km(array $dist, array $matrix, string $home, array $stops): int {
  $t = 0; $prev = $home;
  foreach ($stops as $o) { $t += leg_km($dist, $matrix, $prev, $o); $prev = $o; }
  return $t + leg_km($dist, $matrix, $prev, $home);
}
function tour_zeiten(bool $ganztags): array {
  $abf = 8 * 60 + rint(0, 11);
  $ank = $ganztags ? rint(17 * 60, 22 * 60 + 1) : rint(13 * 60, 17 * 60 + 1);
  return [hhmm($abf), hhmm($ank), hhmm($ank - $abf)];
}
function privat_zeiten(int $kmP): array {
  $start = rint(9, 18) * 60;
  $fz = max((int) ($kmP / 70 * 60) + rint(5, 15), 15);
  return [hhmm($start), hhmm($start + $fz), hhmm($fz)];
}

/**
 * $fahrzeuge: [[id, bezeichnung, privat_km_min, privat_km_max, dienstlich_quote], ...]
 * $zeitraeume: [[fahrzeug_id, von, bis], ...], $keywords: [[Ort, Zweck], ...]
 * Rueckgabe: [[monat => fahrten], fehlende_orte]
 */
function generiere_monate(int $jahr, array $monate, array $st, array $fahrzeuge, array $zeitraeume, array $keywords, array $p): array {
  $hol = austria_holidays($jahr);
  $home = ort_clean((string) ($st['wohnort'] ?? '') ?: 'Oberhofen am Irrsee');
  $buero = ort_clean((string) ($st['dienstort'] ?? '') ?: 'Straßwalchen');
  $entf = to_int($st['entfernung'] ?? null, 25);
  $matrix = $p['matrix'] ?? [];
  $matrixOrte = [];
  foreach (array_keys($matrix) as $k) foreach (explode('|', $k) as $o) $matrixOrte[$o] = true;
  $dist = [];
  foreach (($p['distanzen'] ?? []) as $o => $km) {
    if ((int) $km > PLAUSI_LEG_KM) { verdacht("$o: $km km einfach vom Wohnort"); continue; }
    $dist[norm_ort($o)] = max(0, (int) $km);
  }
  $dist[norm_ort($home)] = 0;
  if (!isset($dist[norm_ort($buero)])) $dist[norm_ort($buero)] = max(0, $entf);
  $fehlende = [];

  $namen = []; $privRange = []; $quote = [];
  foreach ($fahrzeuge as $f) {
    $id = (int) $f['id'];
    $namen[$id] = (string) $f['bezeichnung'];
    $privRange[$id] = [to_int($f['privat_km_min'] ?? null, 5), to_int($f['privat_km_max'] ?? null, 20)];
    $quote[$id] = max(0, min(100, to_int($f['dienstlich_quote'] ?? null, 90)));
  }
  if (!$namen) throw new InvalidArgumentException('Keine Fahrzeuge vorhanden – zuerst Fahrzeuge anlegen und speichern.');
  $zr = [];
  foreach ($zeitraeume as $z) {
    $v = to_iso($z['von'] ?? null); $b = to_iso($z['bis'] ?? null); $fid = to_int($z['fahrzeug_id'] ?? null, null);
    if ($v && $b && $fid !== null && isset($namen[$fid])) $zr[] = [$v, $b, $fid];
  }
  $deckt = false;
  foreach ($zr as [$v, $b]) if ((int) substr($v, 0, 4) <= $jahr && $jahr <= (int) substr($b, 0, 4)) $deckt = true;
  if (!$deckt) throw new InvalidArgumentException("Kein Zeitraum deckt das Jahr $jahr ab! Bitte Zeiträume (von/bis) im Tab „Fahrzeuge & Orte“ anpassen.");

  $ids = array_flip($namen);
  $urlaub = $p['urlaubstage'] ?? [];
  $urlaubFz = $ids[$p['urlaub_fahrzeug_name'] ?? ''] ?? null;
  $hauptId = $ids[$p['hauptfahrzeug_name'] ?? ''] ?? null;
  $hauptAnteil = to_float($p['hauptfahrzeug_anteil'] ?? 70) / 100;
  $probFeiertag = to_float($p['prob_feiertag_urlaub'] ?? 5) / 100;
  $probWerktag = to_int($p['prob_werktag'] ?? 75);
  $kw = $keywords ?: [['Ort' => 'Büro', 'Zweck' => 'Büro']];
  $privKm = function ($fid) use ($privRange) {
    if ($fid !== null && isset($privRange[$fid])) return rint($privRange[$fid][0], $privRange[$fid][1]);
    return rint(5, 21);
  };
  $stopps = function (int $n) use ($kw, $dist, $matrixOrte, &$fehlende) {
    $orte = []; $txt = [];
    foreach (sample($kw, $n) as $r) {
      $o = trim((string) $r['Ort']);
      $orte[] = $o; $txt[] = "$o ({$r['Zweck']})";
      if (!isset($dist[norm_ort($o)]) && !isset($matrixOrte[norm_ort($o)])) $fehlende[$o] = true;
    }
    return [$orte, $txt];
  };

  $tMin = to_int($p['target_km_min'] ?? null, 1650); $tMax = to_int($p['target_km_max'] ?? null, 2000);
  if ($tMin > $tMax) [$tMin, $tMax] = [$tMax, $tMin];

  $result = [];
  foreach ($monate as $monat) {
    $tage = (int) date('t', mktime(0, 0, 0, $monat, 1, $jahr));
    $rows = [];
    $sonderDone = false;
    for ($tag = 1; $tag <= $tage; $tag++) {
      $ts = mktime(12, 0, 0, $monat, $tag, $jahr);
      $datum = date('Y-m-d', $ts);
      $wd = (int) date('N', $ts) - 1; // 0 = Montag
      $route = 'Keine Fahrt'; $kmD = 0; $kmP = 0; $abf = $ank = $dauer = '00:00';
      $fid = null; $fname = 'Kein Fahrzeug';
      $gueltig = [];
      foreach ($zr as [$v, $b, $f]) if ($v <= $datum && $datum <= $b) $gueltig[] = $f;
      if ($gueltig) {
        if ($hauptId !== null && in_array($hauptId, $gueltig, true) && count($gueltig) > 1) {
          $rest = (1.0 - $hauptAnteil) / (count($gueltig) - 1);
          $x = rnd(); $acc = 0.0; $fid = end($gueltig);
          foreach ($gueltig as $g) { $acc += $g === $hauptId ? $hauptAnteil : $rest; if ($x < $acc) { $fid = $g; break; } }
        } else $fid = $gueltig[array_rand($gueltig)];
        $fname = $namen[$fid] ?? 'Unbekannt';
      }
      if ($wd === 0) $sonderDone = false;
      $isHol = isset($hol[$datum]); $isUrl = isset($urlaub[$datum]);

      if ($isHol || $isUrl) {
        if (rnd() < $probFeiertag) {
          [$orte, $txt] = $stopps(rint(1, 3));
          $kmD = tour_km($dist, $matrix, $home, $orte);
          $route = ($isHol ? 'Feiertag: ' : 'Urlaub: ') . implode(' - ', array_merge([$home], $txt, [$home]));
          [$abf, $ank, $dauer] = tour_zeiten(false);
        } else {
          if ($isUrl) {
            if ($urlaubFz !== null && in_array($urlaubFz, $gueltig, true)) {
              $fid = $urlaubFz; $fname = $namen[$fid];
              $kmP = rint(to_int($p['urlaub_km_min'] ?? 30), to_int($p['urlaub_km_max'] ?? 80) + 1);
              $route = 'Urlaub';
            } else { $kmP = rint(5, 21); $route = 'Urlaub (Urlaubs-FZ nicht verfügbar)'; }
          } else { $kmP = $privKm($fid); $route = 'Feiertag'; }
          [$abf, $ank, $dauer] = privat_zeiten($kmP);
        }
      } elseif ($wd === 5) {
        if (rnd() < 0.4) {
          [$orte, $txt] = $stopps(1);
          $kmD = tour_km($dist, $matrix, $home, $orte);
          $route = implode(' - ', array_merge([$home], $txt, [$home]));
          [$abf, $ank, $dauer] = tour_zeiten(false);
        }
      } elseif ($wd === 6) {
        $kmP = $privKm($fid); $route = 'Sonntag';
        [$abf, $ank, $dauer] = privat_zeiten($kmP);
      } else {
        $q = ($quote[$fid] ?? 90) / 100;
        if (rnd() >= $q) {
          $kmP = $privKm($fid);
          $route = rnd() < 0.4 ? "$home - $buero (Arbeitsweg)" : 'Privatfahrt';
          $a = 8 * 60 + rint(0, 11); $e = rint(16 * 60, 19 * 60 + 1);
          [$abf, $ank, $dauer] = [hhmm($a), hhmm($e), hhmm($e - $a)];
        } else {
          $woche = (int) date('W', $ts);
          $zielTag = $woche % 2 === 1 ? 0 : 1;
          if ($wd === $zielTag && !$sonderDone) {
            // 2-woechentliche Sonderfahrt ueber den Dienstort (Buero)
            $sonderDone = true;
            $kmP = matrix_wert($matrix, $home, $buero) ?? max(1, $entf);
            [$orte, $txt] = $stopps(rint(1, 4));
            $route = implode(' - ', array_merge([$home, "$buero (Büro)"], $txt, [$home]));
            $kmD = tour_km($dist, $matrix, $home, array_merge([$buero], $orte));
          } else {
            $n = $probWerktag >= 90 ? rint(1, 3) : ($probWerktag >= 70 ? rint(1, 4) : ($probWerktag >= 50 ? rint(2, 4) : rint(2, 5)));
            [$orte, $txt] = $stopps($n);
            $route = implode(' - ', array_merge([$home], $txt, [$home]));
            $kmD = tour_km($dist, $matrix, $home, $orte); $kmP = 0;
          }
          [$abf, $ank, $dauer] = tour_zeiten(true);
        }
      }
      $rows[] = ['datum' => $datum, 'fahrzeug_id' => $fid, 'fahrzeug' => $fname, 'route' => $route,
        'km_d' => $kmD, 'km_p' => $kmP, 'abf' => $abf, 'ank' => $ank, 'dauer' => $dauer, 'abfahrt_km' => 0];
    }
    // Monatsziel v5: jeder Monat wuerfelt sein Ziel im Korridor [Min - 100 .. Max + 100]
    $cur = array_sum(array_column($rows, 'km_d'));
    if ($tMax > 0 && $cur > 0) {
      $ziel = rint(max(0, $tMin - 100), $tMax + 100 + 1);
      $sf = max(SCALE_MIN, min(SCALE_MAX, $ziel / $cur));
      if ($ziel > 0) foreach ($rows as &$r) if ($r['km_d'] > 0) $r['km_d'] = (int) round($r['km_d'] * $sf);
      unset($r);
    }
    $result[$monat] = korrigiere_geschwindigkeit($rows);
  }
  $f = array_keys($fehlende); sort($f);
  return [$result, $f, verdacht()];
}

/* ---------- HU-Korrektur ---------- */
function hu_leg(array $matrix, array $dist, string $a, string $b): ?int {
  $na = norm_ort($a); $nb = norm_ort($b);
  $m = matrix_wert($matrix, $a, $b);
  if ($m !== null) return $m;
  if (!array_key_exists($na, $dist) || !array_key_exists($nb, $dist)) return null;
  return max(abs($dist[$na] - $dist[$nb]), 5);
}
function hu_kilometer(array $dist, array $matrix, string $home, string $werk, array $vor, array $nach, array &$msg): array {
  $dw = $dist[norm_ort($werk)] ?? 0;
  $hatMatrix = false;
  foreach (array_keys($matrix) as $k) if (in_array(norm_ort($werk), explode('|', $k), true)) { $hatMatrix = true; break; }
  if ($dw <= 0 && !$hatMatrix) {
    $msg[] = "HINWEIS: Weder Distanz noch Online-Matrix für „{$werk}“ vorhanden – generische Werte verwendet.";
    $kmD = rint(20, 40) + (count($vor) + count($nach)) * rint(10, 20); $kmP = rint(15, 30);
    return [max($kmD, 10), $kmP, $kmP, $kmP];
  }
  $kmD = 0; $kmP = 0; $prev = $home;
  foreach ($vor as $s) { $seg = hu_leg($matrix, $dist, $prev, $s); if ($seg === null) { $msg[] = "HINWEIS: Keine Distanz für „{$s}“ – Segment +10 km."; $seg = 10; } $kmD += $seg; $prev = $s; }
  $segW = hu_leg($matrix, $dist, $prev, $werk);
  if ($segW === null) { $msg[] = "HINWEIS: Keine Distanz für „{$werk}“ – Segment +10 km."; $segW = 10; }
  $kmP += $segW; $hin = $kmD + $segW;
  $nachweg = 0; $prev = $werk;
  foreach ($nach as $s) { $seg = hu_leg($matrix, $dist, $prev, $s); if ($seg === null) { $msg[] = "HINWEIS: Keine Distanz für „{$s}“ – Segment +10 km."; $seg = 10; } $kmD += $seg; $nachweg += $seg; $prev = $s; }
  if ($nach) { $r = hu_leg($matrix, $dist, $prev, $home) ?? max($dist[norm_ort($prev)] ?? 0, 5); $kmD += $r; $nachweg += $r; }
  else { $h = hu_leg($matrix, $dist, $werk, $home) ?? max($dw, 5); $kmP += $h; $nachweg += $h; }
  return [max($kmD, 10), $kmP, $hin, $nachweg];
}
// Skaliert km der angegebenen Fahrten; mit $ziel wird der Rundungsrest km-genau verteilt.
// Die Fahrzeit bleibt (Kundentermine dauern gleich lang) - nur wenn die km bei dieser
// Zeit unrealistisch schnell waeren, wird die Fahrzeit verlaengert.
function hu_skaliere(array &$jahr, array $refs, float $f, ?int $ziel): void {
  foreach ($refs as [$m, $i]) {
    $jahr[$m][$i]['km_d'] = (int) round(to_int($jahr[$m][$i]['km_d']) * $f);
    $jahr[$m][$i]['km_p'] = (int) round(to_int($jahr[$m][$i]['km_p']) * $f);
  }
  if ($ziel !== null) hu_rest_verteilen($jahr, $refs, $ziel);
  foreach ($refs as [$m, $i]) $jahr[$m][$i] = korrigiere_geschwindigkeit([$jahr[$m][$i]])[0];
}
function hu_rest_verteilen(array &$jahr, array $refs, int $ziel): void {
  $sum = 0; $kand = [];
  foreach ($refs as [$m, $i]) { $sum += $jahr[$m][$i]['km_d'] + $jahr[$m][$i]['km_p']; if ($jahr[$m][$i]['km_d'] > 0) $kand[] = [$m, $i]; }
  usort($kand, function ($a, $b) use ($jahr) { return $jahr[$b[0]][$b[1]]['km_d'] <=> $jahr[$a[0]][$a[1]]['km_d']; });
  $diff = $ziel - $sum; $guard = 0;
  while ($diff !== 0 && $kand && $guard++ < 100000) {
    foreach ($kand as [$m, $i]) {
      if ($diff === 0) break;
      if ($diff > 0) { $jahr[$m][$i]['km_d']++; $diff--; }
      elseif ($jahr[$m][$i]['km_d'] > 1) { $jahr[$m][$i]['km_d']--; $diff++; }
    }
  }
}
// Fehlende Kilometer bis zur HU als Privatfahrten ueber den Zeitraum verteilen.
// Dienstfahrten bleiben unveraendert (sonst haetten Monate 3000+ Dienst-km).
// Tage: zuerst Tage ohne Dienstfahrt dieses Fahrzeugs (bestehende Privat-/Leerzeilen
// bekommen km dazu, Tage ohne Eintrag eine neue Privatfahrt). Bei grossen Mengen
// einige Ausfluege (300-800 km) an Wochenenden/Feiertagen, mind. 21 Tage Abstand.
function hu_privat_dazu(array &$jahr, int $fid, string $name, ?string $von, string $bis, int $km, array &$msg): void {
  if ($km <= 0) return;
  $tage = [];
  foreach ($jahr as $m => $rows) foreach ($rows as $i => $r) {
    $d = (string) $r['datum'];
    if (($von !== null && $d <= $von) || $d >= $bis) continue;
    $tage[$d] = $tage[$d] ?? ['privat' => null, 'dienst' => false, 'fz' => false];
    if (to_int($r['fahrzeug_id'], null) !== $fid) continue;
    $tage[$d]['fz'] = true;
    if (to_int($r['km_d']) > 0 || strpos((string) $r['route'], '(HU)') !== false || strpos((string) $r['route'], 'Arbeitsweg') !== false) $tage[$d]['dienst'] = true;
    elseif ($tage[$d]['privat'] === null) $tage[$d]['privat'] = [$m, $i];
  }
  $kand = array_keys(array_filter($tage, function ($t) { return !$t['dienst']; }));
  $nurDienst = false;
  if (!$kand) { $kand = array_keys($tage); $nurDienst = true; }
  if (!$kand) { $msg[] = "WARNUNG: Keine Tage vor der HU vorhanden – $km km konnten nicht verteilt werden."; return; }
  sort($kand);
  $hol = [];
  foreach (array_unique(array_map(function ($d) { return (int) substr($d, 0, 4); }, $kand)) as $y) $hol += austria_holidays($y);
  $frei = function ($d) use ($hol) { return (int) date('N', strtotime($d)) >= 6 || isset($hol[$d]); };
  // Ausfluege
  $gross = [];
  $anzG = min(8, intdiv($km, 2500));
  $wkend = array_values(array_filter($kand, $frei)) ?: $kand;
  $versuche = 0;
  while (count($gross) < $anzG && $versuche++ < 500) {
    $d = $wkend[array_rand($wkend)];
    $ok = true;
    foreach (array_keys($gross) as $x) if (abs(strtotime($d) - strtotime($x)) < 21 * 86400) { $ok = false; break; }
    if ($ok && array_sum($gross) + 300 <= $km * 0.5) $gross[$d] = min(mt_rand(300, 800), (int) ($km * 0.5) - array_sum($gross));
  }
  $rest = $km - array_sum($gross);
  // Rest auf normale Tage: ca. 60 km pro Tag, zufaellig gewichtet, Summe exakt
  $normal = array_values(array_diff($kand, array_keys($gross)));
  shuffle($normal);
  $n = max(1, min(count($normal), (int) ceil($rest / 60)));
  $wahl = array_slice($normal, 0, $n);
  $w = []; foreach ($wahl as $d) $w[$d] = mt_rand(50, 150);
  $sw = array_sum($w) ?: 1; $zu = [];
  foreach ($w as $d => $x) $zu[$d] = (int) floor($rest * $x / $sw);
  $diff = $rest - array_sum($zu); $ks = array_keys($zu); $j = 0;
  while ($diff > 0 && $ks) { $zu[$ks[$j++ % count($ks)]]++; $diff--; }
  $alle = $zu;
  foreach ($gross as $d => $x) $alle[$d] = ($alle[$d] ?? 0) + $x;
  ksort($alle);
  $neu = 0; $erg = 0;
  foreach ($alle as $d => $x) {
    if ($x <= 0) continue;
    $g = isset($gross[$d]);
    $t = $tage[$d];
    if ($t['privat'] !== null) {
      [$m, $i] = $t['privat']; $r = &$jahr[$m][$i];
      $r['km_p'] = to_int($r['km_p']) + $x;
      [$r['abf'], $r['ank'], $r['dauer']] = privat_zeiten_frei($r['km_p'], $g);
      if (in_array(trim((string) $r['route']), ['Keine Fahrt', ''], true)) $r['route'] = $g ? 'Privatfahrt (Ausflug)' : 'Privatfahrt';
      unset($r); $erg++;
    } elseif ($nurDienst && $t['fz']) {
      foreach ($jahr as $m => $rows) foreach ($rows as $i => $r) if ($r['datum'] === $d && to_int($r['fahrzeug_id'], null) === $fid) { $jahr[$m][$i]['km_p'] = to_int($r['km_p']) + $x; $jahr[$m][$i] = korrigiere_geschwindigkeit([$jahr[$m][$i]])[0]; break 2; }
      $erg++;
    } else {
      [$a, $e, $du] = privat_zeiten_frei($x, $g);
      $jahr[(int) substr($d, 5, 2)][] = ['datum' => $d, 'fahrzeug_id' => $fid, 'fahrzeug' => $name, 'route' => $g ? 'Privatfahrt (Ausflug)' : 'Privatfahrt',
        'km_d' => 0, 'km_p' => $x, 'abf' => $a, 'ank' => $e, 'dauer' => $du, 'abfahrt_km' => 0];
      $neu++;
    }
  }
  $msg[] = 'Fehlende ' . number_format($km, 0, ',', '.') . ' km bis zur HU als Privatfahrten verteilt: '
    . count($gross) . ' Ausflüge (' . number_format(array_sum($gross), 0, ',', '.') . ' km), ' . ($neu + $erg - count($gross)) . ' weitere Tage. Dienstfahrten unverändert.';
}
// Zu viele Kilometer bis zur HU: zuerst Privat-km kuerzen, erst dann Dienstfahrten (Faktor >= 0,5)
function hu_kuerzen(array &$jahr, array $refs, int $km, array &$msg): void {
  $priv = []; $dienst = []; $sp = 0; $sd = 0;
  foreach ($refs as [$m, $i]) {
    if (to_int($jahr[$m][$i]['km_d']) > 0) { $dienst[] = [$m, $i]; $sd += to_int($jahr[$m][$i]['km_d']) + to_int($jahr[$m][$i]['km_p']); }
    elseif (to_int($jahr[$m][$i]['km_p']) > 0) { $priv[] = [$m, $i]; $sp += to_int($jahr[$m][$i]['km_p']); }
  }
  $vonPriv = min($km, (int) floor($sp * 0.8)); // Privatfahrten behalten mind. 20 %
  if ($vonPriv > 0) {
    $f = ($sp - $vonPriv) / $sp; $weg = 0;
    foreach ($priv as [$m, $i]) {
      $alt = to_int($jahr[$m][$i]['km_p']); $neuKm = max(1, (int) floor($alt * $f));
      $weg += $alt - $neuKm; $jahr[$m][$i]['km_p'] = $neuKm;
    }
    // Abrundung: zu viel gekuerzte km zurueckgeben (km-genau)
    for ($k = 0; $weg > $vonPriv && $priv; $k++) { [$m, $i] = $priv[$k % count($priv)]; $jahr[$m][$i]['km_p']++; $weg--; }
    foreach ($priv as [$m, $i]) [$jahr[$m][$i]['abf'], $jahr[$m][$i]['ank'], $jahr[$m][$i]['dauer']] = privat_zeiten_frei(to_int($jahr[$m][$i]['km_p']), false);
    $vonPriv = $weg;
  }
  $rest = $km - $vonPriv;
  $msg[] = 'HU-Stand liegt unter den eingetragenen Kilometern: ' . number_format($vonPriv, 0, ',', '.') . ' km bei Privatfahrten gekürzt'
    . ($rest > 0 ? ', ' . number_format($rest, 0, ',', '.') . ' km bei Dienstfahrten.' : '.');
  if ($rest <= 0 || $sd <= 0) return;
  $ziel = $sd - $rest;
  $f = $ziel / $sd;
  if ($f < HU_FAKTOR_MIN) { $msg[] = sprintf('ACHTUNG: HU-Stand passt stark nicht (Dienstfahrten müssten auf %.0f %% gekürzt werden) – auf 50 %% begrenzt. HU-Stand und Startwert prüfen!', $f * 100); hu_skaliere($jahr, $dienst, HU_FAKTOR_MIN, null); return; }
  hu_skaliere($jahr, $dienst, $f, $ziel);
}
/** $korrekturen: [[fahrzeug_id, datum, km_at_hu, werkstattort, stopps_vor(array), stopps_nach(array)]] */
// $neu = true: HU auch dann neu berechnen, wenn schon eine HU-Fahrt eingetragen ist (nach einer
// Korrektur der Fahrten). Das ist unbedenklich, weil der Faktor immer auf den echten HU-Stand
// zielt und nicht auf den alten Faktor aufbaut.
function wende_hu_an(array $jahr, array $anchor, array $namen, array $korrekturen, string $wohnort, array $distanzen, array $matrix, bool $neu = false): array {
  $msg = [];
  $home = ort_clean($wohnort);
  $home = preg_replace('/^[A-Za-z]?-?\d{4,5}\s+/', '', $home);
  $dist = [];
  foreach ($distanzen as $o => $km) {
    if ((int) $km > PLAUSI_LEG_KM) { verdacht("$o: $km km einfach vom Wohnort"); continue; }
    $dist[norm_ort($o)] = max(0, (int) $km);
  }
  if ($home !== '') $dist[norm_ort($home)] = 0;
  foreach ($jahr as $m => $rows) $jahr[$m] = sort_fahrten($rows);
  usort($korrekturen, function ($a, $b) { return strcmp((string) $a['datum'], (string) $b['datum']); });
  $letzteHu = [];

  foreach ($korrekturen as $c) {
    $fid = (int) $c['fahrzeug_id']; $hu = (string) $c['datum']; $kmHu = to_int($c['km_at_hu']);
    $werk = trim((string) $c['werkstattort']); $vor = $c['stopps_vor'] ?? []; $nach = $c['stopps_nach'] ?? [];
    $name = $namen[$fid] ?? "FZ $fid";
    $msg[] = "**HU {$name} am " . date('d.m.Y', strtotime($hu)) . ' (Tacho laut HU: ' . number_format($kmHu, 0, ',', '.') . ' km)**';
    // Zeitraum: seit der letzten HU dieses Fahrzeugs (in diesem Lauf) bzw. ab Jahresbeginn
    $prev = $letzteHu[$fid] ?? null;
    $refVor = []; $refTag = []; $sumVor = 0; $sumBisPrev = 0; $gefunden = false;
    foreach ($jahr as $m => $rows) foreach ($rows as $i => $r) {
      if (to_int($r['fahrzeug_id'], null) !== $fid) continue;
      $gefunden = true;
      $k = to_int($r['km_d']) + to_int($r['km_p']);
      if ($prev !== null && $r['datum'] <= $prev) $sumBisPrev += $k;
      elseif ($r['datum'] < $hu) { $refVor[] = [$m, $i]; $sumVor += $k; }
      elseif ($r['datum'] === $hu) $refTag[] = [$m, $i];
    }
    if (!$gefunden) { $msg[] = 'Keine Fahrten dieses Fahrzeugs gefunden – übersprungen.'; continue; }
    if (!$neu) foreach ($refTag as [$m, $i]) if (strpos((string) $jahr[$m][$i]['route'], '(HU)') !== false) {
      $msg[] = 'Bereits angewendet (HU-Fahrt am HU-Tag vorhanden) – übersprungen, Kilometer bleiben unverändert.';
      $letzteHu[$fid] = $hu;
      continue 2;
    }
    [$huD, $huP, $hin, $nachweg] = hu_kilometer($dist, $matrix, $home, $werk, $vor, $nach, $msg);
    $startBereich = (int) ($anchor[$fid] ?? 0) + $sumBisPrev;
    $zielVor = $kmHu - $hin - $startBereich;
    $diff = $zielVor - $sumVor;
    if ($zielVor < 0) $msg[] = 'ACHTUNG: HU-Stand liegt unter dem Tacho-Stand am Beginn des Zeitraums (' . number_format($startBereich, 0, ',', '.') . ' km) – Startwert und HU-Stand prüfen! Kilometer nicht verändert.';
    elseif ($diff > 0) hu_privat_dazu($jahr, $fid, $name, $prev, $hu, $diff, $msg);
    elseif ($diff < 0) hu_kuerzen($jahr, $refVor, -$diff, $msg);
    else $msg[] = 'Kilometer passen bereits genau zum HU-Stand.';
    $teile = array_merge([$home], $vor, ["$werk (HU)"], $nach, [$home]);
    $huRoute = implode(' - ', array_values(array_filter($teile, 'strlen')));
    $huDauer = 90 + (count($vor) + 1 + count($nach)) * 20;
    $hu_row = korrigiere_geschwindigkeit([['fahrzeug_id' => $fid, 'fahrzeug' => $name, 'route' => $huRoute, 'km_d' => $huD, 'km_p' => $huP,
      'abf' => '08:30', 'ank' => hhmm(8 * 60 + 30 + $huDauer), 'dauer' => hhmm($huDauer)]])[0];
    $monatHu = (int) substr($hu, 5, 2);
    if ($refTag) { [$m, $i] = $refTag[0]; $jahr[$m][$i] = array_merge($jahr[$m][$i], $hu_row); }
    else {
      // Fahrzeug hat am HU-Tag keinen Eintrag: eigene HU-Zeile anlegen. Nie die Fahrt eines anderen
      // Fahrzeugs umbauen - sonst verschiebt sich dessen Kilometerkette (und dessen HU stimmt nicht mehr).
      $jahr[$monatHu][] = array_merge(['datum' => $hu, 'abfahrt_km' => 0], $hu_row);
      $jahr[$monatHu] = sort_fahrten($jahr[$monatHu]);
    }
    $msg[] = "HU-Fahrt: $huD km dienstlich, $huP km privat (Weg zur Werkstatt).";
    $msg[] = 'Abfahrt am HU-Tag: ' . number_format($kmHu - $hin, 0, ',', '.') . " km (= HU-Stand minus $hin km Weg zur Werkstatt).";
    $msg[] = 'Fahrten nach der HU bleiben unverändert.';
    $letzteHu[$fid] = $hu;
  }
  foreach (verdacht() as $v) $msg[] = "WARNUNG: Unplausible Distanz ignoriert ($v) – im Tab „Fahrzeuge & Orte“ unter „Orte-Check“ prüfen.";
  [$jahr, $km] = baue_kette_neu($jahr, $anchor);
  return [$jahr, $km, $msg];
}

/* ---------- Privat-KM verteilen ---------- */
function privat_zeiten_frei(int $km, bool $gross): array {
  $d = max(min((int) ($km / 70 * 60) + mt_rand(5, 30), 840), 15);
  $s = min($gross ? 6 * 60 + mt_rand(0, 120) : 8 * 60 + mt_rand(0, 540), 20 * 60);
  return [hhmm($s), hhmm(min($s + $d, 23 * 60 + 59)), hhmm($d)];
}
function verteile_privat_km(array $jahr, int $fid, string $fname, int $total, array $o, array $anchor): array {
  if (!$jahr) throw new InvalidArgumentException('Keine Fahrten vorhanden – zuerst generieren.');
  if ($total <= 0) throw new InvalidArgumentException('Privat-KM Summe muss größer 0 sein.');
  $msg = [];
  $alle = []; $fzRow = []; $huTage = []; $arbeit = [];
  foreach ($jahr as $m => $rows) foreach ($rows as $i => $r) {
    $d = (string) $r['datum']; $alle[$d] = true;
    if (to_int($r['fahrzeug_id'], null) === $fid) {
      $fzRow[$d] = [$m, $i];
      if (strpos((string) $r['route'], '(HU)') !== false) $huTage[$d] = true;
      if (to_int($r['km_d']) > 0) $arbeit[$d] = true;
    }
  }
  if ($huTage) $msg[] = count($huTage) . ' HU-Tag(e) bleiben von der Verteilung ausgenommen.';
  foreach ($fzRow as $d => [$m, $i]) if (!isset($huTage[$d])) $jahr[$m][$i]['km_p'] = 0;
  $tage = array_keys($alle); sort($tage);
  $kandGross = array_values(array_filter($tage, function ($d) use ($huTage, $arbeit) { return !isset($huTage[$d]) && !isset($arbeit[$d]); }));
  if (count($kandGross) < 20) $kandGross = array_values(array_filter($tage, function ($d) use ($huTage) { return !isset($huTage[$d]); }));
  $gross = []; $versuche = 0;
  while (count($gross) < $o['anzahl_gross'] && $versuche++ < 800 && $kandGross) {
    $d = $kandGross[array_rand($kandGross)]; $ok = true;
    foreach (array_keys($gross) as $x) if (abs((strtotime($d) - strtotime($x)) / 86400) < 21) { $ok = false; break; }
    if ($ok) $gross[$d] = mt_rand($o['gross_min'], max($o['gross_min'], $o['gross_max']));
  }
  $sumG = array_sum($gross);
  if ($sumG > $total) {
    $msg[] = 'HINWEIS: Die Summe reicht nicht für alle großen Fahrten – Anzahl wurde reduziert.';
    while ($sumG > $total && $gross) { arsort($gross); $k = array_key_first($gross); $sumG -= $gross[$k]; unset($gross[$k]); }
  }
  $rest = $total - $sumG;
  $msg[] = count($gross) . ' große Privatfahrten (Urlaub/Ausflüge) mit zusammen ' . number_format($sumG, 0, ',', '.') . ' km.';
  $verteilt = $gross;
  if ($rest > 0) {
    $frei = array_values(array_filter($tage, function ($d) use ($huTage, $verteilt) { return !isset($huTage[$d]) && !isset($verteilt[$d]); }));
    shuffle($frei);
    $zielSchnitt = max(($o['normal_min'] + $o['normal_max']) / 2, 1);
    $n = max(1, min(count($frei), (int) round($rest / $zielSchnitt) + 1));
    $werte = [];
    foreach (array_slice($frei, 0, $n) as $d) $werte[$d] = mt_rand($o['normal_min'], max($o['normal_min'] + 1, $o['normal_max']));
    $s = array_sum($werte);
    if ($s === 0) { foreach ($werte as $d => $_) $werte[$d] = 1; $s = count($werte); }
    $zu = [];
    foreach ($werte as $d => $v) $zu[$d] = (int) round($v * $rest / $s);
    $diff = $rest - array_sum($zu); $keys = array_keys($zu); $g = 0;
    while ($diff !== 0 && $keys && $g++ < 100000) {
      $d = $keys[array_rand($keys)];
      if ($diff > 0) { $zu[$d]++; $diff--; } elseif ($zu[$d] > 0) { $zu[$d]--; $diff++; }
    }
    foreach ($zu as $d => $km) if ($km > 0) $verteilt[$d] = $km;
  }
  $msg[] = (count($verteilt) - count($gross)) . ' weitere Tage mit privaten Fahrten.';
  ksort($verteilt);
  foreach ($verteilt as $d => $km) {
    if ($km <= 0) continue;
    $isG = isset($gross[$d]);
    if (isset($fzRow[$d])) {
      [$m, $i] = $fzRow[$d]; $r = &$jahr[$m][$i];
      $r['km_p'] = $km;
      if (to_int($r['km_d']) === 0) {
        // Fahrzeit immer zur neuen km-Zahl passend (sonst z. B. "Sonntag 34 km in 15 Min")
        [$r['abf'], $r['ank'], $r['dauer']] = privat_zeiten_frei($km, $isG);
        if (strpos((string) $r['route'], 'Keine Fahrt') !== false || trim((string) $r['route']) === '') $r['route'] = $isG ? 'Privatfahrt (Urlaub)' : 'Privatfahrt';
      } else $r = korrigiere_geschwindigkeit([$r])[0];
      unset($r);
    } else {
      [$a, $e, $du] = privat_zeiten_frei($km, $isG);
      $jahr[(int) substr($d, 5, 2)][] = ['datum' => $d, 'fahrzeug_id' => $fid, 'fahrzeug' => $fname,
        'route' => $isG ? 'Privatfahrt (Urlaub)' : 'Privatfahrt', 'km_d' => 0, 'km_p' => $km, 'abf' => $a, 'ank' => $e, 'dauer' => $du, 'abfahrt_km' => 0];
    }
  }
  [$jahr, $km] = baue_kette_neu($jahr, $anchor);
  $summe = 0; $tg = 0;
  foreach ($jahr as $rows) foreach ($rows as $r) if ($r['fahrzeug_id'] === $fid && $r['km_p'] > 0) { $summe += $r['km_p']; $tg++; }
  $msg[] = "Jahres-Summe privat {$fname}: " . number_format($summe, 0, ',', '.') . " km auf $tg Tagen.";
  return [$jahr, $km, $msg];
}

/* ---------- Abgleich: passen die gespeicherten Kilometer zu den Orten der Route? ---------- */
// Orte einer Route: "Feiertag: A - B (Zweck) - C" -> [A, B, C]
function route_orte(string $route): array {
  $r = preg_replace('/^(Feiertag|Urlaub):\s*/u', '', trim($route));
  if (strpos($r, ' - ') === false) return [];
  $out = [];
  foreach (explode(' - ', $r) as $t) {
    $t = trim(preg_replace('/\s*\([^)]*\)\s*$/u', '', $t));
    if ($t !== '') $out[] = $t;
  }
  return $out;
}
function median(array $v): float { if (!$v) return 1.0; sort($v); $n = count($v); return $n % 2 ? $v[intdiv($n, 2)] : ($v[$n / 2 - 1] + $v[$n / 2]) / 2; }
/**
 * Prueft jede Dienstfahrt: Strecke laut Orte/Matrix (Rohwert) mal dem ueblichen Faktor des
 * Monats (Monatsziel + HU) ergibt den erwarteten Wert. Auffaellig ist, was weit darueber liegt,
 * ueber 360 km hat oder eine unplausible Strecke (> 120 km) enthaelt.
 * Rueckgabe: [auffaellige, unbekannte_orte, gepruefte_anzahl]
 */
function fahrten_abgleich(array $jahr, array $matrix, array $distanzen, string $home): array {
  $dist = [];
  foreach ($distanzen as $o => $km) if ((int) $km > 0 && (int) $km <= PLAUSI_LEG_KM) $dist[norm_ort($o)] = (int) $km;
  $dist[norm_ort($home)] = 0;
  $strecken = [];
  $leg = function (string $a, string $b, array &$probleme) use ($matrix, $dist, &$strecken): ?int {
    $na = norm_ort($a); $nb = norm_ort($b);
    if ($na === $nb) return MIN_LEG_KM;
    $m = $matrix[mkey($a, $b)] ?? null;
    if ($m !== null) {
      if ($m <= PLAUSI_LEG_KM) return (int) $m;
      [$x, $y] = strcmp($na, $nb) <= 0 ? [$a, $b] : [$b, $a];
      $strecken["$x – $y: $m km"] = true; // unplausible Strecke: Fahrt gilt als nicht pruefbar
      return null;
    }
    if (isset($dist[$na], $dist[$nb])) return max(abs($dist[$na] - $dist[$nb]), MIN_LEG_KM);
    return null;
  };
  $pruef = []; $unbekannt = []; $n = 0;
  foreach ($jahr as $m => $rows) foreach ($rows as $i => $r) {
    $hu = strpos((string) $r['route'], '(HU)') !== false;
    $ist = to_int($r['km_d']) + ($hu ? to_int($r['km_p']) : 0);
    if (to_int($r['km_d']) <= 0) continue;
    $orte = route_orte((string) $r['route']);
    $probleme = []; $roh = 0; $fehlt = [];
    for ($k = 1; $k < count($orte); $k++) {
      $l = $leg($orte[$k - 1], $orte[$k], $probleme);
      if ($l === null) { foreach ([$orte[$k - 1], $orte[$k]] as $o) if (!isset($dist[norm_ort($o)]) && !isset($matrix[mkey($orte[$k - 1], $orte[$k])])) $fehlt[$o] = true; $roh = null; break; }
      $roh += $l;
    }
    $n++;
    foreach (array_keys($fehlt) as $o) $unbekannt[$o] = true;
    $pruef[] = ['monat' => $m, 'i' => $i, 'hu' => $hu, 'ist' => $ist, 'roh' => count($orte) >= 2 ? $roh : null, 'probleme' => $probleme, 'fehlt' => array_keys($fehlt)];
  }
  // ueblicher Faktor pro Monat (nur normale Fahrten mit bekannter Strecke)
  $faktor = [];
  foreach ($pruef as $p) if (!$p['hu'] && $p['roh'] && !$p['probleme']) $faktor[$p['monat']][] = $p['ist'] / $p['roh'];
  $alleF = array_merge([], ...array_values($faktor ?: [[1.0]]));
  $fJahr = median($alleF);
  $auff = [];
  foreach ($pruef as $p) {
    $r = $jahr[$p['monat']][$p['i']];
    $f = isset($faktor[$p['monat']]) && count($faktor[$p['monat']]) >= 5 ? median($faktor[$p['monat']]) : $fJahr;
    $gruende = $p['probleme'];
    $erw = $p['roh'] ? (int) round($p['roh'] * ($p['hu'] ? 1 : $f)) : null;
    if ($p['ist'] > 2 * PLAUSI_LEG_KM * 1.5) $gruende[] = "{$p['ist']} km an einem Tag";
    elseif ($erw && $p['ist'] > max(2.2 * $erw, $erw + 60)) $gruende[] = "{$p['ist']} km statt ca. $erw km für diese Orte";
    if (!$gruende) continue;
    $auff[] = ['monat' => $p['monat'], 'i' => $p['i'], 'datum' => $r['datum'], 'fahrzeug' => $r['fahrzeug'], 'route' => $r['route'],
      'ist' => $p['ist'], 'erwartet' => $erw, 'hu' => $p['hu'], 'grund' => implode('; ', array_unique($gruende)), 'fehlt' => $p['fehlt']];
  }
  $u = array_keys($unbekannt); sort($u);
  return [$auff, $u, $n, array_keys($strecken)];
}
// Auffaellige Fahrten auf den erwarteten Wert setzen (Fahrten ohne berechenbare Strecke: auf den
// Monatsschnitt pro Stopp). Rueckgabe: [jahr, anzahl_korrigiert]
function fahrten_korrigieren(array $jahr, array $auff): array {
  $k = 0;
  foreach ($auff as $a) {
    if (!$a['erwartet']) continue;
    $r = &$jahr[$a['monat']][$a['i']];
    if ($a['hu']) {
      $f = $a['erwartet'] / max(1, $a['ist']);
      $r['km_d'] = max(1, (int) round(to_int($r['km_d']) * $f)); $r['km_p'] = (int) round(to_int($r['km_p']) * $f);
    } else $r['km_d'] = max(1, $a['erwartet']);
    $r = korrigiere_geschwindigkeit([$r])[0];
    unset($r);
    $k++;
  }
  return [$jahr, $k];
}

/* ---------- Keywords ---------- */
function keywords_aus_text(string $text): array {
  $out = [];
  foreach (preg_split('/\r?\n/', trim($text)) as $line) {
    $p = explode(':', $line);
    if (count($p) !== 2) continue;
    $ort = trim($p[0]);
    foreach (explode(',', $p[1]) as $z) if ($ort !== '') $out[] = ['Ort' => $ort, 'Zweck' => trim($z)];
  }
  return $out;
}
const DEFAULT_KEYWORDS = "Straßwalchen:Büro\nOberhofen am Irrsee:KB\nStraßwalchen:Schaden,Angebot\nMondsee:Antrag,KFZ\nNeumarkt:Angebot,KFZ\nHenndorf:Angebot,KB\nZell am Moos:KB,Schaden\nKöstendorf:Angebot,KB\nFrankenmarkt:Angebot,KFZ\nEugendorf:KFZ,Angebot\nMattighofen:KFZ,Angebot\nObertrum:KFZ\nSeekirchen:Angebot,KB\nLochen:KB,Angebot\nFriedburg:Angebot,KB\nVöcklamarkt:KFZ,Angebot\nSt. Georgen:Angebot,Schaden\nSt. Gilgen:Angebot\nUnterach:KB\nOberwang:Angebot\nKirchberg:Antrag,KB\nFornach:Angebot\nSalzburg:Schaden,Angebot\nMunderfing:KB\nSeeham:KB\nHof bei Salzburg:KFZ\nLamprechtshausen:Schaden\nOberndorf:Angebot,KB\nHallwang:Angebot,KB\nSchachen:Antrag\nVöcklabruck:Angebot";
