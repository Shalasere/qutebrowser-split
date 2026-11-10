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
