/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { checkLibPresent, createSigner } from "./kep_sign_service";

/**
 * Універсальний client action клієнтського КЕП-підпису у ТРИ явні кроки:
 *   1. Зчитати ключ  → показати дані власника (перевірка, що ключ правильний).
 *   2. Підписати     → рахуємо підписи в браузері.
 *   3. Відправити    → orm.call kep_submit_signed (ДПС / банк / інша установа).
 *
 * Модель-агностичний: працює з будь-якою моделлю на l10n_ua.sign.mixin.
 * Приватний ключ і пароль обробляються лише в браузері.
 */
export class KepSignAction extends Component {
    static template = "l10n_ua_sign.KepSignAction";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.signer = createSigner();

        const params = this.props.action.params || this.props.action.context || {};
        this.model = params.model;
        this.resId = params.res_id;

        this.state = useState({
            phase: "loading", // loading | ready | done | error
            busy: false,
            error: null,
            libAvailable: false,
            password: "",
            keyFileName: "",
            prepared: null,
            ownerRows: null,   // заповнено після кроку 1
            signed: null,      // заповнено після кроку 2
            receipt: null,     // заповнено після кроку 3
        });
        this.keyFileBuffer = null;
        this._signedPayload = null;

        onWillStart(async () => {
            try {
                this.state.libAvailable = await checkLibPresent();
                this.state.prepared = await this.orm.call(
                    this.model, "kep_prepare_signing", [this.resId]
                );
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

    get docCount() {
        return (this.state.prepared && this.state.prepared.documents || []).length;
    }

    get submitLabel() {
        return (this.state.prepared && this.state.prepared.submit_label)
            || _t("Відправити");
    }

    onKeyFileChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        this.state.ownerRows = null;  // зміна ключа скидає зчитане
        this.state.signed = null;
        this._signedPayload = null;
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

    /** Крок 1 — зчитати ключ і показати власника. */
    async onReadKey() {
        this.state.busy = true;
        this.state.error = null;
        try {
            const { owner, certs } = await this.signer.readKey(
                this.keyFileBuffer, this.state.password);
            this.state.ownerRows = this._summarizeOwner(owner, certs);
            this.notification.add(_t("Ключ зчитано."), { type: "success" });
        } catch (e) {
            this.state.error = this._errMessage(e);
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    /** Крок 2 — підписати документи вже зчитаним ключем. */
    async onSign() {
        this.state.busy = true;
        this.state.error = null;
        try {
            this._signedPayload = await this.signer.sign(this.state.prepared);
            this.state.signed = true;
            this.notification.add(_t("Документи підписано."), { type: "success" });
        } catch (e) {
            this.state.error = this._errMessage(e);
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    /** Крок 3 — відправити підписане (ДПС / банк / інша установа). */
    async onSend() {
        this.state.busy = true;
        this.state.error = null;
        try {
            const { auth_signature, signed } = this._signedPayload;
            const result = await this.orm.call(
                this.model, "kep_submit_signed",
                [this.resId, signed, auth_signature]
            );
            this.state.receipt = (result && result.receipt) || _t("Успішно");
            this.state.phase = "done";
            this.notification.add(_t("Відправлено."), { type: "success" });
        } catch (e) {
            this.state.error = this._errMessage(e);
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    /** Зчитати з об'єкта власника читабельні рядки для показу. */
    _summarizeOwner(owner, certs) {
        const o = owner || {};
        const rows = [];
        const push = (label, val) => {
            if (val) rows.push({ label, value: String(val) });
        };
        push(_t("Власник"), o.subjCN || o.subjFullName || o.subject);
        push(_t("Організація"), o.subjOrg);
        push(_t("РНОКПП"), o.subjDRFOCode);
        push(_t("ЄДРПОУ"), o.subjEDRPOUCode);
        push(_t("Видавець"), o.issuerCN);
        const cert = certs && certs[0];
        const info = cert && (cert.infoEx || cert.info);
        if (info) {
            push(_t("Дійсний з"), info.certBeginTime);
            push(_t("Дійсний до"), info.certEndTime);
        }
        if (!rows.length) {
            rows.push({ label: _t("Ключ"), value: _t("зчитано") });
        }
        return rows;
    }

    async onClose() {
        await this.action.doAction({
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
