<?php
// Fahrtenbuch – PDF-Erzeugung ohne Fremdbibliothek (Helvetica, WinAnsi-Zeichensatz: ä ö ü ß € funktionieren).
// Layout wie die bisherigen ReportLab-PDFs (monats_pdf.py / jahres_pdf.py).
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

const PDF_W_REG = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,278,278,584,584,584,556,1015,667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,667,611,722,667,944,667,667,611,278,278,278,469,556,333,556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,556,556,333,500,278,556,500,722,500,500,500,334,260,334,584,350,556,350,222,556,333,1000,556,556,333,1000,667,333,1000,350,611,350,350,222,222,333,333,350,556,1000,333,1000,500,333,944,350,500,667,278,333,556,556,556,556,260,556,333,737,370,556,584,333,737,333,400,584,333,333,333,556,537,278,333,333,365,556,834,834,834,611,667,667,667,667,667,667,1000,722,667,667,667,667,278,278,278,278,722,722,778,778,778,778,778,584,778,722,722,722,722,667,667,611,556,556,556,556,556,556,889,500,556,556,556,556,278,278,278,278,556,556,556,556,556,556,556,584,611,556,556,556,556,500,556,500];
const PDF_W_BOLD = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,278,333,474,556,556,889,722,238,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,333,333,584,584,584,611,975,722,722,722,722,667,611,778,722,278,556,722,611,833,722,778,667,778,722,667,611,722,667,944,667,667,611,333,278,333,584,556,333,556,611,556,611,556,333,611,611,278,278,556,278,889,611,611,611,611,389,556,333,611,556,778,556,556,500,389,280,389,584,350,556,350,278,556,500,1000,556,556,333,1000,667,333,1000,350,611,350,350,278,278,500,500,350,556,1000,333,1000,556,333,944,350,500,667,278,333,556,556,556,556,280,556,333,737,370,556,584,333,737,333,400,584,333,333,333,611,556,278,333,333,365,556,834,834,834,611,722,722,722,722,722,722,1000,722,667,667,667,667,278,278,278,278,722,722,778,778,778,778,778,584,778,722,722,722,722,667,667,611,556,556,556,556,556,556,889,556,556,556,556,556,278,278,278,278,611,611,611,611,611,611,611,584,611,611,611,611,611,556,611,556];

const MM = 72 / 25.4;

class Pdf {
  public float $W = 595.28; public float $H = 841.89;   // A4 in Punkt
  private array $pages = []; private string $cur = '';
  public int $page = 0;
  public $onPage = null;                                 // callable(Pdf) – z. B. Fußzeile

