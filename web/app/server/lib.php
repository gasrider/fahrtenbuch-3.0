<?php
// Fahrtenbuch - gemeinsame Server-Funktionen (Datenbank, Anmeldung, Einstellungen, E-Mail)
declare(strict_types=1);

if (!defined('FAHRTENBUCH')) { http_response_code(403); exit; }

$GLOBALS['FB_CFG'] = require __DIR__ . '/config.php';

function cfg(string $k, $default = null) {
  $c = $GLOBALS['FB_CFG'];
  return (isset($c[$k]) && $c[$k] !== '') ? $c[$k] : $default;
}

function db(): PDO {
  static $pdo = null;
  if ($pdo) return $pdo;
  $host = (string) cfg('db_host', 'localhost');
  $port = null;
  if (preg_match('/^(.+):(\d+)$/', $host, $m)) { $host = $m[1]; $port = $m[2]; }
  $dsn = 'mysql:host=' . $host . ($port ? ';port=' . $port : '') . ';dbname=' . cfg('db_name', '') . ';charset=utf8mb4';
  $pdo = new PDO($dsn, (string) cfg('db_user', ''), (string) cfg('db_pass', ''), [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES => false,
  ]);
  $pdo->exec("SET time_zone = '+00:00'");
  return $pdo;
}

// Alle Tabellen (idempotent). Praefix fb_, damit die Datenbank mit anderen Apps geteilt werden kann.
function create_schema(): void {
  $db = db();
  $o = 'ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci';
  $db->exec("CREATE TABLE IF NOT EXISTS fb_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    email VARCHAR(190) NOT NULL DEFAULT '',
    pass_hash VARCHAR(255) NOT NULL,
    is_admin TINYINT(1) NOT NULL DEFAULT 0,
    force_pw_change TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
  ) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used DATETIME NULL,
    expires_at DATETIME NOT NULL,
    INDEX (user_id)
  ) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_attempts (
    id INT AUTO_INCREMENT PRIMARY KEY, ip VARCHAR(64) NOT NULL,
    ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, INDEX (ip, ts)) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_system (k VARCHAR(64) PRIMARY KEY, v TEXT NULL) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_stammdaten (
    username VARCHAR(120) PRIMARY KEY,
    name VARCHAR(190) NOT NULL DEFAULT '', pnr VARCHAR(60) NOT NULL DEFAULT '',
    wohnort VARCHAR(190) NOT NULL DEFAULT '', dienstort VARCHAR(190) NOT NULL DEFAULT '',
    entfernung INT NOT NULL DEFAULT 25,
    taggeld_min_stunden DOUBLE NOT NULL DEFAULT 5, taggeld_basis DOUBLE NOT NULL DEFAULT 10,
    taggeld_stufung DOUBLE NOT NULL DEFAULT 2.5, taggeld_max_betrag DOUBLE NOT NULL DEFAULT 30,
    taggeld_max_stunden DOUBLE NOT NULL DEFAULT 13, km_geld DOUBLE NOT NULL DEFAULT 0.42
  ) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_fahrzeuge (
    id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(120) NOT NULL,
    bezeichnung VARCHAR(190) NOT NULL, kennzeichen VARCHAR(60) NOT NULL DEFAULT '',
    start_km_vorjahr INT NOT NULL DEFAULT 0, privat_km_min INT NOT NULL DEFAULT 5,
    privat_km_max INT NOT NULL DEFAULT 20, dienstlich_quote INT NOT NULL DEFAULT 90,
    INDEX (username)) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_zeitraeume (
    id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(120) NOT NULL,
    fahrzeug_id INT NOT NULL, von DATE NOT NULL, bis DATE NOT NULL, INDEX (username)) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_fahrten (
    id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(120) NOT NULL,
    jahr SMALLINT NOT NULL, monat TINYINT NOT NULL, datum DATE NOT NULL,
    fahrzeug_id INT NULL, fahrzeug VARCHAR(190) NOT NULL DEFAULT '', route TEXT NULL,
    km_d INT NOT NULL DEFAULT 0, km_p INT NOT NULL DEFAULT 0,
    abf VARCHAR(5) NOT NULL DEFAULT '00:00', ank VARCHAR(5) NOT NULL DEFAULT '00:00',
    dauer VARCHAR(6) NOT NULL DEFAULT '00:00', abfahrt_km INT NOT NULL DEFAULT 0,
    INDEX (username, jahr, monat)) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_hu (
    id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(120) NOT NULL, fahrzeug_id INT NOT NULL,
    datum DATE NOT NULL, km_at_hu INT NOT NULL DEFAULT 0, werkstattort VARCHAR(190) NOT NULL DEFAULT '',
    stopps_vor_hu TEXT NULL, stopps_nach_hu TEXT NULL, INDEX (username)) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_orte (
    username VARCHAR(120) NOT NULL, ort VARCHAR(190) NOT NULL,
    km_einfach INT NOT NULL DEFAULT 0, PRIMARY KEY (username, ort)) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_koordinaten (
    username VARCHAR(120) NOT NULL, ort_key VARCHAR(190) NOT NULL, ort VARCHAR(190) NOT NULL DEFAULT '',
    lat DOUBLE NULL, lon DOUBLE NULL, display_name TEXT NULL, PRIMARY KEY (username, ort_key)) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_matrix (
    username VARCHAR(120) NOT NULL, key_a VARCHAR(190) NOT NULL, key_b VARCHAR(190) NOT NULL,
    ort_a VARCHAR(190) NOT NULL DEFAULT '', ort_b VARCHAR(190) NOT NULL DEFAULT '',
    km INT NOT NULL, quelle VARCHAR(20) NOT NULL DEFAULT 'osrm', PRIMARY KEY (username, key_a, key_b)) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_start_km (
    username VARCHAR(120) NOT NULL, jahr SMALLINT NOT NULL, fahrzeug_id INT NOT NULL,
    start_km INT NOT NULL, PRIMARY KEY (username, jahr, fahrzeug_id)) $o");
  $db->exec("CREATE TABLE IF NOT EXISTS fb_gen_settings (
    username VARCHAR(120) NOT NULL, jahr SMALLINT NOT NULL, settings_json MEDIUMTEXT NULL,
    PRIMARY KEY (username, jahr)) $o");
}

