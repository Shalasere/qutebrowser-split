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
def widget(qtbot, monkeypatch, config_stub):
    w = tabwidget.TabWidget(0)
    qtbot.add_widget(w)
    monkeypatch.setattr(tabwidget.objects, 'backend',
                        usertypes.Backend.QtWebKit)
    w.resize(800, 600)
    w.show()
    return w


@pytest.fixture
def tabs(widget, fake_web_tab):
    result = [fake_web_tab(tab_id=i) for i in range(5)]
    for i, tab in enumerate(result):
        widget.addTab(tab, f'tab{i}')
    return result


def pair_state(widget):
    """Get a comparable description of all pairs of a widget."""
    return [(widget.indexOf(pair.first), widget.indexOf(pair.second),
             pair.orientation, pytest.approx(pair.ratio))
            for pair in widget.pairs()]


class TestSavePairs:

    def test_no_pairs(self, widget, tabs):
        assert sessions._save_pairs(widget) == []

    def test_pair(self, widget, tabs):
        pair = widget.pair_tabs(tabs[1], tabs[3], VERTICAL)
        pair.set_ratio(0.25)
        assert sessions._save_pairs(widget) == [
            {'tabs': [1, 3], 'orientation': 'top-bottom', 'ratio': 0.25},
        ]

    def test_references_saved_position_not_creation_order(self, widget, tabs):
        widget.pair_tabs(tabs[0], tabs[4], HORIZONTAL)
        widget.tabBar().moveTab(2, 0)  # Unrelated tab, shifts the pair
        assert sessions._save_pairs(widget) == [
            {'tabs': [1, 4], 'orientation': 'left-right', 'ratio': 0.5},
        ]


class TestLoadPairs:

    @pytest.mark.parametrize("orientation", [HORIZONTAL, VERTICAL])
    def test_round_trip(self, widget, tabs, orientation):
        pair = widget.pair_tabs(tabs[1], tabs[3], orientation)
        pair.set_ratio(0.3)
        widget.pair_tabs(tabs[0], tabs[2], HORIZONTAL)
        expected = pair_state(widget)
        data = sessions._save_pairs(widget)
        widget.unpair(tabs[1])
        widget.unpair(tabs[0])
        assert widget.pairs() == []

        sessions._load_pairs(widget, data)

        assert pair_state(widget) == expected
        assert pair_state(widget)[0] == (1, 3, orientation, pytest.approx(0.3))

    def test_round_trip_into_other_widget(self, widget, tabs, qtbot,
                                          fake_web_tab):
        widget.pair_tabs(tabs[2], tabs[0], VERTICAL)
        data = sessions._save_pairs(widget)

        other = tabwidget.TabWidget(1)
        qtbot.add_widget(other)
        for i in range(3):
            other.addTab(fake_web_tab(tab_id=10 + i), f'other{i}')
        sessions._load_pairs(other, data)

        assert pair_state(other) == [(2, 0, VERTICAL, 0.5)]

    def test_loaded_pair_is_displayed(self, widget, tabs, qtbot):
        sessions._load_pairs(widget, [
            {'tabs': [0, 2], 'orientation': 'left-right', 'ratio': 0.5}])
        assert widget.currentWidget() is tabs[0]
        qtbot.wait_until(lambda: tabs[2].width() > 50, timeout=2000)
        assert tabs[0].isVisible()
        assert tabs[2].isVisible()
        assert not tabs[1].isVisible()

    @pytest.mark.parametrize("ratio, expected", [
        (0.4, 0.4), (0, 0.1), (-3, 0.1), (1, 0.9), (200, 0.9), (1e308, 0.9),
    ])
    def test_ratio_is_clamped(self, widget, tabs, ratio, expected):
        sessions._load_pairs(widget, [
            {'tabs': [0, 1], 'orientation': 'top-bottom', 'ratio': ratio}])
        assert widget.pairs()[0].ratio == pytest.approx(expected)

    def test_missing_ratio_uses_default(self, widget, tabs):
        sessions._load_pairs(widget, [
            {'tabs': [0, 1], 'orientation': 'top-bottom'}])
        assert widget.pairs()[0].ratio == 0.5

    @pytest.mark.parametrize("entry", [
        None,
        "string",
        42,
        [],
        {},
        {'orientation': 'left-right'},
        {'tabs': [0, 1]},
        {'tabs': [0], 'orientation': 'left-right'},
        {'tabs': [0, 1, 2], 'orientation': 'left-right'},
        {'tabs': 'ab', 'orientation': 'left-right'},
        {'tabs': None, 'orientation': 'left-right'},
        {'tabs': [0, 0], 'orientation': 'left-right'},  # same tab twice
        {'tabs': [0, 5], 'orientation': 'left-right'},  # out of range
        {'tabs': [-1, 1], 'orientation': 'left-right'},
        {'tabs': [0, 1.0], 'orientation': 'left-right'},
        {'tabs': [True, 1], 'orientation': 'left-right'},
        {'tabs': ['0', '1'], 'orientation': 'left-right'},
        {'tabs': [0, 1], 'orientation': 'diagonal'},
        {'tabs': [0, 1], 'orientation': None},
        {'tabs': [0, 1], 'orientation': ['left-right']},
        {'tabs': [0, 1], 'orientation': 1},
        {'tabs': [0, 1], 'orientation': 'left-right', 'ratio': 'half'},
        {'tabs': [0, 1], 'orientation': 'left-right', 'ratio': None},
        {'tabs': [0, 1], 'orientation': 'left-right', 'ratio': True},
        {'tabs': [0, 1], 'orientation': 'left-right', 'ratio': float('nan')},
        {'tabs': [0, 1], 'orientation': 'left-right', 'ratio': float('inf')},
    ])
    def test_malformed_pair_is_discarded(self, widget, tabs, entry):
        sessions._load_pairs(widget, [entry])
        assert widget.pairs() == []
        assert widget.count() == 5  # every tab is kept

    @pytest.mark.parametrize("data", [None, "x", 3, {'tabs': [0, 1]}])
    def test_malformed_container_is_discarded(self, widget, tabs, data):
        sessions._load_pairs(widget, data)
        assert widget.pairs() == []

    def test_valid_pairs_survive_invalid_ones(self, widget, tabs):
        sessions._load_pairs(widget, [
            {'tabs': [0, 0], 'orientation': 'left-right'},
            {'tabs': [1, 2], 'orientation': 'top-bottom', 'ratio': 0.5},
            "garbage",
        ])
        assert pair_state(widget) == [(1, 2, VERTICAL, 0.5)]

    def test_overlapping_pairs_keep_the_first(self, widget, tabs):
        sessions._load_pairs(widget, [
            {'tabs': [0, 1], 'orientation': 'left-right'},
            {'tabs': [1, 2], 'orientation': 'left-right'},
        ])
        assert pair_state(widget) == [(0, 1, HORIZONTAL, 0.5)]

    def test_pinned_tab_is_not_paired(self, widget, tabs):
        tabs[1].set_pinned(True)
        sessions._load_pairs(widget, [
            {'tabs': [0, 1], 'orientation': 'left-right'}])
        assert widget.pairs() == []
