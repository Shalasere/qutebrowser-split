# SPDX-FileCopyrightText: Jacob Burns
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for saving/loading tab pairs in qutebrowser.misc.sessions.

This is separate from test_sessions.py, which needs QtWebKit.
"""

import pytest

from qutebrowser.qt.core import Qt

from qutebrowser.mainwindow import tabwidget
from qutebrowser.misc import sessions
from qutebrowser.utils import usertypes

HORIZONTAL = Qt.Orientation.Horizontal
VERTICAL = Qt.Orientation.Vertical


@pytest.fixture
def widget(qtbot, monkeypatch, config_stub, fake_web_tab):
    w = tabwidget.TabWidget(0)
    qtbot.add_widget(w)
    monkeypatch.setattr(tabwidget.objects, 'backend',
                        usertypes.Backend.QtWebKit)
    w.show()
    for i in range(5):
        w.addTab(fake_web_tab(tab_id=i), f'tab{i}')
    return w


def pair_state(widget):
    return [(widget.indexOf(pair.first), widget.indexOf(pair.second),
             pair.orientation, pytest.approx(pair.ratio))
            for pair in widget.pairs()]


def test_save(widget):
    pair = widget.pair_tabs(widget.widget(0), widget.widget(4), VERTICAL)
    pair.set_ratio(0.25)
    widget.tabBar().moveTab(2, 0)  # Unrelated tab, shifts the pair
    assert sessions._save_pairs(widget) == [
        {'tabs': [1, 4], 'orientation': 'top-bottom', 'ratio': 0.25},
    ]


@pytest.mark.parametrize("orientation", [HORIZONTAL, VERTICAL])
def test_round_trip(widget, orientation):
    widget.pair_tabs(widget.widget(1), widget.widget(3), orientation).set_ratio(0.3)
    widget.pair_tabs(widget.widget(0), widget.widget(2), HORIZONTAL)
    expected = pair_state(widget)
    data = sessions._save_pairs(widget)
    widget.unpair(widget.widget(1))
    widget.unpair(widget.widget(0))

    sessions._load_pairs(widget, data)

    assert pair_state(widget) == expected
    assert expected[0] == (1, 3, orientation, pytest.approx(0.3))


@pytest.mark.parametrize("ratio, expected", [
    (0.4, 0.4), (-3, 0.1), (200, 0.9), (1e308, 0.9), (None, 0.5),
])
def test_ratio_is_clamped(widget, ratio, expected):
    entry = {'tabs': [0, 1], 'orientation': 'top-bottom'}
    if ratio is not None:
        entry['ratio'] = ratio
    sessions._load_pairs(widget, [entry])
    assert widget.pairs()[0].ratio == pytest.approx(expected)


@pytest.mark.parametrize("entry", [
    None,
    "string",
    {},
    {'tabs': [0, 1]},
    {'orientation': 'left-right'},
    {'tabs': [0], 'orientation': 'left-right'},
    {'tabs': [0, 1, 2], 'orientation': 'left-right'},
    {'tabs': 'ab', 'orientation': 'left-right'},
    {'tabs': [0, 0], 'orientation': 'left-right'},
    {'tabs': [0, 5], 'orientation': 'left-right'},
    {'tabs': [-1, 1], 'orientation': 'left-right'},
    {'tabs': [0, 1.0], 'orientation': 'left-right'},
    {'tabs': ['0', '1'], 'orientation': 'left-right'},
    {'tabs': [0, 1], 'orientation': 'diagonal'},
    {'tabs': [0, 1], 'orientation': ['left-right']},
    {'tabs': [0, 1], 'orientation': 'left-right', 'ratio': 'half'},
    {'tabs': [0, 1], 'orientation': 'left-right', 'ratio': None},
    {'tabs': [0, 1], 'orientation': 'left-right', 'ratio': float('nan')},
    {'tabs': [0, 1], 'orientation': 'left-right', 'ratio': float('inf')},
])
def test_malformed_pair_is_discarded(widget, entry):
    sessions._load_pairs(widget, [entry])
    assert widget.pairs() == []
    assert widget.count() == 5


@pytest.mark.parametrize("data", [None, "x", 3, {'tabs': [0, 1]}])
def test_malformed_container_is_discarded(widget, data):
    sessions._load_pairs(widget, data)
    assert widget.pairs() == []


def test_pinned_tab_is_not_paired(widget):
    widget.widget(3).set_pinned(True)
    sessions._load_pairs(widget, [
        {'tabs': [2, 3], 'orientation': 'left-right'},
        {'tabs': [1, 2], 'orientation': 'top-bottom'},
    ])
    assert pair_state(widget) == [(1, 2, VERTICAL, 0.5)]


def test_overlapping_pairs_keep_the_first(widget):
    sessions._load_pairs(widget, [
        {'tabs': [0, 1], 'orientation': 'left-right'},
        {'tabs': [1, 2], 'orientation': 'left-right'},
    ])
    assert pair_state(widget) == [(0, 1, HORIZONTAL, 0.5)]


def test_entries_beyond_the_possible_number_of_pairs_are_ignored(widget):
    entry = {'tabs': [0, 1], 'orientation': 'left-right'}
    sessions._load_pairs(widget, [{}, {}, entry])
    assert widget.pairs() == []
