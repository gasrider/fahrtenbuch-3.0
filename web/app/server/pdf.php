<?php
// Fahrtenbuch - Monats- und Jahres-PDF (Layout wie in der Streamlit-Version)
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }
if (!defined('FPDF_FONTPATH')) define('FPDF_FONTPATH', __DIR__ . '/font/');
require_once __DIR__ . '/fpdf.php';

function pdf_txt($s): string {
  $s = str_replace(['–', '„', '“', '…'], ['-', '"', '"', '...'], (string) $s);
  $r = @iconv('UTF-8', 'windows-1252//TRANSLIT', $s);
  return $r === false ? utf8_decode_fallback($s) : $r;
}
function utf8_decode_fallback(string $s): string { return mb_convert_encoding($s, 'ISO-8859-1', 'UTF-8'); }
function geld(float $v): string { return number_format($v, 2, ',', ''); }

class FbPdf extends FPDF {
  public $fusszeile = '';
  function Footer() {
    if ($this->fusszeile === '') return;
    $this->SetY(-14);
    $this->SetFont('Helvetica', '', 8);
    $this->Cell(0, 5, pdf_txt($this->fusszeile . ' | Seite ' . $this->PageNo() . ' | Gedruckt: ' . date('d.m.Y H:i:s')), 0, 0, 'R');
  }
  // Text in Zeilen fuer eine Spaltenbreite umbrechen
  function zeilen(string $txt, float $w): array {
    $words = preg_split('/\s+/', pdf_txt($txt)); $lines = []; $cur = '';
    foreach ($words as $wd) {
      $try = $cur === '' ? $wd : "$cur $wd";
      if ($this->GetStringWidth($try) <= $w - 2) { $cur = $try; continue; }
      if ($cur !== '') $lines[] = $cur;
      $cur = $wd;
      while ($this->GetStringWidth($cur) > $w - 2 && strlen($cur) > 1) {
        $cut = strlen($cur);
        while ($cut > 1 && $this->GetStringWidth(substr($cur, 0, $cut)) > $w - 2) $cut--;
        $lines[] = substr($cur, 0, $cut); $cur = substr($cur, $cut);
      }
    }
    if ($cur !== '' || !$lines) $lines[] = $cur;
    return $lines;
  }
  // Tabellenzeile mit umbrechender Spalte $wrapIdx
  function zeile(array $cells, array $widths, array $align, float $lh, int $wrapIdx = -1, bool $fill = false, string $style = ''): void {
    $size = $this->FontSizePt;
    $this->SetFont('Helvetica', $style, $size);
    $lines = $wrapIdx >= 0 ? $this->zeilen((string) $cells[$wrapIdx], $widths[$wrapIdx]) : [''];
    $h = max(1, count($lines)) * $lh + 1.5;
    if ($this->GetY() + $h > $this->PageBreakTrigger) {
      $this->AddPage();
      if (isset($this->kopf)) ($this->kopf)();
      $this->SetFont('Helvetica', $style, $size);
    }
    $x = $this->GetX(); $y = $this->GetY();
    foreach ($cells as $i => $c) {
      $w = $widths[$i];
      if ($fill) { $this->SetFillColor(245, 245, 245); $this->Rect($x, $y, $w, $h, 'F'); }
      $this->SetDrawColor(150, 150, 150); $this->Rect($x, $y, $w, $h);
      if ($i === $wrapIdx) {
        foreach ($lines as $n => $l) { $this->SetXY($x + 1, $y + 0.75 + $n * $lh); $this->Cell($w - 2, $lh, $l, 0, 0, 'L'); }
      } else { $this->SetXY($x, $y); $this->Cell($w, $h, pdf_txt($c), 0, 0, $align[$i] ?? 'C'); }
      $x += $w;
    }
    $this->SetXY($this->lMargin, $y + $h);
  }
  public $kopf = null;
}

function fz_liste(array $fahrzeuge, bool $nummer): string {
  $t = [];
  foreach (array_values($fahrzeuge) as $i => $f) $t[] = ($nummer ? ($i + 1) . '-' : '') . $f['bezeichnung'] . ' (' . $f['kennzeichen'] . ')';
  return implode($nummer ? '  |  ' : ', ', $t);
}

