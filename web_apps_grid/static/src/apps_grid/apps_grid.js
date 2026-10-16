import { Component, onMounted, useExternalListener, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

import {
    groupApps,
    neighbourInDirection,
    pickApps,
    recentApps,
    searchMenus,
} from "./apps_grid_utils";

export class AppsGrid extends Component {
    static template = "web_apps_grid.AppsGrid";
    static props = {
        prefs: Object,
        close: Function,
    };

    setup() {
        this.menuService = useService("menu");
        this.root = useRef("root");
        this.searchInput = useRef("search");
        this.state = useState({ query: "", dragId: null });
        this.prefsData = useState(this.props.prefs.data);
        useExternalListener(window, "keydown", this.onWindowKeydown, { capture: true });
        onMounted(() => this.searchInput.el?.focus());
    }

    get apps() {
        return this.menuService.getApps();
    }

    get currentApp() {
        return this.menuService.getCurrentApp();
    }

    get pinned() {
        return pickApps(this.apps, this.prefsData.pinned);
    }

    get recent() {
        return recentApps(this.apps, this.prefsData);
    }

    get grouped() {
        return this.prefsData.grouped;
    }

    get groups() {
        return this.grouped
            ? groupApps(this.apps)
            : [{ key: "all", label: "", apps: this.apps }];
    }

    get results() {
        return searchMenus(this.menuService, this.apps, this.state.query);
    }

    isPinned(app) {
        return this.prefsData.pinned.includes(app.id);
    }

    pinTitle(app) {
        return this.isPinned(app) ? _t("Unpin") : _t("Pin to the top");
    }

    get groupTitle() {
        return this.grouped ? _t("Show as one grid") : _t("Group by area");
    }

    href(menu) {
        return `/odoo/${menu.actionPath || "action-" + menu.actionID}`;
    }

    iconLetter(app) {
        return (app.name || "?").trim().charAt(0).toUpperCase();
    }

    // ---- actions

    async open(menu, app = menu) {
        this.props.prefs.touch(app.appID || app.id);
        this.props.close();
        await this.menuService.selectMenu(menu);
    }

    onTileClick(ev, menu, app) {
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button === 1) {
            return; // let the browser open the link in a new tab
        }
        ev.preventDefault();
        this.open(menu, app);
    }

    togglePin(ev, app) {
        ev.preventDefault();
        ev.stopPropagation();
        this.props.prefs.togglePin(app.id);
    }

    toggleGrouped() {
        this.props.prefs.setGrouped(!this.grouped);
    }

    onBackdropClick(ev) {
        if (!ev.target.closest(".o_apps_grid_item, .o_apps_grid_toolbar, .o_apps_grid_search")) {
            this.props.close();
        }
    }

    // ---- drag & drop of pinned tiles

    onDragStart(ev, app) {
        this.state.dragId = app.id;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(app.id));
    }

    onDragOver(ev) {
        if (this.state.dragId) {
            ev.preventDefault();
        }
    }

    onDrop(ev, beforeApp) {
        ev.preventDefault();
        if (this.state.dragId && this.state.dragId !== beforeApp?.id) {
            this.props.prefs.movePinned(this.state.dragId, beforeApp?.id);
            }
        this.state.dragId = null;
    }

    onDragEnd() {
        this.state.dragId = null;
    }

    // ---- keyboard

    get focusables() {
        return [...(this.root.el?.querySelectorAll(".o_apps_grid_item") || [])];
    }

    onWindowKeydown(ev) {
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            if (this.state.query) {
                this.state.query = "";
                this.searchInput.el?.focus();
            } else {
                this.props.close();
            }
            return;
        }
        const active = document.activeElement;
        const inSearch = active === this.searchInput.el;
        const items = this.focusables;
        if (ev.key.startsWith("Arrow")) {
            if (inSearch) {
                if (ev.key === "ArrowDown" && items.length) {
                    ev.preventDefault();
                    items[0].focus();
                }
                return;
            }
            if (!items.includes(active)) {
                return;
            }
            ev.preventDefault();
            const next = neighbourInDirection(items, active, ev.key);
            if (next) {
                next.focus();
                next.scrollIntoView({ block: "nearest" });
            } else if (ev.key === "ArrowUp") {
                this.searchInput.el?.focus();
            }
            return;
        }
        if (ev.key === "Enter" && inSearch) {
            ev.preventDefault();
            items[0]?.click();
            return;
        }
        // Typing anywhere goes to the search box.
        if (
            !inSearch &&
            ev.key.length === 1 &&
            !ev.ctrlKey &&
            !ev.metaKey &&
            !ev.altKey &&
            ev.key !== " "
        ) {
            this.searchInput.el?.focus();
        }
    }
}
