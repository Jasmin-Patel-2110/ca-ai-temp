<?php

declare(strict_types=1);

use PhpMyAdmin\Common;
use PhpMyAdmin\UrlRedirector;

if (! defined('ROOT_PATH')) {
    // phpcs:disable PSR1.Files.SideEffects
    define('ROOT_PATH', __DIR__ . DIRECTORY_SEPARATOR);
    // phpcs:enable
}

if (PHP_VERSION_ID < 80200) {
    die(
        '<p>Due to packaging complexities PHP 8.2.0+ is required ('
        . '<a href="https://bugs.launchpad.net/bugs/2016016">Ubuntu Launchpad bug #2016016</a>'
        . '&nbsp;and&nbsp;<a href="https://github.com/phpmyadmin/phpmyadmin/issues/17503">phpMyAdmin issue #17503</a>'
        . ').</p><p>Currently installed version is: ' . PHP_VERSION . '</p>'
    );
}

// phpcs:disable PSR1.Files.SideEffects
define('PHPMYADMIN', true);
// phpcs:enable

require_once ROOT_PATH . 'libraries/constants.php';

/**
 * Activate autoloader
 */
if (! @is_readable(AUTOLOAD_FILE)) {
    die(
        '<p>File <samp>' . AUTOLOAD_FILE . '</samp> missing or not readable.</p>'
        . '<p>Most likely you did not run Composer to '
        . '<a href="https://docs.phpmyadmin.net/en/latest/setup.html#installing-from-git">'
        . 'install library files</a>.</p>'
    );
}

require AUTOLOAD_FILE;

$isMinimumCommon = true;

Common::run();

UrlRedirector::redirect();
