/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { checkLibPresent, signDocuments } from "./kep_sign_service";

/**
 * Універсальний client action клієнтського КЕП-підпису.
 *
 * Модель-агностичний: працює з будь-якою моделлю, що успадковує
 * l10n_ua.sign.mixin. Приватний ключ і пароль обробляються лише в браузері;
 * на сервер ідуть тільки base64-підписи.
 *
 * Потік:
 *   1. orm.call(model, 'kep_prepare_signing', [resId]) → {auth_subject, documents}
 *   2. euscp: прочитати файл-ключ + пароль → підписати документи (+auth)
 *   3. orm.call(model, 'kep_submit_signed', [resId, signed, authSig]) → результат
 */
export class KepSignAction extends Component {
    static template = "l10n_ua_sign.KepSignAction";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        const params = this.props.action.params || this.props.action.context || {};
        this.model = params.model;
        this.resId = params.res_id;

        this.state = useState({
            phase: "loading", // loading | ready | signing | done | error
            error: null,
            receipt: null,
            libAvailable: false,
            password: "",
            keyFileName: "",
            prepared: null,
        });
        this.keyFileBuffer = null;

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

    async onSign() {
        this.state.phase = "signing";
        this.state.error = null;
        try {
            const { auth_signature, signed } = await signDocuments(
                this.state.prepared, this.keyFileBuffer, this.state.password
            );
            const result = await this.orm.call(
                this.model, "kep_submit_signed",
                [this.resId, signed, auth_signature]
            );
            this.state.receipt = (result && result.receipt) || _t("Успішно");
            this.state.phase = "done";
            this.notification.add(_t("Документ підписано й подано."),
                { type: "success" });
        } catch (e) {
            this.state.phase = "ready";
            this.state.error = this._errMessage(e);
            this.notification.add(this.state.error, { type: "danger" });
        }
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
