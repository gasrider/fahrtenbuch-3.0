<?php
// Fahrtenbuch – Installationsdatei
// Diese eine Datei per WebFTP in den Ordner "fahrtenbuch" hochladen und im Browser öffnen.
// Sie entpackt die App, legt die Datenbank-Tabellen an und löscht sich danach selbst.
// Bei einer bestehenden Installation werden nur die App-Dateien erneuert (Daten + Zugangsdaten bleiben).
declare(strict_types=1);
header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-store');
header('X-Robots-Tag: noindex');

$DIR = __DIR__;
$VERSION = '/*__VERSION__*/';
$FILES = [
/*__FILES__*/
];

function e($s) { return htmlspecialchars((string) $s, ENT_QUOTES, 'UTF-8'); }
function v($k, $d = '') { return isset($_POST[$k]) ? trim((string) $_POST[$k]) : $d; }

$https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
$base = ($https ? 'https://' : 'http://') . ($_SERVER['HTTP_HOST'] ?? '') . rtrim(str_replace('\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '/')), '/') . '/';

$checks = [
  ['PHP-Version ' . PHP_VERSION, version_compare(PHP_VERSION, '7.4', '>='), 'Mindestens PHP 7.4 – im World4You-Kundenbereich unter PHP eine neuere Version wählen.', true],
  ['Datenbank-Treiber (PDO MySQL)', extension_loaded('pdo_mysql'), 'Bitte den World4You-Support fragen.', true],
  ['Ordner beschreibbar', is_writable($DIR), 'Der Ordner erlaubt keine neuen Dateien. Bitte den Support fragen.', true],
  ['Excel-Import (ZipArchive)', class_exists('ZipArchive'), 'Excel-Dateien gehen dann nicht, CSV-Dateien schon.', false],
  ['Online-Karte (cURL)', function_exists('curl_init') || ini_get('allow_url_fopen'), 'Distanzen online berechnen geht dann nicht.', false],
  ['Sichere Verbindung (https)', $https, 'Funktioniert auch so, aber bitte SSL aktivieren und die Seite mit https:// öffnen.', false],
];
$blocking = false; foreach ($checks as $c) if (!$c[1] && $c[3]) $blocking = true;

function write_files(array $files, string $dir): string {
  foreach ($files as $rel => $b64) {
    $path = $dir . '/' . $rel;
    if (!is_dir(dirname($path))) @mkdir(dirname($path), 0755, true);
    if (@file_put_contents($path, base64_decode($b64)) === false) return 'Konnte die Datei ' . $rel . ' nicht schreiben.';
    if (function_exists('opcache_invalidate')) @opcache_invalidate($path, true); // neue Version sofort aktiv
  }
  return '';
}

// Schon installiert?
$installed = false;
if (is_file("$DIR/server/config.php") && is_file("$DIR/server/lib.php")) {
  try {
    if (!defined('FAHRTENBUCH')) define('FAHRTENBUCH', 1);
    require_once "$DIR/server/lib.php";
    if (cfg('db_name', '') !== '') $installed = (int) db()->query('SELECT COUNT(*) FROM fb_users')->fetchColumn() > 0;
  } catch (Throwable $ex) { $installed = false; }
}

$error = ''; $done = false; $updated = false;
if ($installed && !$blocking) {
  $error = write_files($FILES, $DIR);
  if ($error === '') {
    try { create_schema(); $updated = true; }   // idempotent: neue Tabellen/Spalten werden ergänzt
    catch (Throwable $ex) { $error = 'Fehler beim Aktualisieren der Datenbank: ' . $ex->getMessage(); }
  }
}
if (!$installed && !$blocking && ($_SERVER['REQUEST_METHOD'] ?? '') === 'POST') {
  $db = ['db_host' => v('db_host', 'localhost'), 'db_name' => v('db_name'), 'db_user' => v('db_user'), 'db_pass' => (string) ($_POST['db_pass'] ?? '')];
  $adminName = mb_strtolower(v('admin_name')); $adminEmail = mb_strtolower(v('admin_email')); $adminPw = (string) ($_POST['admin_pw'] ?? '');
  $invite = v('invite_code');
  if ($db['db_name'] === '' || $db['db_user'] === '') $error = 'Bitte Datenbankname und Benutzer eintragen.';
  elseif ($adminName === '') $error = 'Bitte deinen Benutzernamen eintragen.';
  elseif ($adminEmail !== '' && !filter_var($adminEmail, FILTER_VALIDATE_EMAIL)) $error = 'Bitte eine gültige E-Mail-Adresse eintragen.';
  elseif (strlen($adminPw) < 8) $error = 'Dein Passwort braucht mindestens 8 Zeichen.';
  else {
    try {
      $host = $db['db_host']; $port = null;
      if (preg_match('/^(.+):(\d+)$/', $host, $m)) { $host = $m[1]; $port = $m[2]; }
      $pdo = new PDO('mysql:host=' . $host . ($port ? ';port=' . $port : '') . ';dbname=' . $db['db_name'] . ';charset=utf8mb4', $db['db_user'], $db['db_pass'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
      $pdo = null;
    } catch (Throwable $ex) {
      $error = 'Keine Verbindung zur Datenbank. Bitte Server, Name, Benutzer und Passwort genau mit World4You vergleichen. (Meldung: ' . $ex->getMessage() . ')';
    }
    if ($error === '') $error = write_files($FILES, $DIR);
    if ($error === '') {
      $cfg = "<?php\n// Fahrtenbuch – Server-Einstellungen (vom Installer erstellt)\n// Geheim: der Ordner server ist per .htaccess gesperrt.\nreturn " . var_export($db, true) . ";\n";
      if (@file_put_contents("$DIR/server/config.php", $cfg) === false) $error = 'Konnte server/config.php nicht schreiben.';
    }
    if ($error === '') {
      try {
        if (!defined('FAHRTENBUCH')) define('FAHRTENBUCH', 1);
        $GLOBALS['FB_CFG'] = $db;
        require_once "$DIR/server/lib.php";
        $GLOBALS['FB_CFG'] = $db;
        create_schema();
        $pdo = db();
        if ((int) $pdo->query('SELECT COUNT(*) FROM fb_users')->fetchColumn() === 0) {
          $pdo->prepare('INSERT INTO fb_users (username, pass_hash, email, is_admin) VALUES (?, ?, ?, 1)')->execute([$adminName, password_hash($adminPw, PASSWORD_DEFAULT), $adminEmail]);
        }
        if ($invite !== '') setting_save('invite_code', $invite);
        $done = true;
      } catch (Throwable $ex) { $error = 'Fehler beim Anlegen der Tabellen: ' . $ex->getMessage(); }
    }
  }
}
$selfDeleted = false;
if ($done || $updated) $selfDeleted = @unlink(__FILE__);
?><!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Fahrtenbuch installieren</title>
<style>
:root{--bg:#eef0f6;--s:#fff;--ink:#151a33;--mu:#5d6482;--li:#d7dbe8;--ac:#2b3fd1;--ok:#1d8a5a;--hi:#c8283a;--wa:#c2410c;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0f1220;--s:#181c30;--ink:#e9ecfa;--mu:#9aa1c2;--li:#2b3150;--ac:#8c9bff;--ok:#4cc38a;--hi:#f07a84;--wa:#f59e5b;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif;padding:24px 16px}
main{max-width:560px;margin:0 auto;display:grid;gap:16px}h1{margin:0;font-size:1.8rem}h2{margin:0;font-size:1.1rem}
.card{background:var(--s);border:1px solid var(--li);border-radius:14px;padding:16px;display:grid;gap:12px}
.row{display:grid;grid-template-columns:22px 1fr;gap:10px;align-items:start}.row small{display:block;color:var(--mu)}
.y{color:var(--ok);font-weight:800}.n{color:var(--hi);font-weight:800}.w{color:var(--wa);font-weight:800}
label{display:grid;gap:4px;font-size:.85rem;font-weight:700;color:var(--mu)}label small{font-weight:400}
input{font:inherit;padding:11px 12px;border:1px solid var(--li);border-radius:10px;background:var(--s);color:var(--ink);font-size:16px;width:100%}
button,.btn{font:inherit;font-weight:700;background:var(--ac);color:#fff;border:0;border-radius:12px;padding:13px 16px;text-decoration:none;text-align:center;cursor:pointer;display:block}
.err{color:var(--hi);font-weight:600}.ok{color:var(--ok);font-weight:700;font-size:1.1rem}code{background:var(--bg);padding:2px 6px;border-radius:6px}
.hint{color:var(--mu);font-size:.9rem;margin:0}
</style></head><body><main>
<h1>Fahrtenbuch installieren</h1>
<p class="hint">Version <?= e($VERSION) ?></p>
<div class="card">
<?php foreach ($checks as [$label, $ok, $hint, $must]): ?>
  <div class="row"><span class="<?= $ok ? 'y' : ($must ? 'n' : 'w') ?>"><?= $ok ? '✓' : ($must ? '✕' : '!') ?></span><span><?= e($label) ?><?php if (!$ok): ?><small><?= e($hint) ?></small><?php endif; ?></span></div>
<?php endforeach; ?>
</div>
<?php if ($done || $updated): ?>
  <div class="card">
    <p class="ok"><?= $done ? 'Fertig! Das Fahrtenbuch ist installiert.' : 'Fertig! Das Fahrtenbuch ist auf die neue Version aktualisiert.' ?></p>
    <?php if ($updated): ?><p class="hint">Deine Daten, Zugänge und Zugangsdaten sind unverändert.</p><?php endif; ?>
    <?php if ($done): ?><p class="hint">Nächster Schritt: anmelden und unter <strong>Admin → Umzug von Supabase</strong> die bisherigen Daten übernehmen.</p><?php endif; ?>
    <?php if ($selfDeleted): ?><p class="hint">Diese Installationsdatei hat sich aus Sicherheitsgründen selbst gelöscht.</p>
    <?php else: ?><p class="err">Bitte lösche jetzt die Datei <code>installieren.php</code> im WebFTP.</p><?php endif; ?>
    <p>Die Adresse deiner App:<br><strong><?= e($base) ?></strong></p>
    <a class="btn" href="<?= e($base) ?>">Zur App und anmelden</a>
  </div>
<?php elseif ($installed && $error): ?>
  <div class="card"><p class="err"><?= e($error) ?></p></div>
<?php elseif ($blocking): ?>
  <div class="card"><p class="err">Bitte zuerst die rot markierten Punkte lösen, dann diese Seite neu laden.</p></div>
<?php else: ?>
  <form class="card" method="post" autocomplete="off">
    <?php if ($error): ?><p class="err"><?= e($error) ?></p><?php endif; ?>
    <h2>1. Datenbank</h2>
    <p class="hint">Diese Angaben zeigt World4You unter „Datenbanken“. Genau so übernehmen. Du kannst auch die Datenbank vom Notizbuch verwenden – die Tabellen heißen anders (fb_…).</p>
    <label>Server / Host <input name="db_host" required value="<?= e(v('db_host', 'localhost')) ?>"></label>
    <label>Datenbankname <input name="db_name" required value="<?= e(v('db_name')) ?>"></label>
    <label>Benutzer <input name="db_user" required value="<?= e(v('db_user')) ?>"></label>
    <label>Passwort der Datenbank <input name="db_pass" type="password" value="<?= e($_POST['db_pass'] ?? '') ?>"></label>
    <h2>2. Dein Admin-Zugang für die App</h2>
    <label>Benutzername <small>(am besten wie bisher, z. B. „christian mayerhofer“)</small><input name="admin_name" required value="<?= e(v('admin_name', 'christian mayerhofer')) ?>" autocomplete="username"></label>
    <label>E-Mail <input name="admin_email" type="email" value="<?= e(v('admin_email')) ?>"></label>
    <label>Passwort für die App <small>(mindestens 8 Zeichen – nicht das Datenbank-Passwort)</small><input name="admin_pw" type="password" required minlength="8" autocomplete="new-password"></label>
    <h2>3. Optional</h2>
    <label>Einladungs-Code für neue Benutzer <small>(leer = Registrierung gesperrt, später unter Admin änderbar)</small><input name="invite_code" value="<?= e(v('invite_code')) ?>"></label>
    <button type="submit">Installieren</button>
  </form>
<?php endif; ?>
</main></body></html>