function out(array $data, int $code = 200): void {
  http_response_code($code);
  header('Content-Type: application/json; charset=utf-8');
  echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PARTIAL_OUTPUT_ON_ERROR);
  exit;
}
function fail(int $code, string $msg): void { out(['error' => $msg], $code); }

function json_input(): array {
  $raw = file_get_contents('php://input');
  if ($raw === false || $raw === '') return [];
  $d = json_decode($raw, true);
  return is_array($d) ? $d : [];
}
function client_ip(): string { return substr((string) ($_SERVER['REMOTE_ADDR'] ?? ''), 0, 64); }

/* ---------- Anmeldung ---------- */
function current_user(): ?array {
  static $done = false, $user = null;
  if ($done) return $user;
  $done = true;
  $t = (string) ($_SERVER['HTTP_X_AUTH_TOKEN'] ?? '');
  if (!preg_match('/^[a-f0-9]{64}$/', $t)) return null;
  $st = db()->prepare('SELECT u.*, k.id AS token_id FROM fb_tokens k JOIN fb_users u ON u.id = k.user_id WHERE k.token_hash = ? AND k.expires_at > UTC_TIMESTAMP()');
  $st->execute([hash('sha256', $t)]);
  $r = $st->fetch();
  if (!$r) return null;
  db()->prepare('UPDATE fb_tokens SET last_used = UTC_TIMESTAMP() WHERE id = ?')->execute([$r['token_id']]);
  return $user = $r;
}
function require_user(): array {
  $u = current_user();
  if (!$u) fail(401, 'Bitte neu anmelden.');
  if ((int) $u['force_pw_change']) fail(428, 'Bitte zuerst ein neues Passwort setzen.');
  return $u;
}
function require_admin(): array { $u = require_user(); if (!(int) $u['is_admin']) fail(403, 'Nur Admins dürfen das.'); return $u; }
function public_user(array $u): array {
  return ['id' => (int) $u['id'], 'username' => $u['username'], 'email' => $u['email'],
    'is_admin' => (bool) (int) $u['is_admin'], 'force_pw_change' => (bool) (int) $u['force_pw_change']];
}
function issue_token(int $userId): string {
  $token = bin2hex(random_bytes(32));
  db()->prepare('INSERT INTO fb_tokens (user_id, token_hash, expires_at) VALUES (?, ?, UTC_TIMESTAMP() + INTERVAL 180 DAY)')
    ->execute([$userId, hash('sha256', $token)]);
  return $token;
}
// Passwort pruefen. Alte Passwoerter aus Streamlit (SHA256 ohne Salz) werden beim
// ersten Login automatisch auf ein sicheres Verfahren umgestellt.
function check_password(array $u, string $pw): bool {
  $h = (string) $u['pass_hash'];
  if (strpos($h, 'sha256:') === 0) {
    if (!hash_equals(substr($h, 7), hash('sha256', $pw))) return false;
    db()->prepare('UPDATE fb_users SET pass_hash = ? WHERE id = ?')->execute([password_hash($pw, PASSWORD_DEFAULT), $u['id']]);
    return true;
  }
  return password_verify($pw, $h);
}