  public function addPage(): void {
    if ($this->page > 0) $this->finishPage();
    $this->page++; $this->cur = '';
  }
  private function finishPage(): void {
    if (is_callable($this->onPage)) ($this->onPage)($this);
    $this->pages[] = $this->cur;
  }
  public static function enc(string $s): string {
    $c = @iconv('UTF-8', 'CP1252//TRANSLIT', $s);
    if ($c === false) $c = mb_convert_encoding($s, 'ISO-8859-1', 'UTF-8');
    return $c;
  }
  public static function width(string $s, float $size, bool $bold = false): float {
    $w = 0; $t = $bold ? PDF_W_BOLD : PDF_W_REG; $e = self::enc($s);
    for ($i = 0, $n = strlen($e); $i < $n; $i++) $w += $t[ord($e[$i])] ?: 556;
    return $w * $size / 1000;
  }
  private static function esc(string $s): string { return strtr(self::enc($s), ['\\' => '\\\\', '(' => '\\(', ')' => '\\)', "\r" => '', "\n" => ' ']); }
  // x/y in mm von links oben (y = Grundlinie)
  public function text(float $x, float $y, string $s, float $size, bool $bold = false, string $align = 'L', array $rgb = [0, 0, 0]): void {
    if ($s === '') return;
    $px = $x * MM;
    if ($align !== 'L') { $w = self::width($s, $size, $bold); $px -= $align === 'R' ? $w : $w / 2; }
    $col = sprintf('%.3F %.3F %.3F rg ', $rgb[0], $rgb[1], $rgb[2]);
    $this->cur .= sprintf("BT %s/%s %.2F Tf %.2F %.2F Td (%s) Tj ET\n", $col, $bold ? 'F2' : 'F1', $size, $px, $this->H - $y * MM, self::esc($s));
  }
  public function line(float $x1, float $y1, float $x2, float $y2, float $w = 0.25, float $gray = 0.5): void {
    $this->cur .= sprintf("%.3F G %.2F w %.2F %.2F m %.2F %.2F l S\n", $gray, $w, $x1 * MM, $this->H - $y1 * MM, $x2 * MM, $this->H - $y2 * MM);
  }
  public function fillRect(float $x, float $y, float $w, float $h, float $gray): void {
    $this->cur .= sprintf("%.3F g %.2F %.2F %.2F %.2F re f 0 g\n", $gray, $x * MM, $this->H - ($y + $h) * MM, $w * MM, $h * MM);
  }
  // Zeilenumbruch nach Breite (mm)
  public static function wrap(string $s, float $wmm, float $size, bool $bold = false): array {
    $max = $wmm * MM; $lines = [];
    foreach (preg_split('/\r\n|\r|\n/', $s) as $para) {
      $words = preg_split('/ +/', $para); $line = '';
      foreach ($words as $wd) {
        $try = $line === '' ? $wd : "$line $wd";
        if (self::width($try, $size, $bold) <= $max || $line === '') {
          if ($line === '' && self::width($wd, $size, $bold) > $max) {
            // überlanges Wort hart trennen
            $chunk = '';
            foreach (preg_split('//u', $wd, -1, PREG_SPLIT_NO_EMPTY) as $ch) {
              if (self::width($chunk . $ch, $size, $bold) > $max && $chunk !== '') { $lines[] = $chunk; $chunk = ''; }
              $chunk .= $ch;
            }
            $line = $chunk;
          } else $line = $try;
        } else { $lines[] = $line; $line = $wd; }
      }
      $lines[] = $line;
    }
    return $lines;
  }
  public function output(): string {
    $this->finishPage();
    $objs = [];
    $objs[1] = '<< /Type /Catalog /Pages 2 0 R >>';
    $objs[3] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>';
    $objs[4] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>';
    $kids = []; $n = 5;
    foreach ($this->pages as $c) {
      $z = function_exists('gzcompress') ? gzcompress($c) : null;
      $objs[$n + 1] = $z !== null ? '<< /Length ' . strlen($z) . " /Filter /FlateDecode >>\nstream\n" . $z . "\nendstream"
                                  : '<< /Length ' . strlen($c) . " >>\nstream\n" . $c . "\nendstream";
      $objs[$n] = sprintf('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2F %.2F] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>', $this->W, $this->H, $n + 1);
      $kids[] = "$n 0 R"; $n += 2;
    }
    $objs[2] = '<< /Type /Pages /Kids [' . implode(' ', $kids) . '] /Count ' . count($kids) . ' >>';
    ksort($objs);
    $out = "%PDF-1.4\n%\xE2\xE3\xCF\xD3\n"; $off = [];
    foreach ($objs as $i => $o) { $off[$i] = strlen($out); $out .= "$i 0 obj\n$o\nendobj\n"; }
    $x = strlen($out); $cnt = max(array_keys($objs)) + 1;
    $out .= "xref\n0 $cnt\n0000000000 65535 f \n";
    for ($i = 1; $i < $cnt; $i++) $out .= sprintf("%010d 00000 n \n", $off[$i] ?? 0);
    $out .= "trailer\n<< /Size $cnt /Root 1 0 R >>\nstartxref\n$x\n%%EOF";
    return $out;
  }
}

/**
 * Tabelle mit Gitter, Kopfzeilen (werden auf Folgeseiten wiederholt), Spaltenverbindung (span) und Umbruch.
 * Zelle: string|int oder ['t'=>text,'b'=>fett,'a'=>'L|C|R','span'=>n,'wrap'=>bool]
 * $o: x, y, widths[], size, leading, bottom (mm), header (Anzahl Kopfzeilen), headBg, lastBold, lastBg, thickLast
 */
