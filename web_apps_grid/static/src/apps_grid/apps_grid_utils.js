import { reactive } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";

// Same physical keys on the US-QWERTY and Ukrainian ЙЦУКЕН layouts.
const EN_KEYS = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./\\";
const UK_KEYS = "'йцукенгшщзхїфівапролджєячсмитьбю.ґ";
// Russian-only letters land on the same keys as these Ukrainian ones.
const RU_TO_UK = { ы: "і", э: "є", ъ: "ї", ё: "'" };

const EN_TO_UK = Object.fromEntries([...EN_KEYS].map((c, i) => [c, UK_KEYS[i]]));
const UK_TO_EN = Object.fromEntries([...UK_KEYS].map((c, i) => [c, EN_KEYS[i]]));

function mapChars(text, table) {
    return [...text].map((c) => table[c] ?? c).join("");
}

export function normalize(text) {
    return (text || "")
        .toLowerCase()
        .replace(/[ыэъё]/g, (c) => RU_TO_UK[c])
        .replace(/[’ʼ`]/g, "'")
        .trim();
}

/**
 * The query as typed plus how it reads if it was typed on the other layout:
 * "ифтл" -> "банк" is what you get with Ukrainian text and the EN layout on.
 */
export function queryVariants(query) {
    const q = normalize(query);
    if (!q) {
        return [];
    }
    return [...new Set([q, mapChars(q, EN_TO_UK), mapChars(q, UK_TO_EN)])];
}

/** 0 = no match; higher is better. */
export function matchScore(name, variants) {
    const text = normalize(name);
    let best = 0;
    for (const v of variants) {
        if (text === v) {
            return 100;
        }
        if (text.startsWith(v)) {
            best = Math.max(best, 80);
        } else if (text.split(/[\s/()«»"-]+/).some((w) => w.startsWith(v))) {
            best = Math.max(best, 60);
        } else if (text.includes(v)) {
            best = Math.max(best, 40);
        }
    }
    return best;
}

/** Every menu below an app that opens something, with its breadcrumb. */
export function collectMenuItems(menuService, apps) {
    const items = [];
    const walk = (menu, app, path) => {
        for (const child of menu.childrenTree || []) {
            const childPath = [...path, child.name];
            if (child.actionID) {
                items.push({ menu: child, app, path: childPath });
            }
            walk(child, app, childPath);
        }
    };
    for (const app of apps) {
        walk(menuService.getMenuAsTree(app.id), app, []);
    }
    return items;
}

export function searchMenus(menuService, apps, query, limit = 40) {
    const variants = queryVariants(query);
    if (!variants.length) {
        return { apps: [], items: [] };
    }
    const scoredApps = apps
        .map((app) => ({ app, score: matchScore(app.name, variants) }))
        .filter((r) => r.score)
        .sort((a, b) => b.score - a.score)
        .map((r) => r.app);
    const items = collectMenuItems(menuService, apps)
        .map((item) => {
            // The leaf name counts most; a hit on a parent section still finds it.
            const own = matchScore(item.menu.name, variants);
            const viaPath = Math.max(
                matchScore(item.app.name, variants),
                ...item.path.slice(0, -1).map((p) => matchScore(p, variants))
            );
            return { ...item, score: own ? own + 10 : viaPath / 2 };
        })
        .filter((r) => r.score)
        .sort((a, b) => b.score - a.score)
        .slice(0, limit);
    return { apps: scoredApps, items };
}

// Grouping by the module that owns the app's root menu xmlid.
const GROUPS = [
    { key: "finance", label: () => _t("Finance"), re: /^(account|l10n_ua_(account|accounting|bank|tax|asset|budget|nonprofit|consolidation|medoc|cash|vat|erpn|mono)|payment|analytic|spreadsheet_dashboard_account)/ },
    { key: "hr", label: () => _t("Human Resources"), re: /^(hr|l10n_ua_hr|l10n_ua_payroll)/ },
    { key: "sales", label: () => _t("Sales"), re: /^(sale|crm|point_of_sale|pos_|website|l10n_ua_marketplace|agreement|contract|sign|loyalty|event|l10n_ua_sale|l10n_ua_doc)/ },
    { key: "operations", label: () => _t("Inventory & Manufacturing"), re: /^(stock|mrp|purchase|repair|fleet|maintenance|quality|delivery|l10n_ua_(stock|mrp|purchase|supplier|fleet|transport))/ },
    { key: "industry", label: () => _t("Industries"), re: /^l10n_ua_(education|medecin|agro|construction|hotel|restaurant|retail|logistics)/ },
    { key: "collab", label: () => _t("Collaboration"), re: /^(mail|calendar|contacts|project|spreadsheet|knowledge|note|survey|utm|im_livechat|documents|todo|hr_timesheet)/ },
    { key: "settings", label: () => _t("Settings"), re: /^base(_|$)/ },
];

export function appGroupKey(app) {
    const module = (app.xmlid || "").split(".")[0];
    return GROUPS.find((g) => g.re.test(module))?.key || "other";
}

export function groupApps(apps) {
    const byKey = new Map();
    for (const app of apps) {
        const key = appGroupKey(app);
        if (!byKey.has(key)) {
            byKey.set(key, []);
        }
        byKey.get(key).push(app);
    }
    const ordered = [...GROUPS, { key: "other", label: () => _t("Other") }];
    return ordered
        .filter((g) => byKey.has(g.key))
        .map((g) => ({ key: g.key, label: g.label(), apps: byKey.get(g.key) }));
}

// Per-user preferences kept in the browser; any storage failure (private
// window, blocked site data) just means defaults.
const MAX_RECENT = 6;

export class AppsGridPrefs {
    constructor(userId) {
        this.key = `web_apps_grid.${userId}`;
        const data = { pinned: [], recent: [], grouped: true };
        try {
            const raw = browser.localStorage.getItem(this.key);
            if (raw) {
                Object.assign(data, JSON.parse(raw));
            }
        } catch {
            // keep defaults
        }
        // Reactive so components that read it through useState re-render.
        this.data = reactive(data);
    }
    save() {
        try {
            browser.localStorage.setItem(this.key, JSON.stringify(this.data));
        } catch {
            // not persisted, still works for this page
        }
    }
    isPinned(appId) {
        return this.data.pinned.includes(appId);
    }
    togglePin(appId) {
        const pinned = this.data.pinned;
        this.data.pinned = pinned.includes(appId)
            ? pinned.filter((id) => id !== appId)
            : [...pinned, appId];
        this.save();
    }
    movePinned(appId, beforeAppId) {
        const pinned = this.data.pinned.filter((id) => id !== appId);
        const index = beforeAppId ? pinned.indexOf(beforeAppId) : -1;
        pinned.splice(index < 0 ? pinned.length : index, 0, appId);
        this.data.pinned = pinned;
        this.save();
    }
    touch(appId) {
        if (!appId || this.data.recent[0] === appId) {
            return;
        }
        this.data.recent = [appId, ...this.data.recent.filter((id) => id !== appId)].slice(
            0,
            MAX_RECENT * 2
        );
        this.save();
    }
    setGrouped(grouped) {
        this.data.grouped = grouped;
        this.save();
    }
}

export function pickApps(apps, ids) {
    const byId = new Map(apps.map((a) => [a.id, a]));
    return ids.map((id) => byId.get(id)).filter(Boolean);
}

export function recentApps(apps, data) {
    return pickApps(apps, data.recent)
        .filter((a) => !data.pinned.includes(a.id))
        .slice(0, MAX_RECENT);
}

/**
 * Arrow-key target among focusable tiles by on-screen geometry, so it works
 * across group headers and the result list alike.
 */
export function neighbourInDirection(elements, current, key) {
    const r0 = current.getBoundingClientRect();
    const cx = r0.left + r0.width / 2;
    const cy = r0.top + r0.height / 2;
    let best = null;
    let bestScore = Infinity;
    for (const el of elements) {
        if (el === current) {
            continue;
        }
        const r = el.getBoundingClientRect();
        const x = r.left + r.width / 2;
        const y = r.top + r.height / 2;
        const dx = x - cx;
        const dy = y - cy;
        let primary;
        let secondary;
        if (key === "ArrowRight" || key === "ArrowLeft") {
            primary = key === "ArrowRight" ? dx : -dx;
            secondary = Math.abs(dy);
            // same row only
            if (secondary > r0.height / 2) {
                continue;
            }
        } else {
            primary = key === "ArrowDown" ? dy : -dy;
            secondary = Math.abs(dx);
        }
        if (primary <= 1) {
            continue;
        }
        const score = primary + secondary * 2;
        if (score < bestScore) {
            bestScore = score;
            best = el;
        }
    }
    if (!best && (key === "ArrowRight" || key === "ArrowLeft")) {
        // wrap to the next / previous tile in reading order
        const index = elements.indexOf(current);
        best = elements[index + (key === "ArrowRight" ? 1 : -1)] || null;
    }
    return best;
}