/* ---------- System-Einstellungen (Mail) ---------- */
function settings_all(): array {
  static $cache = null;
  if ($cache !== null) return $cache;
  $cache = [];
  foreach (db()->query('SELECT k, v FROM fb_system')->fetchAll() as $r) $cache[$r['k']] = (string) $r['v'];
  return $cache;
}
function setting(string $k, $default = '') {
  $s = settings_all();
  if (isset($s[$k]) && $s[$k] !== '') return $s[$k];
  return cfg($k, $default);
}
function setting_save(string $k, ?string $v): void {
  db()->prepare('INSERT INTO fb_system (k, v) VALUES (?, ?) ON DUPLICATE KEY UPDATE v = VALUES(v)')->execute([$k, $v]);
}

/* ---------- HTTP ---------- */
function http_request(string $method, string $url, ?string $body, array $headers, int $timeout = 30): array {
  if (function_exists('curl_init')) {
    $ch = curl_init($url);
    $opt = [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => $timeout, CURLOPT_CONNECTTIMEOUT => 15,
      CURLOPT_HTTPHEADER => $headers, CURLOPT_CUSTOMREQUEST => $method, CURLOPT_FOLLOWLOCATION => true];
    if ($body !== null) $opt[CURLOPT_POSTFIELDS] = $body;
    curl_setopt_array($ch, $opt);
    $res = curl_exec($ch);
    $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    curl_close($ch);
    if ($res === false) return [0, null, $err];
    return [$code, json_decode((string) $res, true), ''];
  }
  $ctx = stream_context_create(['http' => ['method' => $method, 'header' => implode("\r\n", $headers),
    'content' => $body ?? '', 'timeout' => $timeout, 'ignore_errors' => true]]);
  $res = @file_get_contents($url, false, $ctx);
  $code = 0;
  foreach (($http_response_header ?? []) as $h) if (preg_match('#^HTTP/\S+\s+(\d{3})#', $h, $m)) $code = (int) $m[1];
  if ($res === false) return [0, null, 'Keine Verbindung'];
  return [$code, json_decode((string) $res, true), ''];
}
function http_get_json(string $url, array $headers = [], int $timeout = 30): array { return http_request('GET', $url, null, $headers, $timeout); }
function http_post_json(string $url, array $body, array $headers, int $timeout = 30): array {
  $headers[] = 'Content-Type: application/json';
  return http_request('POST', $url, json_encode($body, JSON_UNESCAPED_UNICODE), $headers, $timeout);
}
function http_post_form(string $url, array $fields, int $timeout = 30): array {
  return http_request('POST', $url, http_build_query($fields), ['Content-Type: application/x-www-form-urlencoded'], $timeout);
}

/* ---------- E-Mail-Versand (SMTP, PHP mail oder Microsoft 365 / Graph) ---------- */
function mail_enabled(): bool { return in_array((string) setting('mail_mode', 'off'), ['php', 'smtp', 'graph'], true); }
function mime_header(string $s): string { return preg_match('/[^\x20-\x7e]/', $s) ? '=?UTF-8?B?' . base64_encode($s) . '?=' : $s; }
function clean_header(string $s): string { return trim(str_replace(["\r", "\n"], ' ', $s)); }

