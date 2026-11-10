Feature: Paired tabs
    Two tabs of a window can be shown side by side. Both stay normal tabs.

    Background:
        Given I clean up open tabs
        And I set tabs.tabs_are_windows to false
        And I clear the log

    Scenario: Opening a background tab shows only the current tab
        When I open data/numbers/1.txt
        And I run :open -b http://localhost:(port)/data/numbers/2.txt
        And I wait until data/numbers/2.txt is loaded
        Then the visible tabs should be 1

    # Creating a pair

    Scenario: Pairing the current tab with a new tab
        When I open data/numbers/1.txt
        And I run :vsplit
        Then data/numbers/1.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            - data/numbers/1.txt
            """
        And tabs 1 and 2 should be paired left-right
        And the visible tabs should be 1 and 2

    Scenario: Pairing with an existing tab
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I open data/numbers/3.txt in a new tab
        And I run :vsplit 1
        Then the following tabs should be open:
            """
            - data/numbers/1.txt
            - data/numbers/2.txt
            - data/numbers/3.txt (active)
            """
        And tabs 3 and 1 should be paired left-right
        And the visible tabs should be 1 and 3

    Scenario: Pairing with an existing tab top and bottom
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I run :hsplit 1
        Then tabs 2 and 1 should be paired top-bottom
        And the visible tabs should be 1 and 2

    Scenario: Changing the orientation of a pair
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I run :hsplit
        Then tabs 1 and 2 should be paired top-bottom
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            - data/numbers/1.txt
            """

    # Errors

    Scenario: Pairing with a tab which doesn't exist
        When I open data/numbers/1.txt
        And I run :vsplit 5
        Then the error "There's no tab with index 5!" should be shown

    Scenario: Pairing a tab with itself
        When I open data/numbers/1.txt
        And I run :vsplit 1
        Then the error "Can't split a tab with itself" should be shown

    Scenario: Pairing a pinned tab without index doesn't open a tab
        When I open data/numbers/1.txt
        And I run :tab-pin
        And I run :vsplit
        Then the error "Can't split a pinned tab" should be shown
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active) (pinned)
            """

    Scenario: Pairing a tab which is in another pair
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I open data/numbers/3.txt in a new tab
        And I run :vsplit 2
        And I run :vsplit 1
        Then the error "The tab is already part of a split, use :split-close first" should be shown
        And tabs 3 and 2 should be paired left-right

    Scenario: Pairing tabs when using windows as tabs
        When I open data/numbers/1.txt
        And I set tabs.tabs_are_windows to true
        And I run :vsplit
        Then the error "Can't split when using windows as tabs" should be shown

    Scenario: Closing a pair which doesn't exist
        When I open data/numbers/1.txt
        And I run :split-close
        Then the error "The current tab is not in a split" should be shown

    Scenario: Focusing a pair which doesn't exist
        When I open data/numbers/1.txt
        And I run :split-focus
        Then the error "The current tab is not in a split" should be shown

    # Commands act on the selected tab

    Scenario: Commands act on the selected tab
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I run :open http://localhost:(port)/data/numbers/3.txt
        Then data/numbers/3.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/3.txt (active)
            - data/numbers/1.txt
            """

    Scenario: Commands act on the other tab after focusing it
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I run :split-focus
        And I run :open http://localhost:(port)/data/numbers/3.txt
        Then data/numbers/3.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt
            - data/numbers/3.txt (active)
            """
        And the visible tabs should be 1 and 2

    Scenario: Each tab has its own history
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I run :split-focus
        And I open data/numbers/3.txt
        And I run :back
        And I wait until data/numbers/1.txt is loaded
        Then the session should look like:
            """
            windows:
            - tabs:
              - history:
                - url: about:blank
                - active: true
                  url: http://localhost:*/data/numbers/1.txt
              - active: true
                history:
                - url: http://localhost:*/data/numbers/1.txt
                  active: true
                - url: http://localhost:*/data/numbers/3.txt
            """
        And tabs 1 and 2 should be paired left-right

    Scenario: Clicking into the other tab selects it
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I click into tab 2
        And I run :open http://localhost:(port)/data/numbers/3.txt
        Then data/numbers/3.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/1.txt
            - data/numbers/3.txt (active)
            """
        And the visible tabs should be 1 and 2

    # Unrelated tabs

    Scenario: Selecting an unrelated tab and returning
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I open data/numbers/3.txt in a new tab
        Then the visible tabs should be 3
        When I run :tab-focus 1
        Then the visible tabs should be 1 and 2
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            - data/numbers/1.txt
            - data/numbers/3.txt
            """
        And tabs 1 and 2 should be paired left-right

    Scenario: Opening a background tab keeps the pair
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I open data/numbers/3.txt in a new tab
        And I run :tab-focus 1
        And I run :open -b http://localhost:(port)/data/numbers/4.txt
        And I wait until data/numbers/4.txt is loaded
        Then the visible tabs should be 1 and 2
        And the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            - data/numbers/1.txt
            - data/numbers/3.txt
            - data/numbers/4.txt
            """
        And tabs 1 and 2 should be paired left-right

    Scenario: Full screen shows only the page which requested it
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And the current page enters full screen
        Then the visible tabs should be 1
        When the current page leaves full screen
        Then the visible tabs should be 1 and 2
        And tabs 1 and 2 should be paired left-right

    # Live pages

    Scenario: Pairing, selecting and unpairing doesn't reload or reparent pages
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I record the loads and parents of all pages
        And I run :vsplit 1
        And I run :split-focus
        And I run :hsplit
        And I run :tab-focus 1
        And I run :split-close
        Then no page should have loaded or changed its parent

    # Ending a pair

    Scenario: Closing a pair
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I run :split-close
        And I run :open http://localhost:(port)/data/numbers/3.txt
        Then data/numbers/3.txt should be loaded
        And the following tabs should be open:
            """
            - data/numbers/3.txt (active)
            - data/numbers/1.txt
            """
        And the visible tabs should be 1
        And no tabs should be paired

    Scenario: Closing the current tab of a pair
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I run :vsplit 1
        And I run :tab-close
        Then the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            """
        And the visible tabs should be 1
        And no tabs should be paired

    Scenario: Pinning a tab of a pair
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I run :tab-pin
        Then the message "Closed the split because the tab was pinned." should be shown
        And the visible tabs should be 1
        And no tabs should be paired

    Scenario: Moving a tab of a pair
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I run :tab-move +
        Then the following tabs should be open:
            """
            - data/numbers/1.txt
            - data/numbers/1.txt (active)
            """
        And the visible tabs should be 2
        And no tabs should be paired

    Scenario: Undoing the close of a tab of a pair
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I run :vsplit 1
        And I run :tab-close
        And I run :undo
        Then the following tabs should be open:
            """
            - data/numbers/1.txt
            - data/numbers/2.txt (active)
            """
        And no tabs should be paired

    # Sessions

    Scenario: Saving and loading a pair
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I open data/numbers/3.txt in a new tab
        And I run :vsplit 1
        And I run :session-save pair_session
        And I run :session-load pair_session
        And I wait until data/numbers/3.txt is loaded
        And I run :window-only
        And I wait for "removed: main-window" in the log
        Then the following tabs should be open:
            """
            - data/numbers/1.txt
            - data/numbers/2.txt
            - data/numbers/3.txt (active)
            """
        And tabs 3 and 1 should be paired left-right
        And the visible tabs should be 1 and 3

    Scenario: Loading a session without pairs
        When I open data/numbers/1.txt
        And I open data/numbers/2.txt in a new tab
        And I run :session-save plain_session
        And I run :session-load plain_session
        And I wait until data/numbers/2.txt is loaded
        And I run :window-only
        And I wait for "removed: main-window" in the log
        Then the following tabs should be open:
            """
            - data/numbers/1.txt
            - data/numbers/2.txt (active)
            """
        And no tabs should be paired
        And the visible tabs should be 2

    Scenario: Loading a session with a malformed pair
        When I open data/numbers/1.txt
        And I run :vsplit
        And I wait until data/numbers/1.txt is loaded
        And I run :session-save broken_session
        And I replace "left-right" by "diagonal" in the "broken_session" session file
        And I run :session-load broken_session
        And I wait until data/numbers/1.txt is loaded
        And I run :window-only
        And I wait for "removed: main-window" in the log
        Then the following tabs should be open:
            """
            - data/numbers/1.txt (active)
            - data/numbers/1.txt
            """
        And no tabs should be paired
        And the visible tabs should be 1