function monats_pdf(array $rows, int $monat, int $jahr, array $st, array $fahrzeuge): string {
  $p = new FbPdf('P', 'mm', 'A4');
  $p->SetMargins(12, 12, 12); $p->SetAutoPageBreak(true, 22);
  $p->fusszeile = 'Erstellt von: ' . ($st['name'] ?? '');
  $p->AddPage();
  $p->SetFont('Helvetica', 'B', 16);
  $p->Cell(93, 9, pdf_txt('Fahrtenbuch Monatsübersicht'), 0, 0, 'L');
  $p->Cell(93, 9, pdf_txt(MONATE[$monat - 1] . " $jahr"), 0, 1, 'R');
  $p->Ln(5);
  $p->SetFont('Helvetica', '', 9);
  foreach (['Name: ' . ($st['name'] ?? ''), 'PNR: ' . ($st['pnr'] ?? ''), 'Wohnort: ' . ($st['wohnort'] ?? ''),
    'Dienstort: ' . ($st['dienstort'] ?? ''), 'Entfernung zwischen Arbeitsplatz und Wohnung: ' . to_int($st['entfernung'] ?? 0) . ' km',
    'Fahrzeug(e): ' . fz_liste($fahrzeuge, true)] as $l) $p->MultiCell(0, 4.6, pdf_txt($l));
  $p->Ln(3); $p->Line(12, $p->GetY(), 198, $p->GetY()); $p->Ln(4);

  $w = [12, 10, 10, 12, 65, 16, 17, 16, 13, 15];
  $al = ['C', 'C', 'C', 'C', 'L', 'C', 'C', 'C', 'C', 'C'];
  $kopf = function () use ($p, $w, $al) {
    $p->SetFontSize(8.5);
    $p->zeile(['Tag', 'Abf.', 'Ank.', 'Dauer', 'Reiseweg - Ziel - Zweck', 'Abfahrt', 'km dienstl.', 'km privat', 'Taggeld', 'KFZ'], $w, $al, 4, -1, true, 'B');
    $p->SetFontSize(8);
  };
  $p->kopf = $kopf; $kopf();
  $tp = taggeld_params($st); $sd = 0; $sp = 0; $stg = 0.0;
  foreach ($rows as $r) {
    $ts = strtotime((string) $r['datum']);
    $kd = to_int($r['km_d']); $kp = to_int($r['km_p']);
    $tg = taggeld(dauer_min($r['dauer']), $kd, $tp);
    $sd += $kd; $sp += $kp; $stg += $tg;
    $p->zeile([WOCHENTAGE[(int) date('N', $ts) - 1] . '.' . date('d', $ts) . '.', $r['abf'], $r['ank'], $r['dauer'], (string) $r['route'],
      (string) to_int($r['abfahrt_km']), (string) $kd, (string) $kp, geld($tg), (string) $r['fahrzeug']], $w, $al, 3.6, 4);
  }
  $p->kopf = null;
  $p->zeile(['Einzelsummen:', '', '', '', '', '', (string) $sd, (string) $sp, geld($stg), ''], $w, ['L', 'C', 'C', 'C', 'L', 'C', 'C', 'C', 'C', 'C'], 4, -1, true, 'B');
  $p->Ln(5); $p->SetFont('Helvetica', '', 9);
  $p->Cell(0, 5, pdf_txt('Privat-KM beinhalten die Fahrtstrecke Wohnung-Arbeitsplatz.'), 0, 1);
  $p->Cell(0, 5, pdf_txt('km-Geld Satz PKW amtlich: EUR ' . geld(to_float($st['km_geld'] ?? null, 0.42))), 0, 1);
  return $p->Output('S');
}

