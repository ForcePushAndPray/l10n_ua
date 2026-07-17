/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

// Файли бібліотеки IIT euscp лежать тут (пропрієтарні, поза бандлом і git —
// див. static/src/lib/euscp/README.md). Вантажимо їх ЛІНИВО за URL, а не
// через web.assets_backend: euscp.worker.js ~16МБ, euscp.js ~5МБ — у бандлі
// це зламало б worker і роздуло кожну сторінку.
const EUSCP_BASE = "/l10n_ua_tax_cabinet/static/src/lib/euscp";
// Порядок важливий. За потреби підлаштуйте під вашу версію пакета IIT
// (орієнтир — github.com/kelatev/SA-SignInfo).
const EUSCP_SCRIPTS = ["euscpm.js", "euutils.js", "eusw.js", "euscp.js"];

/**
 * Клієнтський action для реєстрації податкової накладної в ЄРПН (#146).
 *
 * Увесь КЕП-підпис відбувається в браузері через бібліотеку IIT euscp (WASM):
 * приватний ключ і пароль НЕ покидають клієнта. Сервер лише пересилає готові
 * base64-підписи (див. erpn_prepare_signing / erpn_submit_signed на моделі
 * та _api_submit_document_presigned у конфігурації кабінету).
 *
 * Потік:
 *   1. orm.call(model, 'erpn_prepare_signing', [resId]) → xml/taxpayer/cert/filename
 *   2. euscp: прочитати файл-ключ + пароль → підписати taxpayer_code (auth) і
 *      sign+envelope(xml, dpsCert) (конверт подачі)
 *   3. orm.call(model, 'erpn_submit_signed', [resId, authSig, envelope, filename])
 */
