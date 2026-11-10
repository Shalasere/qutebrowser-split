# SPDX-FileCopyrightText: Freya Bruhin (The Compiler) <mail@qutebrowser.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tab widget used for TabbedBrowser from browser.py."""

import functools
import contextlib
import dataclasses
from typing import Any

from qutebrowser.qt.core import (pyqtSignal, pyqtSlot, Qt, QSize, QRect, QPoint,
                          QTimer, QUrl)
from qutebrowser.qt.widgets import (QTabWidget, QTabBar, QSizePolicy, QProxyStyle,
                             QStyle, QStylePainter, QStyleOptionTab,
                             QCommonStyle, QWidget, QBoxLayout, QApplication)
from qutebrowser.qt.gui import QIcon, QPalette, QColor

from qutebrowser.utils import qtutils, objreg, utils, usertypes, log
from qutebrowser.config import config, stylesheet
from qutebrowser.misc import objects, debugcachestats
from qutebrowser.browser import browsertab
from qutebrowser.mainwindow import viewhost


class TabWidget(QWidget):

    """The tab widget used for TabbedBrowser.

    This replaces QTabWidget and keeps the parts of its API which callers use
    (the camelCase names). The tab bar and the list of tabs live here, while
    the ViewHost shows the current tab, or both tabs of its pair.

    A pair links two distinct, unpinned tabs of this window. Both stay ordinary
    tabs, a pair only decides which tabs are shown while one of them is
    current. Closing, moving or pinning a member dissolves its pair. Pairs refer
    to tabs, not indices.

    Attributes:
        _bar: The TabBar.
        _view_host: The ViewHost which owns and shows the tab widgets.
        _layout: Lays out the tab bar and the view host.
        _tabs: All tab widgets in tab bar order.
        _pairs: All tab pairs of this window.
        _tab_position: The current QTabWidget.TabPosition of the tab bar.

    Signals:
        tab_index_changed: Emitted when the current tab was changed.
                           arg 0: The index of the tab which is now focused.
                           arg 1: The total count of tabs.
        new_tab_requested: Emitted when a new tab is requested.
        currentChanged: Emitted when the current tab index changed.
        tabCloseRequested: Emitted when closing a tab was requested.
    """

    tab_index_changed = pyqtSignal(int, int)
    new_tab_requested = pyqtSignal('QUrl', bool, bool)
    currentChanged = pyqtSignal(int)  # noqa: N815
    tabCloseRequested = pyqtSignal(int)  # noqa: N815

    # Strings for controlling the mute/audible text
    MUTE_STRING = '[M] '
    AUDIBLE_STRING = '[A] '

    def __init__(self, win_id, parent=None):
        super().__init__(parent)
        self._tabs: list[browsertab.AbstractTab] = []
        self._pairs: list[viewhost.ViewPair] = []
        self._tab_position: QTabWidget.TabPosition | None = None

        self._layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._view_host = viewhost.ViewHost(self)

        bar = TabBar(win_id, self)
        self._bar = bar
        self.setStyle(TabBarStyle())

        # Keep our tab list and the displayed tab in sync with the bar first,
        # only then notify everyone else.
        bar.tabMoved.connect(self._on_tab_moved)
        bar.currentChanged.connect(self._on_bar_current_changed)
        bar.tabCloseRequested.connect(self.tabCloseRequested)
        bar.tabMoved.connect(functools.partial(
            QTimer.singleShot, 0, self.update_tab_titles))
        bar.currentChanged.connect(self._on_current_changed)
        bar.new_tab_requested.connect(self._on_new_tab_requested)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bar.setDocumentMode(True)
        bar.setExpanding(False)
        bar.setUsesScrollButtons(True)
        bar.setDrawBase(False)
        self._init_config()
        config.instance.changed.connect(self._init_config)

        app = QApplication.instance()
        assert isinstance(app, QApplication), app
        app.focusChanged.connect(self._on_focus_changed)

    @config.change_filter('tabs')
    def _init_config(self):
        """Initialize attributes based on the config."""
        bar = self.tab_bar()
        bar.setMovable(True)
        bar.setTabsClosable(False)
        position = config.val.tabs.position
        selection_behavior = config.val.tabs.select_on_remove
        self._set_tab_position(position)
        bar.setElideMode(config.val.tabs.title.elide)

        bar.vertical = position in [
            QTabWidget.TabPosition.West, QTabWidget.TabPosition.East]
        bar.setSelectionBehaviorOnRemove(selection_behavior)
        bar.refresh()

    def _set_tab_position(self, position: QTabWidget.TabPosition) -> None:
        """Move the tab bar to the given side of the displayed tabs."""
        if position == self._tab_position:
            return
        self._tab_position = position

        shapes = {
            QTabWidget.TabPosition.North: QTabBar.Shape.RoundedNorth,
            QTabWidget.TabPosition.South: QTabBar.Shape.RoundedSouth,
            QTabWidget.TabPosition.West: QTabBar.Shape.RoundedWest,
            QTabWidget.TabPosition.East: QTabBar.Shape.RoundedEast,
        }
        self._bar.setShape(shapes[position])

        vertical = position in [
            QTabWidget.TabPosition.West, QTabWidget.TabPosition.East]
        bar_first = position in [
            QTabWidget.TabPosition.North, QTabWidget.TabPosition.West]
        self._layout.setDirection(
            QBoxLayout.Direction.LeftToRight if vertical
            else QBoxLayout.Direction.TopToBottom)
        self._layout.removeWidget(self._bar)
        self._layout.removeWidget(self._view_host)
        if bar_first:
            self._layout.addWidget(self._bar)
            self._layout.addWidget(self._view_host, stretch=1)
        else:
            self._layout.addWidget(self._view_host, stretch=1)
            self._layout.addWidget(self._bar)

    # QTabWidget-compatible tab API

    def tabBar(self) -> "TabBar":
        """Get the TabBar (QTabWidget API)."""
        return self._bar

    def count(self) -> int:
        """Get the number of tabs."""
        return len(self._tabs)

    def widget(self, idx: int) -> browsertab.AbstractTab | None:
        """Get the tab widget at the given index, or None if out of range."""
        if 0 <= idx < len(self._tabs):
            return self._tabs[idx]
        return None

    def indexOf(self, tab: QWidget | None) -> int:
        """Get the index of the given tab widget, or -1 if it's not a tab."""
        for idx, candidate in enumerate(self._tabs):
            if candidate is tab:
                return idx
        return -1

    def currentIndex(self) -> int:
        """Get the index of the current tab, or -1 if there is none."""
        return self._bar.currentIndex()

    def setCurrentIndex(self, idx: int) -> None:
        """Make the tab at the given index current."""
        self._bar.setCurrentIndex(idx)

    def currentWidget(self) -> browsertab.AbstractTab | None:
        """Get the current tab widget, or None if there is none."""
        return self.widget(self.currentIndex())

    def setCurrentWidget(self, tab: QWidget) -> None:
        """Make the given tab current."""
        self.setCurrentIndex(self.indexOf(tab))

    def addTab(self, page, icon_or_text, text_or_empty=None):
        """Add a tab at the end.

        See insertTab for the arguments.

        Return:
            The index of the newly added tab.
        """
        return self.insertTab(
            len(self._tabs), page, icon_or_text, text_or_empty)

    def insertTab(self, idx, page, icon_or_text, text_or_empty=None):
        """Insert a tab, using our own text setting logic.

        This mirrors the two QTabWidget::insertTab overloads:
            - int index, QWidget * page, const QIcon & icon,
              const QString & label
            - int index, QWidget * page, const QString & label

        This means we'll get different arguments based on the chosen overload.

        Args:
            idx: Where to insert the widget. If out of range, it's appended.
            page: The QWidget to add.
            icon_or_text: Either the QIcon to add or the label.
            text_or_empty: Either the label or None.

        Return:
            The index of the newly added tab.
        """
        if text_or_empty is None:
            icon = QIcon()
            text = icon_or_text
        else:
            icon = icon_or_text
            text = text_or_empty

        if not 0 <= idx <= len(self._tabs):
            idx = len(self._tabs)

        self._view_host.add_view(page)
        # The bar emits currentChanged, so our list must be up to date.
        self._tabs.insert(idx, page)
        self._bar.insertTab(idx, icon, '')
        self.update_tab_titles()
        self.set_page_title(idx, text)
        return idx

    def removeTab(self, idx: int) -> None:
        """Remove the tab at the given index.

        Like QTabWidget::removeTab, this neither destroys nor reparents the
        tab widget.
        """
        if not 0 <= idx < len(self._tabs):
            return
        tab = self._tabs[idx]
        # Before the bar selects another tab, so the survivor of the pair is
        # shown alone whichever one that is.
        self.unpair(tab)
        del self._tabs[idx]
        self._bar.removeTab(idx)
        self.update_tab_titles()

    @pyqtSlot(int, int)
    def _on_tab_moved(self, from_idx: int, to_idx: int) -> None:
        """Keep our tab list in the same order as the tab bar."""
        tab = self._tabs.pop(from_idx)
        self._tabs.insert(to_idx, tab)
        self.unpair(tab)

    @pyqtSlot(int)
    def _on_bar_current_changed(self, index: int) -> None:
        """Show the new current tab and notify QTabWidget-style listeners."""
        self.update_display()
        self.currentChanged.emit(index)

    @pyqtSlot()
    def update_display(self) -> None:
        """Show the current tab, together with its partner if it has one.

        A tab in page full screen is shown alone, so the page fills the window.
        """
        tab = self.currentWidget()
        pair = self.pair_of(tab)
        if tab is None:
            self._view_host.show_views([])
        elif pair is None or tab.data.fullscreen:
            self._view_host.show_views([tab], focus=tab)
        else:
            self._view_host.show_pair(pair, focus=tab)

    def pairs(self) -> list[viewhost.ViewPair]:
        """Get all tab pairs of this window."""
        return list(self._pairs)

    def pair_of(self, tab: QWidget | None) -> viewhost.ViewPair | None:
        """Get the pair the given tab is a member of, if any."""
        for pair in self._pairs:
            if pair.contains(tab):
                return pair
        return None

    def check_pairable(self, tab: browsertab.AbstractTab) -> None:
        """Check that a tab can become part of a new pair.

        Raises ValueError with a message for the user if not.
        """
        if tab.data.pinned:
            raise ValueError("Can't split a pinned tab")
        if self.pair_of(tab) is not None:
            raise ValueError("The tab is already part of a split, "
                             "use :split-close first")

    def pair_tabs(
            self,
            first: browsertab.AbstractTab,
            second: browsertab.AbstractTab,
            orientation: Qt.Orientation,
            ratio: float = 0.5,
    ) -> viewhost.ViewPair:
        """Show two tabs together whenever one of them is current.

        If the tabs are already paired with each other, only the orientation
        changes.

        Args:
            first: The tab shown left/top.
            second: The tab shown right/bottom.
            orientation: Horizontal for left/right, Vertical for top/bottom.
            ratio: The fraction of the space for the first tab.

        Raises ValueError with a message for the user if the tabs can't be
        paired.
        """
        if first is second:
            raise ValueError("Can't split a tab with itself")

        pair = self.pair_of(first)
        if pair is not None and pair.contains(second):
            pair.orientation = orientation
        else:
            self.check_pairable(first)
            self.check_pairable(second)
            pair = viewhost.ViewPair(first, second, orientation, ratio)
            self._pairs.append(pair)
            log.webview.debug(f"Paired {first!r} with {second!r}")
        self.update_display()
        return pair

    def unpair(self, tab: QWidget | None) -> bool:
        """Dissolve the pair of the given tab, keeping both tabs open.

        Return:
            True if there was a pair, False otherwise.
        """
        pair = self.pair_of(tab)
        if pair is None:
            return False
        log.webview.debug(f"Dissolving pair of {tab!r}")
        self._pairs.remove(pair)
        self.update_display()
        return True

    @pyqtSlot('QWidget*', 'QWidget*')
    def _on_focus_changed(self, _old: QWidget | None, new: QWidget | None) -> None:
        """Select the partner of the current tab when focus moves into it.

        Commands apply to the current tab, so a click into the other half of a
        pair has to select it before a command can run.

        This can't loop: it only reacts to focus in the partner of the current
        tab, and selecting that tab moves focus to it. ViewHost also focuses
        the current tab before hiding the old ones, so Qt never moves focus
        into the partner on its own.
        """
        current = self.currentWidget()
        pair = self.pair_of(current)
        if current is None or pair is None or new is None:
            return
        other = pair.other(current)
        # A hidden partner (current tab in full screen) can still get focus.
        if other.isVisible() and (new is other or other.isAncestorOf(new)):
            self.setCurrentWidget(other)

    def tab_bar(self) -> "TabBar":
        """Get the TabBar for this TabWidget."""
        bar = self.tabBar()
        assert isinstance(bar, TabBar), bar
        return bar

    def _tab_by_idx(self, idx: int) -> browsertab.AbstractTab | None:
        """Get the tab at the given index."""
        tab = self.widget(idx)
        if tab is not None:
            assert isinstance(tab, browsertab.AbstractTab), tab
        return tab

    def set_tab_indicator_color(self, idx, color):
        """Set the tab indicator color.

        Args:
            idx: The tab index.
            color: A QColor.
        """
        bar = self.tab_bar()
        bar.set_tab_data(idx, 'indicator-color', color)
        bar.update(bar.tabRect(idx))

    def tab_indicator_color(self, idx):
        """Get the tab indicator color for the given index."""
        return self.tab_bar().tab_indicator_color(idx)

    def set_page_title(self, idx, title):
        """Set the tab title user data."""
        tabbar = self.tab_bar()

        if config.cache['tabs.tooltips']:
            # always show only plain title in tooltips
            tabbar.setTabToolTip(idx, title)

        tabbar.set_tab_data(idx, 'page-title', title)
        self.update_tab_title(idx)

    def page_title(self, idx):
        """Get the tab title user data."""
        return self.tab_bar().page_title(idx)

    def update_tab_title(self, idx, field=None):
        """Update the tab text for the given tab.

        Args:
            idx: The tab index to update.
            field: A field name which was updated. If given, the title
                   is only set if the given field is in the template.
        """
        assert idx != -1
        tab = self._tab_by_idx(idx)
        assert tab is not None
        if tab.data.pinned:
            fmt = config.cache['tabs.title.format_pinned']
        else:
            fmt = config.cache['tabs.title.format']

        if (field is not None and
                (fmt is None or ('{' + field + '}') not in fmt)):
            return

        def right_align(num):
            return str(num).rjust(len(str(self.count())))

        def left_align(num):
            return str(num).ljust(len(str(self.count())))

        bar = self.tab_bar()
        cur_idx = bar.currentIndex()
        if idx == cur_idx:
            rel_idx = left_align(idx + 1) + " "
        else:
            rel_idx = " " + right_align(abs(idx - cur_idx))

        fields = self.get_tab_fields(idx)
        fields['current_title'] = fields['current_title'].replace('&', '&&')
        fields['index'] = idx + 1
        fields['aligned_index'] = right_align(idx + 1)
        fields['relative_index'] = rel_idx

        title = '' if fmt is None else fmt.format(**fields)

        # Only change the tab title if it changes, setting the tab title causes
        # a size recalculation which is slow.
        if bar.tabText(idx) != title:
            bar.setTabText(idx, title)

    def get_tab_fields(self, idx):
        """Get the tab field data."""
        tab = self._tab_by_idx(idx)
        assert tab is not None

        page_title = self.page_title(idx)

        fields: dict[str, Any] = {}
        fields['id'] = tab.tab_id
        fields['current_title'] = page_title
        fields['title_sep'] = ' - ' if page_title else ''
        fields['perc_raw'] = tab.progress()
        fields['backend'] = objects.backend.name
        fields['private'] = ' [Private Mode] ' if tab.is_private else ''
        try:
            if tab.audio.is_muted():
                fields['audio'] = TabWidget.MUTE_STRING
            elif tab.audio.is_recently_audible():
                fields['audio'] = TabWidget.AUDIBLE_STRING
            else:
                fields['audio'] = ''
        except browsertab.WebTabError:
            # Muting is only implemented with QtWebEngine
            fields['audio'] = ''

        if tab.load_status() == usertypes.LoadStatus.loading:
            fields['perc'] = '[{}%] '.format(tab.progress())
        else:
            fields['perc'] = ''

        try:
            url = self.tab_url(idx)
        except qtutils.QtValueError:
            fields['host'] = ''
            fields['current_url'] = ''
            fields['protocol'] = ''
        else:
            fields['host'] = url.host()
            fields['current_url'] = url.toDisplayString()
            fields['protocol'] = url.scheme()

        y = tab.scroller.pos_perc()[1]
        if y <= 0:
            scroll_pos = 'top'
        elif y >= 100:
            scroll_pos = 'bot'
        else:
            scroll_pos = '{:2}%'.format(y)

        fields['scroll_pos'] = scroll_pos
        return fields

    @contextlib.contextmanager
    def _toggle_visibility(self):
        """Toggle visibility while running.

        Every single call to setTabText calls the size hinting functions for
        every single tab, which are slow. Since we know we are updating all
        the tab's titles, we can delay this processing by making the tab
        non-visible. To avoid flickering, disable repaint updates while we
        work.
        """
        bar = self.tab_bar()
        toggle = (self.count() > 10 and
                  not bar.drag_in_progress and
                  bar.isVisible())
        if toggle:
            bar.setUpdatesEnabled(False)
            bar.setVisible(False)

        yield

        if toggle:
            bar.setVisible(True)
            bar.setUpdatesEnabled(True)

    def update_tab_titles(self):
        """Update all texts."""
        with self._toggle_visibility():
            for idx in range(self.count()):
                self.update_tab_title(idx)

    @pyqtSlot(int)
    def _on_current_changed(self, index):
        """Emit the tab_index_changed signal if the current tab changed."""
        self.tab_bar().on_current_changed()
        self.update_tab_titles()
        self.tab_index_changed.emit(index, self.count())

    @pyqtSlot()
    def _on_new_tab_requested(self):
        """Open a new tab."""
        self.new_tab_requested.emit(config.val.url.default_page, False, False)

    def tab_url(self, idx):
        """Get the URL of the tab at the given index.

        Return:
            The tab URL as QUrl.
        """
        tab = self._tab_by_idx(idx)
        url = QUrl() if tab is None else tab.url()
        # It's possible for url to be invalid, but the caller will handle that.
        qtutils.ensure_valid(url)
        return url

    def update_tab_favicon(self, tab: browsertab.AbstractTab) -> None:
        """Update favicon of the given tab."""
        idx = self.indexOf(tab)

        icon = tab.icon() if tab.data.should_show_icon() else QIcon()
        self.setTabIcon(idx, icon)

        if config.val.tabs.tabs_are_windows:
            window = self.window()
            assert window is not None
            window.setWindowIcon(tab.icon())

    def setTabIcon(self, idx: int, icon: QIcon) -> None:
        """Always show tab icons for pinned tabs in some circumstances."""
        tab = self._tab_by_idx(idx)
        if (icon.isNull() and
                config.cache['tabs.favicons.show'] != 'never' and
                config.cache['tabs.pinned.shrink'] and
                not self.tab_bar().vertical and
                tab is not None and tab.data.pinned):
            style = self.style()
            assert style is not None
            icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        self._bar.setTabIcon(idx, icon)


