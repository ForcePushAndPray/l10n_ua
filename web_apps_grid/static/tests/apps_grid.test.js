import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { keyDown, press, queryAllTexts } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineMenus,
    getService,
    makeMockEnv,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

import "@web_apps_grid/navbar_patch";
import { browser } from "@web/core/browser/browser";
import { NavBar } from "@web/webclient/navbar/navbar";
import {
    appGroupKey,
    AppsGridPrefs,
    matchScore,
    queryVariants,
    searchMenus,
} from "@web_apps_grid/apps_grid/apps_grid_utils";

describe.current.tags("desktop");

const MENUS = [
    {
        id: 1,
        name: "Бухоблік",
        xmlid: "l10n_ua_accounting.menu_root",
        actionID: 11,
        children: [
            {
                id: 10,
                name: "Звіти",
                children: [
                    { id: 100, name: "Оборотно-сальдова відомість", actionID: 1100 },
                    { id: 101, name: "Банківські виписки", actionID: 1101 },
                ],
            },
        ],
    },
    { id: 2, name: "Співробітники", xmlid: "hr.menu_hr_root", actionID: 22 },
    { id: 3, name: "Склад", xmlid: "stock.menu_stock_root", actionID: 33 },
    { id: 4, name: "Налаштування", xmlid: "base.menu_administration", actionID: 44 },
];

describe("utils", () => {
    test("wrong keyboard layout is understood", () => {
        // Ukrainian word typed with the EN layout on, and the other way round
        expect(queryVariants(",fyr")).toInclude("банк");
        expect(queryVariants("ифтл")).toInclude("bank");
        expect(queryVariants("сrm")).toInclude("crm");
        expect(queryVariants("pdsn")).toInclude("звіт");
        // Russian layout letters map onto Ukrainian ones
        expect(queryVariants("ызщ")[0]).toBe("ізщ");
        expect(queryVariants("  ")).toEqual([]);
    });

    test("match score prefers prefixes and whole words", () => {
        const v = queryVariants("банк");
        expect(matchScore("Банк", v)).toBe(100);
        expect(matchScore("Банківські виписки", v)).toBe(80);
        expect(matchScore("Звіт з банку", v)).toBe(60);
        expect(matchScore("Склад", v)).toBe(0);
    });

    test("apps are grouped by the owning module", () => {
        expect(appGroupKey({ xmlid: "l10n_ua_accounting.menu_root" })).toBe("finance");
        expect(appGroupKey({ xmlid: "l10n_ua_hr_salary.menu_hr_payroll_root" })).toBe("hr");
        expect(appGroupKey({ xmlid: "stock.menu_stock_root" })).toBe("operations");
        expect(appGroupKey({ xmlid: "base.menu_management" })).toBe("settings");
        expect(appGroupKey({ xmlid: "x_custom.menu" })).toBe("other");
        expect(appGroupKey({})).toBe("other");
    });

    test("prefs survive broken storage", () => {
        patchWithCleanup(browser.localStorage, {
            getItem: () => {
                throw new Error("blocked");
            },
            setItem: () => {
                throw new Error("blocked");
            },
        });
        const prefs = new AppsGridPrefs(7);
        prefs.togglePin(3);
        prefs.togglePin(1);
        prefs.movePinned(1, 3);
        expect(prefs.data.pinned).toEqual([1, 3]);
        prefs.touch(2);
        prefs.touch(3);
        prefs.touch(2);
        expect(prefs.data.recent).toEqual([2, 3]);
    });
});

describe("grid", () => {
    beforeEach(() => {
        defineMenus(MENUS);
    });

    test("toggle button opens the grid with grouped tiles", async () => {
        await mountWithCleanup(NavBar);
        expect(".o_apps_grid").toHaveCount(0);
        await contains(".o_apps_grid_toggle button").click();
        expect(".o_apps_grid").toHaveCount(1);
        expect(".o_apps_grid_tile").toHaveCount(4);
        expect(".o_apps_grid_section[data-group=finance] .o_apps_grid_name").toHaveText("Бухоблік");
        expect(".o_apps_grid_tile:first").toHaveAttribute("href", "/odoo/action-11");
        expect(".o_apps_grid_search input").toBeFocused();
    });

    test("search finds nested menus typed on the wrong layout", async () => {
        await mountWithCleanup(NavBar);
        await contains(".o_apps_grid_toggle button").click();
        await contains(".o_apps_grid_search input").edit(",fyr", { confirm: false });
        await animationFrame();
        expect(queryAllTexts(".o_apps_grid_result .fw-bold")).toEqual(["Банківські виписки"]);
        expect(".o_apps_grid_result").toHaveAttribute("href", "/odoo/action-1101");
    });

    test("searching by section name lists its items", async () => {
        await makeMockEnv();
        const menuService = getService("menu");
        const { items } = searchMenus(menuService, menuService.getApps(), "звіти");
        expect(items.map((i) => i.menu.id).sort()).toEqual([100, 101]);
    });

    test("Enter opens the first hit, Esc clears then closes", async () => {
        await mountWithCleanup(NavBar);
        const selected = [];
        patchWithCleanup(getService("menu"), {
            selectMenu: (menu) => selected.push(menu.id),
        });
        await contains(".o_apps_grid_toggle button").click();
        await contains(".o_apps_grid_search input").edit("склад", { confirm: false });
        await press("Enter");
        await animationFrame();
        expect(selected).toEqual([3]);
        expect(".o_apps_grid").toHaveCount(0);

        await contains(".o_apps_grid_toggle button").click();
        await contains(".o_apps_grid_search input").edit("щось", { confirm: false });
        await keyDown("Escape");
        await animationFrame();
        expect(".o_apps_grid_search input").toHaveValue("");
        await keyDown("Escape");
        await animationFrame();
        expect(".o_apps_grid").toHaveCount(0);
    });

    test("pinning puts the app in its own row", async () => {
        await mountWithCleanup(NavBar);
        await contains(".o_apps_grid_toggle button").click();
        expect(".o_apps_grid_pinned_section").toHaveCount(0);
        await contains(".o_apps_grid_tile[data-menu-xmlid='hr.menu_hr_root'] .o_apps_grid_pin").click();
        expect(".o_apps_grid_pinned_section .o_apps_grid_name").toHaveText("Співробітники");
        expect(".o_apps_grid").toHaveCount(1);
    });

    test("one-grid mode drops the group headers", async () => {
        await mountWithCleanup(NavBar);
        await contains(".o_apps_grid_toggle button").click();
        expect(".o_apps_grid_section h6").toHaveCount(4);
        await contains(".o_apps_grid_toolbar button:first").click();
        expect(".o_apps_grid_section").toHaveCount(1);
        expect(".o_apps_grid_section h6").toHaveCount(0);
    });
});