export class ErpnSignAction extends Component {
    static template = "l10n_ua_tax_cabinet.ErpnSignAction";
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
                // Легка перевірка наявності файлів (без завантаження 21МБ).
                this.state.libAvailable = await this._checkLibPresent();
                this.state.prepared = await this.orm.call(
                    this.model, "erpn_prepare_signing", [this.resId]
                );
                this.state.phase = "ready";
            } catch (e) {
                this.state.phase = "error";
                this.state.error = this._errMessage(e);
            }
        });
    }

    /**
     * Глобальний об'єкт бібліотеки підпису IIT (euscp «Підпис для WEB»).
     * Повертає null, доки бібліотеку не підвантажено (_ensureEuscpLoaded).
     */
    _getEuLibrary() {
        return window.EndUserLibrary || window.euscp || window.EndUser || null;
    }

    /** HEAD-перевірка, що файли бібліотеки лежать на місці (без завантаження). */
    async _checkLibPresent() {
        try {
            const resp = await fetch(`${EUSCP_BASE}/${EUSCP_SCRIPTS[0]}`, {
                method: "HEAD",
            });
            return resp.ok;
        } catch (e) {
            return false;
        }
    }

    /** Динамічно вставити <script> за URL і дочекатись завантаження. */
    _loadScript(url) {
        return new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[data-euscp="${url}"]`);
            if (existing) {
                resolve();
                return;
            }
            const s = document.createElement("script");
            s.src = url;
            s.async = false;
            s.dataset.euscp = url;
            s.onload = () => resolve();
            s.onerror = () => reject(new Error(`Не вдалося завантажити ${url}`));
            document.head.appendChild(s);
        });
    }

    /**
     * Лінива підгрузка бібліотеки euscp за URL (лише при першому підписі).
     * Worker euscp.worker.js вантажиться самою бібліотекою за URL з EUSCP_BASE —
     * тут головне виставити базовий шлях, а не конкатенувати worker у бандл.
     */
    async _ensureEuscpLoaded() {
        if (this._getEuLibrary()) {
            return this._getEuLibrary();
        }
        // Підказати бібліотеці, де взяти worker/wasm (назва хука залежить від
        // версії пакета; за потреби звірте з README/SA-SignInfo).
        window.EU_WORKER_URL = window.EU_WORKER_URL || `${EUSCP_BASE}/euscp.worker.js`;
        for (const name of EUSCP_SCRIPTS) {
            await this._loadScript(`${EUSCP_BASE}/${name}`);
        }
        const lib = this._getEuLibrary();
        if (!lib) {
            throw new Error(_t(
                "Бібліотеку euscp завантажено, але глобальний об'єкт не знайдено — " +
                "підлаштуйте EUSCP_SCRIPTS / назву глобала під вашу версію IIT."
            ));
        }
        return lib;
    }

    _errMessage(e) {
        return (e && (e.data && e.data.message)) || (e && e.message) || String(e);
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

    _b64ToBytes(b64) {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) {
            bytes[i] = bin.charCodeAt(i);
        }
        return bytes;
    }

    /**
     * Підписати дані в браузері через euscp. Ізольовано, щоб власник міг
     * підлаштувати під конкретну версію API бібліотеки IIT.
     *
     * Очікуваний контракт (EndUserLibrary, promise-API):
     *   await eu.ReadPrivateKeyBinary(keyBytes, password, null, null)
     *   authSig  = await eu.SignDataInternal(true, taxpayerCode, true)   // base64
     *   envelope = await eu.SignData(xmlBytes, true)                     // base64
     * Повертає { authSig, envelope } (обидва base64).
     */
    async _signInBrowser(prepared) {
        // Лінива підгрузка бібліотеки за URL (перший підпис вантажить ~21МБ).
        const Lib = await this._ensureEuscpLoaded();
        if (!this.keyFileBuffer) {
            throw new Error(_t("Виберіть файл-ключ (.dat/.jks)."));
        }
        if (!this.state.password) {
            throw new Error(_t("Введіть пароль до ключа."));
        }

        // Сигнатури методів звірені з реальною TS-обгорткою EndUserLibrary
        // (github.com/kelatev/SA-SignInfo, src/EUSign/EndUserLibrary.ts):
        //   ReadPrivateKeyBinary(privateKey, password, certs, CACommonName)
        //   SignData(data, asBase64String?)
        //   SignDataInternal(appendCert, data, asBase64String?)
        // Точний метод конверта (EnvelopData/SignData+EnvelopData) — за
        // EUSignJavaScriptD.doc вашої версії пакета IIT.
        const eu = Lib.EndUser ? new Lib.EndUser() : new Lib();
        await eu.ReadPrivateKeyBinary(this.keyFileBuffer, this.state.password, null, null);

        // (1) Підпис taxpayer_code → заголовок Authorization (CAdES із сертифікатом).
        const authSig = await eu.SignDataInternal(true, prepared.taxpayer_code, true);

        // (2) Конверт подачі: підпис XML, за потреби — шифрування на сертифікат ДПС.
        // Базово підписуємо (SignData). Якщо ваш регламент вимагає шифрування
        // на EK_C_NEW.cer — додайте EnvelopData(dpsCert, signed, ...) тут згідно
        // з документацією IIT (сертифікат уже приходить у prepared.dps_cert_b64).
        const xmlBytes = this._b64ToBytes(prepared.xml_b64);
        const envelope = await eu.SignData(xmlBytes, true);
        // const dpsCert = this._b64ToBytes(prepared.dps_cert_b64);
        // envelope = await eu.EnvelopData(dpsCert, <signed>, ...);

        return { authSig, envelope };
    }

    async onSign() {
        this.state.phase = "signing";
        this.state.error = null;
        try {
            const { authSig, envelope } = await this._signInBrowser(this.state.prepared);
            const result = await this.orm.call(
                this.model, "erpn_submit_signed",
                [this.resId, authSig, envelope, this.state.prepared.filename]
            );
            this.state.receipt = (result && result.receipt) || _t("Успішно");
            this.state.phase = "done";
            this.notification.add(_t("Податкову накладну зареєстровано в ЄРПН."),
                { type: "success" });
        } catch (e) {
            this.state.phase = "ready";
            this.state.error = this._errMessage(e);
            this.notification.add(this.state.error, { type: "danger" });
        }
    }

    async onClose() {
        // Повернутися до форми накладної.
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

registry.category("actions").add("l10n_ua_tax_cabinet.erpn_sign", ErpnSignAction);