class TabBar(QTabBar):

    """Custom tab bar with our own style.

    FIXME: Dragging tabs doesn't look as nice as it does in QTabBar.  However,
    fixing this would be a lot of effort, so we'll postpone it until we're
    reimplementing drag&drop for other reasons.

    https://github.com/qutebrowser/qutebrowser/issues/126

    Attributes:
        vertical: When the tab bar is currently vertical.
        win_id: The window ID this TabBar belongs to.

    Signals:
        new_tab_requested: Emitted when a new tab is requested.
    """

    STYLESHEET = """
        TabBar {
            font: {{ conf.fonts.tabs.unselected }};
            background-color: {{ conf.colors.tabs.bar.bg }};
        }

        TabBar::tab:selected {
            font: {{ conf.fonts.tabs.selected }};
        }
    """

    new_tab_requested = pyqtSignal()

    def __init__(self, win_id, parent=None):
        super().__init__(parent)
        self._win_id = win_id
        self._our_style = TabBarStyle()
        self.setStyle(self._our_style)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vertical = False
        self._auto_hide_timer = usertypes.Timer()
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.maybe_hide)
        self._on_show_switching_delay_changed()
        self.setAutoFillBackground(True)
        # FIXME:mypy Is it a mypy bug that we need to specify bool here?
        # Otherwise, we get "Cannot determine type of "drag_in_progress" in
        # TabWidget._toggle_visibility below.
        self.drag_in_progress: bool = False
        stylesheet.set_register(self)
        self.ensurePolished()
        config.instance.changed.connect(self._on_config_changed)
        self._set_icon_size()
        QTimer.singleShot(0, self.maybe_hide)
        self._minimum_tab_size_hint_helper = functools.lru_cache(maxsize=2**9)(
            self._minimum_tab_size_hint_helper_uncached
        )
        debugcachestats.register(name=f'tab width cache (win_id={win_id})')(
            self._minimum_tab_size_hint_helper
        )
        self._minimum_tab_height = functools.lru_cache(maxsize=1)(
            self._minimum_tab_height_uncached
        )

    def __repr__(self):
        return utils.get_repr(self, count=self.count())

    def _tab_widget(self):
        """Get the TabWidget we're in."""
        parent = self.parent()
        assert isinstance(parent, TabWidget), parent
        return parent

    def _current_tab(self):
        """Get the current tab object."""
        return self._tab_widget().currentWidget()

    @pyqtSlot(str)
    def _on_config_changed(self, option: str) -> None:
        if option.startswith('fonts.tabs.'):
            self.ensurePolished()
            self._set_icon_size()
        elif option == 'tabs.favicons.scale':
            self._set_icon_size()
        elif option == 'tabs.show_switching_delay':
            self._on_show_switching_delay_changed()
        elif option == 'tabs.show':
            self.maybe_hide()

        if option.startswith('colors.tabs.'):
            self.update()

        # Clear tab size caches when appropriate
        if option in ["tabs.indicator.padding",
                      "tabs.padding",
                      "tabs.indicator.width",
                      "tabs.min_width",
                      "tabs.pinned.shrink",
                      "fonts.tabs.selected",
                      "fonts.tabs.unselected"]:
            self._minimum_tab_size_hint_helper.cache_clear()
            self._minimum_tab_height.cache_clear()

    def _on_show_switching_delay_changed(self):
        """Set timer interval when tabs.show_switching_delay got changed."""
        self._auto_hide_timer.setInterval(config.val.tabs.show_switching_delay)

    def on_current_changed(self):
        """Show tab bar when current tab got changed."""
        self.maybe_hide()  # for fullscreen tabs
        if config.val.tabs.show == 'switching':
            self.show()
            self._auto_hide_timer.start()

    @pyqtSlot()
    def maybe_hide(self):
        """Hide the tab bar if needed."""
        show = config.val.tabs.show
        tab = self._current_tab()
        if (show in ['never', 'switching'] or
                (show == 'multiple' and self.count() == 1) or
                (tab and tab.data.fullscreen)):
            self.hide()
        else:
            self.show()

    def set_tab_data(self, idx, key, value):
        """Set tab data as a dictionary."""
        if not 0 <= idx < self.count():
            raise IndexError("Tab index ({}) out of range ({})!".format(
                idx, self.count()))
        data = self.tabData(idx)
        if data is None:
            data = {}
        data[key] = value
        self.setTabData(idx, data)

    def tab_data(self, idx, key):
        """Get tab data for a given key."""
        if not 0 <= idx < self.count():
            raise IndexError("Tab index ({}) out of range ({})!".format(
                idx, self.count()))
        data = self.tabData(idx)
        if data is None:
            data = {}
        return data[key]

    def tab_indicator_color(self, idx):
        """Get the tab indicator color for the given index."""
        try:
            return self.tab_data(idx, 'indicator-color')
        except KeyError:
            return QColor()

    def page_title(self, idx):
        """Get the tab title user data.

        Args:
            idx: The tab index to get the title for.
        """
        try:
            return self.tab_data(idx, 'page-title')
        except KeyError:
            return ''

    def refresh(self):
        """Properly repaint the tab bar and relayout tabs."""
        # This is a horrible hack, but we need to do this so the underlying Qt
        # code sets layoutDirty so it actually relayouts the tabs.
        self.setIconSize(self.iconSize())

    def _set_icon_size(self):
        """Set the tab bar favicon size."""
        size = self.fontMetrics().height() - 2
        size = int(size * config.val.tabs.favicons.scale)
        self.setIconSize(QSize(size, size))

    def mouseReleaseEvent(self, e):
        """Override mouseReleaseEvent to know when drags stop."""
        self.drag_in_progress = False
        super().mouseReleaseEvent(e)

    def mousePressEvent(self, e):
        """Override mousePressEvent to close tabs if configured.

        Also keep track of if we are currently in a drag."""
        self.drag_in_progress = True
        button = config.val.tabs.close_mouse_button
        if (e.button() == Qt.MouseButton.RightButton and button == 'right' or
                e.button() == Qt.MouseButton.MiddleButton and button == 'middle'):
            e.accept()
            idx = self.tabAt(e.pos())
            if idx == -1:
                action = config.val.tabs.close_mouse_button_on_bar
                if action == 'ignore':
                    return
                elif action == 'new-tab':
                    self.new_tab_requested.emit()
                    return
                elif action == 'close-current':
                    idx = self.currentIndex()
                elif action == 'close-last':
                    idx = self.count() - 1
            self.tabCloseRequested.emit(idx)
            return
        super().mousePressEvent(e)

    def minimumTabSizeHint(self, index: int, ellipsis: bool = True) -> QSize:
        """Set the minimum tab size to indicator/icon/... text.

        Args:
            index: The index of the tab to get a size hint for.
            ellipsis: Whether to use ellipsis to calculate width
                      instead of the tab's text.
                      Forced to False for pinned tabs.
        Return:
            A QSize of the smallest tab size we can make.
        """
        icon = self.tabIcon(index)
        if icon.isNull():
            icon_width = 0
        else:
            icon_width = min(
                icon.actualSize(self.iconSize()).width(),
                self.iconSize().width()) + TabBarStyle.ICON_PADDING

        pinned = self._tab_pinned(index)
        if not self.vertical and pinned and config.val.tabs.pinned.shrink:
            # Never consider ellipsis an option for horizontal pinned tabs
            ellipsis = False
        return self._minimum_tab_size_hint_helper(self.tabText(index),
                                                  icon_width, ellipsis,
                                                  pinned)

    def _minimum_tab_size_hint_helper_uncached(self, tab_text: str,
                                               icon_width: int,
                                               ellipsis: bool, pinned: bool) -> QSize:
        """Helper function to cache tab results.

        Config values accessed in here should be added to _on_config_changed to
        ensure cache is flushed when needed.
        """
        text = '\u2026' if ellipsis else tab_text
        # Don't ever shorten if text is shorter than the ellipsis

        def _text_to_width(text):
            # Calculate text width taking into account qt mnemonics
            return self.fontMetrics().size(Qt.TextFlag.TextShowMnemonic, text).width()
        text_width = min(_text_to_width(text),
                         _text_to_width(tab_text))
        padding = config.cache['tabs.padding']
        indicator_width = config.cache['tabs.indicator.width']
        indicator_padding = config.cache['tabs.indicator.padding']
        padding_h = padding.left + padding.right

        # Only add padding if indicator exists
        if indicator_width != 0:
            padding_h += indicator_padding.left + indicator_padding.right
        height = self._minimum_tab_height()
        width = (text_width + icon_width +
                 padding_h + indicator_width)
        min_width = config.cache['tabs.min_width']
        if (not self.vertical and min_width > 0 and
                not pinned or not config.cache['tabs.pinned.shrink']):
            width = max(min_width, width)
        return QSize(width, height)

    def _minimum_tab_height_uncached(self):
        padding = config.cache['tabs.padding']
        return self.fontMetrics().height() + padding.top + padding.bottom

    def _tab_pinned(self, index: int) -> bool:
        """Return True if tab is pinned."""
        if not 0 <= index < self.count():
            raise IndexError("Tab index ({}) out of range ({})!".format(
                index, self.count()))

        widget = self._tab_widget().widget(index)
        if widget is None:
            # This could happen when Qt calls tabSizeHint while initializing
            # tabs.
            return False
        return widget.data.pinned

    def tabSizeHint(self, index: int) -> QSize:
        """Override tabSizeHint to customize qb's tab size.

        https://wiki.python.org/moin/PyQt/Customising%20tab%20bars

        Args:
            index: The index of the tab.

        Return:
            A QSize.
        """
        if self.count() == 0:
            # This happens on startup on macOS.
            # We return it directly rather than setting `size' because we don't
            # want to ensure it's valid in this special case.
            return QSize()

        height = self._minimum_tab_height()
        if self.vertical:
            confwidth = str(config.cache['tabs.width'])
            if confwidth.endswith('%'):
                main_window = objreg.get('main-window', scope='window',
                                         window=self._win_id)
                perc = int(confwidth.rstrip('%'))
                width = main_window.width() * perc // 100
            else:
                width = int(confwidth)
            size = QSize(width, height)
        else:
            if config.cache['tabs.pinned.shrink'] and self._tab_pinned(index):
                # Give pinned tabs the minimum size they need to display their
                # titles, let Qt handle scaling it down if we get too small.
                width = self.minimumTabSizeHint(index, ellipsis=False).width()
            else:
                # Request as much space as possible so we fill the tabbar, let
                # Qt shrink us down. If for some reason (tests, bugs)
                # self.width() gives 0, use a sane min of 10 px
                width = max(self.width(), 10)
                max_width = config.cache['tabs.max_width']
                if max_width > 0:
                    width = min(max_width, width)
            size = QSize(width, height)
        qtutils.ensure_valid(size)
        return size

    def initStyleOption(self, opt, idx):
        """Override QTabBar.initStyleOption().

        Used to calculate styling clues from a widget for the GUI layer.
        """
        super().initStyleOption(opt, idx)

        # Re-do the text elision that the base QTabBar does, but using a text
        # rectangle computed by out TabBarStyle. With Qt6 the base class ends
        # up using QCommonStyle directly for that which has a different opinion
        # of how vertical tabs should work.
        text_rect = self._our_style.subElementRect(
            QStyle.SubElement.SE_TabBarTabText,
            opt,
            self,
        )
        opt.text = self.fontMetrics().elidedText(
            self.tabText(idx),
            self.elideMode(),
            text_rect.width(),
            Qt.TextFlag.TextShowMnemonic,
        )

    def paintEvent(self, event):
        """Override paintEvent to draw the tabs like we want to."""
        p = QStylePainter(self)
        selected = self.currentIndex()
        for idx in range(self.count()):
            if not event.region().intersects(self.tabRect(idx)):
                # Don't repaint if we are outside the requested region
                continue

            tab = QStyleOptionTab()
            self.initStyleOption(tab, idx)

            setting = 'colors.tabs'
            if self._tab_pinned(idx):
                setting += '.pinned'
            if idx == selected:
                setting += '.selected'
            setting += '.odd' if (idx + 1) % 2 else '.even'

            tab.palette.setColor(QPalette.ColorRole.Window,
                                 config.cache[setting + '.bg'])
            tab.palette.setColor(QPalette.ColorRole.WindowText,
                                 config.cache[setting + '.fg'])

            indicator_color = self.tab_indicator_color(idx)
            tab.palette.setColor(QPalette.ColorRole.Base, indicator_color)
            p.drawControl(QStyle.ControlElement.CE_TabBarTab, tab)

    def tabInserted(self, idx):
        """Update visibility when a tab was inserted."""
        super().tabInserted(idx)
        self.maybe_hide()

    def tabRemoved(self, idx):
        """Update visibility when a tab was removed."""
        super().tabRemoved(idx)
        self.maybe_hide()

    def wheelEvent(self, e):
        """Override wheelEvent to make the action configurable.

        Args:
            e: The QWheelEvent
        """
        if config.val.tabs.mousewheel_switching:
            if utils.is_mac:
                # WORKAROUND for this not being customizable until Qt 6:
                # https://codereview.qt-project.org/c/qt/qtbase/+/327746
                index = self.currentIndex()
                if index == -1:
                    return
                dx = e.angleDelta().x()
                dy = e.angleDelta().y()
                delta = dx if abs(dx) > abs(dy) else dy
                offset = -1 if delta > 0 else 1
                index += offset
                if 0 <= index < self.count():
                    self.setCurrentIndex(index)
            else:
                super().wheelEvent(e)
        else:
            tabbed_browser = objreg.get('tabbed-browser', scope='window',
                                        window=self._win_id)
            tabbed_browser.wheelEvent(e)


