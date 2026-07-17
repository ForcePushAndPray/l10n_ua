/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

/**
 * Сервіс клієнтського КЕП-підпису поверх бібліотеки IIT euscp (WASM).
 *
 * Файли бібліотеки пропрієтарні й лежать поза бандлом/git у
 * static/src/lib/euscp (див. README там). Вантажимо їх ЛІНИВО за URL: worker
 * euscp.worker.js ~16МБ, euscp.js ~5МБ — у web.assets_backend це зламало б
 * worker і роздуло кожну сторінку.
 *
 * Публічне API:
 *   checkLibPresent()               → чи лежать файли (HEAD, без завантаження)
 *   signDocuments(spec, key, pwd)   → { auth_signature, signed: {name: b64} }
 */

export const EUSCP_BASE = "/l10n_ua_sign/static/src/lib/euscp";
// Порядок важливий. За потреби підлаштуйте під вашу версію пакета IIT
// (орієнтир — github.com/kelatev/SA-SignInfo).
export const EUSCP_SCRIPTS = ["euscpm.js", "euutils.js", "eusw.js", "euscp.js"];

function getEuLibrary() {
    return window.EndUserLibrary || window.euscp || window.EndUser || null;
}

/** HEAD-перевірка, що файли бібліотеки на місці (без завантаження ~21МБ). */
export async function checkLibPresent() {
    try {
        const resp = await fetch(`${EUSCP_BASE}/${EUSCP_SCRIPTS[0]}`, {
            method: "HEAD",
        });
        return resp.ok;
    } catch (e) {
        return false;
    }
}

function loadScript(url) {
    return new Promise((resolve, reject) => {
        if (document.querySelector(`script[data-euscp="${url}"]`)) {
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

/** Лінива підгрузка euscp за URL (лише при першому підписі). */
export async function ensureEuscpLoaded() {
    if (getEuLibrary()) {
        return getEuLibrary();
    }
    // Підказати бібліотеці, де взяти worker/wasm (назва хука залежить від версії).
    window.EU_WORKER_URL = window.EU_WORKER_URL || `${EUSCP_BASE}/euscp.worker.js`;
    for (const name of EUSCP_SCRIPTS) {
        await loadScript(`${EUSCP_BASE}/${name}`);
    }
    const lib = getEuLibrary();
    if (!lib) {
        throw new Error(_t(
            "Бібліотеку euscp завантажено, але глобальний об'єкт не знайдено — " +
            "підлаштуйте EUSCP_SCRIPTS / назву глобала під вашу версію IIT."
        ));
    }
    return lib;
}

function b64ToBytes(b64) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
        bytes[i] = bin.charCodeAt(i);
    }
    return bytes;
}

/**
 * Підписати один документ у потрібному форматі.
 * Сигнатури методів звірені з EndUserLibrary (kelatev/SA-SignInfo):
 *   SignData(data, asBase64String?)
 *   SignDataInternal(appendCert, data, asBase64String?)
 * Точні виклики конверта/ASiC залежать від версії пакета — за потреби
 * підлаштуйте (EUSignJavaScriptD.doc).
 */
async function signOneDocument(eu, doc) {
    const bytes = b64ToBytes(doc.data_b64);
    const fmt = doc.format || "cades";
    if (fmt === "cades") {
        // CAdES/P7S із сертифікатом підписувача.
        return await eu.SignDataInternal(true, bytes, true);
    }
    if (fmt === "envelope") {
        // Підпис, за потреби — шифрування на сертифікат отримувача.
        const signed = await eu.SignData(bytes, true);
        // Якщо регламент вимагає шифрування — розкоментуйте (звірте сигнатуру
        // EnvelopData під вашу версію IIT; cert приходить у recipient_cert_b64):
        // if (doc.recipient_cert_b64) {
        //     const cert = b64ToBytes(doc.recipient_cert_b64);
        //     return await eu.EnvelopData(cert, signed, true);
        // }
        return signed;
    }
    if (fmt === "asic") {
        // Контейнер ASiC (для Дії). Метод залежить від версії пакета.
        if (typeof eu.ASiCSignData === "function") {
            return await eu.ASiCSignData(bytes, true);
        }
        throw new Error(_t("ASiC-підпис недоступний у цій версії бібліотеки."));
    }
    throw new Error(_t("Невідомий формат підпису: %s").replace("%s", fmt));
}

/**
 * Стейтфул-підписувач: тримає зчитаний приватний ключ між кроками
 * (зчитати → підписати → відправити). Ключ і пароль не покидають браузер.
 *
 * Використання:
 *   const signer = createSigner();
 *   const { owner, certs } = await signer.readKey(keyBuffer, password);
 *   const { auth_signature, signed } = await signer.sign(spec);
 */
export function createSigner() {
    let eu = null;
    return {
        get ready() {
            return !!eu;
        },
        /**
         * Крок 1 — зчитати ключ і повернути дані власника (для підтвердження).
         * @returns {{owner: Object, certs: Array}}
         */
        async readKey(keyBuffer, password) {
            if (!keyBuffer) {
                throw new Error(_t("Виберіть файл-ключ (.dat/.jks)."));
            }
            if (!password) {
                throw new Error(_t("Введіть пароль до ключа."));
            }
            const Lib = await ensureEuscpLoaded();
            eu = Lib.EndUser ? new Lib.EndUser() : new Lib();
            const owner = await eu.ReadPrivateKeyBinary(keyBuffer, password, null, null);
            let certs = [];
            try {
                certs = await eu.GetOwnCertificates();
            } catch (e) {
                certs = [];
            }
            return { owner, certs };
        },
        /**
         * Крок 2 — підписати документи вже зчитаним ключем.
         * @param {{auth_subject?: string, documents: Array}} spec
         * @returns {{auth_signature: (string|null), signed: Object}}
         */
        async sign(spec) {
            if (!eu) {
                throw new Error(_t("Спершу зчитайте ключ."));
            }
            let authSignature = null;
            if (spec.auth_subject) {
                authSignature = await eu.SignDataInternal(true, spec.auth_subject, true);
            }
            const signed = {};
            for (const doc of spec.documents || []) {
                signed[doc.name] = await signOneDocument(eu, doc);
            }
            return { auth_signature: authSignature, signed };
        },
    };
}