function pdf_table(Pdf $pdf, array $rows, array $o): float {
  $x0 = $o['x']; $y = $o['y']; $wid = $o['widths']; $size = $o['size'] ?? 8; $lead = $o['leading'] ?? $size * 1.2;
  $padX = 6 / MM; $padY = 3 / MM; $bottom = $o['bottom']; $nHead = $o['header'] ?? 0;
  $norm = function ($row, $ri) use ($o, $rows) {
    $cells = []; $c = 0;
    foreach ($row as $cell) {
      if (!is_array($cell)) $cell = ['t' => (string) $cell];
      $cell += ['t' => '', 'b' => false, 'a' => 'C', 'span' => 1, 'wrap' => false, 'col' => $c];
      $cell['t'] = (string) $cell['t'];
      if ($ri < ($o['header'] ?? 0) || (($o['lastBold'] ?? false) && $ri === count($rows) - 1)) $cell['b'] = true;
      $cells[] = $cell; $c += $cell['span'];
    }
    return $cells;
  };
  $prepared = [];
  foreach ($rows as $ri => $row) {
    $cells = $norm($row, $ri); $hLines = 1;
    foreach ($cells as &$cell) {
      $w = 0; for ($k = 0; $k < $cell['span']; $k++) $w += $wid[$cell['col'] + $k];
      $cell['w'] = $w;
      $cell['lines'] = $cell['wrap'] ? Pdf::wrap($cell['t'], $w - 2 * $padX, $size, $cell['b']) : [$cell['t']];
      $hLines = max($hLines, count($cell['lines']));
    }
    unset($cell);
    $prepared[] = ['cells' => $cells, 'h' => $hLines * $lead / MM + 2 * $padY, 'ri' => $ri];
  }
  $draw = function (array $pr, float $y) use ($pdf, $x0, $wid, $size, $lead, $padX, $padY, $o, $rows) {
    $isHead = $pr['ri'] < ($o['header'] ?? 0); $isLast = $pr['ri'] === count($rows) - 1;
    $total = array_sum($wid);
    if (($isHead && ($o['headBg'] ?? true)) || ($isLast && ($o['lastBg'] ?? false))) $pdf->fillRect($x0, $y, $total, $pr['h'], 0.96);
    $x = $x0;
    foreach ($pr['cells'] as $cell) {
      $n = count($cell['lines']);
      $ty = $y + ($pr['h'] - $n * $lead / MM) / 2 + $size * 0.78 / MM;
      foreach ($cell['lines'] as $li => $ln) {
        $tx = $cell['a'] === 'L' ? $x + $padX : ($cell['a'] === 'R' ? $x + $cell['w'] - $padX : $x + $cell['w'] / 2);
        $pdf->text($tx, $ty + $li * $lead / MM, $ln, $size, $cell['b'], $cell['a']);
      }
      $pdf->line($x, $y, $x, $y + $pr['h']);
      $x += $cell['w'];
    }
    $pdf->line($x, $y, $x, $y + $pr['h']);
    $pdf->line($x0, $y, $x0 + $total, $y);
    $pdf->line($x0, $y + $pr['h'], $x0 + $total, $y + $pr['h']);
    if ($isLast && ($o['thickLast'] ?? false)) { $pdf->line($x0, $y, $x0 + $total, $y, 1.5, 0); $pdf->line($x0, $y + $pr['h'], $x0 + $total, $y + $pr['h'], 1.5, 0); }
  };
  $heads = array_slice($prepared, 0, $nHead);
  foreach ($prepared as $i => $pr) {
    if ($i >= $nHead && $y + $pr['h'] > $pdf->H / MM - $bottom) {
      $pdf->addPage(); $y = $o['top'] ?? 12;
      foreach ($heads as $h) { $draw($h, $y); $y += $h['h']; }
    }
    $draw($pr, $y); $y += $pr['h'];
  }
  return $y;
}

function eur(float $v): string { return number_format($v, 2, ',', ''); }

