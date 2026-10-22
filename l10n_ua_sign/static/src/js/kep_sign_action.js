/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import {
    checkLibPresent,
    forgetKey,
    getKeySession,
    listCAs,
    readKey,
    signWithKey,
    KEY_CA_MISMATCH,
} from "./kep_sign_service";

// Останній ЦСК користувача: наступного разу ключ зчитується без перебору.
const CA_STORAGE_KEY = "l10n_ua_sign.ca_name";

function loadSavedCa() {
    try {
        return window.localStorage.getItem(CA_STORAGE_KEY) || "";
    } catch {
        return "";
    }
}

function saveCa(name) {
    try {
        if (name) {
            window.localStorage.setItem(CA_STORAGE_KEY, name);
        } else {
            window.localStorage.removeItem(CA_STORAGE_KEY);
        }
    } catch {
        // сховище браузера недоступне — просто не запам'ятовуємо
    }
}

function lowerFirst(text) {
    return text ? text.charAt(0).toLowerCase() + text.slice(1) : text;
}

/**
 * Універсальне вікно клієнтського КЕП-підпису (client action ``l10n_ua_sign.kep_sign``).
 *
 * Відкривається поверх форми (``target: 'new'`` з ``action_kep_sign()``) для будь-якої
 * моделі на ``l10n_ua.sign.mixin``. Сценарії:
 *   - лише авторизація (``auth_subject`` без документів: перевірка з'єднання,
 *     синхронізація) — одна кнопка «Зчитати ключ і <дія>»;
 *   - документи — спершу ключ (користувач звіряє власника), потім
 *     «Підписати й <дія>» зі списком того, що підписується.
 * Ключ зчитується раз на вкладку (див. getKeySession) і далі не просить пароль.
 * ``mode`` (якщо є) йде обом викликам контракту в контексті як ``kep_mode``.
 * Приватний ключ і пароль обробляються лише в браузері.
 */
export class KepSignAction extends Component {
    static template = "l10n_ua_sign.KepSignAction";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        const params = this.props.action.params || this.props.action.context || {};
        this.model = params.model;
        this.resId = params.res_id;
        this.callKwargs = params.mode ? { context: { kep_mode: params.mode } } : {};
        this.inDialog = this.props.action.target === "new";

        this.state = useState({
            phase: "loading", // loading | ready | done | error
            stage: null,       // read | sign | send — що саме зараз триває
            error: null,
            libAvailable: false,
            caList: [],        // ЦСК для вибору; "" — визначати автоматично
            caName: "",
            password: "",
            keyFileName: "",
            prepared: null,
            key: getKeySession(),
            receipt: null,
        });
        this.keyFileBuffer = null;

