<?php
// Fahrtenbuch – Online-Distanzen über OpenStreetMap, ohne API-Schlüssel (wie services/routing.py).
// Nominatim: Ort → Koordinaten (max. 1 Anfrage/Sekunde), OSRM: echte Fahrstrecke in km.
// Die App ruft das schrittweise auf (wenige Orte/Strecken pro Anfrage), damit kein Server-Zeitlimit greift.
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

const GEO_PAUSE_US = 1100000;
const OSRM_PAUSE_US = 200000;
const FAKTOR_STRASSE = 1.25;

function osm_headers(): array { return ['User-Agent: Fahrtenbuch-App/4.0 (PHP; OpenStreetMap-Distanzen)', 'Accept-Language: de']; }

// 3 Stufen: Österreich zuerst, dann AT+DE, dann weltweit (damit „Neumarkt“ nicht in Deutschland landet)
// $nahe = [lat, lon] des Wohnorts: zuerst nur im Umkreis (~70 km) suchen – so wird „Kirchberg“ das nahe Kirchberg, nicht Kirchberg in Tirol
function geocodiere_ort(string $name, ?array $nahe = null): ?array {
  $name = trim($name);
  if ($name === '') return null;
  $base = (string) cfg('nominatim_url', 'https://nominatim.openstreetmap.org/search');
  $stufen = [["$name, Österreich", 'at', true], ["$name, Österreich", 'at', false], [$name, 'at,de', false], [$name, null, false]];
  if (!$nahe) array_shift($stufen);
  foreach ($stufen as $i => [$q, $cc, $umkreis]) {
    $params = ['q' => $q, 'format' => 'json', 'limit' => 1];
    if ($cc) $params['countrycodes'] = $cc;
    if ($umkreis) { $params['viewbox'] = sprintf('%F,%F,%F,%F', $nahe[1] - 0.9, $nahe[0] + 0.6, $nahe[1] + 0.9, $nahe[0] - 0.6); $params['bounded'] = 1; }
    [$code, $data] = http_json('GET', $base . '?' . http_build_query($params), osm_headers(), null, 15);
    if (is_array($data) && isset($data[0]['lat'], $data[0]['lon'])) {
      return ['lat' => (float) $data[0]['lat'], 'lon' => (float) $data[0]['lon'], 'display_name' => (string) ($data[0]['display_name'] ?? '')];
    }
    usleep(GEO_PAUSE_US);
  }
  return null;
}
function routen_km(float $lat1, float $lon1, float $lat2, float $lon2): ?int {
  $base = (string) cfg('osrm_url', 'https://router.project-osrm.org/route/v1/driving');
  [$code, $data] = http_json('GET', sprintf('%s/%F,%F;%F,%F?overview=false&alternatives=false&steps=false', $base, $lon1, $lat1, $lon2, $lat2), osm_headers(), null, 25);
  if (is_array($data) && ($data['code'] ?? '') === 'Ok' && !empty($data['routes'])) {
    $m = (float) ($data['routes'][0]['distance'] ?? 0);
    if ($m > 0) return (int) round($m / 1000);
  }
  return null;
}
function haversine_km(float $lat1, float $lon1, float $lat2, float $lon2): int {
  $p1 = deg2rad($lat1); $p2 = deg2rad($lat2); $dp = deg2rad($lat2 - $lat1); $dl = deg2rad($lon2 - $lon1);
  $a = sin($dp / 2) ** 2 + cos($p1) * cos($p2) * sin($dl / 2) ** 2;
  return (int) round(2 * 6371.0 * asin(sqrt($a)) * FAKTOR_STRASSE);
}