/* ===================== Monats-PDF ===================== */
function pdf_monat(array $rows, int $monat, int $jahr, array $user, array $fahrzeuge): string {
  $pdf = new Pdf(); $L = 12; $R = 12; $width = 210 - $L - $R;
  $name = (string) ($user['name'] ?? '');
  $druck = (new DateTimeImmutable('now', new DateTimeZone('Europe/Vienna')))->format('d.m.Y H:i:s');
  $pdf->onPage = function (Pdf $p) use ($name, $druck, $R) {
    $p->text(210 - $R, 297 - 10, 'Erstellt von: ' . ($name !== '' ? $name : 'Unbekannt') . " | Seite {$p->page} | Gedruckt: $druck", 8, false, 'R');
  };
  $pdf->addPage();
  $y = 20;
  $pdf->text($L, $y, 'Fahrtenbuch Monatsübersicht', 16, true);
  $pdf->text(210 - $R, $y, MONATE[$monat - 1] . " $jahr", 16, true, 'R');
  $y += 12;
  $fz = [];
  foreach (array_values($fahrzeuge) as $i => $f) $fz[] = ($i + 1) . '-' . $f['bezeichnung'] . ' (' . $f['kennzeichen'] . ')';
  $lines = ['Name: ' . $name, 'PNR: ' . ($user['pnr'] ?? ''), 'Wohnort: ' . ($user['wohnort'] ?? ''), 'Dienstort: ' . ($user['dienstort'] ?? ''),
    'Entfernung zwischen Arbeitsplatz und Wohnung: ' . safe_int($user['entfernung'] ?? 0) . ' km', 'Fahrzeug(e): ' . implode('  |  ', $fz)];
  foreach ($lines as $l) foreach (Pdf::wrap($l, $width, 9) as $wl) { $pdf->text($L + 2, $y, $wl, 9); $y += 4.6; }
  $y += 3; $pdf->line($L, $y, 210 - $R, $y, 1, 0); $y += 5;

  $tp = taggeld_params($user);
  $data = [
    ['Tag', 'Abf.', 'Ank.', 'Dauer', 'Reiseweg - Ziel - Zweck', 'Abfahrt', ['t' => 'gefahrene km', 'span' => 2], 'Taggeld', 'KFZ'],
    ['', '', '', '', '', '', 'dienstl.', 'privat', '', ''],
  ];
  $sd = 0; $sp = 0; $st = 0.0;
  foreach ($rows as $r) {
    $wd = WOCHENTAGE_KURZ[weekday($r['datum'])];
    $kd = (int) $r['km_d']; $kp = (int) $r['km_p'];
    $tg = $kd > 0 ? taggeld_betrag(dauer_min($r['dauer']), $tp) : 0.0;
    $sd += $kd; $sp += $kp; $st += $tg;
    $data[] = [$wd . '.' . substr($r['datum'], 8, 2) . '.', $r['abf'], $r['ank'], $r['dauer'], ['t' => (string) $r['route'], 'a' => 'L', 'wrap' => true],
      (string) (int) $r['abfahrt_km'], (string) $kd, (string) $kp, eur($tg), ['t' => (string) $r['fahrzeug'], 'wrap' => true]];
  }
  $data[] = [['t' => 'Einzelsummen:', 'span' => 5], '', (string) $sd, (string) $sp, eur($st), ''];
  $y = pdf_table($pdf, $data, ['x' => $L, 'y' => $y, 'widths' => [12, 10, 10, 12, 71, 15, 15, 15, 12, 18], 'size' => 8, 'leading' => 9.6,
    'bottom' => 25, 'top' => 12, 'header' => 2, 'lastBg' => true]);
  $y += 6;
  $satz = safe_float($user['km_geld'] ?? null, 0.42);
  foreach (['Privat-KM beinhalten die Fahrtstrecke Wohnung-Arbeitsplatz.', 'km-Geld Satz PKW amtlich: EUR ' . eur($satz)] as $n) {
    if ($y > 297 - 25) { $pdf->addPage(); $y = 15; }
    $pdf->text($L, $y, $n, 10); $y += 6;
  }
  return $pdf->output();
}