function send_mail(array $to, string $subject, string $text): void {
  $mode = (string) setting('mail_mode', 'off');
  $from = (string) setting('mail_from', '');
  $fromName = clean_header((string) setting('mail_from_name', 'Fahrtenbuch'));
  if (!filter_var($from, FILTER_VALIDATE_EMAIL)) throw new RuntimeException('In den Einstellungen fehlt die Absender-Adresse.');
  $to = array_values(array_filter(array_map('trim', $to), function ($e) { return (bool) filter_var($e, FILTER_VALIDATE_EMAIL); }));
  if (!$to) throw new RuntimeException('Keine gültige Empfänger-Adresse.');
  if ($mode === 'graph') { graph_send($from, $to, $subject, $text); return; }
  $host = preg_replace('/[^a-z0-9.-]/i', '', substr(strrchr($from, '@'), 1)) ?: 'localhost';
  $headers = [
    'Date: ' . date('r'),
    'From: ' . mime_header($fromName) . ' <' . $from . '>',
    'To: ' . implode(', ', $to),
    'Subject: ' . mime_header(clean_header($subject)),
    'Message-ID: <' . bin2hex(random_bytes(12)) . '@' . $host . '>',
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
  ];
  $body = rtrim(chunk_split(base64_encode(str_replace(["\r\n", "\r"], "\n", $text)), 76, "\r\n"));
  if ($mode === 'php') {
    $h = array_values(array_filter($headers, function ($l) { return stripos($l, 'To:') !== 0 && stripos($l, 'Subject:') !== 0; }));
    if (!@mail(implode(', ', $to), mime_header(clean_header($subject)), $body, implode("\r\n", $h), '-f' . $from))
      throw new RuntimeException('Der Webserver hat die Mail nicht angenommen. Bitte auf SMTP oder Microsoft 365 umstellen.');
    return;
  }
  if ($mode !== 'smtp') throw new RuntimeException('Der E-Mail-Versand ist ausgeschaltet.');
  smtp_send((string) setting('smtp_host', ''), (int) setting('smtp_port', '587'), (string) setting('smtp_secure', 'tls'),
    (string) setting('smtp_user', ''), (string) setting('smtp_pass', ''), $from, $to, implode("\r\n", $headers) . "\r\n\r\n" . $body);
}

function smtp_send(string $host, int $port, string $secure, string $user, string $pass, string $from, array $to, string $data): void {
  if ($host === '') throw new RuntimeException('In den Einstellungen fehlt der SMTP-Server.');
  $remote = ($secure === 'ssl' ? 'ssl://' : 'tcp://') . $host . ':' . $port;
  $ctx = stream_context_create(['ssl' => ['SNI_enabled' => true, 'peer_name' => $host]]);
  $fp = @stream_socket_client($remote, $errno, $errstr, 15, STREAM_CLIENT_CONNECT, $ctx);
  if (!$fp) throw new RuntimeException("Keine Verbindung zum SMTP-Server $host:$port ($errstr).");
  stream_set_timeout($fp, 20);
  $read = function () use ($fp) {
    $out = '';
    while (($line = fgets($fp, 1024)) !== false) { $out .= $line; if (strlen($line) < 4 || $line[3] === ' ') break; }
    return $out;
  };
  $cmd = function (string $c, array $ok, string $what) use ($fp, $read) {
    if ($c !== '') fwrite($fp, $c . "\r\n");
    $r = $read();
    if (!in_array((int) substr($r, 0, 3), $ok, true)) throw new RuntimeException("SMTP-Fehler bei $what: " . trim(substr($r, 0, 200)));
    return $r;
  };
  try {
    $cmd('', [220], 'Verbindung');
    $ehlo = 'EHLO ' . (preg_replace('/[^a-z0-9.-]/i', '', (string) ($_SERVER['SERVER_NAME'] ?? 'localhost')) ?: 'localhost');
    $cmd($ehlo, [250], 'Begrüßung');
    if ($secure === 'tls') {
      $cmd('STARTTLS', [220], 'Verschlüsselung');
      if (!@stream_socket_enable_crypto($fp, true, STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT | (defined('STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT') ? STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT : 0)))
        throw new RuntimeException('Verschlüsselung (STARTTLS) fehlgeschlagen.');
      $cmd($ehlo, [250], 'Begrüßung nach TLS');
    }
    if ($user !== '') {
      $cmd('AUTH LOGIN', [334], 'Anmeldung');
      $cmd(base64_encode($user), [334], 'Benutzername');
      $cmd(base64_encode($pass), [235], 'Passwort (Benutzer oder Passwort falsch?)');
    }
    $cmd('MAIL FROM:<' . $from . '>', [250], 'Absender');
    foreach ($to as $rcpt) $cmd('RCPT TO:<' . $rcpt . '>', [250, 251], 'Empfänger ' . $rcpt);
    $cmd('DATA', [354], 'Nachricht');
    $cmd(preg_replace('/^\./m', '..', $data) . "\r\n.", [250], 'Senden');
    @fwrite($fp, "QUIT\r\n");
  } finally { @fclose($fp); }
}

