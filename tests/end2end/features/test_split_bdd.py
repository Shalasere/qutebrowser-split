# SPDX-FileCopyrightText: Jacob Burns
#
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

import pytest_bdd as bdd

from end2end.fixtures import testprocess

bdd.scenarios('split.feature')

TABBED_BROWSER = ("objreg.get('tabbed-browser', scope='window', "
                  "window='last-focused')")


def _eval(quteproc, expr):
    quteproc.send_cmd(f':debug-pyeval --quiet {expr}')


def _wait_until_true(quteproc, expr, tries=20):
    """Evaluate expr until it's true (the layout/deletion takes a moment)."""
    for _ in range(tries):
        _eval(quteproc, expr)
        try:
            quteproc.wait_for(category='misc', loglevel=logging.DEBUG,
                              message='pyeval output: True', timeout=500)
        except testprocess.WaitForTimeout:
            continue
        return
    raise AssertionError(f"{expr} never became true")


@bdd.then(bdd.parsers.parse("the pane should be {where} the page"))
def check_pane_position(quteproc, where):
    axis = {'right of': 'x', 'below': 'y'}[where]
    _wait_until_true(quteproc, (
        f"(lambda tab: tab.data.pane.isVisible() and "
        f"tab.data.splitter.main_widget().isVisible() and "
        f"tab.data.pane.{axis}() > tab.data.splitter.main_widget().{axis}())"
        f"({TABBED_BROWSER}.widget.currentWidget())"))


@bdd.then(bdd.parsers.parse("the status bar URL should end with {suffix}"))
def check_statusbar_url(quteproc, suffix):
    _wait_until_true(quteproc, (
        "objreg.get('main-window', scope='window', window='last-focused')"
        f".status.url.text().endswith({suffix!r})"))


@bdd.then(bdd.parsers.parse("there should be {count:d} tab objects"))
def check_tab_objects(quteproc, count):
    _wait_until_true(quteproc, (
        "len(objreg.get('tab-registry', scope='window', "
        f"window='last-focused')) == {count}"))


@bdd.when(bdd.parsers.parse("I open and close a pane {count:d} times"))
def open_and_close_pane(quteproc, server, count):
    url = f'http://localhost:{server.port}/data/numbers/2.txt'
    for _ in range(count):
        quteproc.send_cmd(f':vsplit {url} ;; split-close')


@bdd.when(bdd.parsers.parse("the pane of tab {idx:d} is closed in the "
                            "background"))
def close_pane_in_background(quteproc, idx):
    """Close a pane the way a page's window.close() does."""
    _eval(quteproc, f"{TABBED_BROWSER}.close_pane("
                    f"{TABBED_BROWSER}.widget.widget({idx - 1}))")
    quteproc.wait_for(category='misc', loglevel=logging.DEBUG,
                      message='pyeval output: None')