/* ===================== Jahres-PDF ===================== */
function pdf_jahr(array $year, int $jahr, array $user, array $fahrzeuge): string {
  $pdf = new Pdf(); $L = 20; $width = 170;
  $pdf->addPage();
  $y = 22;
  $pdf->text($L, $y, "Fahrtenbuch Jahresübersicht $jahr", 18, true);
  $y += 12;
  $fz = array_map(function ($f) { return $f['bezeichnung'] . ' (' . $f['kennzeichen'] . ')'; }, $fahrzeuge);
  $lines = ['Name: ' . ($user['name'] ?? ''), 'PNR: ' . ($user['pnr'] ?? ''), 'Wohnort: ' . ($user['wohnort'] ?? ''), 'Dienstort: ' . ($user['dienstort'] ?? ''),
    'Entfernung zwischen Arbeitsplatz und Wohnung: ' . safe_int($user['entfernung'] ?? 0) . ' km', 'Fahrzeug(e): ' . implode(', ', $fz)];
  foreach ($lines as $l) foreach (Pdf::wrap($l, $width, 10) as $wl) { $pdf->text($L, $y, $wl, 10); $y += 4.9; }
  $y += 8;

  $tp = taggeld_params($user); $satz = safe_float($user['km_geld'] ?? null, 0.42);
  $data = [['Monat', ['t' => 'gefahren km', 'span' => 2], ['t' => 'km-Geld', 'span' => 2]], ['Monat', 'dienstl.', 'privat', 'PKW', 'EUR']];
  $td = 0; $tpv = 0; $tk = 0.0; $tt = 0.0;
  foreach (MONATE as $i => $mn) {
    $rows = $year[$i + 1] ?? [];
    $d = 0; $p = 0; $t = 0.0;
    foreach ($rows as $r) { $d += (int) $r['km_d']; $p += (int) $r['km_p']; if ((int) $r['km_d'] > 0) $t += taggeld_betrag(dauer_min($r['dauer']), $tp); }
    $k = $d * $satz;
    $td += $d; $tpv += $p; $tk += $k; $tt += $t;
    $data[] = [$mn, (string) $d, (string) $p, eur($k), eur($t)];
  }
  $data[] = ['Summen', (string) $td, (string) $tpv, eur($tk), eur($tt)];
  $w = [32, 28, 25, 30, 30];
  $y = pdf_table($pdf, $data, ['x' => (210 - array_sum($w)) / 2, 'y' => $y, 'widths' => $w, 'size' => 9, 'leading' => 10.8, 'bottom' => 15, 'top' => 15,
    'header' => 2, 'lastBold' => true, 'thickLast' => true]);
  $y += 12;
  $sum = ["km-Geld Satz PKW amtlich ab 01.01.$jahr EUR " . number_format($satz, 2, '.', ''), "km-Geld Satz PKW dienstlich ab 01.01.$jahr EUR 0,00", '',
    "km-Geld dienstlich für {$td}km: EUR 0,00", "km-Geld amtlich für {$td}km inkl. Mitfahrer: EUR " . eur($tk), 'Taggeld amtlich: EUR ' . eur($tt),
    'Taggeld + km-Geld amtlich: EUR ' . eur($tk + $tt), '', 'Vom Dienstgeber vergütete Reisekosten: EUR 0,00',
    'Für die Arbeitnehmerveranlagung zu berücksichtigen: EUR ' . eur($tk)];
  foreach ($sum as $l) { if ($l === '') { $y += 2; continue; } $pdf->text($L, $y, $l, 9); $y += 4.6; }
  $y += 10;
  $veh = [['Fahrzeug', 'Kennzeichen', 'dienstl.']]; $tv = 0;
  foreach ($fahrzeuge as $f) {
    $n = trim((string) $f['bezeichnung']);
    if ($n === '') continue;
    $km = 0;
    foreach ($year as $rows) foreach ($rows as $r) if (mb_strtolower(trim((string) $r['fahrzeug'])) === mb_strtolower($n)) $km += (int) $r['km_d'];
    $veh[] = [['t' => $n, 'a' => 'L'], $f['kennzeichen'], (string) $km]; $tv += $km;
  }
  $veh[] = [['t' => 'Summen', 'a' => 'L'], '', (string) $tv];
  $w2 = [40, 30, 25];
  if ($y + 8 * count($veh) > 297 - 15) { $pdf->addPage(); $y = 20; }
  $y = pdf_table($pdf, $veh, ['x' => (210 - array_sum($w2)) / 2, 'y' => $y, 'widths' => $w2, 'size' => 9, 'leading' => 10.8, 'bottom' => 15, 'top' => 15,
    'header' => 1, 'lastBold' => true, 'thickLast' => true]);
  $y += 12;
  foreach (Pdf::wrap('Die angegebenen Daten beruhen auf persönlichen Aufzeichnungen der oben genannten Person. UNIQA übernimmt keine Haftung für die Richtigkeit der Angaben.', $width, 8) as $l) {
    $pdf->text($L, $y, $l, 8, false, 'L', [0.5, 0.5, 0.5]); $y += 3.9;
  }
  return $pdf->output();
}
