# SPDX-FileCopyrightText: Freya Bruhin (The Compiler) <mail@qutebrowser.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from qutebrowser.qt.core import QUrl
from qutebrowser.browser import browsertab


class TestAction:

    def test_run_string_valid(self, qtbot, web_tab):
        url_1 = QUrl("qute://testdata/data/backforward/1.txt")
        url_2 = QUrl("qute://testdata/data/backforward/2.txt")

        with qtbot.wait_signal(web_tab.load_finished):
            web_tab.load_url(url_1)
        with qtbot.wait_signal(web_tab.load_finished):
            web_tab.load_url(url_2)

        assert web_tab.url() == url_2
        with qtbot.wait_signal(web_tab.load_finished):
            web_tab.action.run_string("Back")
        assert web_tab.url() == url_1

    @pytest.mark.parametrize("member", ["blah", "PermissionUnknown"])
    def test_run_string_invalid(self, qtbot, web_tab, member):
        with pytest.raises(
            browsertab.WebTabError,
            match=f"{member} is not a valid web action!",
        ):
            web_tab.action.run_string(member)


class TestActivePane:

    @pytest.fixture
    def tab(self, fake_web_tab):
        return fake_web_tab()

    @pytest.fixture
    def pane(self, tab, fake_web_tab):
        pane = fake_web_tab()
        pane.data.pane_owner = tab
        tab.data.pane = pane
        return pane

    def test_no_pane(self, tab):
        assert tab.active_pane() is tab

    def test_unfocused_pane(self, tab, pane):
        assert tab.active_pane() is tab

    def test_focused_pane(self, tab, pane):
        tab.data.pane_active = True
        assert tab.active_pane() is pane

    def test_stale_active_flag_without_pane(self, tab):
        tab.data.pane_active = True
        assert tab.active_pane() is tab