        onWillStart(async () => {
            try {
                const [libAvailable, caList, prepared] = await Promise.all([
                    checkLibPresent(),
                    listCAs().catch(() => []),
                    this.orm.call(
                        this.model, "kep_prepare_signing", [this.resId], this.callKwargs
                    ),
                ]);
                this.state.libAvailable = libAvailable;
                this.state.caList = caList;
                const saved = loadSavedCa();
                this.state.caName = caList.some((ca) => ca.name === saved) ? saved : "";
                this.state.prepared = prepared;
                this.state.phase = "ready";
            } catch (e) {
                this.state.phase = "error";
                this.state.error = this._errMessage(e);
            }
        });
    }

    _errMessage(e) {
        return (e && e.data && e.data.message) || (e && e.message) || String(e);
    }

    get busy() {
        return !!this.state.stage;
    }

    get documents() {
        return (this.state.prepared && this.state.prepared.documents) || [];
    }

    get authSubject() {
        return this.state.prepared && this.state.prepared.auth_subject;
    }

    /** Підписується лише код для авторизації (перевірка з'єднання, синхронізація). */
    get authOnly() {
        return !this.documents.length && !!this.authSubject;
    }

    get submitLabel() {
        return (this.state.prepared && this.state.prepared.submit_label) || _t("Відправити");
    }

    get mainLabel() {
        if (this.authOnly) {
            return this.state.key
                ? this.submitLabel
                : _t("Зчитати ключ і %s").replace("%s", lowerFirst(this.submitLabel));
        }
        return this.state.key
            ? _t("Підписати й %s").replace("%s", lowerFirst(this.submitLabel))
            : _t("Зчитати ключ");
    }

    get stageLabel() {
        return {
            read: _t("Зчитування ключа…"),
            sign: _t("Підписання…"),
            send: _t("Відправлення…"),
        }[this.state.stage];
    }

    get keyRows() {
        const key = this.state.key;
        if (!key) {
            return [];
        }
        const o = key.owner || {};
        const rows = [];
        const push = (label, val) => {
            if (val) {
                rows.push({ label, value: String(val) });
            }
        };
        push(_t("Власник"), o.subjCN || o.subjFullName || o.subject);
        push(_t("Організація"), o.subjOrg);
        push(_t("РНОКПП"), o.subjDRFOCode);
        push(_t("ЄДРПОУ"), o.subjEDRPOUCode);
        push(_t("Видавець"), o.issuerCN);
        const cert = key.certs && key.certs[0];
        const info = cert && (cert.infoEx || cert.info);
        if (info) {
            push(_t("Сертифікат діє до"), info.certEndTime);
        }
        return rows;
    }

    get keyExpiresAt() {
        const key = this.state.key;
        if (!key) {
            return "";
        }
        return new Date(key.expiresAt).toLocaleTimeString("uk-UA", {
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    onCaChange(ev) {
        this.state.caName = ev.target.value;
        saveCa(this.state.caName);
    }

    onKeyFileChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            this.keyFileBuffer = null;
            this.state.keyFileName = "";
            return;
        }
        this.state.keyFileName = file.name;
        const reader = new FileReader();
        reader.onload = () => {
            this.keyFileBuffer = new Uint8Array(reader.result);
        };
        reader.readAsArrayBuffer(file);
    }

    onPasswordInput(ev) {
        this.state.password = ev.target.value;
    }

    async onForgetKey() {
        await forgetKey();
        this.state.key = null;
    }

    /** Головна кнопка: стільки кроків, скільки треба для поточного сценарію. */
    async onMain() {
        this.state.error = null;
        try {
            if (!getKeySession()) {
                this.state.key = null;
                await this._readKey();
                if (!this.authOnly) {
                    // Документи підписуємо лише після того, як власника ключа звірено.
                    return;
                }
            }
            this.state.stage = "sign";
            const { auth_signature, signed } = await signWithKey(this.state.prepared);
            this.state.key = getKeySession();
            this.state.stage = "send";
            const result = await this.orm.call(
                this.model, "kep_submit_signed",
                [this.resId, signed, auth_signature], this.callKwargs
            );
            this.state.receipt = (result && result.receipt) || _t("Готово.");
            this.state.phase = "done";
        } catch (e) {
            this.state.error = this._errMessage(e);
            if (this.state.caName && e && e.code === KEY_CA_MISMATCH) {
                this.state.error = _t(
                    "Сертифікат ключа не знайдено у ЦСК «%s». Оберіть ЦСК, який видав " +
                    "ваш ключ, або «Визначати автоматично»."
                ).replace("%s", this.state.caName);
            }
        } finally {
            this.state.stage = null;
        }
    }

    async _readKey() {
        this.state.stage = "read";
        const key = await readKey(this.keyFileBuffer, this.state.password, this.state.caName || null);
        this.state.password = "";
        if (!this.state.caName) {
            this._rememberDetectedCa(key.owner);
        }
        this.state.key = key;
    }

    /** ЦСК, знайдений перебором, — у вибір і на наступний раз. */
    _rememberDetectedCa(owner) {
        const issuer = owner && owner.issuerCN;
        const ca = issuer && this.state.caList.find((item) => item.issuerCNs.includes(issuer));
        if (ca) {
            this.state.caName = ca.name;
            saveCa(ca.name);
        }
    }

    /** Скасувати — повернутись до форми, з якої відкрили. */
    async onCancel() {
        if (this.inDialog) {
            await this.action.doAction({ type: "ir.actions.act_window_close" });
        } else {
            await this._openRecord();
        }
    }

    /** Закрити після успіху: ``close_action`` споживача або назад до форми (перечитується). */
    async onClose() {
        const closeAction = this.state.prepared && this.state.prepared.close_action;
        if (closeAction) {
            await this.action.doAction(closeAction);
        } else {
            await this.onCancel();
        }
    }

    _openRecord() {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.model,
            res_id: this.resId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("l10n_ua_sign.kep_sign", KepSignAction);