@dataclasses.dataclass
class Layouts:

    """Layout information for tab.

    Used by TabBarStyle._tab_layout().
    """

    text: QRect
    icon: QRect
    indicator: QRect


class TabBarStyle(QProxyStyle):

    """Qt style used by TabBar to fix some issues with the default one.

    This fixes the following things:
        - Remove the focus rectangle Ubuntu draws on tabs.
        - Force text to be left-aligned even though Qt has "centered"
          hardcoded.
    """

    ICON_PADDING = 4

    def __init__(self, style=None):
        # "useless" override as WORKAROUND for
        # https://www.riverbankcomputing.com/pipermail/pyqt/2023-September/045510.html
        super().__init__(style)

    def _base_style(self) -> QStyle:
        """Get the base style."""
        style = self.baseStyle()
        assert style is not None
        return style

    def _draw_indicator(self, layouts, opt, p):
        """Draw the tab indicator.

        Args:
            layouts: The layouts from _tab_layout.
            opt: QStyleOption from drawControl.
            p: QPainter from drawControl.
        """
        color = opt.palette.base().color()
        rect = layouts.indicator
        if color.isValid() and rect.isValid():
            p.fillRect(rect, color)

    def _draw_icon(self, layouts, opt, p):
        """Draw the tab icon.

        Args:
            layouts: The layouts from _tab_layout.
            opt: QStyleOption
            p: QPainter
        """
        qtutils.ensure_valid(layouts.icon)
        icon_mode = (QIcon.Mode.Normal if opt.state & QStyle.StateFlag.State_Enabled
                     else QIcon.Mode.Disabled)
        icon_state = (QIcon.State.On if opt.state & QStyle.StateFlag.State_Selected
                      else QIcon.State.Off)
        icon = opt.icon.pixmap(opt.iconSize, icon_mode, icon_state)
        self._base_style().drawItemPixmap(p, layouts.icon, Qt.AlignmentFlag.AlignCenter, icon)

    def drawControl(self, element, opt, p, widget=None):
        """Override drawControl to draw odd tabs in a different color.

        Draws the given element with the provided painter with the style
        options specified by option.

        Args:
            element: ControlElement
            opt: QStyleOption
            p: QPainter
            widget: QWidget
        """
        if element not in [QStyle.ControlElement.CE_TabBarTab, QStyle.ControlElement.CE_TabBarTabShape,
                           QStyle.ControlElement.CE_TabBarTabLabel]:
            # Let the real style draw it.
            self._base_style().drawControl(element, opt, p, widget)
            return

        layouts = self._tab_layout(opt)
        if layouts is None:
            log.misc.warning("Could not get layouts for tab!")
            return

        if element == QStyle.ControlElement.CE_TabBarTab:
            # We override this so we can control TabBarTabShape/TabBarTabLabel.
            self.drawControl(QStyle.ControlElement.CE_TabBarTabShape, opt, p, widget)
            self.drawControl(QStyle.ControlElement.CE_TabBarTabLabel, opt, p, widget)
        elif element == QStyle.ControlElement.CE_TabBarTabShape:
            p.fillRect(opt.rect, opt.palette.window())
            self._draw_indicator(layouts, opt, p)
            # We use QCommonStyle rather than self.baseStyle() here because we don't want
            # any sophisticated drawing.
            QCommonStyle.drawControl(self, QStyle.ControlElement.CE_TabBarTabShape, opt, p, widget)
        elif element == QStyle.ControlElement.CE_TabBarTabLabel:
            if not opt.icon.isNull() and layouts.icon.isValid():
                self._draw_icon(layouts, opt, p)
            alignment = (config.cache['tabs.title.alignment'] |
                         Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextHideMnemonic)
            self._base_style().drawItemText(
                p,
                layouts.text,
                int(alignment),
                opt.palette,
                bool(opt.state & QStyle.StateFlag.State_Enabled),
                opt.text,
                QPalette.ColorRole.WindowText
            )
        else:
            raise ValueError("Invalid element {!r}".format(element))

    def pixelMetric(self, metric, option=None, widget=None):
        """Override pixelMetric to not shift the selected tab.

        Args:
            metric: PixelMetric
            option: const QStyleOption *
            widget: const QWidget *

        Return:
            An int.
        """
        if metric in [QStyle.PixelMetric.PM_TabBarTabShiftHorizontal,
                      QStyle.PixelMetric.PM_TabBarTabShiftVertical,
                      QStyle.PixelMetric.PM_TabBarTabHSpace,
                      QStyle.PixelMetric.PM_TabBarTabVSpace,
                      QStyle.PixelMetric.PM_TabBarScrollButtonWidth]:
            return 0
        else:
            return self._base_style().pixelMetric(metric, option, widget)

    def subElementRect(self, sr, opt, widget=None):
        """Override subElementRect to use our own _tab_layout implementation.

        Args:
            sr: SubElement
            opt: QStyleOption
            widget: QWidget

        Return:
            A QRect.
        """
        if sr == QStyle.SubElement.SE_TabBarTabText:
            layouts = self._tab_layout(opt)
            if layouts is None:
                log.misc.warning("Could not get layouts for tab!")
                return QRect()
            return layouts.text
        elif sr in [QStyle.SubElement.SE_TabWidgetTabBar,
                    QStyle.SubElement.SE_TabBarScrollLeftButton]:
            # Handling SE_TabBarScrollLeftButton so the left scroll button is
            # aligned properly. Otherwise, empty space will be shown after the
            # last tab even though the button width is set to 0
            #
            # Need to use QCommonStyle here because we also use it to render
            # element in drawControl(); otherwise, we may get bit by
            # style differences...
            return QCommonStyle.subElementRect(self, sr, opt, widget)
        else:
            return self._base_style().subElementRect(sr, opt, widget)

    def _tab_layout(self, opt):
        """Compute the text/icon rect from the opt rect.

        This is based on Qt's QCommonStylePrivate::tabLayout
        (qtbase/src/widgets/styles/qcommonstyle.cpp) as we can't use the
        private implementation.

        Args:
            opt: QStyleOptionTab

        Return:
            A Layout object with two QRects.
        """
        padding = config.cache['tabs.padding']
        indicator_padding = config.cache['tabs.indicator.padding']

        text_rect = QRect(opt.rect)
        if not text_rect.isValid():
            # This happens sometimes according to crash reports, but no idea
            # why...
            return None

        text_rect.adjust(padding.left, padding.top, -padding.right,
                         -padding.bottom)

        indicator_width = config.cache['tabs.indicator.width']
        if indicator_width == 0:
            indicator_rect = QRect()
        else:
            indicator_rect = QRect(opt.rect)
            qtutils.ensure_valid(indicator_rect)
            indicator_rect.adjust(padding.left + indicator_padding.left,
                                  padding.top + indicator_padding.top,
                                  0,
                                  -(padding.bottom + indicator_padding.bottom))
            indicator_rect.setWidth(indicator_width)

            text_rect.adjust(indicator_width + indicator_padding.left +
                             indicator_padding.right, 0, 0, 0)

        icon_rect = self._get_icon_rect(opt, text_rect)
        if icon_rect.isValid():
            text_rect.adjust(
                icon_rect.width() + TabBarStyle.ICON_PADDING, 0, 0, 0)

        text_rect = self._base_style().visualRect(opt.direction, opt.rect, text_rect)
        return Layouts(text=text_rect, icon=icon_rect,
                       indicator=indicator_rect)

    def _get_icon_rect(self, opt, text_rect):
        """Get a QRect for the icon to draw.

        Args:
            opt: QStyleOptionTab
            text_rect: The QRect for the text.

        Return:
            A QRect.
        """
        icon_size = opt.iconSize
        if not icon_size.isValid():
            icon_extent = self.pixelMetric(QStyle.PixelMetric.PM_SmallIconSize)
            icon_size = QSize(icon_extent, icon_extent)
        icon_mode = (QIcon.Mode.Normal if opt.state & QStyle.StateFlag.State_Enabled
                     else QIcon.Mode.Disabled)
        icon_state = (QIcon.State.On if opt.state & QStyle.StateFlag.State_Selected
                      else QIcon.State.Off)
        # reserve space for favicon when tab bar is vertical (issue #1968)
        position = config.cache['tabs.position']
        if (position in [QTabWidget.TabPosition.East, QTabWidget.TabPosition.West] and
                config.cache['tabs.favicons.show'] != 'never'):
            tab_icon_size = icon_size
        else:
            actual_size = opt.icon.actualSize(icon_size, icon_mode, icon_state)
            tab_icon_size = QSize(
                min(actual_size.width(), icon_size.width()),
                min(actual_size.height(), icon_size.height()))

        icon_top = text_rect.center().y() + 1 - tab_icon_size.height() // 2
        icon_rect = QRect(QPoint(text_rect.left(), icon_top), tab_icon_size)
        icon_rect = self._base_style().visualRect(opt.direction, opt.rect, icon_rect)
        return icon_rect
