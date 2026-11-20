<?php
// Fahrtenbuch – Fachlogik (1:1 aus der Python-Version portiert: generator.py, hu_korrektur.py v5,
// privat_km.py, validation.py, taggeld.py, kalender.py, fahrten.py).
// Datenform einer Fahrt: ['datum'=>'YYYY-MM-DD','fahrzeug_id'=>int|null,'fahrzeug'=>str,'route'=>str,
//   'km_d'=>int,'km_p'=>int,'abf'=>'HH:MM','ank'=>'HH:MM','dauer'=>'HH:MM','abfahrt_km'=>int]
// Ein Jahr = [monat => [fahrt, ...]].
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

const MONATE = ['Jänner', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
const WOCHENTAGE_KURZ = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
const IGNORE_ROUTES = ['Keine Fahrt', 'Sonntag', 'Feiertag', 'Urlaub'];
const MIN_LEG_KM = 8;       // Mindest-km pro Teilstrecke im Fallback-Pfad
const SCALE_MIN = 0.80;     // Monats-Skalierung gedämpft
const SCALE_MAX = 1.35;
const HU_FAKTOR_MIN = 0.5;
const HU_FAKTOR_MAX = 2.0;

/* ===================== Hilfsfunktionen ===================== */

// wie Python _safe_int: "1.234" -> 1234, "" -> default
function safe_int($v, ?int $default = 0): ?int {
  if ($v === null) return $default;
  if (is_int($v)) return $v;
  if (is_float($v)) return is_nan($v) ? $default : (int) $v;
  if (is_bool($v)) return (int) $v;
  $s = strtolower(str_replace(['.', ','], '', trim((string) $v)));
  if ($s === '' || in_array($s, ['none', 'nan', 'nat', 'null'], true)) return $default;
  return preg_match('/^-?\d+$/', $s) ? (int) $s : $default;
}
function safe_float($v, float $default = 0.0): float {
  if ($v === null) return $default;
  if (is_int($v) || is_float($v)) return is_nan((float) $v) ? $default : (float) $v;
  $s = str_replace(',', '.', trim((string) $v));
  return is_numeric($s) ? (float) $s : $default;
}
function norm_ort($n): string { return mb_strtolower(trim((string) $n), 'UTF-8'); }
function ort_clean(string $s): string { return strpos($s, ',') !== false ? trim(substr($s, strrpos($s, ',') + 1)) : $s; }
function hhmm(int $mins): string { $mins = max(0, $mins); return sprintf('%02d:%02d', intdiv($mins, 60), $mins % 60); }
function dauer_min($d): int {
  $p = explode(':', (string) $d);
  if (count($p) < 2 || !is_numeric($p[0]) || !is_numeric($p[1])) return 0;
  return (int) $p[0] * 60 + (int) $p[1];
}
function dauer_string(string $abf, string $ank): string {
  $a = explode(':', $abf); $b = explode(':', $ank);
  if (count($a) < 2 || count($b) < 2) return '00:00';
  $m = ((int) $b[0] * 60 + (int) $b[1]) - ((int) $a[0] * 60 + (int) $a[1]);
  if ($m < 0) $m += 24 * 60;
  return hhmm($m);
}
function parse_date_iso($v): ?string {
  if ($v === null) return null;
  $s = trim((string) $v);
  if ($s === '' || in_array(strtolower($s), ['nat', 'nan', 'none', 'null'], true)) return null;
  if (preg_match('/^(\d{4})-(\d{2})-(\d{2})/', $s, $m)) return checkdate((int) $m[2], (int) $m[3], (int) $m[1]) ? "$m[1]-$m[2]-$m[3]" : null;
  if (preg_match('/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/', $s, $m)) return checkdate((int) $m[2], (int) $m[1], (int) $m[3]) ? sprintf('%04d-%02d-%02d', $m[3], $m[2], $m[1]) : null;
  if (preg_match('/^(\d{1,2})\.(\d{1,2})\.(\d{2})$/', $s, $m)) return checkdate((int) $m[2], (int) $m[1], 2000 + (int) $m[3]) ? sprintf('%04d-%02d-%02d', 2000 + (int) $m[3], $m[2], $m[1]) : null;
  return null;
}
function fmt_int(int $n): string { return number_format($n, 0, ',', '.'); }

/* ---------- Zufall (numpy-Semantik: rint(a,b) liefert a..b-1) ---------- */
function rint(int $a, int $b): int { return $b - 1 <= $a ? $a : random_int($a, $b - 1); }
function rincl(int $a, int $b): int { return $b <= $a ? $a : random_int($a, $b); } // Python random.randint (inkl.)
function rnd(): float { return random_int(0, PHP_INT_MAX - 1) / PHP_INT_MAX; }
function runiform(float $a, float $b): float { return $a + ($b - $a) * rnd(); }
function rsample(array $a, int $n): array { shuffle($a); return array_slice($a, 0, max(0, min($n, count($a)))); }
function rchoice(array $a) { return $a[random_int(0, count($a) - 1)]; }
function rchoice_w(array $a, array $w) {
  $sum = array_sum($w); $x = rnd() * $sum; $acc = 0.0;
  foreach ($a as $i => $v) { $acc += $w[$i]; if ($x < $acc) return $v; }
  return end($a);
}
function clip(float $v, float $lo, float $hi): float { return max($lo, min($hi, $v)); }

/* ===================== Kalender (AT) ===================== */
function easter_sunday(int $y): string {
  $a = $y % 19; $b = intdiv($y, 100); $c = $y % 100; $d = intdiv($b, 4); $e = $b % 4;
  $f = intdiv($b + 8, 25); $g = intdiv($b - $f + 1, 3); $h = (19 * $a + $b - $d - $g + 15) % 30;
  $i = intdiv($c, 4); $k = $c % 4; $l = (32 + 2 * $e + 2 * $i - $h - $k) % 7;
  $m = intdiv($a + 11 * $h + 22 * $l, 451);
  $month = intdiv($h + $l - 7 * $m + 114, 31); $day = (($h + $l - 7 * $m + 114) % 31) + 1;
  return sprintf('%04d-%02d-%02d', $y, $month, $day);
}
function add_days(string $d, int $n): string { return (new DateTimeImmutable($d))->modify(($n >= 0 ? '+' : '') . $n . ' days')->format('Y-m-d'); }
function austria_holidays(int $y): array {
  static $cache = [];
  if (isset($cache[$y])) return $cache[$y];
  $E = easter_sunday($y);
  $list = ["$y-01-01", "$y-01-06", "$y-05-01", "$y-08-15", "$y-10-26", "$y-11-01", "$y-12-08", "$y-12-25", "$y-12-26",
    add_days($E, 1), add_days($E, 39), add_days($E, 50), add_days($E, 60)];
  return $cache[$y] = array_fill_keys($list, true);
}
function weekday(string $d): int { return (int) (new DateTimeImmutable($d))->format('N') - 1; } // 0 = Montag
function iso_week(string $d): int { return (int) (new DateTimeImmutable($d))->format('W'); }
function month_days(int $y, int $m): array {
  $n = cal_days_in_month_safe($y, $m); $out = [];
  for ($i = 1; $i <= $n; $i++) $out[] = sprintf('%04d-%02d-%02d', $y, $m, $i);
  return $out;
}
function cal_days_in_month_safe(int $y, int $m): int { return (int) (new DateTimeImmutable(sprintf('%04d-%02d-01', $y, $m)))->format('t'); }

/* ===================== Taggeld ===================== */
function taggeld_params(array $s): array {
  return ['min_stunden' => safe_float($s['taggeld_min_stunden'] ?? null, 5), 'basis' => safe_float($s['taggeld_basis'] ?? null, 10.0),
    'stufung' => safe_float($s['taggeld_stufung'] ?? null, 2.5), 'max_betrag' => safe_float($s['taggeld_max_betrag'] ?? null, 30.0),
    'max_stunden' => safe_float($s['taggeld_max_stunden'] ?? null, 13)];
}
// Taggeld nur bei dienstlicher Auswärtstätigkeit (km_d > 0)
function taggeld_betrag(int $dauerMin, array $p, ?int $kmD = null): float {
  if ($kmD !== null && $kmD <= 0) return 0.0;
  $h = $dauerMin / 60.0;
  if ($h < $p['min_stunden']) return 0.0;
  if ($h >= $p['max_stunden']) return round($p['max_betrag'], 2);
  return round(min($p['basis'] + ($h - $p['min_stunden']) * $p['stufung'], $p['max_betrag']), 2);
}

/* ===================== Kilometerkette ===================== */
function sort_rows(array &$rows): void {
  // stabil nach Datum sortieren
  $i = 0; foreach ($rows as &$r) { $r['_i'] = $i++; } unset($r);
  usort($rows, function ($a, $b) { return [$a['datum'], $a['_i']] <=> [$b['datum'], $b['_i']]; });
  foreach ($rows as &$r) unset($r['_i']); unset($r);
}
// Baut abfahrt_km für ein ganzes Jahr neu auf – Start IMMER am Jahres-Anker. Liefert Endstände je Fahrzeug.
function kette_neu(array &$year, array $anchor): array {
  $km = $anchor;
  ksort($year);
  foreach ($year as $m => &$rows) {
    sort_rows($rows);
    foreach ($rows as &$r) {
      $fz = $r['fahrzeug_id'];
      if ($fz !== null && $fz !== '') {
        $fz = (int) $fz;
        $r['abfahrt_km'] = $km[$fz] ?? 0;
        $km[$fz] = ($km[$fz] ?? 0) + (int) $r['km_d'] + (int) $r['km_p'];
      } else {
        $r['abfahrt_km'] = 0;
      }
    }
    unset($r);
  }
  unset($rows);
  return $km;
}

/* ===================== Generator ===================== */
function matrix_km(array $matrix, $a, $b): ?int {
  $a = norm_ort($a); $b = norm_ort($b);
  if ($a === '' || $b === '' || $a === $b) return null;
  $k = strcmp($a, $b) <= 0 ? "$a|$b" : "$b|$a";
  $v = $matrix[$k] ?? null;
  return ($v !== null && (int) $v > 0) ? (int) $v : null;
}
function leg_km(array $dist, array $matrix, $a, $b): int {
  $km = matrix_km($matrix, $a, $b);
  if ($km !== null) return $km;
  $da = $dist[norm_ort($a)] ?? null; $db = $dist[norm_ort($b)] ?? null;
  if ($da === null || $db === null) return rint(15, 35);
  return max(abs((int) $da - (int) $db), MIN_LEG_KM);
}
function tour_km(array $dist, array $matrix, string $home, array $stops): int {
  $t = 0; $prev = $home;
  foreach ($stops as $o) { $t += leg_km($dist, $matrix, $prev, $o); $prev = $o; }
  return $t + leg_km($dist, $matrix, $prev, $home);
}
// Abfahrt 08:00 (+0–10 Min), Ankunft Ganztag 17:00–22:00 bzw. Halbtag 13:00–17:00
function tour_zeiten(bool $ganztags): array {
  $abf = 8 * 60 + rint(0, 11);
  $ank = $ganztags ? rint(17 * 60, 22 * 60 + 1) : rint(13 * 60, 17 * 60 + 1);
  return [hhmm($abf), hhmm($ank), hhmm($ank - $abf)];
}
function urlaubs_tage(int $wochen, string $verteilung, ?string $start): array {
  $v = [];
  if ($wochen <= 0 || !$start) return $v;
  if ($verteilung === '1x4 Wochen') { for ($j = 0; $j < 28; $j++) $v[add_days($start, $j)] = true; }
  elseif ($verteilung === '2x2 Wochen') { for ($i = 0; $i < 2; $i++) for ($j = 0; $j < 14; $j++) $v[add_days($start, $i * 26 * 7 + $j)] = true; }
  elseif ($verteilung === '4x1 Woche') { for ($i = 0; $i < 4; $i++) for ($j = 0; $j < 7; $j++) $v[add_days($start, $i * 13 * 7 + $j)] = true; }
  return $v;
}

/**
 * Generiert Fahrten für die angegebenen Monate.
 * $fahrzeuge: [['id','bezeichnung','start_km_vorjahr','privat_km_min','privat_km_max','dienstlich_quote'], ...]
 * $keywords:  [['ort'=>..,'zweck'=>..], ...]
 * $p: prob_werktag, prob_feiertag_urlaub, vacation_days (set), urlaub_fahrzeug_name, urlaub_km_min/max,
 *     target_km_min/max, hauptfahrzeug_name, hauptfahrzeug_anteil, distanzen {ort=>km}, matrix {"a|b"=>km}
 * Rückgabe: [ [monat => rows], fehlende_orte[] ]  (abfahrt_km wird danach mit kette_neu() gesetzt)
 */
function generiere_monate(int $jahr, array $monate, array $user, array $fahrzeuge, array $zeitraeume, array $keywords, array $p): array {
  $hol = austria_holidays($jahr);
  $wohnort = (string) (($user['wohnort'] ?? '') !== '' ? $user['wohnort'] : 'Oberhofen am Irrsee');
  $dienstort = (string) (($user['dienstort'] ?? '') !== '' ? $user['dienstort'] : 'Straßwalchen');
  $home = ort_clean($wohnort); $dienst = ort_clean($dienstort);
  $entf = safe_int($user['entfernung'] ?? null, 25);

  $matrix = $p['matrix'] ?? [];
  $matrixOrte = [];
  foreach (array_keys($matrix) as $k) { [$a, $b] = explode('|', $k, 2); $matrixOrte[$a] = true; $matrixOrte[$b] = true; }
  $dist = [];
  foreach (($p['distanzen'] ?? []) as $o => $km) $dist[norm_ort($o)] = max(0, (int) $km);
  $dist[norm_ort($home)] = 0;
  if (!isset($dist[norm_ort($dienst)])) $dist[norm_ort($dienst)] = max(0, $entf);
  $fehlende = [];

  $opt = []; $names = [];
  foreach ($fahrzeuge as $f) {
    if (!isset($f['id'])) continue;
    $b = trim((string) ($f['bezeichnung'] ?? ''));
    if ($b !== '' && !in_array(strtolower($b), ['none', 'nan'], true)) { $opt[$b] = (int) $f['id']; $names[(int) $f['id']] = $b; }
  }
  if (!$opt) throw new InvalidArgumentException('Keine Fahrzeuge mit gültiger ID! Bitte zuerst Fahrzeuge speichern und dann generieren.');
  $privat = []; $quote = [];
  foreach ($fahrzeuge as $f) {
    $id = (int) $f['id'];
    $lo = safe_int($f['privat_km_min'] ?? null, 5); $hi = safe_int($f['privat_km_max'] ?? null, 20);
    $privat[$id] = [$lo, $hi];
    $quote[$id] = max(0, min(100, safe_int($f['dienstlich_quote'] ?? null, 90)));
  }
  $privatKm = function ($fz) use ($privat) { return ($fz !== null && isset($privat[$fz])) ? rint($privat[$fz][0], $privat[$fz][1]) : rint(5, 21); };

  $liste = [];
  foreach ($zeitraeume as $z) {
    $v = parse_date_iso($z['von'] ?? null); $b = parse_date_iso($z['bis'] ?? null); $fid = safe_int($z['fahrzeug_id'] ?? null, null);
    if ($v && $b && $fid !== null) $liste[] = [$v, $b, $fid];
  }
  $deckt = false;
  foreach ($liste as [$v, $b]) if ((int) substr($v, 0, 4) <= $jahr && $jahr <= (int) substr($b, 0, 4)) $deckt = true;
  if (!$deckt) throw new InvalidArgumentException("Kein Zeitraum deckt das Jahr $jahr ab! Bitte Zeiträume (von/bis) aktualisieren.");

  $vac = $p['vacation_days'] ?? [];
  $wdCount = []; $avg = 0;
  foreach ($monate as $mk) {
    $wd = 0;
    foreach (month_days($jahr, $mk) as $t) if (weekday($t) < 5 && !isset($hol[$t]) && !isset($vac[$t])) $wd++;
    $wdCount[$mk] = $wd; $avg += $wd;
  }
  $avg = $monate ? $avg / count($monate) : 21;

  $urlaubFz = $opt[$p['urlaub_fahrzeug_name'] ?? ''] ?? null;
  $hauptId = $opt[$p['hauptfahrzeug_name'] ?? ''] ?? null;
  $hauptAnteil = ((float) ($p['hauptfahrzeug_anteil'] ?? 70)) / 100.0;
  $probFU = ((float) ($p['prob_feiertag_urlaub'] ?? 5)) / 100.0;
  $probW = (int) ($p['prob_werktag'] ?? 75);
  $kw = $keywords ?: [['ort' => 'Büro', 'zweck' => 'Büro']];

  $stopsFor = function (int $n) use ($kw, &$fehlende, $dist, $matrixOrte) {
    $orte = []; $txt = [];
    foreach (rsample($kw, $n) as $r) {
      $o = trim((string) $r['ort']);
      $orte[] = $o; $txt[] = $o . ' (' . $r['zweck'] . ')';
      if (!isset($dist[norm_ort($o)]) && !isset($matrixOrte[norm_ort($o)])) $fehlende[$o] = true;
    }
    return [$orte, $txt];
  };
  $kurzfahrt = function (int $km_p) {
    $start = rint(9, 18) * 60;
    $fz = max(intdiv($km_p * 60, 70) + rint(5, 15), 15);
    return [hhmm($start), hhmm($start + $fz), hhmm($fz)];
  };

  $out = [];
  foreach ($monate as $mk) {
    $rows = [];
    $special = false;
    foreach (month_days($jahr, $mk) as $t) {
      $route = 'Keine Fahrt'; $kd = 0; $kp = 0; $abf = $ank = $dauer = '00:00';
      $fz = null; $fzName = 'Kein Fahrzeug';
      $gueltig = [];
      foreach ($liste as [$v, $b, $fid]) if ($v <= $t && $t <= $b) $gueltig[] = $fid;
      if ($gueltig) {
        if ($hauptId !== null && in_array($hauptId, $gueltig, true) && count($gueltig) > 1) {
          $rest = (1.0 - $hauptAnteil) / (count($gueltig) - 1);
          $w = array_map(function ($f) use ($hauptId, $hauptAnteil, $rest) { return $f === $hauptId ? $hauptAnteil : $rest; }, $gueltig);
          $fz = (int) rchoice_w($gueltig, $w);
        } else {
          $fz = (int) rchoice($gueltig);
        }
        $fzName = $names[$fz] ?? 'Unbekannt';
      }
      $wd = weekday($t);
      if ($wd === 0) $special = false;
      $isHol = isset($hol[$t]); $isVac = isset($vac[$t]);

      if ($isHol || $isVac) {
        if (rnd() < $probFU) {
          [$so, $st] = $stopsFor(rint(1, 3));
          $kd = tour_km($dist, $matrix, $home, $so);
          $route = ($isHol ? 'Feiertag: ' : 'Urlaub: ') . implode(' - ', array_merge([$home], $st, [$home]));
          [$abf, $ank, $dauer] = tour_zeiten(false);
        } else {
          if ($isVac) {
            if ($urlaubFz !== null && in_array($urlaubFz, $gueltig, true)) {
              $fz = $urlaubFz; $fzName = $names[$fz] ?? 'Unbekannt';
              $kp = rint((int) ($p['urlaub_km_min'] ?? 30), (int) ($p['urlaub_km_max'] ?? 80) + 1);
              $route = 'Urlaub';
            } else {
              $kp = rint(5, 21);
              $route = 'Urlaub (Urlaubs-FZ nicht verfügbar)';
            }
          } else {
            $kp = $privatKm($fz);
            $route = 'Feiertag';
          }
          $kd = 0;
          [$abf, $ank, $dauer] = $kurzfahrt($kp);
        }
      } elseif ($wd === 5) {
        if (rnd() < 0.4) {
          [$so, $st] = $stopsFor(1);
          $kd = tour_km($dist, $matrix, $home, $so);
          $route = implode(' - ', array_merge([$home], $st, [$home]));
          [$abf, $ank, $dauer] = tour_zeiten(false);
        }
      } elseif ($wd === 6) {
        $kp = $privatKm($fz); $kd = 0; $route = 'Sonntag';
        [$abf, $ank, $dauer] = $kurzfahrt($kp);
      } else {
        $q = ($fz !== null ? ($quote[$fz] ?? 90) : 90) / 100.0;
        if (!(rnd() < $q)) {
          $kd = 0; $kp = $privatKm($fz);
          $route = rnd() < 0.4 ? "$home - $dienst (Arbeitsweg)" : 'Privatfahrt';
          $a = 8 * 60 + rint(0, 11); $e = rint(16 * 60, 19 * 60 + 1);
          [$abf, $ank, $dauer] = [hhmm($a), hhmm($e), hhmm($e - $a)];
        } else {
          $target = iso_week($t) % 2 === 1 ? 0 : 1;
          if ($wd === $target && !$special) {
            // 2-wöchentliche Sonderfahrt: Wohnort - Dienstort (Büro) - Stopps - Wohnort
            $special = true;
            $kp = matrix_km($matrix, $home, $dienst) ?? max(1, $entf);
            [$so, $st] = $stopsFor(rint(1, 4));
            $route = implode(' - ', array_merge([$home, "$dienst (Büro)"], $st, [$home]));
            $kd = tour_km($dist, $matrix, $home, array_merge([$dienst], $so));
            [$abf, $ank, $dauer] = tour_zeiten(true);
          } else {
            if ($probW >= 90) $n = rint(1, 3); elseif ($probW >= 70) $n = rint(1, 4); elseif ($probW >= 50) $n = rint(2, 4); else $n = rint(2, 5);
            [$so, $st] = $stopsFor($n);
            $route = implode(' - ', array_merge([$home], $st, [$home]));
            $kd = tour_km($dist, $matrix, $home, $so); $kp = 0;
            [$abf, $ank, $dauer] = tour_zeiten(true);
          }
        }
      }
      $rows[] = ['datum' => $t, 'fahrzeug_id' => $fz, 'fahrzeug' => $fzName, 'route' => $route, 'km_d' => (int) $kd, 'km_p' => (int) $kp,
        'abf' => $abf, 'ank' => $ank, 'dauer' => $dauer, 'abfahrt_km' => 0];
    }

    // KM-Skalierung auf das Monatsziel – gedämpft (0,80–1,35), damit echte Distanzen erhalten bleiben
    $tmin = (int) ($p['target_km_min'] ?? 1650); $tmax = (int) ($p['target_km_max'] ?? 2000);
    $cur = array_sum(array_column($rows, 'km_d'));
    if ($tmax > 0 && $cur > 0 && !($tmin <= $cur && $cur <= $tmax)) {
      $base = runiform($tmin, $tmax);
      $wf = clip($avg > 0 ? ($wdCount[$mk] ?? 21) / $avg : 1.0, 0.70, 1.20);
      $zf = runiform(0.88, 1.12);
      $mt = clip($base * $wf * $zf, $tmin * 0.55, $tmax * 1.25);
      $sf = clip($mt / $cur, SCALE_MIN, SCALE_MAX);
      foreach ($rows as &$r) if ($r['km_d'] > 0) $r['km_d'] = (int) ($r['km_d'] * $sf);
      unset($r);
    }
    $out[$mk] = $rows;
  }
  $f = array_keys($fehlende); sort($f);
  return [$out, $f];
}

/* ===================== Plausibilitätsprüfung ===================== */
function ist_ignore_route($route): bool {
  $s = (string) $route;
  foreach (IGNORE_ROUTES as $i) if ($s === $i || strpos($s, $i . ':') === 0 || strpos($s, $i . ' ') === 0) return true;
  return false;
}
function fmt_datum(string $iso): string { return substr($iso, 8, 2) . '.' . substr($iso, 5, 2) . '.' . substr($iso, 0, 4); }
function scan_red_flags(array $rows): array {
  $flags = [];
  foreach ($rows as $r) {
    $d = fmt_datum((string) $r['datum']);
    $total = (int) $r['km_d'] + (int) $r['km_p'];
    if ($total > 0) {
      $dm = dauer_min($r['dauer']);
      if ($dm > 0) { $speed = $total / $dm * 60; if ($speed > 130) $flags[] = "$d: Unrealistische Geschwindigkeit! $total km in {$r['dauer']} (~" . round($speed) . ' km/h).'; }
    }
    if ($total === 0 && !ist_ignore_route($r['route'])) $flags[] = "$d: Fahrt „" . mb_substr((string) $r['route'], 0, 30) . "…“ eingetragen, aber 0 km.";
    $a = dauer_min($r['abf']); $b = dauer_min($r['ank']);
    if ($b < $a && $total > 0) $flags[] = "$d: Ankunft ({$r['ank']}) liegt vor der Abfahrt ({$r['abf']}).";
  }
  $byDay = [];
  foreach ($rows as $r) $byDay[$r['datum']][] = (string) $r['abf'];
  foreach ($byDay as $d => $abfs) if (count($abfs) > 1 && count(array_unique($abfs)) < count($abfs)) $flags[] = fmt_datum((string) $d) . ": Mehrere Fahrten mit exakt gleicher Abfahrtszeit ({$abfs[0]}).";
  return $flags;
}
function pruefe_jahr(array $year): array {
  $res = [];
  foreach ($year as $m => $rows) { $f = scan_red_flags($rows); if ($f) $res[$m] = $f; }
  ksort($res);
  return $res;
}
// Legitime Korrektur: Kilometer bleiben, nur die Fahrzeit wird verlängert
function korrigiere_geschwindigkeiten(array &$rows, int $max = 100): int {
  $n = 0;
  foreach ($rows as &$r) {
    $total = (int) $r['km_d'] + (int) $r['km_p'];
    $dm = dauer_min($r['dauer']);
    if ($total <= 0 || $dm <= 0) continue;
    if ($total / $dm * 60 > $max) {
      $neu = min(intdiv($total * 60, $max) + 20, 840);
      $r['ank'] = hhmm(min(dauer_min($r['abf']) + $neu, 23 * 60 + 59));
      $r['dauer'] = hhmm($neu);
      $n++;
    }
  }
  unset($r);
  return $n;
}

/* ===================== HU-Korrektur v5 ===================== */
function hu_leg(array $matrix, array $dist, $a, $b): ?int {
  $km = matrix_km($matrix, $a, $b);
  if ($km !== null) return $km;
  $da = $dist[norm_ort($a)] ?? null; $db = $dist[norm_ort($b)] ?? null;
  if ($da === null || $db === null) return null;
  return max(abs((int) $da - (int) $db), 5);
}
function hu_kilometer(array $dist, array $matrix, string $home, string $werk, array $vor, array $nach, array &$msg): array {
  $dw = (int) ($dist[norm_ort($werk)] ?? 0);
  $wk = norm_ort($werk); $hatMatrix = false;
  foreach (array_keys($matrix) as $k) { [$a, $b] = explode('|', $k, 2); if ($a === $wk || $b === $wk) { $hatMatrix = true; break; } }
  if ($dw <= 0 && !$hatMatrix) {
    $msg[] = "- HINWEIS: Weder Distanz noch Online-Matrix für „{$werk}“ vorhanden (Tab „Fahrzeuge & Orte“ → Distanzen online berechnen). Es werden generische Werte verwendet!";
    $kd = rint(20, 40) + (count($vor) + count($nach)) * rint(10, 20);
    $kp = rint(15, 30);
    return [max($kd, 10), $kp, $kp, $kp];
  }
  $kd = 0; $kp = 0; $prev = $home;
  foreach ($vor as $s) { $seg = hu_leg($matrix, $dist, $prev, $s); if ($seg === null) { $msg[] = "- HINWEIS: Keine Distanz für „{$s}“ – Segment +10 km."; $seg = 10; } $kd += $seg; $prev = $s; }
  $segW = hu_leg($matrix, $dist, $prev, $werk);
  if ($segW === null) { $msg[] = "- HINWEIS: Keine Distanz für „{$werk}“ – Segment +10 km."; $segW = 10; }
  $kp += $segW;
  $hin = $kd + $segW;
  $nachweg = 0; $prev = $werk;
  foreach ($nach as $s) { $seg = hu_leg($matrix, $dist, $prev, $s); if ($seg === null) { $msg[] = "- HINWEIS: Keine Distanz für „{$s}“ – Segment +10 km."; $seg = 10; } $kd += $seg; $nachweg += $seg; $prev = $s; }
  if ($nach) {
    $r = hu_leg($matrix, $dist, $prev, $home);
    if ($r === null) $r = max((int) ($dist[norm_ort($prev)] ?? 0), 5);
    $kd += $r; $nachweg += $r;
  } else {
    $h = hu_leg($matrix, $dist, $werk, $home);
    if ($h === null) $h = max($dw, 5);
    $kp += $h; $nachweg += $h;
  }
  return [max($kd, 10), $kp, $hin, $nachweg];
}
function scale_dauer(string $d, float $f): string {
  $t = dauer_min($d);
  if ($t <= 0) return $d;
  return hhmm(min(max((int) ($t * $f), 10), 840));
}

// Skaliert alle Fahrten eines Fahrzeugs vor ($vor=true) bzw. nach dem HU-Tag. $ziel = gewünschte km-Summe (oder null)
function hu_skaliere(array &$year, int $fz, string $hu, bool $vor, float $f, ?int $ziel): void {
  if ($f == 1.0 && $ziel === null) return;
  $teile = []; $summe = 0;
  foreach ($year as $m => &$rows) {
    foreach ($rows as $i => &$r) {
      if ($r['fahrzeug_id'] === null || (int) $r['fahrzeug_id'] !== $fz || $r['datum'] === $hu || ($vor ? $r['datum'] > $hu : $r['datum'] < $hu)) continue;
      foreach (['km_d', 'km_p'] as $k) {
        $exakt = $r[$k] * $f; $neu = (int) floor($exakt);
        if ($r[$k] > 0) $teile[] = [$m, $i, $k, $exakt - $neu];
        $r[$k] = $neu; $summe += $neu;
      }
      $r['dauer'] = scale_dauer((string) $r['dauer'], $f);
      $r['ank'] = hhmm(min(dauer_min($r['abf']) + dauer_min($r['dauer']), 23 * 60 + 59));
    }
    unset($r);
  }
  unset($rows);
  if ($ziel === null || !$teile) return;
  $rest = $ziel - $summe;
  usort($teile, function ($a, $b) { return $b[3] <=> $a[3]; });
  for ($j = 0; $rest > 0 && $j < 100000; $j++, $rest--) { [$m, $i, $k] = $teile[$j % count($teile)]; $year[$m][$i][$k]++; }
}

/**
 * Wendet HU-Einträge auf EIN Jahr an. $corr: [['fahrzeug_id','datum','km_at_hu','werkstattort','stopps_vor'=>[],'stopps_nach'=>[]]]
 * $anchor: Jahres-Startkilometer je Fahrzeug. Rückgabe: [$year, $endKm, $meldungen]
 */
function wende_hu_an(array $year, array $anchor, array $names, array $corr, string $wohnortRaw, array $distanzen, array $matrix): array {
  $msg = [];
  $home = (string) $wohnortRaw;
  if (strpos($home, ',') !== false) $home = preg_replace('/^[A-Za-z]?-?\d{4,5}\s+/', '', trim(substr($home, strrpos($home, ',') + 1)));
  $dist = [];
  foreach ($distanzen as $o => $km) $dist[norm_ort($o)] = max(0, (int) $km);
  if ($home !== '') $dist[norm_ort($home)] = 0;

  foreach ($corr as $c) {
    $fz = (int) $c['fahrzeug_id']; $hu = (string) $c['datum']; $kmHu = (int) $c['km_at_hu'];
    $werk = trim((string) $c['werkstattort']); $vor = $c['stopps_vor']; $nach = $c['stopps_nach'];
    $fzName = $names[$fz] ?? "FZ $fz";
    $msg[] = "**HU $fzName am " . fmt_datum($hu) . ' (Tacho laut HU: ' . fmt_int($kmHu) . ' km)**';

    $sumVor = 0; $sumNach = 0; $sumTag = 0; $hat = false;
    foreach ($year as $rows) foreach ($rows as $r) {
      if ((int) ($r['fahrzeug_id'] ?? -1) !== $fz || $r['fahrzeug_id'] === null) continue;
      $hat = true; $s = (int) $r['km_d'] + (int) $r['km_p'];
      if ($r['datum'] < $hu) $sumVor += $s; elseif ($r['datum'] > $hu) $sumNach += $s; else $sumTag += $s;
    }
    if (!$hat) { $msg[] = '- Keine Fahrten dieses Fahrzeugs gefunden – übersprungen.'; continue; }
    $start = (int) ($anchor[$fz] ?? 0);
    $ende = $start + $sumVor + $sumTag + $sumNach;

    [$huKd, $huKp, $hin, $nachweg] = hu_kilometer($dist, $matrix, $home, $werk, $vor, $nach, $msg);
    // KERN: Tacho bei Ankunft Werkstatt = km_at_hu. Abfahrt am HU-Tag = km_at_hu − Weg zur Werkstatt.
    $zielVor = $kmHu - $start - $hin;
    $fVor = ($sumVor > 0 && $zielVor > 0) ? $zielVor / $sumVor : 1.0;
    $abfHuTag = $kmHu - $hin;
    $zielNach = $ende - $kmHu - $nachweg;
    $fNach = ($sumNach > 0 && $zielNach > 0) ? $zielNach / $sumNach : 1.0;
    $fv = clip($fVor, HU_FAKTOR_MIN, HU_FAKTOR_MAX); $fn = clip($fNach, HU_FAKTOR_MIN, HU_FAKTOR_MAX);
    if (abs($fv - $fVor) > 0.01) $msg[] = '- ACHTUNG: HU-Stand passt stark nicht zu den generierten km (Faktor wäre ' . number_format($fVor, 2, ',', '') . ') – auf ' . number_format($fv, 2, ',', '') . ' begrenzt.';
    if (abs($fn - $fNach) > 0.01) $msg[] = '- Faktor nach HU auf ' . number_format($fn, 2, ',', '') . ' begrenzt.';
    $msg[] = "- HU-Fahrt: $huKd km dienstlich, $huKp km privat (Weg zur Werkstatt)";
    $msg[] = '- Abfahrt am HU-Tag: **' . fmt_int($abfHuTag) . ' km** (= ' . fmt_int($kmHu) . " minus $hin km Weg zur Werkstatt) – Tacho zeigt bei Ankunft Werkstatt genau den HU-Stand.";
    $msg[] = '- Faktor vor HU: ' . number_format($fv, 3, ',', '') . ' | nach HU: ' . number_format($fn, 3, ',', '') . ' (Jahressumme bleibt erhalten)';

    $parts = array_merge([$home], $vor, [$werk . ' (HU)'], $nach, [$home]);
    $huRoute = implode(' - ', array_values(array_filter($parts, function ($x) { return $x !== ''; })));
    $huDauer = 90 + (count($vor) + 1 + count($nach)) * 20;
    $huRow = ['route' => $huRoute, 'km_d' => $huKd, 'km_p' => $huKp, 'abf' => '08:30', 'ank' => hhmm(8 * 60 + 30 + $huDauer), 'dauer' => hhmm($huDauer)];

    // Skalieren; die beim Abrunden verlorenen Rest-km werden verteilt, damit der HU-Stand EXAKT stimmt
    // (die Python-Version hat nur abgeschnitten und lag dadurch einige km daneben).
    $exaktVor = abs($fv - $fVor) <= 0.01 && $zielVor > 0 ? $zielVor : null;
    $exaktNach = abs($fn - $fNach) <= 0.01 && $zielNach > 0 ? $zielNach : null;
    hu_skaliere($year, $fz, $hu, true, $fv, $exaktVor);
    hu_skaliere($year, $fz, $hu, false, $fn, $exaktNach);

    $angelegt = false;
    foreach ($year as $m => &$rows) {
      foreach ($rows as &$r) {
        if ($r['fahrzeug_id'] !== null && (int) $r['fahrzeug_id'] === $fz && $r['datum'] === $hu) { $r = array_merge($r, $huRow); $angelegt = true; }
      }
      unset($r);
      if (!$angelegt) {
        foreach ($rows as &$r) {
          if ($r['datum'] === $hu) { $r = array_merge($r, $huRow, ['fahrzeug_id' => $fz, 'fahrzeug' => $fzName]); $angelegt = true; break; }
        }
        unset($r);
        if (!$angelegt && (int) substr($hu, 5, 2) === (int) $m) {
          $rows[] = array_merge(['datum' => $hu, 'fahrzeug_id' => $fz, 'fahrzeug' => $fzName, 'abfahrt_km' => 0], $huRow);
          sort_rows($rows);
          $angelegt = true;
        }
      }
    }
    unset($rows);
    $msg[] = $angelegt ? '- HU-Fahrt am ' . fmt_datum($hu) . ' angelegt.' : '- WARNUNG: HU-Tag liegt außerhalb der gespeicherten Monate!';
  }
  $end = kette_neu($year, $anchor);
  return [$year, $end, $msg];
}

/* ===================== Privat-KM verteilen ===================== */
function zeiten_privat(int $km, bool $gross): array {
  $dauer = max(min(intdiv($km * 60, 70) + rincl(5, 30), 840), 15);
  $start = $gross ? 6 * 60 + rincl(0, 120) : 8 * 60 + rincl(0, 9 * 60);
  $start = min($start, 20 * 60);
  return [hhmm($start), hhmm(min($start + $dauer, 23 * 60 + 59)), hhmm($dauer)];
}
function days_between(string $a, string $b): int { return (int) (new DateTimeImmutable($a))->diff(new DateTimeImmutable($b))->days; }

function verteile_privat_km(array $year, int $fid, int $total, string $fzName, array $o, array $anchor): array {
  $anzGross = (int) ($o['anzahl_gross'] ?? 4); $gMin = (int) ($o['gross_min'] ?? 300); $gMax = max((int) ($o['gross_max'] ?? 800), $gMin);
  $nMin = (int) ($o['normal_min'] ?? 5); $nMax = (int) ($o['normal_max'] ?? 45);
  $msg = [];
  if (!$year) throw new InvalidArgumentException('Keine Fahrten vorhanden – zuerst generieren.');
  if ($total <= 0) throw new InvalidArgumentException('Privat-KM-Summe muss größer 0 sein.');

  $alle = []; $fzRows = []; $huTage = []; $arbeit = [];
  foreach ($year as $m => $rows) foreach ($rows as $i => $r) {
    $d = $r['datum']; $alle[$d] = true;
    if ($r['fahrzeug_id'] !== null && (int) $r['fahrzeug_id'] === $fid) {
      $fzRows[$d] = [$m, $i];
      if (strpos((string) $r['route'], '(HU)') !== false) $huTage[$d] = true;
      if ((int) $r['km_d'] > 0) $arbeit[$d] = true;
    }
  }
  $alle = array_keys($alle); sort($alle);
  if ($huTage) $msg[] = '- ' . count($huTage) . ' HU-Tag(e) bleiben von der Verteilung ausgenommen.';

  // 1) Bestehende Privat-KM des Fahrzeugs auf 0 (HU-Tag bleibt)
  foreach ($fzRows as $d => [$m, $i]) if (!isset($huTage[$d])) $year[$m][$i]['km_p'] = 0;

  // 2) Große Fahrten (bevorzugt Tage ohne Dienstfahrt dieses Fahrzeugs), mind. 21 Tage Abstand
  $kand = array_values(array_filter($alle, function ($d) use ($huTage, $arbeit) { return !isset($huTage[$d]) && !isset($arbeit[$d]); }));
  if (count($kand) < 20) $kand = array_values(array_filter($alle, function ($d) use ($huTage) { return !isset($huTage[$d]); }));
  $gross = []; $versuche = 0;
  while (count($gross) < $anzGross && $versuche < 800 && $kand) {
    $versuche++;
    $d = rchoice($kand);
    $ok = true;
    foreach (array_keys($gross) as $g) if (days_between($d, $g) < 21) { $ok = false; break; }
    if ($ok) $gross[$d] = rincl($gMin, $gMax);
  }
  $sumG = array_sum($gross);
  if ($sumG > $total) {
    $msg[] = '- HINWEIS: Gesamt-Summe (' . fmt_int($total) . ' km) reicht für ' . count($gross) . ' große Fahrten (~' . fmt_int($sumG) . ' km) nicht – Anzahl wurde reduziert.';
    while ($sumG > $total && $gross) { arsort($gross); $k = array_key_first($gross); $sumG -= $gross[$k]; unset($gross[$k]); }
  }
  $rest = $total - $sumG;
  $msg[] = '- ' . count($gross) . ' große Privatfahrten (Urlaub/Ausflüge) mit zusammen ' . fmt_int($sumG) . ' km.';

  // 3) Rest proportional auf normale Tage (Summe exakt)
  $verteilt = $gross;
  if ($rest > 0) {
    $frei = array_values(array_filter($alle, function ($d) use ($huTage, $verteilt) { return !isset($huTage[$d]) && !isset($verteilt[$d]); }));
    shuffle($frei);
    $ziel = max(($nMin + $nMax) / 2.0, 1);
    $n = max(1, min(count($frei), (int) round($rest / $ziel) + 1));
    $werte = [];
    foreach (array_slice($frei, 0, $n) as $d) $werte[$d] = rincl($nMin, max($nMin + 1, $nMax));
    $s = array_sum($werte);
    if ($s === 0) { foreach ($werte as $d => $v) $werte[$d] = 1; $s = count($werte); }
    $f = $rest / $s;
    $zu = [];
    foreach ($werte as $d => $v) $zu[$d] = (int) round($v * $f);
    $diff = $rest - array_sum($zu);
    $tage = array_keys($zu); $guard = 0;
    while ($diff !== 0 && $tage && $guard < 100000) {
      $guard++;
      $d = rchoice($tage);
      if ($diff > 0) { $zu[$d]++; $diff--; } elseif ($zu[$d] > 0) { $zu[$d]--; $diff++; }
    }
    foreach ($zu as $d => $km) if ($km > 0) $verteilt[$d] = $km;
  }
  $msg[] = '- ' . (count($verteilt) - count($gross)) . ' weitere Tage mit privaten Fahrten.';

  // 4a) vorhandene Zeilen des Fahrzeugs aktualisieren, 4b) neue Zeilen anlegen
  ksort($verteilt);
  foreach ($verteilt as $d => $km) {
    $km = (int) $km;
    if ($km <= 0) continue;
    $g = isset($gross[$d]);
    if (isset($fzRows[$d])) {
      [$m, $i] = $fzRows[$d];
      $r = &$year[$m][$i];
      if ((int) $r['km_d'] === 0) {
        $alt = (string) $r['route'];
        if (strpos($alt, 'Keine Fahrt') !== false || trim($alt) === '' || (string) $r['abf'] === '00:00') {
          [$r['abf'], $r['ank'], $r['dauer']] = zeiten_privat($km, $g);
          $r['route'] = $g ? 'Privatfahrt (Urlaub)' : 'Privatfahrt';
        }
      }
      $r['km_p'] = $km;
      unset($r);
    } else {
      $m = (int) substr((string) $d, 5, 2);
      if (!isset($year[$m])) continue;
      [$a, $e, $du] = zeiten_privat($km, $g);
      $year[$m][] = ['datum' => $d, 'fahrzeug_id' => $fid, 'fahrzeug' => $fzName, 'route' => $g ? 'Privatfahrt (Urlaub)' : 'Privatfahrt',
        'km_d' => 0, 'km_p' => $km, 'abf' => $a, 'ank' => $e, 'dauer' => $du, 'abfahrt_km' => 0];
    }
  }
  // 5) Kilometerkette neu aufbauen (Anker bleibt unverändert)
  $end = kette_neu($year, $anchor);
  $summe = 0; $tage = 0;
  foreach ($year as $rows) foreach ($rows as $r) if ($r['fahrzeug_id'] !== null && (int) $r['fahrzeug_id'] === $fid) { $summe += (int) $r['km_p']; if ((int) $r['km_p'] > 0) $tage++; }
  $msg[] = "- Jahres-Summe privat $fzName: **" . fmt_int($summe) . " km** auf $tage Tagen (inkl. HU-Tag, falls vorhanden).";
  return [$year, $end, $msg];
}

/* ===================== Keywords ===================== */
function keywords_aus_text(string $text): array {
  $kw = [];
  foreach (preg_split('/\r\n|\r|\n/', trim($text)) as $line) {
    $p = explode(':', $line);
    if (count($p) === 2) {
      $ort = trim($p[0]);
      foreach (explode(',', $p[1]) as $z) $kw[] = ['ort' => $ort, 'zweck' => trim($z)];
    }
  }
  return $kw;
}
const DEFAULT_KEYWORD_TEXT = "Straßwalchen:Büro\nOberhofen am Irrsee:KB\nStraßwalchen:Schaden,Angebot\n"
  . "Mondsee:Antrag,KFZ\nNeumarkt:Angebot,KFZ\nHenndorf:Angebot,KB\nZell am Moos:KB,Schaden\n"
  . "Köstendorf:Angebot,KB\nFrankenmarkt:Angebot,KFZ\nEugendorf:KFZ,Angebot\n"
  . "Mattighofen:KFZ,Angebot\nObertrum:KFZ\nSeekirchen:Angebot,KB\nLochen:KB,Angebot\n"
  . "Friedburg:Angebot,KB\nVöcklamarkt:KFZ,Angebot\nSt. Georgen:Angebot,Schaden\n"
  . "St. Gilgen:Angebot\nUnterach:KB\nOberwang:Angebot\nKirchberg:Antrag,KB\nFornach:Angebot\n"
  . "Salzburg:Schaden,Angebot\nMunderfing:KB\nSeeham:KB\nHof bei Salzburg:KFZ\n"
  . "Lamprechtshausen:Schaden\nOberndorf:Angebot,KB\nHallwang:Angebot,KB\nSchachen:Antrag\n"
  . "Vöcklabruck:Angebot";
