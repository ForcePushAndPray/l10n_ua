import { useState } from "@odoo/owl";
import { useBus } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { WebClient } from "@web/webclient/webclient";

import { AppsGrid } from "./apps_grid/apps_grid";
import { AppsGridPrefs } from "./apps_grid/apps_grid_utils";

NavBar.components = { ...NavBar.components, AppsGrid };

// The app Odoo opens by itself on /odoo is not one the user chose.
let loadingDefaultApp = false;

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.appsGrid = useState({ open: false });
        this.appsGridPrefs = new AppsGridPrefs(user.userId);
        useBus(this.env.bus, "WEB_APPS_GRID:OPEN", () => this.openAppsGrid());
        // Apps reached any other way (links, breadcrumbs) count as recent too.
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
            if (!loadingDefaultApp) {
                this.appsGridPrefs.touch(this.menuService.getCurrentApp()?.id);
            }
        });
    },

    openAppsGrid() {
        this._closeAppMenuSidebar();
        this.appsGrid.open = true;
    },

    closeAppsGrid() {
        this.appsGrid.open = false;
    },

    toggleAppsGrid() {
        this.appsGrid.open ? this.closeAppsGrid() : this.openAppsGrid();
    },

    // Mobile burger: "All Apps" opens the grid instead of the plain list.
    onAllAppsBtnClick() {
        this.openAppsGrid();
    },
});

// /odoo with no action: Community opens the first app; show the grid over it,
// like a home screen. Esc then lands on a real page, not an empty one.
patch(WebClient.prototype, {
    async _loadDefaultApp() {
        loadingDefaultApp = true;
        let result;
        try {
            result = await super._loadDefaultApp(...arguments);
        } finally {
            loadingDefaultApp = false;
        }
        this.env.bus.trigger("WEB_APPS_GRID:OPEN");
        return result;
    },
});