function graph_token(): string {
  $tenant = preg_replace('/[^a-z0-9.-]/i', '', (string) setting('graph_tenant', ''));
  $client = trim((string) setting('graph_client', ''));
  $secret = (string) setting('graph_secret', '');
  if ($tenant === '' || $client === '' || $secret === '') throw new RuntimeException('Für Microsoft 365 fehlen Verzeichnis-ID, Anwendungs-ID oder geheimer Schlüssel.');
  [$code, $res, $err] = http_post_form("https://login.microsoftonline.com/$tenant/oauth2/v2.0/token", [
    'client_id' => $client, 'client_secret' => $secret, 'grant_type' => 'client_credentials', 'scope' => 'https://graph.microsoft.com/.default']);
  if ($code === 0) throw new RuntimeException('Keine Verbindung zu Microsoft' . ($err ? " ($err)" : '') . '.');
  if ($code >= 400 || empty($res['access_token'])) {
    $d = (string) ($res['error_description'] ?? $res['error'] ?? "Fehler $code");
    if (strpos($d, 'AADSTS7000215') !== false) $d = 'Der geheime Clientschlüssel stimmt nicht. Bitte den WERT des Schlüssels eintragen, nicht die Schlüssel-ID.';
    elseif (strpos($d, 'AADSTS700016') !== false) $d = 'Die Anwendungs-ID (Client-ID) wurde in diesem Verzeichnis nicht gefunden.';
    elseif (strpos($d, 'AADSTS90002') !== false) $d = 'Die Verzeichnis-ID (Tenant-ID) stimmt nicht.';
    throw new RuntimeException('Anmeldung bei Microsoft fehlgeschlagen: ' . strtok($d, "\r\n"));
  }
  return (string) $res['access_token'];
}
function graph_send(string $from, array $to, string $subject, string $text): void {
  $token = graph_token();
  $msg = ['subject' => $subject, 'body' => ['contentType' => 'Text', 'content' => $text],
    'toRecipients' => array_map(function ($e) { return ['emailAddress' => ['address' => $e]]; }, $to)];
  [$code, $res, $err] = http_post_json('https://graph.microsoft.com/v1.0/users/' . rawurlencode($from) . '/sendMail',
    ['message' => $msg, 'saveToSentItems' => false], ['Authorization: Bearer ' . $token]);
  if ($code === 0) throw new RuntimeException('Keine Verbindung zu Microsoft' . ($err ? " ($err)" : '') . '.');
  if ($code >= 400) {
    $m = (string) ($res['error']['message'] ?? "Fehler $code");
    $c = (string) ($res['error']['code'] ?? '');
    if ($code === 403 || $c === 'ErrorAccessDenied') $m = 'Microsoft verweigert den Versand. Ist die Berechtigung „Mail.Send“ (Anwendung) eingetragen und die Administratorzustimmung erteilt?';
    elseif ($code === 404 || $c === 'ErrorInvalidUser' || $c === 'MailboxNotEnabledForRESTAPI') $m = "Das Postfach $from gibt es in Microsoft 365 nicht oder es hat keine Lizenz.";
    throw new RuntimeException('Microsoft 365: ' . $m);
  }
}
