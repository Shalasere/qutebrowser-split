# SPDX-FileCopyrightText: Jacob Burns
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os.path
import logging

import pytest_bdd as bdd
bdd.scenarios('pair.feature')


def _indices(text):
    return [int(part) for part in text.replace('and', ',').split(',')]


@bdd.then(bdd.parsers.parse("the visible tabs should be {indices}"))
def check_visible_tabs(quteproc, indices):
    """Check which tabs are visible, with 1-based indices like "1 and 3"."""
    expected = ','.join(str(idx - 1) for idx in _indices(indices))
    quteproc.send_cmd(
        ":debug-pyeval --quiet ','.join(str(i) for i, tab in enumerate("
        "objreg.get('tabbed-browser', scope='window', window='last-focused')"
        ".widgets()) if tab.isVisible())")
    quteproc.wait_for(category='misc', loglevel=logging.DEBUG,
                      message=f"pyeval output: '{expected}'")


RECORD_SCRIPT = """
tabbed_browser = objreg.get('tabbed-browser', scope='window',
                            window='last-focused')
for tab in tabbed_browser.widgets():
    tab.test_loads = 0
    tab.test_parent = tab.parentWidget()
    tab.load_started.connect(
        lambda tab=tab: setattr(tab, 'test_loads', tab.test_loads + 1))
"""


@bdd.when("I record the loads and parents of all pages")
def record_loads(quteproc):
    path = os.path.join(quteproc.basedir, 'record.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(RECORD_SCRIPT)
    quteproc.send_cmd(f':debug-pyeval --file {path}')
    quteproc.wait_for(category='misc', loglevel=logging.DEBUG,
                      message='pyeval output: No error')


@bdd.then("no page should have loaded or changed its parent")
def check_loads(quteproc):
    quteproc.send_cmd(
        ":debug-pyeval --quiet ','.join(f'{tab.test_loads}"
        "{tab.parentWidget() is tab.test_parent}' for tab in "
        "objreg.get('tabbed-browser', scope='window', window='last-focused')"
        ".widgets())")
    quteproc.wait_for(category='misc', loglevel=logging.DEBUG,
                      message="pyeval output: '0True,0True'")


@bdd.then(bdd.parsers.parse(
    "tabs {first:d} and {second:d} should be paired {orientation}"))
def check_paired(quteproc, first, second, orientation):
    """Check the saved pair of the window, with 1-based tab indices."""
    window = quteproc.get_session()['windows'][0]
    assert window['pairs'] == [{
        'tabs': [first - 1, second - 1],
        'orientation': orientation,
        'ratio': 0.5,
    }]


@bdd.then("no tabs should be paired")
def check_not_paired(quteproc):
    assert 'pairs' not in quteproc.get_session()['windows'][0]


@bdd.when(bdd.parsers.parse('I replace "{pattern}" by "{replacement}" in the '
                            '"{name}" session file'))
def session_replace(quteproc, pattern, replacement, name):
    # First wait until the session was actually saved
    quteproc.wait_for(category='message', loglevel=logging.INFO,
                      message=f'Saved session {name}.')
    filename = os.path.join(quteproc.basedir, 'data', 'sessions', name + '.yml')
    with open(filename, 'r', encoding='utf-8') as f:
        data = f.read()
    assert pattern in data
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(data.replace(pattern, replacement))


CLICK_SCRIPT = """
from qutebrowser.qt.core import Qt
from qutebrowser.qt.test import QTest

tabbed_browser = objreg.get('tabbed-browser', scope='window',
                            window='last-focused')
tab = tabbed_browser.widget.widget({idx})
target = tab
while target.focusProxy() is not None:
    target = target.focusProxy()
QTest.mouseClick(target, Qt.MouseButton.LeftButton)
"""


@bdd.when(bdd.parsers.parse("I click into tab {idx:d}"))
def click_into_tab(quteproc, idx):
    """Click into the page of a visible tab, with a 1-based index."""
    path = os.path.join(quteproc.basedir, 'click.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(CLICK_SCRIPT.format(idx=idx - 1))
    quteproc.send_cmd(f':debug-pyeval --file {path}')
    quteproc.wait_for(category='misc', loglevel=logging.DEBUG,
                      message='pyeval output: No error')


FULLSCREEN_SCRIPT = """
tabbed_browser = objreg.get('tabbed-browser', scope='window',
                            window='last-focused')
tab = tabbed_browser.widget.currentWidget()
# What QtWebEngine does when the page toggles full screen
tab.data.fullscreen = {on}
tab.fullscreen_requested.emit({on})
"""


@bdd.when(bdd.parsers.parse("the current page {action} full screen"))
def toggle_fullscreen(quteproc, action):
    """Fake the current page entering/leaving full screen."""
    on = {'enters': True, 'leaves': False}[action]
    path = os.path.join(quteproc.basedir, 'fullscreen.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(FULLSCREEN_SCRIPT.format(on=on))
    quteproc.send_cmd(f':debug-pyeval --file {path}')
    quteproc.wait_for(category='misc', loglevel=logging.DEBUG,
                      message='pyeval output: No error')
