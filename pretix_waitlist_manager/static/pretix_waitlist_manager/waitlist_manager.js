(function () {
    function managedFields(form) {
        return Array.from(form.querySelectorAll("select, input, textarea")).filter((field) => {
            return !["button", "submit", "hidden"].includes(field.type);
        });
    }

    function dirtyWarningFields(form) {
        return Array.from(form.querySelectorAll("select, input, textarea")).filter((field) => {
            return !["button", "submit"].includes(field.type);
        });
    }

    function storageKey(form) {
        return `pretix-waitlist-manager:${window.location.pathname}:${form.id}`;
    }

    function saveFormState(form) {
        const payload = {};
        managedFields(form).forEach((field) => {
            if (!field.name) {
                return;
            }

            if (field.type === "checkbox") {
                payload[field.name] = field.checked;
            } else if (field.type === "radio") {
                if (field.checked) {
                    payload[field.name] = field.value;
                }
            } else {
                payload[field.name] = field.value;
            }
        });
        form._waitlistManagerState = payload;
        window.sessionStorage.setItem(storageKey(form), JSON.stringify(payload));
    }

    function restoreFormState(form) {
        const payload = loadStoredState(form);
        if (!payload) {
            return;
        }

        managedFields(form).forEach((field) => {
            if (!field.name || !(field.name in payload)) {
                return;
            }

            if (field.type === "checkbox") {
                field.checked = Boolean(payload[field.name]);
            } else if (field.type === "radio") {
                field.checked = field.value === payload[field.name];
            } else {
                field.value = payload[field.name];
            }
        });
    }

    function loadStoredState(form) {
        if (form._waitlistManagerState) {
            return form._waitlistManagerState;
        }
        const raw = window.sessionStorage.getItem(storageKey(form));
        if (!raw) {
            return null;
        }

        try {
            form._waitlistManagerState = JSON.parse(raw);
            return form._waitlistManagerState;
        } catch (error) {
            window.sessionStorage.removeItem(storageKey(form));
            return null;
        }
    }

    function preferredStoredValue(form, field) {
        const payload = loadStoredState(form);
        if (!payload || !field.name || !(field.name in payload)) {
            return field.value;
        }
        return payload[field.name];
    }

    function suppressDirtyWarning(form) {
        dirtyWarningFields(form).forEach((field) => {
            field.setAttribute("data-ays-ignore", "1");
        });

        if (window.jQuery) {
            window.jQuery(form).trigger("reinitialize.areYouSure");
        }
    }

    function initializeSessionState(form) {
        loadStoredState(form);
        restoreFormState(form);

        const persist = () => saveFormState(form);
        managedFields(form).forEach((field) => {
            field.addEventListener("change", persist);
            field.addEventListener("input", persist);
        });
        form.addEventListener("submit", persist);

        suppressDirtyWarning(form);
    }

    function setSelectChoices(field, choices, currentValue) {
        field.innerHTML = "";
        choices.forEach(([value, label]) => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = label;
            if (value === currentValue) {
                option.selected = true;
            }
            field.appendChild(option);
        });

        if (!field.value && choices.length) {
            field.value = choices[0][0];
        }
    }

    const jsonCache = new Map();

    function cacheKey(url, params) {
        const search = new URLSearchParams(params);
        return `${url}?${search.toString()}`;
    }

    function fetchJson(url, params, useCache = true) {
        const key = cacheKey(url, params);
        if (useCache && jsonCache.has(key)) {
            return Promise.resolve(jsonCache.get(key));
        }

        return fetch(key, {
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        }).then((response) => response.json()).then((payload) => {
            if (useCache) {
                jsonCache.set(key, payload);
            }
            return payload;
        });
    }

    function clearPreviewCache() {
        jsonCache.clear();
    }

    function applyImportChoices(preview, form, payload) {
        const formId = preview.dataset.formId;
        const questionFieldId = preview.dataset.questionFieldId;
        const answerFieldId = preview.dataset.answerFieldId;
        if (!formId || !questionFieldId || !answerFieldId) {
            return;
        }

        const questionField = document.getElementById(questionFieldId);
        const answerField = document.getElementById(answerFieldId);
        if (!form || !questionField || !answerField) {
            return;
        }

        if (!payload.question_choices || !payload.answer_choices_by_question) {
            return;
        }

        const currentQuestion = preferredStoredValue(form, questionField);
        const currentAnswer = preferredStoredValue(form, answerField);
        setSelectChoices(questionField, payload.question_choices, currentQuestion);
        setSelectChoices(
            answerField,
            payload.answer_choices_by_question[questionField.value]
                || payload.answer_choices_by_question[""]
                || [["", "No answer filter"]],
            currentAnswer
        );
        saveFormState(form);
    }

    function applyRandomizeChoices(preview, form, payload) {
        const formId = preview.dataset.formId;
        const groupQuestionFieldId = preview.dataset.groupQuestionFieldId;
        if (!formId || !groupQuestionFieldId) {
            return;
        }

        const groupQuestionField = document.getElementById(groupQuestionFieldId);
        if (!form || !groupQuestionField || !payload.group_question_choices) {
            return;
        }

        const currentValue = preferredStoredValue(form, groupQuestionField);
        setSelectChoices(groupQuestionField, payload.group_question_choices, currentValue);
        saveFormState(form);
    }

    function initializePreview(preview) {
        const formId = preview.dataset.formId;
        const previewUrl = preview.dataset.previewUrl;
        const errorMessage = preview.dataset.previewErrorMessage || "Preview could not be loaded.";
        const seedFieldId = preview.dataset.seedFieldId;
        const form = document.getElementById(formId);
        const extraParams = {};
        if (!form || !previewUrl) {
            return;
        }
        form.addEventListener("submit", clearPreviewCache);

        let timer = null;

        const loadPreview = () => {
            const data = new FormData(form);
            data.delete("csrfmiddlewaretoken");
            const params = new URLSearchParams();
            for (const [key, value] of data.entries()) {
                params.append(key, value);
            }
            Object.entries(extraParams).forEach(([key, value]) => {
                params.set(key, value);
            });

            fetchJson(previewUrl, params)
                .then((payload) => {
                    applyImportChoices(preview, form, payload);
                    applyRandomizeChoices(preview, form, payload);
                    preview.innerHTML = payload.html;
                    if (seedFieldId && payload.seed) {
                        const seedField = document.getElementById(seedFieldId);
                        if (seedField) {
                            seedField.value = payload.seed;
                        }
                    }
                })
                .catch(() => {
                    preview.innerHTML = `<div class="alert alert-warning">${errorMessage}</div>`;
                });
        };

        const schedulePreview = () => {
            if (timer) {
                window.clearTimeout(timer);
            }
            timer = window.setTimeout(loadPreview, 150);
        };

        const resetPagingAndSchedulePreview = () => {
            Object.keys(extraParams).forEach((key) => {
                delete extraParams[key];
            });
            schedulePreview();
        };

        form.querySelectorAll("select, input").forEach((field) => {
            if (field.type === "submit") {
                return;
            }
            field.addEventListener("change", resetPagingAndSchedulePreview);
        });

        preview.addEventListener("click", (event) => {
            const trigger = event.target.closest("[data-preview-page-key]");
            if (!trigger) {
                return;
            }
            event.preventDefault();
            extraParams[trigger.dataset.previewPageKey] = trigger.dataset.previewPageValue;
            loadPreview();
        });

        loadPreview();
    }

    function initialize() {
        document.querySelectorAll("#waitlist-import-form, #waitlist-randomize-form").forEach((form) => {
            initializeSessionState(form);
        });

        document.querySelectorAll(".waitlist-manager-preview").forEach((preview) => {
            initializePreview(preview);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialize);
    } else {
        initialize();
    }
}());