function jahres_pdf(array $jahrDaten, int $jahr, array $st, array $fahrzeuge): string {
  $p = new FbPdf('P', 'mm', 'A4');
  $p->SetMargins(20, 15, 20); $p->SetAutoPageBreak(true, 15);
  $p->AddPage();
  $p->SetFont('Helvetica', 'B', 18); $p->Cell(0, 10, pdf_txt("Fahrtenbuch Jahresübersicht $jahr"), 0, 1); $p->Ln(4);
  $p->SetFont('Helvetica', '', 10);
  foreach (['Name: ' . ($st['name'] ?? ''), 'PNR: ' . ($st['pnr'] ?? ''), 'Wohnort: ' . ($st['wohnort'] ?? ''),
    'Dienstort: ' . ($st['dienstort'] ?? ''), 'Entfernung zwischen Arbeitsplatz und Wohnung: ' . to_int($st['entfernung'] ?? 0) . ' km',
    'Fahrzeug(e): ' . fz_liste($fahrzeuge, false)] as $l) $p->MultiCell(0, 5.5, pdf_txt($l));
  $p->Ln(6);
  $w = [32, 28, 25, 30, 30]; $al = ['C', 'C', 'C', 'C', 'C'];
  $p->SetFontSize(9);
  $p->zeile(['Monat', 'km dienstl.', 'km privat', 'km-Geld PKW', 'Taggeld EUR'], $w, $al, 5, -1, true, 'B');
  $satz = to_float($st['km_geld'] ?? null, 0.42); $tp = taggeld_params($st);
  $td = 0; $tpv = 0; $tkg = 0.0; $ttg = 0.0; $proFz = [];
  foreach (MONATE as $i => $mn) {
    $rows = $jahrDaten[$i + 1] ?? [];
    $d = 0; $pv = 0; $tg = 0.0;
    foreach ($rows as $r) {
      $kd = to_int($r['km_d']); $d += $kd; $pv += to_int($r['km_p']);
      $tg += taggeld(dauer_min($r['dauer']), $kd, $tp);
      $k = mb_strtolower(trim((string) $r['fahrzeug']), 'UTF-8'); $proFz[$k] = ($proFz[$k] ?? 0) + $kd;
    }
    $kg = $d * $satz; $td += $d; $tpv += $pv; $tkg += $kg; $ttg += $tg;
    $p->zeile([$mn, (string) $d, (string) $pv, geld($kg), geld($tg)], $w, $al, 5);
  }
  $p->zeile(['Summen', (string) $td, (string) $tpv, geld($tkg), geld($ttg)], $w, $al, 5, -1, true, 'B');
  $p->Ln(8); $p->SetFont('Helvetica', '', 9);
  foreach (["km-Geld Satz PKW amtlich ab 01.01.$jahr EUR " . geld($satz), "km-Geld Satz PKW dienstlich ab 01.01.$jahr EUR 0,00", '',
    "km-Geld dienstlich für {$td}km: EUR 0,00", "km-Geld amtlich für {$td}km inkl. Mitfahrer: EUR " . geld($tkg),
    'Taggeld amtlich: EUR ' . geld($ttg), 'Taggeld + km-Geld amtlich: EUR ' . geld($tkg + $ttg), '',
    'Vom Dienstgeber vergütete Reisekosten: EUR 0,00', 'Für die Arbeitnehmerveranlagung zu berücksichtigen: EUR ' . geld($tkg)] as $l)
    $p->Cell(0, 4.8, pdf_txt($l), 0, 1);
  $p->Ln(6);
  $w2 = [50, 35, 25]; $p->zeile(['Fahrzeug', 'Kennzeichen', 'km dienstl.'], $w2, ['L', 'C', 'C'], 5, -1, true, 'B');
  $summe = 0;
  foreach ($fahrzeuge as $f) {
    $k = $proFz[mb_strtolower(trim((string) $f['bezeichnung']), 'UTF-8')] ?? 0; $summe += $k;
    $p->zeile([(string) $f['bezeichnung'], (string) $f['kennzeichen'], (string) $k], $w2, ['L', 'C', 'C'], 5);
  }
  $p->zeile(['Summen', '', (string) $summe], $w2, ['L', 'C', 'C'], 5, -1, true, 'B');
  $p->Ln(8); $p->SetFont('Helvetica', '', 8); $p->SetTextColor(120, 120, 120);
  $p->MultiCell(0, 4, pdf_txt('Die angegebenen Daten beruhen auf persönlichen Aufzeichnungen der oben genannten Person. UNIQA übernimmt keine Haftung für die Richtigkeit der Angaben.'));
  return $p->Output('S');
}
